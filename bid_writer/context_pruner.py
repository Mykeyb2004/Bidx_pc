"""
章节级上下文裁剪模块
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import Config
from .embedding_store import EmbeddingStore
from .hybrid_retriever import HybridRetriever
from .llm_verifier import LLMVerifier
from .outline_parser import HeadingNode
from .retrieval_models import RetrievedUnit
from .source_unit_parser import SourceUnitParser


_RESPONSE_LABEL_RE = re.compile(r'(?:响应|对应评分标准)\s*[:：]\s*([^）)]+)')
_LEADING_NUMBER_RE = re.compile(r'^\s*[\d一二三四五六七八九十百千万零]+(?:[.、]\d+)*[.、]?\s*')
_PAREN_CONTENT_RE = re.compile(r'[（(][^（）()]*[)）]')
_MARKDOWN_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_TABLE_ALIGN_CELL_RE = re.compile(r'^:?-{3,}:?$')
_CHINESE_PUNCT_RE = re.compile(r'[\s\u3000,，。；;：:“”"\'‘’（）()\[\]【】《》<>/\\|+*_`~-]+')
_KEYWORD_SPLIT_RE = re.compile(r'[、，,；;：:/\s和与及及其并以及]+')
_TRACE_MAX_SCORING_CANDIDATES = 20
_GENERIC_SUFFIXES = (
    "管理制度",
    "工作制度",
    "实施方案",
    "组织实施方案",
    "保障方案",
    "质量控制方案",
    "控制方案",
    "保障计划",
    "工作计划",
    "进度计划",
    "报告模板",
    "方案",
    "制度",
    "机制",
    "措施",
    "计划",
    "体系",
    "流程",
    "预案",
    "说明",
    "分析",
    "设计",
)
_NOISE_GROUPS = (
    ("费用", ("费用", "报价", "价格")),
    ("团队", ("团队", "人员", "负责人")),
    ("样本", ("样本", "抽样", "范围", "对象")),
    ("方法", ("方法", "问卷", "访谈", "电话调查", "文案研究", "技术说明")),
)
_FOCUS_TERM_EXPANSIONS = (
    ("验收", ("验收", "验收标准", "验收要求", "结案报告", "合同要求", "招标文件")),
    ("成果", ("成果", "成果交付", "成果应用", "调查报告", "指标体系", "调查问卷", "报告")),
    ("应用", ("应用", "应用转化", "借鉴", "支撑", "依据")),
)
@dataclass
class ScoringCriterion:
    """命中的评分标准行。"""

    subitem: str
    standard: str
    weight: str = ""
    match_score: int = 0

@dataclass
class ChapterContext:
    """章节级裁剪后的上下文。"""

    response_labels: list[str] = field(default_factory=list)
    chapter_focus_terms: list[str] = field(default_factory=list)
    match_keywords: list[str] = field(default_factory=list)
    scoring_items: list[ScoringCriterion] = field(default_factory=list)
    scoring_candidates: list[ScoringCriterion] = field(default_factory=list)
    scoring_must_respond: list[ScoringCriterion] = field(default_factory=list)
    scoring_reference: list[ScoringCriterion] = field(default_factory=list)
    retrieval_mode: str = ""
    fallback_reason: str = ""
    selected_scoring_unit_ids: list[str] = field(default_factory=list)


class ChapterContextPruner:
    """基于规则的章节级上下文裁剪。"""

    def __init__(self, config: Config):
        self.config = config
        self.source_unit_parser = SourceUnitParser()
        self.hybrid_retriever = HybridRetriever()
        self.embedding_store = EmbeddingStore(config) if config.embedding_is_configured else None
        self.llm_verifier = LLMVerifier(config) if config.pruning_api_is_configured else None

    def build_context(self, heading: HeadingNode) -> ChapterContext:
        """构建当前章节的局部上下文。"""
        context = self._build_signal_context(heading)
        scoring_focus_terms = self._expand_focus_terms(context.chapter_focus_terms)
        processing_path = self.config.processing_path
        fallback_reasons: list[str] = []

        if processing_path == "auto":
            return self._build_context_auto(heading, context, scoring_focus_terms)

        if processing_path in {"legacy_rule", "hybrid_extract"}:
            scoring_mode = processing_path
        else:
            scoring_mode = self.config.context_pruning_scoring_mode

        runtime_errors = self.config.validate_context_pruning_runtime(raise_on_error=False)
        if runtime_errors:
            if self.config.context_pruning_unavailable_policy == "fail_fast":
                raise ValueError("；".join(runtime_errors))
            if scoring_mode == "hybrid_extract":
                scoring_mode = "legacy_rule"
            fallback_reasons.extend(runtime_errors)

        if scoring_mode == "hybrid_extract":
            try:
                (
                    context.scoring_items,
                    context.scoring_candidates,
                    context.selected_scoring_unit_ids,
                ) = self._route_scoring_items_hybrid(
                    heading,
                    context.response_labels,
                    context.match_keywords,
                    scoring_focus_terms,
                )
            except Exception as exc:
                if self.config.context_pruning_unavailable_policy == "fail_fast":
                    raise
                fallback_reasons.append(f"评分标准 hybrid_extract 失败，回退 legacy_rule: {exc}")
                scoring_mode = "legacy_rule"

        if scoring_mode == "legacy_rule":
            context.scoring_items, context.scoring_candidates = self._route_scoring_items(
                heading,
                context.response_labels,
                context.match_keywords,
                scoring_focus_terms,
            )

        if processing_path in {"full_context", "legacy_rule", "hybrid_extract"}:
            context.retrieval_mode = (
                f"path={processing_path};"
                f"vector={'on' if self.config.context_pruning_retrieval_vector_enabled else 'off'};"
                f"verify={'on' if self.config.context_pruning_rerank_or_verify_enabled else 'off'}"
            )
        else:
            context.retrieval_mode = (
                f"scoring={scoring_mode};"
                f"vector={'on' if self.config.context_pruning_retrieval_vector_enabled else 'off'};"
                f"verify={'on' if self.config.context_pruning_rerank_or_verify_enabled else 'off'}"
            )
        context.fallback_reason = "；".join(reason for reason in fallback_reasons if reason).strip()
        return context

    def _build_context_auto(
        self,
        heading: HeadingNode,
        context: ChapterContext,
        scoring_focus_terms: list[str],
    ) -> ChapterContext:
        """auto 模式：hybrid 检索 + H2 级评分分类。"""
        fallback_reasons: list[str] = []

        # 评分：hybrid_extract 检索
        try:
            (
                context.scoring_items,
                context.scoring_candidates,
                context.selected_scoring_unit_ids,
            ) = self._route_scoring_items_hybrid(
                heading,
                context.response_labels,
                context.match_keywords,
                scoring_focus_terms,
            )
        except Exception as exc:
            fallback_reasons.append(f"auto 评分检索失败，回退 legacy_rule: {exc}")
            context.scoring_items, context.scoring_candidates = self._route_scoring_items(
                heading,
                context.response_labels,
                context.match_keywords,
                scoring_focus_terms,
            )

        # 评分分类（H2 级缓存）
        if context.scoring_items and self.llm_verifier is not None:
            try:
                context.scoring_must_respond, context.scoring_reference = (
                    self._classify_scoring_with_h2_cache(heading, context)
                )
            except Exception as exc:
                fallback_reasons.append(f"评分分类失败: {exc}")
                context.scoring_must_respond = list(context.scoring_items)
                context.scoring_reference = []

        context.retrieval_mode = (
            f"path=auto;"
            f"vector={'on' if self.config.context_pruning_retrieval_vector_enabled else 'off'};"
            f"classify={'on' if context.scoring_must_respond or context.scoring_reference else 'off'}"
        )
        context.fallback_reason = "；".join(reason for reason in fallback_reasons if reason).strip()
        return context

    # ── auto 模式：H2 级评分分类缓存 ──

    @staticmethod
    def _find_h2_ancestor(heading: HeadingNode) -> HeadingNode:
        """找到 heading 的 H2（level==2）祖先，找不到则返回 parent。"""
        current: Optional[HeadingNode] = heading
        while current is not None:
            if current.level == 2:
                return current
            current = current.parent
        return heading.parent if heading.parent is not None else heading

    def _classify_scoring_with_h2_cache(
        self,
        heading: HeadingNode,
        context: ChapterContext,
    ) -> tuple[list[ScoringCriterion], list[ScoringCriterion]]:
        """使用 H4 级缓存对评分项做 must_respond/reference 分类。

        缓存 key 以当前 H4 章节的完整路径为粒度，保证分类结果对本章节精确。
        分类时传入 H4 标题、完整路径和同级章节信息，让分类器能够区分
        哪些评分项属于本章节职责范围，哪些应由相邻章节负责。
        """
        import hashlib
        from pathlib import Path

        # 缓存 key：当前章节路径 + 评分标准内容，精确到 H4
        cache_input = (
            self.config.scoring_criteria.strip()
            + heading.full_path
        )
        cache_key = hashlib.sha1(cache_input.encode("utf-8")).hexdigest()[:16]
        cache_dir = Path(self.config.scoring_classify_cache_dir)
        cache_path = cache_dir / f"h4_{cache_key}.json"

        # 尝试读缓存
        cached_ids = self._read_classify_cache(cache_path)
        if cached_ids is not None:
            return self._split_by_cached_ids(context.scoring_items, cached_ids)

        # 未命中：调用 LLMVerifier，传入当前 H4 节点的信息
        all_items = [
            {
                "id": f"{i}_{item.subitem}",
                "subitem": item.subitem,
                "standard": item.standard,
                "weight": item.weight,
            }
            for i, item in enumerate(context.scoring_items)
        ]

        # 同级章节标题，用于帮助分类器判断边界
        siblings = []
        if heading.parent:
            siblings = [node.title for node in heading.parent.children if node is not heading]

        focus_terms = self._build_focus_terms(heading)
        response_labels = self._extract_response_labels(heading)
        # 若当前节点无响应标签，补充 H2 的标签作为上下文
        if not response_labels:
            h2 = self._find_h2_ancestor(heading)
            response_labels = self._extract_response_labels(h2)

        assert self.llm_verifier is not None
        result = self.llm_verifier.classify_scoring(
            heading_path=heading.full_path,
            heading_title=heading.title,
            response_labels=response_labels,
            focus_terms=focus_terms,
            all_scoring_items=all_items,
            sibling_titles=siblings,
        )

        # 写缓存
        self._write_classify_cache(cache_path, result.must_respond_ids, result.reference_ids)

        return self._split_by_ids(
            context.scoring_items,
            all_items,
            result.must_respond_ids,
            result.reference_ids,
        )

    @staticmethod
    def _read_classify_cache(cache_path) -> Optional[dict]:
        try:
            if not cache_path.exists():
                return None
            import json
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if "must_respond_ids" in data and "reference_ids" in data:
                return data
            return None
        except Exception:
            return None

    @staticmethod
    def _write_classify_cache(cache_path, must_ids: list[str], ref_ids: list[str]) -> None:
        import json
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"must_respond_ids": must_ids, "reference_ids": ref_ids},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(cache_path)
        except OSError:
            pass

    @staticmethod
    def _split_by_cached_ids(
        scoring_items: list[ScoringCriterion],
        cached: dict,
    ) -> tuple[list[ScoringCriterion], list[ScoringCriterion]]:
        """按缓存的 ID 前缀（index_subitem）匹配拆分。"""
        must_set = set(cached.get("must_respond_ids", []))
        ref_set = set(cached.get("reference_ids", []))
        must, ref = [], []
        for i, item in enumerate(scoring_items):
            key = f"{i}_{item.subitem}"
            if key in must_set:
                must.append(item)
            elif key in ref_set:
                ref.append(item)
            else:
                must.append(item)
        return must, ref

    @staticmethod
    def _split_by_ids(
        scoring_items: list[ScoringCriterion],
        all_items: list[dict],
        must_ids: list[str],
        ref_ids: list[str],
    ) -> tuple[list[ScoringCriterion], list[ScoringCriterion]]:
        must_set = set(must_ids)
        ref_set = set(ref_ids)
        must, ref = [], []
        for item_dict, item in zip(all_items, scoring_items):
            if item_dict["id"] in must_set:
                must.append(item)
            elif item_dict["id"] in ref_set:
                ref.append(item)
            else:
                must.append(item)
        return must, ref

    def _build_signal_context(self, heading: HeadingNode) -> ChapterContext:
        """构建章节级匹配信号，不包含具体命中结果。"""
        response_labels = self._extract_response_labels(heading)
        chapter_focus_terms = self._build_focus_terms(heading)
        match_keywords = self._build_match_keywords(heading, response_labels)

        return ChapterContext(
            response_labels=response_labels,
            chapter_focus_terms=chapter_focus_terms,
            match_keywords=match_keywords,
        )

    def _route_scoring_items_hybrid(
        self,
        heading: HeadingNode,
        response_labels: list[str],
        match_keywords: list[str],
        focus_terms: list[str],
    ) -> tuple[list[ScoringCriterion], list[ScoringCriterion], list[str]]:
        if not self.config.context_pruning_scoring_enabled:
            return [], [], []

        query_text = self.hybrid_retriever.build_query(heading, response_labels, match_keywords)
        units = self.source_unit_parser.parse_scoring(
            self.config.scoring_criteria,
            parse_mode=self.config.context_pruning_scoring_parse_mode,
        )
        hits = self.hybrid_retriever.retrieve(
            query_text,
            units,
            response_labels=response_labels,
            keywords=match_keywords,
            focus_terms=focus_terms,
            top_k_lexical=self.config.context_pruning_retrieval_top_k_lexical,
            top_k_vector=self.config.context_pruning_retrieval_top_k_vector,
            top_k_fused=self.config.context_pruning_retrieval_top_k_fused,
            embedding_store=self.embedding_store if self.config.context_pruning_retrieval_vector_enabled else None,
        )
        selected_hits = self.hybrid_retriever.select_final(
            hits,
            top_k_final=min(
                self.config.context_pruning_scoring_max_rows,
                self.config.context_pruning_retrieval_top_k_final,
            ),
            min_score=self.config.context_pruning_retrieval_min_fused_score,
        )
        selected_hits = self._verify_hits_if_needed(
            heading=heading,
            response_labels=response_labels,
            focus_terms=focus_terms,
            hits=hits,
            selected_hits=selected_hits,
        )
        selected_ids = [hit.unit.unit_id for hit in selected_hits]
        scoring_items = [self._to_scoring_criterion(hit) for hit in selected_hits]
        scoring_candidates = [self._to_scoring_criterion(hit) for hit in hits[:_TRACE_MAX_SCORING_CANDIDATES]]
        return scoring_items, scoring_candidates, selected_ids

    @staticmethod
    def _to_scoring_criterion(hit: RetrievedUnit) -> ScoringCriterion:
        standard = hit.unit.source_text_exact or hit.unit.source_text
        title = hit.unit.title or hit.unit.section_path or hit.unit.unit_id
        return ScoringCriterion(
            subitem=title,
            standard=standard,
            weight=hit.unit.weight_text,
            match_score=int(hit.rerank_score or hit.fused_score or hit.lexical_score),
        )

    def _verify_hits_if_needed(
        self,
        *,
        heading: HeadingNode,
        response_labels: list[str],
        focus_terms: list[str],
        hits: list[RetrievedUnit],
        selected_hits: list[RetrievedUnit],
    ) -> list[RetrievedUnit]:
        if not hits or not self.config.context_pruning_rerank_or_verify_enabled:
            return selected_hits
        if self.llm_verifier is None:
            return selected_hits

        verify_candidates = hits[: self.config.context_pruning_extraction_llm_verify_max_candidates]
        result = self.llm_verifier.verify(
            heading_path=heading.full_path,
            heading_title=heading.title,
            response_labels=response_labels,
            focus_terms=focus_terms,
            candidates=verify_candidates,
            limit=self.config.context_pruning_extraction_llm_verify_max_candidates,
        )
        if not result.selected_ids:
            return selected_hits

        selected_map = {hit.unit.unit_id: hit for hit in verify_candidates}
        verified_hits: list[RetrievedUnit] = []
        for unit_id in result.selected_ids:
            hit = selected_map.get(unit_id)
            if hit is None:
                continue
            hit.rerank_score = max(hit.rerank_score, hit.fused_score)
            verified_hits.append(hit)
        return verified_hits or selected_hits

    @staticmethod
    def _heading_chain(heading: HeadingNode) -> list[HeadingNode]:
        chain: list[HeadingNode] = []
        current: Optional[HeadingNode] = heading
        while current is not None:
            chain.insert(0, current)
            current = current.parent
        return chain

    @staticmethod
    def _normalize_text(text: str) -> str:
        stripped = _LEADING_NUMBER_RE.sub("", text.strip())
        stripped = _PAREN_CONTENT_RE.sub(" ", stripped)
        stripped = _CHINESE_PUNCT_RE.sub("", stripped)
        return stripped.lower()

    @staticmethod
    def _title_core(text: str) -> str:
        stripped = _LEADING_NUMBER_RE.sub("", text.strip())
        return re.sub(r'\s+', ' ', stripped).strip()

    @classmethod
    def _extract_keyword_variants(cls, text: str) -> list[str]:
        variants: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            normalized = cls._title_core(value)
            if len(normalized) < 2 or normalized in seen:
                return
            seen.add(normalized)
            variants.append(normalized)

        core = cls._title_core(text)
        if not core:
            return variants

        add(core)

        for part in _KEYWORD_SPLIT_RE.split(core):
            add(part)

        for suffix in _GENERIC_SUFFIXES:
            if core.endswith(suffix):
                add(core[: -len(suffix)])

        return variants

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

    def _extract_response_labels(self, heading: HeadingNode) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()

        for node in self._heading_chain(heading):
            for match in _RESPONSE_LABEL_RE.findall(node.title):
                for part in re.split(r'[、，,;/；]+', match):
                    label = part.strip()
                    if not label or label in seen:
                        continue
                    seen.add(label)
                    labels.append(label)

        return labels

    def _build_focus_terms(self, heading: HeadingNode) -> list[str]:
        """提取当前章节自身的焦点词，优先用于需求聚焦。"""
        focus_terms: list[str] = []
        seen: set[str] = set()
        for variant in self._extract_keyword_variants(heading.title):
            normalized = self._normalize_text(variant)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            focus_terms.append(variant)
        return focus_terms

    def _expand_focus_terms(self, focus_terms: list[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            normalized = self._normalize_text(term)
            if len(normalized) < 2 or normalized in seen:
                return
            seen.add(normalized)
            expanded.append(term)

        for term in focus_terms:
            add(term)
            normalized = self._normalize_text(term)
            for root, variants in _FOCUS_TERM_EXPANSIONS:
                if root in normalized:
                    for variant in variants:
                        add(variant)

        return expanded

    @staticmethod
    def _split_markdown_row(line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    @classmethod
    def _parse_markdown_tables(cls, text: str) -> list[tuple[list[str], list[list[str]]]]:
        lines = text.splitlines()
        tables: list[tuple[list[str], list[list[str]]]] = []
        index = 0

        while index < len(lines) - 2:
            if not _MARKDOWN_TABLE_LINE_RE.match(lines[index]) or not _MARKDOWN_TABLE_LINE_RE.match(lines[index + 1]):
                index += 1
                continue

            header = cls._split_markdown_row(lines[index])
            align_row = cls._split_markdown_row(lines[index + 1])
            if len(header) != len(align_row) or not all(_TABLE_ALIGN_CELL_RE.match(cell.replace(" ", "")) for cell in align_row):
                index += 1
                continue

            rows: list[list[str]] = []
            cursor = index + 2
            while cursor < len(lines) and _MARKDOWN_TABLE_LINE_RE.match(lines[cursor]):
                row = cls._split_markdown_row(lines[cursor])
                if len(row) == len(header):
                    rows.append(row)
                cursor += 1

            if rows:
                tables.append((header, rows))
            index = cursor

        return tables

    @staticmethod
    def _find_header_index(headers: list[str], candidates: list[str]) -> Optional[int]:
        normalized_headers = [header.strip().lower() for header in headers]
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for index, header in enumerate(normalized_headers):
                if header == candidate_lower:
                    return index
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for index, header in enumerate(normalized_headers):
                if candidate_lower in header:
                    return index
        return None

    def _parse_scoring_rows(self) -> list[ScoringCriterion]:
        text = self.config.scoring_criteria.strip()
        if not text:
            return []

        tables = self._parse_markdown_tables(text)
        criteria: list[ScoringCriterion] = []
        for headers, rows in tables:
            subitem_index = self._find_header_index(headers, ["子项", "评分项", "评审因素", "项目", "子项目"])
            standard_index = self._find_header_index(headers, ["评审标准", "评分标准", "评审内容", "标准"])
            weight_index = self._find_header_index(headers, ["权重", "分值", "满分", "分数"])
            if subitem_index is None or standard_index is None:
                continue

            for row in rows:
                subitem = row[subitem_index].strip()
                standard = row[standard_index].strip()
                weight = row[weight_index].strip() if weight_index is not None else ""
                if not subitem or not standard:
                    continue
                criteria.append(ScoringCriterion(subitem=subitem, standard=standard, weight=weight))

        return criteria

    def _build_match_keywords(self, heading: HeadingNode, response_labels: list[str]) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()

        for label in response_labels:
            for variant in self._extract_keyword_variants(label):
                if variant not in seen:
                    seen.add(variant)
                    keywords.append(variant)

        for node in self._heading_chain(heading):
            for variant in self._extract_keyword_variants(node.title):
                if variant not in seen:
                    seen.add(variant)
                    keywords.append(variant)

        return keywords

    def _score_criterion(self, criterion: ScoringCriterion, response_labels: list[str], keywords: list[str]) -> int:
        subitem_norm = self._normalize_text(criterion.subitem)
        standard_norm = self._normalize_text(criterion.standard)
        combined_norm = f"{subitem_norm}{standard_norm}"
        score = 0

        for label in response_labels:
            label_norm = self._normalize_text(label)
            if not label_norm:
                continue
            if label_norm == subitem_norm:
                score += 120
            elif label_norm in subitem_norm or subitem_norm in label_norm:
                score += 80
            elif label_norm in combined_norm:
                score += 40

        for keyword in keywords:
            keyword_norm = self._normalize_text(keyword)
            if len(keyword_norm) < 2:
                continue
            if keyword_norm == subitem_norm:
                score += 60
            elif keyword_norm in subitem_norm or subitem_norm in keyword_norm:
                score += 35
            elif keyword_norm in combined_norm:
                score += 12
            common_length = self._longest_common_substring_length(keyword_norm, combined_norm)
            if common_length >= 2:
                score += common_length * 8

        return score

    def _score_focus_terms(self, text: str, focus_terms: list[str]) -> int:
        """用当前章节自身焦点词提高匹配精度。"""
        text_norm = self._normalize_text(text)
        if not text_norm:
            return 0

        score = 0
        for focus_term in focus_terms:
            focus_norm = self._normalize_text(focus_term)
            if len(focus_norm) < 2:
                continue
            if focus_norm in text_norm:
                score += max(len(focus_norm), 2) * 16
            common_length = self._longest_common_substring_length(focus_norm, text_norm)
            if common_length >= 2:
                score += common_length * 10
        return score

    @staticmethod
    def _contains_any(text_norm: str, terms: tuple[str, ...]) -> bool:
        return any(term in text_norm for term in terms)

    def _noise_penalty(self, text: str, focus_terms: list[str]) -> int:
        """对明显偏离当前章节焦点的通用噪音块降权。"""
        text_norm = self._normalize_text(text)
        if not text_norm:
            return 0

        penalties = 0
        focus_norms = [self._normalize_text(term) for term in focus_terms if self._normalize_text(term)]
        for _, terms in _NOISE_GROUPS:
            if not self._contains_any(text_norm, terms):
                continue
            if any(any(term in focus for term in terms) or any(focus in term for term in terms) for focus in focus_norms):
                continue
            penalties += 72
        return penalties

    def _route_scoring_items(
        self,
        heading: HeadingNode,
        response_labels: list[str],
        match_keywords: Optional[list[str]] = None,
        focus_terms: Optional[list[str]] = None,
    ) -> tuple[list[ScoringCriterion], list[ScoringCriterion]]:
        if not self.config.context_pruning_scoring_enabled:
            return [], []

        keywords = list(match_keywords) if match_keywords is not None else self._build_match_keywords(heading, response_labels)
        current_focus_terms = list(focus_terms or [])
        matches: list[ScoringCriterion] = []
        for criterion in self._parse_scoring_rows():
            match_score = self._score_criterion(criterion, response_labels, keywords)
            if current_focus_terms:
                match_score += self._score_focus_terms(
                    f"{criterion.subitem}\n{criterion.standard}",
                    current_focus_terms,
                )
            if match_score <= 0:
                continue
            matches.append(
                ScoringCriterion(
                    subitem=criterion.subitem,
                    standard=criterion.standard,
                    weight=criterion.weight,
                    match_score=match_score,
                )
            )

        matches.sort(key=lambda item: (-item.match_score, item.subitem, item.weight))
        return matches[: self.config.context_pruning_scoring_max_rows], matches[:_TRACE_MAX_SCORING_CANDIDATES]

    @staticmethod
    def _sanitize_debug_filename(text: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', text)
        sanitized = re.sub(r'[_\s]+', '_', sanitized).strip(' ._')
        return sanitized or "untitled"

    def dump_debug(self, heading: HeadingNode, context: ChapterContext, prompt: str) -> Optional[Path]:
        """将章节裁剪结果写入 sidecar 调试文件。"""
        if not self.config.context_pruning_debug_dump:
            return None

        debug_dir = Path(self.config.output_directory) / "_context_pruning_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self._sanitize_debug_filename(heading.title)}__{self._sanitize_debug_filename(heading.full_path)[:32]}.md"
        filepath = debug_dir / filename

        scoring_lines = []
        for item in context.scoring_items:
            title = item.subitem
            if item.weight:
                title = f"{title}（权重：{item.weight}）"
            scoring_lines.append(f"- {title} [score={item.match_score}]")
            scoring_lines.append(f"  {item.standard}")

        content = "\n".join([
            f"# 章节上下文调试 - {heading.title}",
            "",
            f"- full_path: {heading.full_path}",
            f"- retrieval_mode: {context.retrieval_mode or '（无）'}",
            f"- fallback_reason: {context.fallback_reason or '（无）'}",
            f"- response_labels: {', '.join(context.response_labels) if context.response_labels else '（无）'}",
            f"- match_keywords: {', '.join(context.match_keywords) if context.match_keywords else '（无）'}",
            f"- scoring_items: {len(context.scoring_items)}",
            f"- scoring_must_respond: {len(context.scoring_must_respond)}",
            f"- scoring_reference: {len(context.scoring_reference)}",
            f"- scoring_candidates: {len(context.scoring_candidates)}",
            f"- selected_scoring_unit_ids: {', '.join(context.selected_scoring_unit_ids) if context.selected_scoring_unit_ids else '（无）'}",
            f"- prompt_chars: {len(prompt)}",
            "",
            "## 命中评分项",
            "\n".join(scoring_lines) or "（无）",
        ])

        filepath.write_text(content, encoding="utf-8")
        return filepath
