"""招标文件导入确认 UI 辅助。"""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import messagebox, ttk

from .gui import apply_window_surface, setup_gui_theme, style_text_widget
from .tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
)
from .tender_selection_model import (
    TenderSelectionDocument,
    TenderSourceHint,
    build_source_hint,
    source_hint_to_markdown,
    validate_selection_markdown,
)


SECTION_LABELS = {
    "bid_requirements": "项目采购需求",
    "scoring_criteria": "评分标准",
}

def build_initial_section_selection(
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
) -> tuple[TenderSelectionDocument, TenderSourceHint | None, TenderSourceHint | None]:
    document = TenderSelectionDocument.from_blocks(conversion.blocks)
    requirements = build_source_hint(document, extraction.requirements)
    scoring = build_source_hint(document, extraction.scoring)
    return document, requirements, scoring


def build_confirmation_status(
    section_key: str,
    hint: TenderSourceHint | None,
    warnings: list[str],
) -> str:
    label = SECTION_LABELS[section_key]
    parts = [label]
    if hint is None:
        parts.append("未自动定位，请手动选择。")
    else:
        parts.append("已跳到疑似章节，请选择源文并放入目标编辑框。")
    parts.extend(warnings)
    return "\n".join(parts)


class ManualTenderSectionConfirmDialog(tk.Toplevel):
    section_order = ("bid_requirements", "scoring_criteria")

    def __init__(
        self,
        parent,
        conversion: TenderConversionResult,
        extraction: TenderSectionExtraction,
        *,
        save_section: Callable[[ManualTenderSectionSelection], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.style = setup_gui_theme(self)
        apply_window_surface(self)
        self.title("确认招标文件章节")
        self.geometry("1180x720")
        self.minsize(920, 560)

        self.document, requirements, scoring = build_initial_section_selection(conversion, extraction)
        self.source_hints: dict[str, TenderSourceHint | None] = {
            "bid_requirements": requirements,
            "scoring_criteria": scoring,
        }
        self.confirmed: dict[str, ManualTenderSectionSelection] = {}
        self.current_index = 0
        self.result = ManualTenderConfirmationResult(cancelled=True)
        self.save_section = save_section
        self.status_var = tk.StringVar()
        self.selection_help_var = tk.StringVar(
            value="可鼠标拖选文本；较长内容可先点起始位置，再按住 Shift+点击 结束位置扩展选区。"
        )
        self._user_source_selection_range: tuple[int, int] | None = None

        self._create_widgets()
        self._load_current_section()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _create_widgets(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)

        controls = ttk.Frame(self, padding=12)
        controls.grid(row=0, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=1)

        ttk.Label(controls, text="确认流程").grid(row=0, column=0, sticky="w")
        self.step_label = ttk.Label(controls, text="")
        self.step_label.grid(row=1, column=0, sticky="w", pady=(4, 12))
        ttk.Label(controls, textvariable=self.status_var, wraplength=210, justify="left").grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 16),
        )
        ttk.Label(controls, textvariable=self.selection_help_var, wraplength=210, justify="left").grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        self.use_selection_button = ttk.Button(controls, text="使用人工所选", command=self._use_source_selection)
        self.use_selection_button.grid(row=4, column=0, sticky="ew", pady=3)
        self.use_system_recommendation_button = ttk.Button(
            controls,
            text="使用系统推荐",
            command=self._use_system_recommendation,
        )
        self.use_system_recommendation_button.grid(row=5, column=0, sticky="ew", pady=3)
        self.save_button = ttk.Button(controls, text="", command=self._save_current_section)
        self.save_button.grid(row=6, column=0, sticky="ew", pady=3)
        ttk.Button(controls, text="取消", command=self._cancel).grid(row=7, column=0, sticky="ew", pady=3)

        source_frame = ttk.Frame(self, padding=(0, 12, 6, 12))
        source_frame.grid(row=0, column=1, sticky="nsew")
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(1, weight=1)
        ttk.Label(source_frame, text="Markdown 源文").grid(row=0, column=0, sticky="w")
        self.source_text = tk.Text(
            source_frame,
            wrap="word",
            undo=False,
            borderwidth=1,
            relief="solid",
            exportselection=False,
        )
        style_text_widget(self.source_text)
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_text.yview)
        self.source_text.configure(yscrollcommand=source_scroll.set)
        self.source_text.grid(row=1, column=0, sticky="nsew")
        source_scroll.grid(row=1, column=1, sticky="ns")
        self.source_text.configure(state="normal")
        self.source_text.insert("1.0", self.document.markdown)
        self.source_text.tag_configure("source_hint", background="#fff2b8")
        self.source_text.tag_configure("current_selection", background="#cfe8ff")
        self.source_text.bind("<Key>", lambda _event: "break")
        self.source_text.bind("<B1-Motion>", self._sync_source_selection_highlight)
        self.source_text.bind("<ButtonRelease-1>", self._sync_source_selection_highlight)
        self.source_text.bind("<KeyRelease>", self._sync_source_selection_highlight)

        target_frame = ttk.Frame(self, padding=(6, 12, 12, 12))
        target_frame.grid(row=0, column=2, sticky="nsew")
        target_frame.columnconfigure(0, weight=1)
        target_frame.rowconfigure(1, weight=1)
        ttk.Label(target_frame, text="目标编辑框").grid(row=0, column=0, sticky="w")
        self.target_text = tk.Text(target_frame, wrap="word", undo=True, borderwidth=1, relief="solid")
        style_text_widget(self.target_text)
        target_scroll = ttk.Scrollbar(target_frame, orient="vertical", command=self.target_text.yview)
        self.target_text.configure(yscrollcommand=target_scroll.set)
        self.target_text.grid(row=1, column=0, sticky="nsew")
        target_scroll.grid(row=1, column=1, sticky="ns")

    def _load_current_section(self) -> None:
        section_key = self._current_section_key()
        label = SECTION_LABELS[section_key]
        self.step_label.configure(text=f"{self.current_index + 1}/2：{label}")
        self.save_button.configure(text="存入项目需求" if section_key == "bid_requirements" else "存入评分标准")
        self._clear_target_editor()
        self._apply_source_hint(self.source_hints[section_key])
        self._update_status()

    def _current_section_key(self) -> str:
        return self.section_order[self.current_index]

    def _current_source_selection(self) -> str:
        try:
            selected = self.source_text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            return ""
        return selected

    def _current_user_highlighted_source_text(self) -> str:
        if self._user_source_selection_range is None:
            return ""
        start, end = self._user_source_selection_range
        return self.source_text.get(f"1.0+{start}c", f"1.0+{end}c").strip()

    def _use_source_selection(self) -> None:
        self._sync_source_selection_highlight()
        selected = self._current_source_selection() or self._current_user_highlighted_source_text()
        if not selected:
            messagebox.showinfo("需要手动选择", "请先在源文区选择文本。", parent=self)
            return
        self.target_text.delete("1.0", "end")
        self.target_text.insert("1.0", selected)
        self.target_text.focus_set()
        self._update_status()

    def _use_system_recommendation(self) -> None:
        section_key = self._current_section_key()
        hint = self.source_hints[section_key]
        if hint is None:
            messagebox.showinfo("暂无系统推荐", "当前步骤没有可用的系统推荐，请先在源文区手动选择文本。", parent=self)
            return
        selected = source_hint_to_markdown(self.document, hint)
        if not selected:
            messagebox.showinfo("暂无系统推荐", "当前步骤没有可用的系统推荐，请先在源文区手动选择文本。", parent=self)
            return
        self.target_text.delete("1.0", "end")
        self.target_text.insert("1.0", selected)
        self.target_text.focus_set()
        self._update_status()

    def _clear_target_editor(self) -> None:
        self.target_text.delete("1.0", "end")

    def _apply_source_hint(self, hint: TenderSourceHint | None) -> None:
        self.source_text.configure(state="normal")
        self.source_text.tag_remove("source_hint", "1.0", "end")
        self.source_text.tag_remove("current_selection", "1.0", "end")
        self.source_text.tag_remove("sel", "1.0", "end")
        self._user_source_selection_range = None
        if hint is None:
            self.source_text.see("1.0")
            return
        range_start, range_end = self._hint_char_range(hint)
        if range_start is None or range_end is None:
            return
        start_index = f"1.0+{range_start}c"
        end_index = f"1.0+{range_end}c"
        self.source_text.tag_add("source_hint", start_index, end_index)
        self.source_text.mark_set("insert", start_index)
        self.source_text.see(start_index)

    def _sync_source_selection_highlight(self, _event=None) -> None:
        try:
            start = self.source_text.index("sel.first")
            end = self.source_text.index("sel.last")
        except tk.TclError:
            return
        start_offset = len(self.source_text.get("1.0", start))
        end_offset = len(self.source_text.get("1.0", end))
        if start_offset == end_offset:
            return
        self.source_text.tag_remove("current_selection", "1.0", "end")
        self.source_text.tag_add("current_selection", start, end)
        self._user_source_selection_range = (start_offset, end_offset)

    def _hint_char_range(self, hint: TenderSourceHint) -> tuple[int | None, int | None]:
        start_range = self.document.block_ranges.get(hint.start_block_id)
        end_range = self.document.block_ranges.get(hint.end_block_id)
        if start_range is None or end_range is None:
            return None, None
        return min(start_range.start, end_range.start), max(start_range.end, end_range.end)

    def _update_status(self, warnings: list[str] | None = None) -> None:
        section_key = self._current_section_key()
        self.status_var.set(build_confirmation_status(section_key, self.source_hints[section_key], warnings or []))

    def _save_current_section(self) -> None:
        section_key = self._current_section_key()
        markdown = self._target_editor_markdown()
        warnings = validate_selection_markdown(section_key, markdown)
        blocking = [warning for warning in warnings if "不能为空" in warning]
        if blocking:
            self._update_status(blocking)
            messagebox.showwarning(
                "目标编辑框不能为空",
                "目标编辑框不能为空。请先在源文区选择文本并点击“使用人工所选”，或点击“使用系统推荐”，或直接填写目标编辑框。",
                parent=self,
            )
            return
        if warnings and not messagebox.askyesno("确认选区", "\n".join([*warnings, "是否继续存入？"]), parent=self):
            self._update_status(warnings)
            return

        hint = self.source_hints[section_key]
        matches_hint = self._target_matches_source_hint(section_key, markdown)
        selection = ManualTenderSectionSelection(
            section_key=section_key,
            markdown=markdown,
            start_block_id=hint.start_block_id if hint is not None and matches_hint else None,
            end_block_id=hint.end_block_id if hint is not None and matches_hint else None,
            manually_adjusted=not matches_hint,
        )
        if not self._persist_selection(selection):
            return
        self.confirmed[section_key] = selection

        if self.current_index < len(self.section_order) - 1:
            self.current_index += 1
            self._load_current_section()
            return

        self.result = ManualTenderConfirmationResult(
            requirements=self.confirmed.get("bid_requirements"),
            scoring=self.confirmed.get("scoring_criteria"),
            cancelled=False,
        )
        self.destroy()

    def _target_editor_markdown(self) -> str:
        return self.target_text.get("1.0", "end-1c").strip()

    def _target_matches_source_hint(self, section_key: str, markdown: str) -> bool:
        hint = self.source_hints[section_key]
        if hint is None:
            return False
        return markdown.strip() == source_hint_to_markdown(self.document, hint).strip()

    def _persist_selection(self, selection: ManualTenderSectionSelection) -> bool:
        if self.save_section is None:
            return True
        try:
            self.save_section(selection)
        except Exception as exc:
            messagebox.showerror("写入失败", str(exc), parent=self)
            return False
        return True

    def _cancel(self) -> None:
        self.result = ManualTenderConfirmationResult(
            requirements=self.confirmed.get("bid_requirements"),
            scoring=self.confirmed.get("scoring_criteria"),
            cancelled=True,
        )
        self.destroy()


