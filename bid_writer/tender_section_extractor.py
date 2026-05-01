"""从转换后的招标文件 Markdown block 中抽取采购需求和评分标准。"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .tender_import_models import (
    ConvertedBlock,
    SectionCandidate,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
)
from .tender_section_boundary_config import load_boundary_config
from .tender_section_boundary_detector import (
    TenderSectionBoundarySpan,
    detect_boundary_matches,
    resolve_extraction_spans,
)


REQUIREMENT_ALIASES = (
    "项目采购需求",
    "采购需求",
    "采购服务要求",
    "项目需求",
    "服务需求",
    "技术需求",
    "技术和服务要求",
    "采购内容及要求",
    "项目内容及要求",
    "服务内容及要求",
    "技术参数及要求",
    "用户需求书",
    "商务技术要求",
)

SCORING_ALIASES = (
    "评分标准",
    "评审标准",
    "评审办法",
    "评审方法",
    "评分办法",
    "评分细则",
    "评标方法",
    "评标标准",
    "评标方法及评标标准",
    "综合评分法",
    "详细评审",
    "评审因素",
    "技术商务评分表",
    "综合评分表",
    "评标办法",
)

REQUIREMENT_TERMS = ("服务", "技术", "要求", "内容", "范围", "参数", "成果", "验收", "采购")
SCORING_TERMS = ("评分", "评审", "分值", "满分", "权重", "得分", "得", "分")
SCORING_TABLE_TERMS = ("评审因素", "评分项", "评分标准", "评审内容", "分值", "权重", "得分")
STRONG_STOP_TITLES = ("合同条款", "投标人须知", "响应文件格式", "开标评标定标")
TOC_DOTTED_RE = re.compile(r"\.{3,}|…{2,}|[.．·]{2,}\s*\d+\s*$")
TOC_PAGE_RE = re.compile(r"^.{2,80}\s+\d{1,4}\s*$")


def extract_tender_sections(conversion: TenderConversionResult) -> TenderSectionExtraction:
    blocks = sorted(conversion.blocks, key=lambda item: item.order_index)
    candidates = _collect_candidates(blocks)
    boundary_config = load_boundary_config()
    boundary_matches = detect_boundary_matches(blocks, boundary_config)
    requirements_span, scoring_span, boundary_warnings = resolve_extraction_spans(
        blocks=blocks,
        matches=boundary_matches,
        requirements_candidate_index=_candidate_index_for("bid_requirements", candidates, blocks),
        scoring_candidate_index=_candidate_index_for("scoring_criteria", candidates, blocks),
    )
    requirements = _build_result("bid_requirements", blocks, candidates, requirements_span)
    scoring = _build_result("scoring_criteria", blocks, candidates, scoring_span)

    warnings: list[str] = []
    warnings.extend(boundary_config.warnings)
    warnings.extend(boundary_warnings)
    if requirements is None:
        warnings.append("未定位到项目采购需求章节。")
    if scoring is None:
        warnings.append("未定位到评分标准章节。")

    return TenderSectionExtraction(
        requirements=requirements,
        scoring=scoring,
        candidates=candidates,
        warnings=tuple(warnings),
    )


def _collect_candidates(blocks: list[ConvertedBlock]) -> list[SectionCandidate]:
    candidates: list[SectionCandidate] = []
    in_toc_region = False
    for block in blocks:
        if _is_toc_header(block):
            in_toc_region = True
            continue
        if in_toc_region and block.heading_level is not None:
            in_toc_region = False
        if _is_toc_like(block, in_toc_region=in_toc_region):
            continue
        title = _candidate_title(block)
        if not title and block.block_type != "table":
            continue

        requirement_score, requirement_reason = _alias_score(title, REQUIREMENT_ALIASES)
        if requirement_score > 0:
            if block.block_type == "heading":
                requirement_score += 5.0
            candidates.append(
                SectionCandidate(
                    section_key="bid_requirements",
                    block_id=block.block_id,
                    title=title,
                    score=requirement_score,
                    reason=requirement_reason,
                    order_index=block.order_index,
                )
            )

        scoring_score, scoring_reason = _alias_score(title, SCORING_ALIASES)
        table_bonus = _scoring_table_bonus(block)
        if scoring_score > 0 or table_bonus > 0:
            if scoring_score > 0:
                combined_score = scoring_score + min(table_bonus, 15.0)
                if block.block_type == "heading":
                    combined_score += 5.0
            else:
                combined_score = min(95.0, 45.0 + table_bonus)
            candidates.append(
                SectionCandidate(
                    section_key="scoring_criteria",
                    block_id=block.block_id,
                    title=title or block.text[:40],
                    score=combined_score,
                    reason=scoring_reason if scoring_score > 0 else "scoring_table_terms",
                    order_index=block.order_index,
                )
            )
    candidates.sort(key=lambda item: (-item.score, item.order_index))
    return candidates


def _candidate_title(block: ConvertedBlock) -> str:
    if block.heading_title:
        return block.heading_title.strip()
    if block.block_type == "heading":
        return block.text.strip()
    if block.block_type in {"paragraph", "table"} and len(block.text.strip()) <= 40:
        return block.text.strip()
    return ""


def _alias_score(title: str, aliases: tuple[str, ...]) -> tuple[float, str]:
    normalized = _normalize_title(title)
    if not normalized:
        return 0.0, ""
    best = 0.0
    best_alias = ""
    for alias in aliases:
        alias_norm = _normalize_title(alias)
        if alias_norm == normalized:
            return 120.0, "exact_alias"
        if normalized.startswith(alias_norm) or normalized.endswith(alias_norm):
            best = max(best, 100.0)
            best_alias = alias
            continue
        if alias_norm in normalized:
            best = max(best, 45.0)
            best_alias = alias
            continue
        ratio = float(fuzz.partial_ratio(alias_norm, normalized))
        if ratio > best:
            best = ratio
            best_alias = alias
    if best >= 100:
        return 100.0, f"anchored_alias:{best_alias}"
    if best >= 82:
        return 85.0, f"fuzzy_alias:{best_alias}"
    if best >= 68:
        return 55.0, f"weak_alias:{best_alias}"
    return 0.0, ""


def _normalize_title(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text.strip())
    text = re.sub(r"^[第]?[一二三四五六七八九十百千万\d]+[章节条、.．\s]+", "", text)
    text = re.sub(r"[\s　:：|（）()\[\]【】《》<>/\\-]+", "", text)
    return text.lower()


def _scoring_table_bonus(block: ConvertedBlock) -> float:
    text = block.text
    hits = sum(1 for term in SCORING_TABLE_TERMS if term in text)
    if block.block_type == "table" and hits >= 2:
        return 55.0 + hits * 8.0
    if hits >= 3:
        return 35.0
    return 0.0


def _is_toc_header(block: ConvertedBlock) -> bool:
    text = block.text.strip()
    return _normalize_title(block.heading_title or text) == "目录"


def _is_toc_like(block: ConvertedBlock, *, in_toc_region: bool = False) -> bool:
    text = block.text.strip()
    if _is_toc_header(block):
        return True
    if in_toc_region and TOC_PAGE_RE.search(text):
        return True
    return bool(TOC_DOTTED_RE.search(text)) and len(text) <= 80


def _build_result(
    section_key: str,
    blocks: list[ConvertedBlock],
    candidates: list[SectionCandidate],
    span: TenderSectionBoundarySpan | None = None,
) -> TenderExtractionResult | None:
    candidate = next((item for item in candidates if item.section_key == section_key), None)
    if candidate is None:
        return None
    index_by_id = {block.block_id: idx for idx, block in enumerate(blocks)}
    candidate_index = index_by_id[candidate.block_id]
    if span is None:
        start_index = _adjust_start_index(section_key, blocks, candidate_index)
        end_index = _find_end_index(section_key, blocks, start_index)
    else:
        start_index = span.start_index
        end_index = span.end_index
    selected = blocks[start_index:end_index]
    markdown = _join_markdown(selected)
    confidence, warnings = _confidence(section_key, candidate.score, markdown, selected)
    return TenderExtractionResult(
        section_key=section_key,
        title=candidate.title,
        markdown=markdown,
        start_block_id=selected[0].block_id,
        end_block_id=selected[-1].block_id,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def _candidate_index_for(
    section_key: str,
    candidates: list[SectionCandidate],
    blocks: list[ConvertedBlock],
) -> int | None:
    candidate = next((item for item in candidates if item.section_key == section_key), None)
    if candidate is None:
        return None
    index_by_id = {block.block_id: idx for idx, block in enumerate(blocks)}
    return index_by_id.get(candidate.block_id)


def _adjust_start_index(section_key: str, blocks: list[ConvertedBlock], candidate_index: int) -> int:
    candidate = blocks[candidate_index]
    if candidate.block_type == "heading":
        return candidate_index
    for index in range(candidate_index - 1, -1, -1):
        block = blocks[index]
        if _is_opposite_section_boundary(section_key, block) or _is_strong_stop_boundary(block):
            break
        if _is_start_marker_for_key(section_key, block):
            return index
        if block.heading_level is not None:
            break
    return candidate_index


def _find_end_index(section_key: str, blocks: list[ConvertedBlock], start_index: int) -> int:
    start_block = blocks[start_index]
    start_level = start_block.heading_level or 2
    for index in range(start_index + 1, len(blocks)):
        block = blocks[index]
        title = block.heading_title or block.text
        if block.heading_level is not None and block.heading_level <= start_level:
            return index
        if _is_strong_stop_boundary(block):
            return index
        if _is_opposite_section_boundary(section_key, block):
            return index
    return len(blocks)


def _is_start_marker_for_key(section_key: str, block: ConvertedBlock) -> bool:
    if block.block_type == "table":
        return False
    title = _candidate_title(block)
    if not title:
        return False
    aliases = REQUIREMENT_ALIASES if section_key == "bid_requirements" else SCORING_ALIASES
    score, _reason = _alias_score(title, aliases)
    if score > 0:
        return block.block_type == "heading" or _looks_like_section_title(title)
    if section_key == "scoring_criteria":
        return "评分" in title and ("分值" in title or "因素" in title or "细则" in title)
    return False


def _looks_like_section_title(title: str) -> bool:
    stripped = title.strip()
    if len(stripped) > 36:
        return False
    return not any(mark in stripped for mark in "，,。；;")


def _is_opposite_section_boundary(section_key: str, block: ConvertedBlock) -> bool:
    if block.block_type == "table":
        return False
    title = _candidate_title(block)
    if not title:
        return False
    aliases = SCORING_ALIASES if section_key == "bid_requirements" else REQUIREMENT_ALIASES
    score, _reason = _alias_score(title, aliases)
    return score > 0


def _is_strong_stop_boundary(block: ConvertedBlock) -> bool:
    if block.block_type == "table":
        return False
    title = _candidate_title(block) or block.text
    return any(term in title for term in STRONG_STOP_TITLES)


def _join_markdown(blocks: list[ConvertedBlock]) -> str:
    return "\n\n".join(block.markdown.strip() for block in blocks if block.markdown.strip()).strip() + "\n"


def _confidence(
    section_key: str,
    candidate_score: float,
    markdown: str,
    blocks: list[ConvertedBlock],
) -> tuple[float, list[str]]:
    del markdown
    warnings: list[str] = []
    score = min(candidate_score / 120.0, 1.0)
    text = "\n".join(block.text for block in blocks)
    if section_key == "bid_requirements":
        hits = sum(1 for term in REQUIREMENT_TERMS if term in text)
        if len(text.strip()) < 40:
            score -= 0.30
            warnings.append("采购需求摘录内容较短。")
        if hits < 3:
            score -= 0.20
            warnings.append("采购需求关键词命中较少。")
    else:
        hits = sum(1 for term in SCORING_TERMS if term in text)
        has_table = any(block.block_type == "table" for block in blocks)
        if hits < 2 and not has_table:
            score -= 0.25
            warnings.append("评分标准关键词命中较少。")
        if has_table:
            score += 0.10
    return max(0.0, min(score, 1.0)), warnings
