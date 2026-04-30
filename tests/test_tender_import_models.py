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
                paragraph_index=1,
            )
        ],
        warnings=("converted",),
    )

    payload = dump_conversion_map(result)

    assert payload["source_path"].endswith("tender.docx")
    assert payload["warnings"] == ["converted"]
    assert payload["blocks"][0]["block_id"] == "docx:p0001"
    assert payload["blocks"][0]["heading_level"] == 2


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

    assert payload["requirements"]["confidence"] == 0.91
    assert payload["scoring"]["warnings"] == ["命中评分表"]
    assert payload["candidates"][0]["reason"] == "exact_alias"
    assert payload["warnings"] == ["ok"]