def confirm_tender_sections(
    parent,
    *,
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
    save_section: Callable[[ManualTenderSectionSelection], None] | None = None,
    **_kwargs,
) -> ManualTenderConfirmationResult:
    dialog = ManualTenderSectionConfirmDialog(parent, conversion, extraction, save_section=save_section)
    parent.wait_window(dialog)
    return dialog.result


def build_low_confidence_preview(extraction: TenderSectionExtraction, *, max_chars: int = 420) -> str:
    parts: list[str] = ["抽取结果置信度偏低，请确认是否写入项目资料文件。"]
    for label, result in (
        ("项目采购需求", extraction.requirements),
        ("评分标准", extraction.scoring),
    ):
        if result is None:
            parts.append(f"\n{label}：未抽取到")
            continue
        parts.append(_format_result(label, result, max_chars=max_chars))
    return "\n".join(parts)


def confirm_low_confidence(parent, extraction: TenderSectionExtraction) -> bool:
    return messagebox.askyesno(
        "确认导入",
        build_low_confidence_preview(extraction),
        parent=parent,
    )


def confirm_extracted_sections_preview(
    parent,
    *,
    extraction: TenderSectionExtraction,
    **_kwargs,
) -> ManualTenderConfirmationResult:
    if not extraction.is_complete:
        messagebox.showwarning(
            "需要人工确认",
            "未能自动定位完整的项目采购需求和评分标准。后续人工确认窗口将支持手动选择，请暂时手动整理资料文件。",
            parent=parent,
        )
        return ManualTenderConfirmationResult(cancelled=True)
    if not confirm_low_confidence(parent, extraction):
        return ManualTenderConfirmationResult(cancelled=True)
    return ManualTenderConfirmationResult(
        requirements=ManualTenderSectionSelection(
            section_key="bid_requirements",
            markdown=extraction.requirements.markdown,
            start_block_id=extraction.requirements.start_block_id,
            end_block_id=extraction.requirements.end_block_id,
            manually_adjusted=False,
        ),
        scoring=ManualTenderSectionSelection(
            section_key="scoring_criteria",
            markdown=extraction.scoring.markdown,
            start_block_id=extraction.scoring.start_block_id,
            end_block_id=extraction.scoring.end_block_id,
            manually_adjusted=False,
        ),
        cancelled=False,
    )


def _format_result(label: str, result: TenderExtractionResult, *, max_chars: int) -> str:
    excerpt = result.markdown.strip().replace("\n\n", "\n")
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n..."
    warnings = "；".join(result.warnings) if result.warnings else "无"
    return "\n".join(
        [
            f"\n{label}：{result.confidence:.0%}",
            f"标题：{result.title}",
            f"提示：{warnings}",
            "预览：",
            excerpt,
        ]
    )
