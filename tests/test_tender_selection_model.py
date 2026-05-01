from bid_writer.tender_import_models import ConvertedBlock, ManualTenderSectionSelection, TenderExtractionResult
from bid_writer.tender_selection_model import (
    TenderSelectionDocument,
    build_default_selection,
    expand_selection_to_next_block,
    expand_selection_to_previous_block,
    selection_to_markdown,
    validate_selection_markdown,
)


def _block(block_id: str, markdown: str, order: int, block_type: str = "paragraph", heading_level=None):
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type=block_type,
        markdown=markdown,
        text=markdown.replace("#", "").strip(),
        order_index=order,
        heading_level=heading_level,
        heading_title=markdown.replace("#", "").strip() if heading_level else "",
    )


def _document():
    return TenderSelectionDocument.from_blocks(
        [
            _block("h1", "## 项目采购需求", 1, "heading", 2),
            _block("r1", "服务内容包括调查、成果提交和验收。", 2),
            _block("r2", "技术要求应满足采购范围。", 3),
            _block("h2", "## 评分标准", 4, "heading", 2),
            _block("s1", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", 5, "table"),
        ]
    )


def test_document_joins_blocks_and_records_ranges():
    document = _document()

    assert document.markdown.startswith("## 项目采购需求")
    assert document.block_ranges["h1"].start == 0
    assert document.block_ranges["r1"].start > document.block_ranges["h1"].end
    assert document.ordered_block_ids == ["h1", "r1", "r2", "h2", "s1"]

    unsorted_document = TenderSelectionDocument.from_blocks(
        [
            _block("b2", "正文", 2),
            _block("b1", "## 标题", 1, "heading", 2),
        ]
    )

    assert unsorted_document.markdown == "## 标题\n\n正文"
    assert unsorted_document.ordered_block_ids == ["b1", "b2"]
    assert unsorted_document.block_ranges["b1"].start == 0
    assert unsorted_document.block_ranges["b1"].end == 5
    assert unsorted_document.block_ranges["b2"].start == 7
    assert unsorted_document.block_ranges["b2"].end == 9


def test_build_default_selection_maps_extraction_block_ids():
    document = _document()
    extraction = TenderExtractionResult(
        section_key="bid_requirements",
        title="项目采购需求",
        markdown="",
        start_block_id="h1",
        end_block_id="r2",
        confidence=0.9,
    )

    selection = build_default_selection(document, extraction)

    assert selection is not None
    assert selection.start_block_id == "h1"
    assert selection.end_block_id == "r2"
    assert "项目采购需求" in selection_to_markdown(document, selection)
    assert "评分标准" not in selection_to_markdown(document, selection)


def test_build_default_selection_returns_none_for_missing_extraction_or_blocks():
    document = _document()
    missing = TenderExtractionResult("bid_requirements", "需求", "", "missing", "r2", 0.1)

    assert build_default_selection(document, None) is None
    assert build_default_selection(document, missing) is None


def test_expand_selection_to_adjacent_blocks():
    document = _document()
    selection = build_default_selection(
        document,
        TenderExtractionResult("bid_requirements", "项目采购需求", "", "r1", "r1", 0.9),
    )

    previous = expand_selection_to_previous_block(document, selection)
    expanded = expand_selection_to_next_block(document, previous)

    assert previous.start_block_id == "h1"
    assert previous.end_block_id == "r1"
    assert previous.manually_adjusted is True
    assert expanded.start_block_id == "h1"
    assert expanded.end_block_id == "r2"
    assert expanded.manually_adjusted is True


def test_selection_to_markdown_uses_character_range():
    document = _document()
    selection = build_default_selection(
        document,
        TenderExtractionResult("scoring_criteria", "评分标准", "", "h2", "s1", 0.9),
    )

    markdown = selection_to_markdown(document, selection)

    assert markdown.startswith("## 评分标准")
    assert "10分" in markdown
    assert "项目采购需求" not in markdown


def test_selection_to_markdown_falls_back_to_manual_markdown_without_valid_blocks():
    document = _document()
    selection = ManualTenderSectionSelection(
        section_key="bid_requirements",
        markdown="手动拖选内容",
        start_block_id=None,
        end_block_id=None,
        manually_adjusted=True,
    )
    missing_block_selection = ManualTenderSectionSelection(
        section_key="bid_requirements",
        markdown="手动拖选内容",
        start_block_id="missing",
        end_block_id="r1",
        manually_adjusted=True,
    )

    assert selection_to_markdown(document, selection) == "手动拖选内容"
    assert selection_to_markdown(document, missing_block_selection) == "手动拖选内容"


def test_validate_selection_markdown_warns_for_empty_short_and_suspicious_content():
    assert "不能为空" in validate_selection_markdown("bid_requirements", "")[0]
    assert "内容较短" in validate_selection_markdown("bid_requirements", "短")[0]
    assert any("可能不是项目采购需求" in item for item in validate_selection_markdown("bid_requirements", "只有一句普通说明但没有关键词" * 3))
    assert any("可能不是评分标准" in item for item in validate_selection_markdown("scoring_criteria", "普通说明文字" * 10))
    assert validate_selection_markdown("scoring_criteria", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |") == []
