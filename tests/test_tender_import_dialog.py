from pathlib import Path
import tkinter as tk
from tkinter import ttk

import pytest

from bid_writer.gui import ensure_tk_runtime
from bid_writer.tender_import_dialog import (
    ManualTenderSectionConfirmDialog,
    SECTION_LABELS,
    build_confirmation_status,
    build_initial_section_selection,
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


def _selected_line_range(text: tk.Text) -> tuple[int, int]:
    start = int(text.index("sel.first").split(".", 1)[0])
    end = int(text.index("sel.last").split(".", 1)[0])
    if text.index("sel.last").split(".", 1)[1] == "0":
        end -= 1
    return start, end


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


def test_manual_dialog_saves_default_source_selection_without_user_drag():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction)

        dialog._save_current_section()
        dialog._save_current_section()

        assert dialog.result.cancelled is False
        assert dialog.result.requirements is not None
        assert "服务内容" in dialog.result.requirements.markdown
        assert dialog.result.requirements.start_block_id == "r0"
        assert dialog.result.requirements.end_block_id == "r1"
        assert dialog.result.requirements.manually_adjusted is False
        assert dialog.result.scoring is not None
        assert "10分" in dialog.result.scoring.markdown
        assert dialog.result.scoring.start_block_id == "s0"
        assert dialog.result.scoring.end_block_id == "s1"
        assert dialog.result.scoring.manually_adjusted is False
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_chapter_buttons_move_source_selection_by_line_count():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction)

        assert _selected_line_range(dialog.source_text) == (1, 3)

        dialog._move_next()

        assert _selected_line_range(dialog.source_text) == (4, 6)
        assert dialog.selections["bid_requirements"] is not None
        assert dialog.selections["bid_requirements"].start_block_id is None
        assert dialog.selections["bid_requirements"].end_block_id is None
        assert dialog.selections["bid_requirements"].manually_adjusted is True

        dialog._move_previous()

        assert _selected_line_range(dialog.source_text) == (1, 3)
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_uses_chapter_navigation_button_labels():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction)

        button_texts = [
            child.cget("text")
            for child in dialog.winfo_children()[0].winfo_children()
            if isinstance(child, ttk.Button)
        ]

        assert "上一章节" in button_texts
        assert "下一章节" in button_texts
        assert "向前扩展" not in button_texts
        assert "向后扩展" not in button_texts
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


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
