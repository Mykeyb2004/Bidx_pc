"""Pure selection helpers for manual tender section confirmation."""

from __future__ import annotations

from dataclasses import dataclass

from .tender_import_models import ConvertedBlock, ManualTenderSectionSelection, TenderExtractionResult


REQUIREMENT_TERMS = ("服务", "技术", "要求", "内容", "范围", "参数", "成果", "验收", "采购")
SCORING_TERMS = ("评分", "评审", "分值", "满分", "权重", "得分")


@dataclass(frozen=True)
class TextRange:
    start: int
    end: int


@dataclass(frozen=True)
class TenderSelectionDocument:
    markdown: str
    blocks: list[ConvertedBlock]
    block_ranges: dict[str, TextRange]
    ordered_block_ids: list[str]

    @classmethod
    def from_blocks(cls, blocks: list[ConvertedBlock]) -> "TenderSelectionDocument":
        ordered = sorted(blocks, key=lambda item: item.order_index)
        parts: list[str] = []
        ranges: dict[str, TextRange] = {}
        cursor = 0
        for block in ordered:
            if parts:
                parts.append("\n\n")
                cursor += 2
            markdown = block.markdown.strip()
            start = cursor
            parts.append(markdown)
            cursor += len(markdown)
            ranges[block.block_id] = TextRange(start=start, end=cursor)
        return cls(
            markdown="".join(parts),
            blocks=ordered,
            block_ranges=ranges,
            ordered_block_ids=[block.block_id for block in ordered],
        )


def build_default_selection(
    document: TenderSelectionDocument,
    extraction: TenderExtractionResult | None,
) -> ManualTenderSectionSelection | None:
    if extraction is None:
        return None
    if extraction.start_block_id not in document.block_ranges or extraction.end_block_id not in document.block_ranges:
        return None
    start_block_id, end_block_id = _canonical_block_ids(document, extraction.start_block_id, extraction.end_block_id)
    markdown = selection_to_markdown(
        document,
        ManualTenderSectionSelection(
            section_key=extraction.section_key,
            markdown="",
            start_block_id=start_block_id,
            end_block_id=end_block_id,
            manually_adjusted=False,
        ),
    )
    return ManualTenderSectionSelection(
        section_key=extraction.section_key,
        markdown=markdown,
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        manually_adjusted=False,
    )


def selection_to_markdown(document: TenderSelectionDocument, selection: ManualTenderSectionSelection) -> str:
    if selection.start_block_id is None or selection.end_block_id is None:
        return selection.markdown.strip()
    start_block_id, end_block_id = _canonical_block_ids(document, selection.start_block_id, selection.end_block_id)
    start_range = document.block_ranges.get(start_block_id)
    end_range = document.block_ranges.get(end_block_id)
    if start_range is None or end_range is None:
        return selection.markdown.strip()
    return document.markdown[start_range.start : end_range.end].strip()


def _replace_block_range(
    document: TenderSelectionDocument,
    selection: ManualTenderSectionSelection,
    *,
    start_block_id: str | None,
    end_block_id: str | None,
) -> ManualTenderSectionSelection:
    start_block_id, end_block_id = _canonical_block_ids(document, start_block_id, end_block_id)
    updated = ManualTenderSectionSelection(
        section_key=selection.section_key,
        markdown="",
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        manually_adjusted=True,
    )
    return ManualTenderSectionSelection(
        section_key=selection.section_key,
        markdown=selection_to_markdown(document, updated),
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        manually_adjusted=True,
    )


def _canonical_block_ids(
    document: TenderSelectionDocument,
    start_block_id: str | None,
    end_block_id: str | None,
) -> tuple[str | None, str | None]:
    if start_block_id not in document.ordered_block_ids or end_block_id not in document.ordered_block_ids:
        return start_block_id, end_block_id
    start_index = document.ordered_block_ids.index(start_block_id)
    end_index = document.ordered_block_ids.index(end_block_id)
    if start_index <= end_index:
        return start_block_id, end_block_id
    return end_block_id, start_block_id


def validate_selection_markdown(section_key: str, markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return ["选区不能为空。"]
    warnings: list[str] = []
    if len(text) < 20:
        warnings.append("选区内容较短，请确认是否完整。")
    if section_key == "bid_requirements":
        hits = sum(1 for term in REQUIREMENT_TERMS if term in text)
        if hits < 2:
            warnings.append("当前内容可能不是项目采购需求，请确认。")
    elif section_key == "scoring_criteria":
        has_table = "|" in text and "---" in text
        hits = sum(1 for term in SCORING_TERMS if term in text)
        if hits < 2 and not has_table:
            warnings.append("当前内容可能不是评分标准，请确认。")
    return warnings
