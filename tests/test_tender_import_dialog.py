from bid_writer.tender_import_dialog import build_low_confidence_preview
from bid_writer.tender_import_models import TenderExtractionResult, TenderSectionExtraction


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
