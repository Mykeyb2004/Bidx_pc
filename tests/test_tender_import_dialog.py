from pathlib import Path

from bid_writer.tender_import_dialog import (
    SECTION_LABELS,
    build_confirmation_status,
    build_initial_section_selection,
    can_expand_selection,
    build_low_confidence_preview,
    confirm_extracted_sections_preview,
)
from bid_writer.tender_import_models import (
    ConvertedBlock,
    ManualTenderSectionSelection,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
)


def _conversion() -> TenderConversionResult:
    blocks = [
        ConvertedBlock("r0", "tender.md", "md", "heading", "## 项目采购需求", "项目采购需求", 1, heading_level=2, heading_title="项目采购需求"),
        ConvertedBlock("r1", "tender.md", "md", "paragraph", "服务内容包括成果提交和验收。", "服务内容包括成果提交和验收。", 2),
        ConvertedBlock("s0", "tender.md", "md", "heading", "## 评分标准", "评分标准", 3, heading_level=2, heading_title="评分标准"),
        ConvertedBlock("s1", "tender.md", "md", "table", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", "| 评分项 | 分值 |", 4),
    ]
    return TenderConversionResult(
        source_path=Path("tender.md"),
        output_dir=Path(".bid_writer/imports/test"),
        converted_markdown_path=Path(".bid_writer/imports/test/converted.md"),
        conversion_map_path=Path(".bid_writer/imports/test/conversion_map.json"),
        blocks=blocks,
    )


def test_manual_selection_dataclass_keeps_block_range():
    selection = ManualTenderSectionSelection(
        section_key="bid_requirements",
        markdown="需求",
        start_block_id="b1",
        end_block_id="b3",
        manually_adjusted=True,
    )

    assert selection.section_key == "bid_requirements"
    assert selection.start_block_id == "b1"
    assert selection.end_block_id == "b3"


def test_section_labels_match_required_flow():
    assert SECTION_LABELS["bid_requirements"] == "项目采购需求"
    assert SECTION_LABELS["scoring_criteria"] == "评分标准"


def test_build_initial_section_selection_uses_extraction_default():
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
    )
    document, requirements, scoring = build_initial_section_selection(_conversion(), extraction)

    assert requirements is not None
    assert scoring is not None
    assert "服务内容" in requirements.markdown
    assert "10分" in scoring.markdown
    assert document.markdown.startswith("## 项目采购需求")


def test_build_initial_section_selection_handles_missing_extraction():
    document, requirements, scoring = build_initial_section_selection(_conversion(), TenderSectionExtraction())

    assert requirements is None
    assert scoring is None
    assert "评分标准" in document.markdown


def test_build_confirmation_status_mentions_missing_auto_location():
    status = build_confirmation_status("bid_requirements", None, [])

    assert "未自动定位" in status
    assert "项目采购需求" in status


def test_build_confirmation_status_includes_warnings():
    selection = ManualTenderSectionSelection("scoring_criteria", "普通文字" * 20, None, None, True)
    status = build_confirmation_status("scoring_criteria", selection, ["当前内容可能不是评分标准，请确认。"])

    assert "评分标准" in status
    assert "可能不是评分标准" in status


def test_can_expand_selection_requires_block_backed_selection():
    assert can_expand_selection(None) is False
    assert can_expand_selection(ManualTenderSectionSelection("bid_requirements", "手选", None, None, True)) is False
    assert can_expand_selection(ManualTenderSectionSelection("bid_requirements", "", "r1", "r2", False)) is True


def test_low_confidence_preview_includes_confidence_and_excerpt():
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult(
            "bid_requirements",
            "项目采购需求",
            "# 项目采购需求\n\n" + "需求正文" * 80,
            "r1",
            "r3",
            0.61,
            ("采购需求摘录内容较短。",),
        ),
        scoring=TenderExtractionResult(
            "scoring_criteria",
            "评分标准",
            "# 评分标准\n\n评分正文",
            "s1",
            "s3",
            0.88,
        ),
    )

    preview = build_low_confidence_preview(extraction)

    assert "项目采购需求：61%" in preview
    assert "采购需求摘录内容较短" in preview
    assert "评分标准：88%" in preview
    assert len(preview) < 1600


def test_confirm_extracted_sections_preview_warns_when_extraction_incomplete(monkeypatch):
    warnings = []
    extraction = TenderSectionExtraction(requirements=None, scoring=None)

    monkeypatch.setattr(
        "bid_writer.tender_import_dialog.messagebox.showwarning",
        lambda title, message, **kwargs: warnings.append((title, message, kwargs)),
    )

    result = confirm_extracted_sections_preview("parent", extraction=extraction)

    assert result.cancelled is True
    assert warnings == [
        (
            "需要人工确认",
            "未能自动定位完整的项目采购需求和评分标准。后续人工确认窗口将支持手动选择，请暂时手动整理资料文件。",
            {"parent": "parent"},
        )
    ]
