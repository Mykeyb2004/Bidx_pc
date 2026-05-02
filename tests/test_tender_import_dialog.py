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
from bid_writer.tender_selection_model import TenderSelectionDocument, TenderSourceHint


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


def _tagged_text(text: tk.Text, tag_name: str) -> str:
    ranges = text.tag_ranges(tag_name)
    if not ranges:
        return ""
    return text.get(ranges[0], ranges[1])


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


def test_build_initial_section_selection_uses_extraction_as_source_hint_only():
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
    )
    document, requirements, scoring = build_initial_section_selection(_conversion(), extraction)

    assert isinstance(requirements, TenderSourceHint)
    assert isinstance(scoring, TenderSourceHint)
    assert requirements.start_block_id == "r0"
    assert requirements.end_block_id == "r1"
    assert scoring.start_block_id == "s0"
    assert scoring.end_block_id == "s1"
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
    hint = TenderSourceHint("scoring_criteria", "s0", "s1")
    status = build_confirmation_status("scoring_criteria", hint, ["当前内容可能不是评分标准，请确认。"])

    assert "评分标准" in status
    assert "已跳到疑似章节" in status
    assert "可能不是评分标准" in status


def test_manual_dialog_starts_with_empty_target_editor_and_source_hint(monkeypatch):
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

        assert dialog.target_text.get("1.0", "end-1c") == ""
        assert "项目采购需求" in _tagged_text(dialog.source_text, "source_hint")
        assert "服务内容" in _tagged_text(dialog.source_text, "source_hint")
        assert dialog.source_text.tag_ranges("current_selection") == ()

        warnings = []
        monkeypatch.setattr(
            "bid_writer.tender_import_dialog.messagebox.showwarning",
            lambda title, message, **kwargs: warnings.append((title, message, kwargs)),
        )

        dialog._save_current_section()

        assert dialog.result.cancelled is True
        assert dialog.confirmed == {}
        assert "不能为空" in dialog.status_var.get()
        assert warnings == [
            (
                "目标编辑框不能为空",
                "目标编辑框不能为空。请先在源文区选择文本并点击“使用人工所选”，或点击“使用系统推荐”，或直接填写目标编辑框。",
                {"parent": dialog},
            )
        ]
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_use_selection_requires_user_selected_source(monkeypatch):
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        infos = []
        monkeypatch.setattr(
            "bid_writer.tender_import_dialog.messagebox.showinfo",
            lambda title, message, **kwargs: infos.append((title, message, kwargs)),
        )
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction)

        dialog._use_source_selection()

        assert dialog.target_text.get("1.0", "end-1c") == ""
        assert infos == [("需要手动选择", "请先在源文区选择文本。", {"parent": dialog})]
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_user_selection_gets_blue_highlight_and_replaces_target_editor():
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

        dialog.source_text.tag_add("sel", "1.0", "4.0")
        dialog._sync_source_selection_highlight()
        dialog._use_source_selection()

        assert "项目采购需求" in _tagged_text(dialog.source_text, "current_selection")
        assert "服务内容" in _tagged_text(dialog.source_text, "current_selection")
        assert "项目采购需求" in dialog.target_text.get("1.0", "end-1c")
        assert "服务内容" in dialog.target_text.get("1.0", "end-1c")
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_syncs_blue_highlight_while_dragging_source_selection():
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

        assert dialog.source_text.bind("<B1-Motion>")
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_shows_manual_and_system_buttons_and_selection_instructions():
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

        assert "使用人工所选" in button_texts
        assert "使用系统推荐" in button_texts
        assert "使用选区" not in button_texts
        assert "上一章节" not in button_texts
        assert "下一章节" not in button_texts
        assert "Shift+点击" in dialog.selection_help_var.get()
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_use_selection_keeps_user_highlight_when_tk_selection_is_lost(monkeypatch):
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        infos = []
        monkeypatch.setattr(
            "bid_writer.tender_import_dialog.messagebox.showinfo",
            lambda title, message, **kwargs: infos.append((title, message, kwargs)),
        )
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction)
        dialog.source_text.tag_add("sel", "1.0", "4.0")
        dialog._sync_source_selection_highlight()
        dialog.source_text.tag_remove("sel", "1.0", "end")

        dialog._use_source_selection()

        assert infos == []
        assert "项目采购需求" in _tagged_text(dialog.source_text, "current_selection")
        assert "项目采购需求" in dialog.target_text.get("1.0", "end-1c")
        assert "服务内容" in dialog.target_text.get("1.0", "end-1c")
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_use_system_recommendation_replaces_target_editor():
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
        dialog.target_text.insert("1.0", "用户已经输入的内容")

        dialog._use_system_recommendation()

        assert dialog.target_text.get("1.0", "end-1c") == "## 项目采购需求\n\n服务内容包括成果提交和验收。"
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_saves_edited_target_editor_content():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        saved = []
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _conversion(), extraction, save_section=saved.append)

        dialog.source_text.tag_add("sel", "1.0", "4.0")
        dialog._sync_source_selection_highlight()
        dialog._use_source_selection()
        dialog.target_text.insert("end", "\n\n人工补充说明。")
        dialog._save_current_section()
        dialog.source_text.tag_add("sel", "5.0", "end")
        dialog._sync_source_selection_highlight()
        dialog._use_source_selection()
        dialog.target_text.delete("1.0", "end")
        dialog.target_text.insert("1.0", "## 评分标准\n\n| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |\n\n人工调整评分。")
        dialog._save_current_section()

        assert dialog.result.cancelled is False
        assert dialog.result.requirements is not None
        assert "人工补充说明" in dialog.result.requirements.markdown
        assert dialog.result.requirements.start_block_id is None
        assert dialog.result.requirements.end_block_id is None
        assert dialog.result.requirements.manually_adjusted is True
        assert dialog.result.scoring is not None
        assert "人工调整评分" in dialog.result.scoring.markdown
        assert dialog.result.scoring.manually_adjusted is True
        assert [item.section_key for item in saved] == ["bid_requirements", "scoring_criteria"]
        assert "人工补充说明" in saved[0].markdown
        assert "人工调整评分" in saved[1].markdown
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()


def test_manual_dialog_removes_chapter_navigation_buttons():
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

        assert "上一章节" not in button_texts
        assert "下一章节" not in button_texts
        assert "使用人工所选" in button_texts
        assert "使用系统推荐" in button_texts
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
