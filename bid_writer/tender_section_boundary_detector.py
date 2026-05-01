"""招标文件章节边界检测与章节范围解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .tender_import_models import ConvertedBlock
from .tender_section_boundary_config import (
    TenderSectionBoundaryConfig,
    TenderSectionBoundaryMatch,
    TenderSectionBoundaryRule,
    normalize_boundary_text,
)


@dataclass(frozen=True)
class TenderSectionBoundarySpan:
    section_key: str
    kind: Literal["major", "fallback"]
    start_index: int
    end_index: int
    start_block_id: str
    end_block_id: str
    rule_name: str
    boundary_block_id: str


def detect_boundary_matches(
    blocks: list[ConvertedBlock],
    config: TenderSectionBoundaryConfig,
) -> list[TenderSectionBoundaryMatch]:
    matches: list[TenderSectionBoundaryMatch] = []
    strip_invisible = bool(config.normalization.get("strip_invisible", True))
    collapse_space = bool(config.normalization.get("collapse_space", True))
    rules = [*config.major_markers, *config.fallback_markers]

    for index, block in enumerate(blocks):
        normalized = _normalized_block_text(
            block,
            strip_invisible=strip_invisible,
            collapse_space=collapse_space,
        )
        if not normalized:
            continue
        candidates = [_match_rule(block, index, normalized, rule) for rule in rules]
        candidates = [match for match in candidates if match is not None]
        if not candidates:
            continue
        matches.append(_best_match(candidates))
    return matches


def resolve_extraction_spans(
    *,
    blocks: list[ConvertedBlock],
    matches: list[TenderSectionBoundaryMatch],
    requirements_candidate_index: int | None,
    scoring_candidate_index: int | None,
) -> tuple[TenderSectionBoundarySpan | None, TenderSectionBoundarySpan | None, tuple[str, ...]]:
    requirements_major = _span_for_candidate(
        "bid_requirements",
        "major",
        blocks,
        matches,
        requirements_candidate_index,
    )
    scoring_major = _span_for_candidate(
        "scoring_criteria",
        "major",
        blocks,
        matches,
        scoring_candidate_index,
    )
    warnings: list[str] = []

    if _same_span(requirements_major, scoring_major):
        requirements_fallback = _span_for_candidate(
            "bid_requirements",
            "fallback",
            blocks,
            matches,
            requirements_candidate_index,
        )
        scoring_fallback = _span_for_candidate(
            "scoring_criteria",
            "fallback",
            blocks,
            matches,
            scoring_candidate_index,
        )
        warnings.append("项目采购需求和评分标准位于同一大章节，已降级使用小节边界。")
        return (
            requirements_fallback or requirements_major,
            scoring_fallback or scoring_major,
            tuple(warnings),
        )

    requirements_span = requirements_major or _span_for_candidate(
        "bid_requirements",
        "fallback",
        blocks,
        matches,
        requirements_candidate_index,
    )
    scoring_span = scoring_major or _span_for_candidate(
        "scoring_criteria",
        "fallback",
        blocks,
        matches,
        scoring_candidate_index,
    )
    return requirements_span, scoring_span, tuple(warnings)


def _normalized_block_text(
    block: ConvertedBlock,
    *,
    strip_invisible: bool,
    collapse_space: bool,
) -> str:
    source = block.heading_title or block.text or block.markdown
    first_line = str(source).splitlines()[0] if source else ""
    return normalize_boundary_text(
        first_line,
        strip_invisible=strip_invisible,
        collapse_space=collapse_space,
    )


def _match_rule(
    block: ConvertedBlock,
    index: int,
    normalized: str,
    rule: TenderSectionBoundaryRule,
) -> TenderSectionBoundaryMatch | None:
    match = rule.regex.search(normalized)
    if not match:
        return None
    title = (match.groupdict().get("title") or "").strip()
    ordinal = (match.groupdict().get("ordinal") or "").strip()
    return TenderSectionBoundaryMatch(
        block_id=block.block_id,
        block_index=index,
        kind=rule.kind,
        rule_name=rule.name,
        priority=rule.priority,
        marker_text=match.group(0).strip(),
        ordinal=ordinal,
        title=title,
        normalized_text=normalized,
    )


def _best_match(matches: list[TenderSectionBoundaryMatch]) -> TenderSectionBoundaryMatch:
    return sorted(
        matches,
        key=lambda item: (item.priority, len(item.marker_text), bool(item.title)),
        reverse=True,
    )[0]


def _span_for_candidate(
    section_key: str,
    kind: Literal["major", "fallback"],
    blocks: list[ConvertedBlock],
    matches: list[TenderSectionBoundaryMatch],
    candidate_index: int | None,
) -> TenderSectionBoundarySpan | None:
    if candidate_index is None:
        return None
    previous = [match for match in matches if match.kind == kind and match.block_index <= candidate_index]
    if not previous:
        return None
    start_match = max(previous, key=lambda item: item.block_index)
    next_boundary = _next_boundary_index(matches, kind, start_match.block_index, len(blocks))
    if kind == "fallback":
        next_major = _next_boundary_index(matches, "major", start_match.block_index, len(blocks))
        end_index = min(next_boundary, next_major)
    else:
        end_index = next_boundary
    if end_index <= start_match.block_index:
        return None
    return TenderSectionBoundarySpan(
        section_key=section_key,
        kind=kind,
        start_index=start_match.block_index,
        end_index=end_index,
        start_block_id=blocks[start_match.block_index].block_id,
        end_block_id=blocks[end_index - 1].block_id,
        rule_name=start_match.rule_name,
        boundary_block_id=start_match.block_id,
    )


def _next_boundary_index(
    matches: list[TenderSectionBoundaryMatch],
    kind: Literal["major", "fallback"],
    start_index: int,
    default: int,
) -> int:
    later = [match.block_index for match in matches if match.kind == kind and match.block_index > start_index]
    return min(later) if later else default


def _same_span(
    left: TenderSectionBoundarySpan | None,
    right: TenderSectionBoundarySpan | None,
) -> bool:
    if left is None or right is None:
        return False
    return left.start_index == right.start_index and left.end_index == right.end_index
