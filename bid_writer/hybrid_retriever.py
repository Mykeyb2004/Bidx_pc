"""
lexical-only 的 hybrid retrieval 骨架。
"""

from __future__ import annotations

import re

from .retrieval_models import RetrievedUnit, SourceUnit


_LEADING_NUMBER_RE = re.compile(r'^\s*[\d一二三四五六七八九十百千万零]+(?:[.、]\d+)*[.、]?\s*')
_PAREN_CONTENT_RE = re.compile(r'[（(][^（）()]*[)）]')
_CHINESE_PUNCT_RE = re.compile(r'[\s\u3000,，。；;：:“”"\'‘’（）()\[\]【】《》<>/\\|+*_`~-]+')
_NOISE_GROUPS = (
    ("费用", ("费用", "报价", "价格")),
    ("团队", ("团队", "人员", "负责人")),
    ("样本", ("样本", "抽样", "范围", "对象")),
    ("方法", ("方法", "问卷", "访谈", "电话调查", "文案研究", "技术说明")),
)


class HybridRetriever:
    """统一的检索排序入口。"""

    @staticmethod
    def _normalize_text(text: str) -> str:
        stripped = _LEADING_NUMBER_RE.sub("", text.strip())
        stripped = _PAREN_CONTENT_RE.sub(" ", stripped)
        stripped = _CHINESE_PUNCT_RE.sub("", stripped)
        return stripped.lower()

    @staticmethod
    def _title_core(text: str) -> str:
        stripped = _LEADING_NUMBER_RE.sub("", text.strip())
        return re.sub(r"\s+", " ", stripped).strip()

    @staticmethod
    def _longest_common_substring_length(left: str, right: str) -> int:
        if not left or not right:
            return 0

        if len(left) > len(right):
            left, right = right, left

        previous = [0] * (len(right) + 1)
        longest = 0
        for left_char in left:
            current = [0]
            for index, right_char in enumerate(right, start=1):
                if left_char == right_char:
                    value = previous[index - 1] + 1
                    current.append(value)
                    if value > longest:
                        longest = value
                else:
                    current.append(0)
            previous = current
        return longest

    def build_query(self, heading, response_labels: list[str], match_keywords: list[str]) -> str:
        chain: list[str] = []
        current = heading
        while current is not None:
            chain.insert(0, current.title)
            current = current.parent
        parts = chain + response_labels + match_keywords
        deduped: list[str] = []
        seen: set[str] = set()
        for part in parts:
            normalized = self._title_core(part)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return " ".join(deduped)

    def retrieve(
        self,
        query_text: str,
        units: list[SourceUnit],
        *,
        response_labels: list[str],
        keywords: list[str],
        focus_terms: list[str],
        top_k_lexical: int,
        top_k_vector: int,
        top_k_fused: int,
        embedding_store=None,
    ) -> list[RetrievedUnit]:
        lexical_hits = self.lexical_retrieve(
            units=units,
            response_labels=response_labels,
            keywords=keywords,
            focus_terms=focus_terms,
            top_k=top_k_lexical,
        )
        vector_hits: list[RetrievedUnit] = []
        if embedding_store is not None:
            vector_hits = self.vector_retrieve(
                query_text=query_text,
                units=units,
                embedding_store=embedding_store,
                top_k=top_k_vector,
            )
        return self.fuse_rank(lexical_hits, vector_hits)[:top_k_fused]

    def lexical_retrieve(
        self,
        *,
        units: list[SourceUnit],
        response_labels: list[str],
        keywords: list[str],
        focus_terms: list[str],
        top_k: int,
    ) -> list[RetrievedUnit]:
        hits: list[RetrievedUnit] = []
        for unit in units:
            score = self._score_unit(unit, response_labels, keywords, focus_terms)
            if score <= 0:
                continue
            hits.append(
                RetrievedUnit(
                    unit=unit,
                    lexical_score=float(score),
                    fused_score=float(score),
                )
            )
        hits.sort(key=lambda item: (-item.fused_score, item.unit.order_index, item.unit.unit_id))
        return hits[:top_k]

    @staticmethod
    def fuse_rank(lexical_hits: list[RetrievedUnit], vector_hits: list[RetrievedUnit]) -> list[RetrievedUnit]:
        merged: dict[str, RetrievedUnit] = {}
        rrf_k = 60

        for rank, hit in enumerate(lexical_hits, start=1):
            existing = merged.get(hit.unit.unit_id)
            if existing is None:
                existing = RetrievedUnit(unit=hit.unit)
                merged[hit.unit.unit_id] = existing
            existing.lexical_score = max(existing.lexical_score, hit.lexical_score)
            existing.fused_score += 1.0 / (rrf_k + rank)

        for rank, hit in enumerate(vector_hits, start=1):
            existing = merged.get(hit.unit.unit_id)
            if existing is None:
                existing = RetrievedUnit(unit=hit.unit)
                merged[hit.unit.unit_id] = existing
            existing.vector_score = max(existing.vector_score, hit.vector_score)
            existing.fused_score += 1.0 / (rrf_k + rank)

        return sorted(
            merged.values(),
            key=lambda item: (-item.fused_score, item.unit.order_index, item.unit.unit_id),
        )

    def vector_retrieve(
        self,
        *,
        query_text: str,
        units: list[SourceUnit],
        embedding_store,
        top_k: int,
    ) -> list[RetrievedUnit]:
        if not units:
            return []
        document_embeddings = embedding_store.build_document_embeddings(units)
        query_embedding = embedding_store.embed_query(query_text)
        scored = embedding_store.search(query_embedding, document_embeddings, top_k=top_k)
        unit_map = {unit.unit_id: unit for unit in units}
        hits: list[RetrievedUnit] = []
        for unit_id, score in scored:
            unit = unit_map.get(unit_id)
            if unit is None:
                continue
            hits.append(
                RetrievedUnit(
                    unit=unit,
                    vector_score=score,
                    fused_score=score,
                )
            )
        return hits

    @staticmethod
    def select_final(hits: list[RetrievedUnit], top_k_final: int, min_score: float = 0.0) -> list[RetrievedUnit]:
        selected = [hit for hit in hits if hit.fused_score >= min_score]
        return selected[:top_k_final]

    def _score_unit(
        self,
        unit: SourceUnit,
        response_labels: list[str],
        keywords: list[str],
        focus_terms: list[str],
    ) -> int:
        title_norm = self._normalize_text(unit.title)
        combined_norm = self._normalize_text(
            "\n".join(
                part for part in [
                    unit.section_path,
                    unit.title,
                    unit.weight_text,
                    unit.source_text,
                    unit.source_text_exact,
                ] if part
            )
        )
        if not combined_norm:
            return 0

        score = 0
        for label in response_labels:
            label_norm = self._normalize_text(label)
            if not label_norm:
                continue
            if label_norm == title_norm:
                score += 120
            elif title_norm and (label_norm in title_norm or title_norm in label_norm):
                score += 80
            elif label_norm in combined_norm:
                score += 40

        for keyword in keywords:
            keyword_norm = self._normalize_text(keyword)
            if len(keyword_norm) < 2:
                continue
            if keyword_norm == title_norm:
                score += 60
            elif title_norm and (keyword_norm in title_norm or title_norm in keyword_norm):
                score += 35
            elif keyword_norm in combined_norm:
                score += 16

            common_length = self._longest_common_substring_length(keyword_norm, combined_norm)
            if common_length >= 2:
                score += common_length * 8

        score += self._score_focus_terms(combined_norm, focus_terms)
        if unit.doc_type == "requirements":
            score -= self._noise_penalty(combined_norm, focus_terms)
        return score

    def _score_focus_terms(self, normalized_text: str, focus_terms: list[str]) -> int:
        score = 0
        for term in focus_terms:
            normalized_term = self._normalize_text(term)
            if len(normalized_term) < 2:
                continue
            if normalized_term in normalized_text:
                score += max(len(normalized_term), 2) * 16
            common_length = self._longest_common_substring_length(normalized_term, normalized_text)
            if common_length >= 2:
                score += common_length * 10
        return score

    def _noise_penalty(self, normalized_text: str, focus_terms: list[str]) -> int:
        penalties = 0
        focus_norms = [self._normalize_text(term) for term in focus_terms if self._normalize_text(term)]
        for _, terms in _NOISE_GROUPS:
            if not any(term in normalized_text for term in terms):
                continue
            if any(
                any(term in focus for term in terms) or any(focus in term for term in terms)
                for focus in focus_norms
            ):
                continue
            penalties += 72
        return penalties
