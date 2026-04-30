from pathlib import Path

from bid_writer.tender_import_models import (
    ConvertedBlock,
    SectionCandidate,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
    dump_conversion_map,
    dump_extraction_report,
)


def test_dump_conversion_map_serializes_blocks(tmp_path: Path):
    result = TenderConversionResult(
        source_path=tmp_path / "tender.docx",
        output_dir=tmp_path / ".bid_writer" / "imports" / "import-1",
        converted_markdown_path=tmp_path / ".bid_writer" / "imports" / "import-1" / "converted.md",
        conversion_map_path=tmp_path / ".bid_writer" / "imports" / "import-1" / "conversion_map.json",
        blocks=[
            ConvertedBlock(
                block_id="docx:p0001",
                source_file="tender.docx",
                source_type="docx",
                block_type="heading",
                markdown="## 项目采购需求",
                text="项目采购需求",
                order_index=1,
                heading_level=2,
                heading_title="项目采购需求",
                page_number=3,
                sheet_name="",
                cell_range="",
                paragraph_index=1,
            )
        ],
        warnings=("converted",),
    )

    payload = dump_conversion_map(result)
    block = payload["blocks"][0]

    assert set(payload) == {
        "source_path",
        "output_dir",
        "converted_markdown_path",
        "conversion_map_path",
        "warnings",
        "blocks",
    }
    assert payload["source_path"].endswith("tender.docx")
    assert payload["output_dir"].endswith(".bid_writer/imports/import-1")
    assert payload["converted_markdown_path"].endswith(".bid_writer/imports/import-1/converted.md")
    assert payload["conversion_map_path"].endswith(".bid_writer/imports/import-1/conversion_map.json")
    assert payload["warnings"] == ["converted"]
    assert set(block) == {
        "block_id",
        "source_file",
        "source_type",
        "block_type",
        "markdown",
        "text",
        "order_index",
        "heading_level",
        "heading_title",
        "page_number",
        "sheet_name",
        "cell_range",
        "paragraph_index",
        "table_index",
    }
    assert block["block_id"] == "docx:p0001"
    assert block["source_file"] == "tender.docx"
    assert block["source_type"] == "docx"
    assert block["heading_level"] == 2
    assert block["page_number"] == 3
    assert block["sheet_name"] == ""
    assert block["cell_range"] == ""
    assert block["paragraph_index"] == 1


def test_dump_extraction_report_serializes_results_and_candidates(tmp_path: Path):
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult(
            section_key="bid_requirements",
            title="项目采购需求",
            markdown="# 项目采购需求\n\n正文",
            start_block_id="b1",
            end_block_id="b3",
            confidence=0.91,
        ),
        scoring=TenderExtractionResult(
            section_key="scoring_criteria",
            title="评分标准",
            markdown="# 评分标准\n\n表格",
            start_block_id="b4",
            end_block_id="b7",
            confidence=0.87,
            warnings=("命中评分表",),
        ),
        candidates=[
            SectionCandidate(
                section_key="scoring_criteria",
                block_id="b4",
                title="评分标准",
                score=120.0,
                reason="exact_alias",
            )
        ],
        warnings=("ok",),
    )

    payload = dump_extraction_report(extraction)
    requirement = payload["requirements"]
    scoring = payload["scoring"]
    candidate = payload["candidates"][0]

    assert set(payload) == {
        "requirements",
        "scoring",
        "candidates",
        "warnings",
        "complete",
        "needs_confirmation",
    }
    assert set(requirement) == {
        "section_key",
        "title",
        "markdown",
        "start_block_id",
        "end_block_id",
        "confidence",
        "warnings",
    }
    assert requirement["section_key"] == "bid_requirements"
    assert requirement["start_block_id"] == "b1"
    assert requirement["end_block_id"] == "b3"
    assert requirement["confidence"] == 0.91
    assert scoring["section_key"] == "scoring_criteria"
    assert scoring["start_block_id"] == "b4"
    assert scoring["end_block_id"] == "b7"
    assert scoring["warnings"] == ["命中评分表"]
    assert set(candidate) == {"section_key", "block_id", "title", "score", "reason", "order_index"}
    assert candidate["reason"] == "exact_alias"
    assert payload["warnings"] == ["ok"]
    assert payload["complete"] is True
    assert payload["needs_confirmation"] is False
