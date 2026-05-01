from bid_writer.tender_import_dialog import (
    build_low_confidence_preview,
    confirm_extracted_sections_preview,
)
from bid_writer.tender_import_models import (
    ManualTenderSectionSelection,
    TenderExtractionResult,
    TenderSectionExtraction,
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
