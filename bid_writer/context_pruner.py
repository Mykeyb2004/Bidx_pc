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
_TRACE_MAX_REQUIREMENT_BLOCKS = 20
_MAX_SELECTED_REQUIREMENT_BLOCKS = 5
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
_SKIP_SUMMARY_LABELS = {"采购需求", "项目概况", "项目任务", "项目内容", "项目技术说明"}
@dataclass
class ScoringCriterion:
    """命中的评分标准行。"""

    subitem: str
    standard: str
    weight: str = ""
    match_score: int = 0


@dataclass
class RequirementBlockMatch:
    """命中的需求段落候选。"""

    index: int
    score: int
    selected: bool = False
    chars: int = 0
    block: str = ""


@dataclass
class ChapterContext:
    """章节级裁剪后的上下文。"""

    local_outline: str = ""
    response_labels: list[str] = field(default_factory=list)
    chapter_focus_terms: list[str] = field(default_factory=list)
    match_keywords: list[str] = field(default_factory=list)
    scoring_items: list[ScoringCriterion] = field(default_factory=list)
    scoring_candidates: list[ScoringCriterion] = field(default_factory=list)
    requirement_seed: str = ""
    requirement_blocks: list[RequirementBlockMatch] = field(default_factory=list)
    requirement_brief: str = ""
    requirement_brief_status: str = ""
    requirement_brief_error: str = ""
    retrieval_mode: str = ""
    fallback_reason: str = ""
    selected_requirement_unit_ids: list[str] = field(default_factory=list)
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
        scoring_mode = self.config.context_pruning_scoring_mode
        requirements_mode = self.config.context_pruning_requirements_mode
        fallback_reasons: list[str] = []

        runtime_errors = self.config.validate_context_pruning_runtime(raise_on_error=False)
        if runtime_errors:
            if self.config.context_pruning_unavailable_policy == "fail_fast":
                raise ValueError("；".join(runtime_errors))
            if scoring_mode == "hybrid_extract":
                scoring_mode = "legacy_rule"
            if requirements_mode == "hybrid_extract":
                requirements_mode = "legacy_rule"
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

        if requirements_mode == "hybrid_extract":
            try:
                (
                    context.requirement_seed,
                    context.requirement_blocks,
                    context.selected_requirement_unit_ids,
                ) = self._build_requirement_seed_hybrid(
                    heading,
                    context.response_labels,
                    context.match_keywords,
                    scoring_focus_terms,
                )
            except Exception as exc:
                if self.config.context_pruning_unavailable_policy == "fail_fast":
                    raise
                fallback_reasons.append(f"采购需求 hybrid_extract 失败，回退 legacy_rule: {exc}")
                requirements_mode = "legacy_rule"

        if requirements_mode == "legacy_rule":
            context.requirement_seed, context.requirement_blocks = self._build_requirement_seed(
                heading,
                context.response_labels,
                context.match_keywords,
                scoring_focus_terms,
            )

        if self.config.context_pruning_requirements_brief_enabled:
            (
                context.requirement_brief,
                context.requirement_brief_status,
                context.requirement_brief_error,
            ) = self._build_requirement_brief_with_cache(heading, context)
        else:
            context.requirement_brief_status = "disabled"

        context.retrieval_mode = (
            f"scoring={scoring_mode};requirements={requirements_mode};"
            f"vector={'on' if self.config.context_pruning_retrieval_vector_enabled else 'off'};"
            f"rerank={'on' if self.config.context_pruning_rerank_or_verify_enabled else 'off'}"
        )
        context.fallback_reason = "；".join(reason for reason in fallback_reasons if reason).strip()
        return context

    def _build_signal_context(self, heading: HeadingNode) -> ChapterContext:
        """构建章节级匹配信号，不包含具体命中结果。"""
        response_labels = self._extract_response_labels(heading)
        chapter_focus_terms = self._build_focus_terms(heading)
        match_keywords = self._build_match_keywords(heading, response_labels)

        return ChapterContext(
            local_outline=self._build_local_outline(heading),
            response_labels=response_labels,
            chapter_focus_terms=chapter_focus_terms,
            match_keywords=match_keywords,
        )

    def _build_requirement_brief_with_cache(
        self,
        heading: HeadingNode,
        context: ChapterContext,
    ) -> tuple[str, str, str]:
        """根据当前章节命中的采购需求原文，生成只含摘录的 requirement_brief。"""
        return self._build_requirement_brief(heading, context)

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

    def _build_requirement_seed_hybrid(
        self,
        heading: HeadingNode,
        response_labels: list[str],
        match_keywords: list[str],
        focus_terms: list[str],
    ) -> tuple[str, list[RequirementBlockMatch], list[str]]:
        text = self.config.bid_requirements.strip()
        if not text:
            return "", [], []

        query_text = self.hybrid_retriever.build_query(heading, response_labels, match_keywords)
        units = [
            unit
            for unit in self.source_unit_parser.parse_requirements(text)
            if not self._is_low_value_requirement_block(unit.source_text_exact or unit.source_text)
        ]
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
                _MAX_SELECTED_REQUIREMENT_BLOCKS,
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

        if not selected_hits:
            selected_hits = [
                RetrievedUnit(unit=unit, lexical_score=0.0, fused_score=0.0)
                for unit in units[:3]
            ]

        selected_ids = [hit.unit.unit_id for hit in selected_hits]
        selected_blocks = [hit.unit.source_text_exact or hit.unit.source_text for hit in selected_hits]
        trace_blocks: list[RequirementBlockMatch] = []

        if hits:
            for hit in hits[:_TRACE_MAX_REQUIREMENT_BLOCKS]:
                block = hit.unit.source_text_exact or hit.unit.source_text
                trace_blocks.append(
                    RequirementBlockMatch(
                        index=hit.unit.order_index,
                        score=int(hit.fused_score),
                        selected=hit.unit.unit_id in selected_ids,
                        chars=len(block),
                        block=block,
                    )
                )
        else:
            for hit in selected_hits[: min(len(selected_hits), 4)]:
                block = hit.unit.source_text_exact or hit.unit.source_text
                trace_blocks.append(
                    RequirementBlockMatch(
                        index=hit.unit.order_index,
                        score=0,
                        selected=True,
                        chars=len(block),
                        block=block,
                    )
                )

        return self._summarize_requirement_blocks(selected_blocks), trace_blocks, selected_ids

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

    def _build_local_outline(self, heading: HeadingNode) -> str:
        chain = self._heading_chain(heading)
        lines: list[str] = []
        seen_paths: set[str] = set()

        def add_node(node: HeadingNode) -> None:
            if node.full_path in seen_paths:
                return
            seen_paths.add(node.full_path)
            lines.append(f"{'#' * node.level} {node.title}")

        if self.config.context_pruning_local_outline_include_ancestors:
            for node in chain[:-1]:
                add_node(node)

        if self.config.context_pruning_local_outline_include_siblings:
            parent = heading.parent
            siblings = list(parent.children) if parent else [heading]
            siblings = self._trim_siblings(siblings, heading, self.config.context_pruning_local_outline_max_siblings)
            for node in siblings:
                add_node(node)
        else:
            add_node(heading)

        return "\n".join(lines).strip()

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
    def _trim_siblings(siblings: list[HeadingNode], current: HeadingNode, max_siblings: int) -> list[HeadingNode]:
        if max_siblings <= 0 or len(siblings) <= max_siblings:
            return siblings

        try:
            current_index = siblings.index(current)
        except ValueError:
            return siblings[:max_siblings]

        selected = [current]
        left = current_index - 1
        right = current_index + 1

        while len(selected) < max_siblings and (left >= 0 or right < len(siblings)):
            if left >= 0:
                selected.insert(0, siblings[left])
                left -= 1
                if len(selected) >= max_siblings:
                    break
            if right < len(siblings):
                selected.append(siblings[right])
                right += 1

        return selected

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
    def _split_requirement_blocks(text: str) -> list[str]:
        blocks: list[str] = []
        current: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if current:
                    blocks.append("\n".join(current).strip())
                    current = []
                continue
            current.append(line)
        if current:
            blocks.append("\n".join(current).strip())
        return ChapterContextPruner._merge_heading_blocks(blocks)

    @staticmethod
    def _looks_like_heading_block(block: str) -> bool:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            return False
        if len(lines) > 2:
            return False
        if len(block) <= 36:
            return True
        first_line = lines[0]
        return bool(
            first_line.startswith(("#", "**", "一、", "二、", "三、", "四、", "五、"))
            or re.match(r'^\d+(?:\.\d+)*', first_line)
        )

    @classmethod
    def _merge_heading_blocks(cls, blocks: list[str]) -> list[str]:
        merged: list[str] = []
        index = 0
        while index < len(blocks):
            block = blocks[index]
            if cls._looks_like_heading_block(block) and index + 1 < len(blocks):
                merged.append(f"{block}\n{blocks[index + 1]}".strip())
                index += 2
                continue
            merged.append(block)
            index += 1
        return merged

    @classmethod
    def _is_low_value_requirement_block(cls, block: str) -> bool:
        """过滤只有标题、没有实质信息的需求块。"""
        lines = [cls._clean_requirement_text(line) for line in block.splitlines() if cls._clean_requirement_text(line)]
        if not lines:
            return True
        if len(lines) <= 2 and all(cls._looks_like_heading_block(line) for line in lines):
            return True
        normalized_lines = [cls._normalize_text(line) for line in lines]
        meaningful_lines = [line for line in normalized_lines if len(line) >= 8]
        return not meaningful_lines

    def _build_requirement_seed(
        self,
        heading: HeadingNode,
        response_labels: list[str],
        match_keywords: Optional[list[str]] = None,
        focus_terms: Optional[list[str]] = None,
    ) -> tuple[str, list[RequirementBlockMatch]]:
        text = self.config.bid_requirements.strip()
        if not text:
            return "", []

        keywords = list(match_keywords) if match_keywords is not None else self._build_match_keywords(heading, response_labels)
        current_focus_terms = list(focus_terms or [])

        blocks = self._split_requirement_blocks(text)
        scored_blocks: list[tuple[int, int, str]] = []
        for index, block in enumerate(blocks):
            block_norm = self._normalize_text(block)
            if not block_norm:
                continue

            score = 0
            for label in response_labels:
                label_norm = self._normalize_text(label)
                if label_norm and (label_norm in block_norm or block_norm in label_norm):
                    score += 40
            for keyword in keywords:
                keyword_norm = self._normalize_text(keyword)
                if len(keyword_norm) < 2:
                    continue
                if keyword_norm in block_norm:
                    occurrences = block_norm.count(keyword_norm)
                    score += occurrences * max(min(len(keyword_norm), 8), 2) * 4
                elif block_norm in keyword_norm:
                    score += 12
                common_length = self._longest_common_substring_length(keyword_norm, block_norm)
                if common_length >= 2:
                    score += common_length * 6
            if current_focus_terms:
                score += self._score_focus_terms(block, current_focus_terms)
                score -= self._noise_penalty(block, current_focus_terms)

            if score > 0:
                scored_blocks.append((score, index, block))

        scored_blocks.sort(key=lambda item: (-item[0], item[1]))

        selected: list[str] = []
        selected_indices: set[int] = set()
        total_chars = 0
        for _, index, block in scored_blocks:
            if block in selected:
                continue
            if self._is_low_value_requirement_block(block):
                continue
            if total_chars >= 1000 or len(selected) >= _MAX_SELECTED_REQUIREMENT_BLOCKS:
                break
            selected.append(block)
            selected_indices.add(index)
            total_chars += len(block)

        if not selected:
            for index, block in enumerate(blocks[:4]):
                if self._is_low_value_requirement_block(block):
                    continue
                if total_chars >= 900 or len(selected) >= 3:
                    break
                selected.append(block)
                selected_indices.add(index)
                total_chars += len(block)

        trace_blocks: list[RequirementBlockMatch] = []
        if scored_blocks:
            for score, index, block in scored_blocks[:_TRACE_MAX_REQUIREMENT_BLOCKS]:
                trace_blocks.append(
                    RequirementBlockMatch(
                        index=index,
                        score=score,
                        selected=index in selected_indices,
                        chars=len(block),
                        block=block,
                    )
                )
        else:
            for index, block in enumerate(blocks[: min(len(blocks), 4)]):
                trace_blocks.append(
                    RequirementBlockMatch(
                        index=index,
                        score=0,
                        selected=index in selected_indices,
                        chars=len(block),
                        block=block,
                    )
                )

        return self._summarize_requirement_blocks(selected), trace_blocks

    @staticmethod
    def _clean_requirement_text(text: str) -> str:
        cleaned = text.replace("**", "").replace("<br>", " ")
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _summarize_requirement_blocks(self, blocks: list[str]) -> str:
        """把命中的原始需求块压成更短的需求要点。"""
        summary_points: list[str] = []
        seen: set[str] = set()

        for block in blocks:
            lines = [self._clean_requirement_text(line) for line in block.splitlines() if self._clean_requirement_text(line)]
            if not lines:
                continue

            label = ""
            content = ""
            if len(lines) >= 2 and self._looks_like_heading_block("\n".join(lines[:2])):
                label = self._title_core(lines[0])
                content = " ".join(lines[1:])
            elif len(lines) >= 2 and len(lines[0]) <= 20:
                label = self._title_core(lines[0])
                content = " ".join(lines[1:])
            else:
                content = " ".join(lines)

            content = re.sub(r'\s+', ' ', content).strip()
            if not content:
                continue

            sentences = [segment.strip() for segment in re.split(r'[。！？；;]', content) if segment.strip()]
            excerpt = "；".join(sentences[:2]).strip("；")
            if not excerpt:
                continue

            point = f"{label}：{excerpt}" if label else excerpt
            point = re.sub(r'\s+', ' ', point).strip()
            if label in _SKIP_SUMMARY_LABELS:
                continue
            if len(point) > 120:
                point = point[:117].rstrip("，、；;：: ") + "..."
            normalized = self._normalize_text(point)
            if len(normalized) < 4 or normalized in seen:
                continue
            seen.add(normalized)
            summary_points.append(f"- {point}")
            if len(summary_points) >= 5:
                break

        return "\n".join(summary_points).strip()

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
            f"- local_outline_chars: {len(context.local_outline)}",
            f"- scoring_items: {len(context.scoring_items)}",
            f"- scoring_candidates: {len(context.scoring_candidates)}",
            f"- requirement_blocks: {len(context.requirement_blocks)}",
            f"- requirement_seed_chars: {len(context.requirement_seed)}",
            f"- requirement_brief_chars: {len(context.requirement_brief)}",
            f"- requirement_brief_status: {context.requirement_brief_status or '（无）'}",
            f"- selected_scoring_unit_ids: {', '.join(context.selected_scoring_unit_ids) if context.selected_scoring_unit_ids else '（无）'}",
            f"- selected_requirement_unit_ids: {', '.join(context.selected_requirement_unit_ids) if context.selected_requirement_unit_ids else '（无）'}",
            f"- prompt_chars: {len(prompt)}",
            "",
            "## 局部大纲",
            context.local_outline or "（无）",
            "",
            "## 命中评分项",
            "\n".join(scoring_lines) or "（无）",
            "",
            "## 需求 Seed",
            context.requirement_seed or "（无）",
            "",
            "## 需求原文摘录",
            context.requirement_brief or "（无）",
        ])

        filepath.write_text(content, encoding="utf-8")
        return filepath

    @classmethod
    def _extract_requirement_excerpt(cls, block: str) -> str:
        """从命中的需求块中截取原文摘录，不做归纳改写。"""
        if cls._is_low_value_requirement_block(block):
            return ""

        lines = [cls._clean_requirement_text(line) for line in block.splitlines() if cls._clean_requirement_text(line)]
        if not lines:
            return ""

        label = ""
        content = ""
        if len(lines) >= 2 and cls._looks_like_heading_block("\n".join(lines[:2])):
            label = cls._title_core(lines[0])
            content = " ".join(lines[1:])
        elif len(lines) >= 2 and len(lines[0]) <= 20:
            label = cls._title_core(lines[0])
            content = " ".join(lines[1:])
        else:
            content = " ".join(lines)

        content = re.sub(r"\s+", " ", content).strip()
        content = _LEADING_NUMBER_RE.sub("", content).strip()
        if not content:
            return ""

        sentences = [segment.strip() for segment in re.split(r"[。！？]", content) if segment.strip()]
        excerpt = "。".join(sentences[:2]).strip("。")
        if not excerpt:
            excerpt = content
        excerpt = f"{excerpt}。"

        if label and label not in _SKIP_SUMMARY_LABELS:
            return f"【{label}】{excerpt}"
        return excerpt

    def _build_requirement_brief(self, heading: HeadingNode, context: ChapterContext) -> tuple[str, str, str]:
        del heading  # requirement_brief 仅依赖当前章节已命中的需求块

        selected_blocks = [match.block for match in context.requirement_blocks if match.selected and match.block.strip()]
        if not selected_blocks:
            return "", "skipped_empty_blocks", ""

        max_quotes = max(self.config.context_pruning_requirements_max_quotes, 1)
        max_quote_chars = max(self.config.context_pruning_requirements_max_quote_chars, 40)
        excerpt_lines: list[str] = []
        seen: set[str] = set()
        for block in selected_blocks:
            excerpt = self._extract_requirement_excerpt(block)
            if len(excerpt) > max_quote_chars:
                excerpt = excerpt[: max_quote_chars - 3].rstrip("，、；;：: ") + "..."
            normalized = self._normalize_text(excerpt)
            if not excerpt or not normalized or normalized in seen:
                continue
            seen.add(normalized)
            excerpt_lines.append(f"{len(excerpt_lines) + 1}. {excerpt}")
            if len(excerpt_lines) >= max_quotes:
                break

        if not excerpt_lines:
            return "", "empty_excerpt", ""
        return "\n".join(excerpt_lines), "extracted", ""
