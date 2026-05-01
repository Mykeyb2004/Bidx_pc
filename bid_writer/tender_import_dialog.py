"""招标文件导入确认 UI 辅助。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
)
from .tender_selection_model import (
    TenderSelectionDocument,
    build_default_selection,
    expand_selection_to_next_block,
    expand_selection_to_previous_block,
    selection_to_markdown,
    validate_selection_markdown,
)


SECTION_LABELS = {
    "bid_requirements": "项目采购需求",
    "scoring_criteria": "评分标准",
}


def build_initial_section_selection(
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
) -> tuple[TenderSelectionDocument, ManualTenderSectionSelection | None, ManualTenderSectionSelection | None]:
    document = TenderSelectionDocument.from_blocks(conversion.blocks)
    requirements = build_default_selection(document, extraction.requirements)
    scoring = build_default_selection(document, extraction.scoring)
    return document, requirements, scoring


def build_confirmation_status(
    section_key: str,
    selection: ManualTenderSectionSelection | None,
    warnings: list[str],
) -> str:
    label = SECTION_LABELS[section_key]
    parts = [label]
    if selection is None:
        parts.append("未自动定位，请手动选择。")
    elif selection.manually_adjusted:
        parts.append("已手动调整选区。")
    else:
        parts.append("已根据自动定位默认选中。")
    parts.extend(warnings)
    return "\n".join(parts)


def can_expand_selection(selection: ManualTenderSectionSelection | None) -> bool:
    return selection is not None and selection.start_block_id is not None and selection.end_block_id is not None


class ManualTenderSectionConfirmDialog(tk.Toplevel):
    section_order = ("bid_requirements", "scoring_criteria")

    def __init__(
        self,
        parent,
        conversion: TenderConversionResult,
        extraction: TenderSectionExtraction,
    ) -> None:
        super().__init__(parent)
        self.title("确认招标文件章节")
        self.geometry("1180x720")
        self.minsize(920, 560)

        self.document, requirements, scoring = build_initial_section_selection(conversion, extraction)
        self.selections: dict[str, ManualTenderSectionSelection | None] = {
            "bid_requirements": requirements,
            "scoring_criteria": scoring,
        }
        self.confirmed: dict[str, ManualTenderSectionSelection] = {}
        self.current_index = 0
        self.result = ManualTenderConfirmationResult(cancelled=True)
        self.status_var = tk.StringVar()
        self._applied_source_selection_range: tuple[int, int] | None = None

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
        ttk.Button(controls, text="向前扩展", command=self._expand_previous).grid(row=3, column=0, sticky="ew", pady=3)
        ttk.Button(controls, text="向后扩展", command=self._expand_next).grid(row=4, column=0, sticky="ew", pady=3)
        self.save_button = ttk.Button(controls, text="", command=self._save_current_section)
        self.save_button.grid(row=5, column=0, sticky="ew", pady=(14, 3))
        ttk.Button(controls, text="取消", command=self._cancel).grid(row=6, column=0, sticky="ew", pady=3)

        rendered_frame = ttk.Frame(self, padding=(0, 12, 6, 12))
        rendered_frame.grid(row=0, column=1, sticky="nsew")
        rendered_frame.columnconfigure(0, weight=1)
        rendered_frame.rowconfigure(1, weight=1)
        ttk.Label(rendered_frame, text="块预览").grid(row=0, column=0, sticky="w")
        self.rendered_text = tk.Text(rendered_frame, wrap="word", height=20, borderwidth=1, relief="solid")
        rendered_scroll = ttk.Scrollbar(rendered_frame, orient="vertical", command=self.rendered_text.yview)
        self.rendered_text.configure(yscrollcommand=rendered_scroll.set)
        self.rendered_text.grid(row=1, column=0, sticky="nsew")
        rendered_scroll.grid(row=1, column=1, sticky="ns")
        self._configure_rendered_tags()

        source_frame = ttk.Frame(self, padding=(6, 12, 12, 12))
        source_frame.grid(row=0, column=2, sticky="nsew")
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(1, weight=1)
        ttk.Label(source_frame, text="Markdown 源文").grid(row=0, column=0, sticky="w")
        self.source_text = tk.Text(source_frame, wrap="word", undo=False, borderwidth=1, relief="solid")
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_text.yview)
        self.source_text.configure(yscrollcommand=source_scroll.set)
        self.source_text.grid(row=1, column=0, sticky="nsew")
        source_scroll.grid(row=1, column=1, sticky="ns")
        self.source_text.configure(state="normal")
        self.source_text.insert("1.0", self.document.markdown)
        self.source_text.tag_configure("current_selection", background="#cfe8ff")
        self.source_text.configure(state="disabled")

    def _configure_rendered_tags(self) -> None:
        self.rendered_text.tag_configure("heading", font=("TkDefaultFont", 12, "bold"), spacing1=8, spacing3=4)
        self.rendered_text.tag_configure("table", font=("TkFixedFont", 10), background="#f4f4f4", lmargin1=8, lmargin2=8)
        self.rendered_text.tag_configure("paragraph", spacing1=3, spacing3=7)
        self.rendered_text.tag_configure("selected_block", background="#d9ecff")

    def _load_current_section(self) -> None:
        section_key = self._current_section_key()
        label = SECTION_LABELS[section_key]
        self.step_label.configure(text=f"{self.current_index + 1}/2：{label}")
        self.save_button.configure(text="存入项目需求" if section_key == "bid_requirements" else "存入评分标准")
        self._render_blocks()
        self._apply_source_selection(self.selections[section_key])
        self._update_status()

    def _render_blocks(self) -> None:
        self.rendered_text.configure(state="normal")
        self.rendered_text.delete("1.0", "end")
        selected_ids = self._current_selected_block_ids()
        for block in self.document.blocks:
            start = self.rendered_text.index("end-1c")
            prefix = ""
            if block.block_type == "heading" and block.heading_level:
                prefix = "#" * block.heading_level + " "
            body = block.markdown.strip() if block.block_type == "table" else block.text or block.markdown.strip()
            self.rendered_text.insert("end", f"{prefix}{body}\n\n")
            end = self.rendered_text.index("end-1c")
            tag = "heading" if block.block_type == "heading" else "table" if block.block_type == "table" else "paragraph"
            self.rendered_text.tag_add(tag, start, end)
            if block.block_id in selected_ids:
                self.rendered_text.tag_add("selected_block", start, end)
        self.rendered_text.configure(state="disabled")

    def _current_selected_block_ids(self) -> set[str]:
        selection = self.selections[self._current_section_key()]
        if selection is None or selection.start_block_id is None or selection.end_block_id is None:
            return set()
        start_id, end_id = selection.start_block_id, selection.end_block_id
        if start_id not in self.document.ordered_block_ids or end_id not in self.document.ordered_block_ids:
            return set()
        start = self.document.ordered_block_ids.index(start_id)
        end = self.document.ordered_block_ids.index(end_id)
        if start > end:
            start, end = end, start
        return set(self.document.ordered_block_ids[start : end + 1])

    def _current_section_key(self) -> str:
        return self.section_order[self.current_index]

    def _current_source_selection(self) -> str:
        try:
            selected = self.source_text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            return ""
        return selected

    def _apply_source_selection(self, selection: ManualTenderSectionSelection | None) -> None:
        self.source_text.configure(state="normal")
        self.source_text.tag_remove("current_selection", "1.0", "end")
        self.source_text.tag_remove("sel", "1.0", "end")
        self._applied_source_selection_range = None
        if selection is None:
            self.source_text.see("1.0")
            self.source_text.configure(state="disabled")
            return
        range_start, range_end = self._selection_char_range(selection)
        if range_start is None or range_end is None:
            self.source_text.configure(state="disabled")
            return
        start_index = f"1.0+{range_start}c"
        end_index = f"1.0+{range_end}c"
        self.source_text.tag_add("current_selection", start_index, end_index)
        self.source_text.tag_add("sel", start_index, end_index)
        self.source_text.mark_set("insert", start_index)
        self.source_text.see(start_index)
        self._applied_source_selection_range = (range_start, range_end)
        self.source_text.configure(state="disabled")

    def _selection_char_range(self, selection: ManualTenderSectionSelection) -> tuple[int | None, int | None]:
        if selection.start_block_id and selection.end_block_id:
            start_range = self.document.block_ranges.get(selection.start_block_id)
            end_range = self.document.block_ranges.get(selection.end_block_id)
            if start_range is not None and end_range is not None:
                return min(start_range.start, end_range.start), max(start_range.end, end_range.end)
        needle = selection.markdown.strip()
        if not needle:
            return None, None
        start = self.document.markdown.find(needle)
        if start < 0:
            return None, None
        return start, start + len(needle)

    def _update_status(self, warnings: list[str] | None = None) -> None:
        section_key = self._current_section_key()
        self.status_var.set(build_confirmation_status(section_key, self.selections[section_key], warnings or []))

    def _save_current_section(self) -> None:
        section_key = self._current_section_key()
        markdown, manually_adjusted = self._selection_for_save(section_key)
        warnings = validate_selection_markdown(section_key, markdown)
        blocking = [warning for warning in warnings if "不能为空" in warning]
        if blocking:
            self._update_status(blocking)
            messagebox.showwarning("选区不能为空", blocking[0], parent=self)
            return
        if warnings and not messagebox.askyesno("确认选区", "\n".join([*warnings, "是否继续存入？"]), parent=self):
            self._update_status(warnings)
            return

        previous = self.selections[section_key]
        selection = ManualTenderSectionSelection(
            section_key=section_key,
            markdown=markdown.strip(),
            start_block_id=None if manually_adjusted else previous.start_block_id if previous else None,
            end_block_id=None if manually_adjusted else previous.end_block_id if previous else None,
            manually_adjusted=manually_adjusted or bool(previous and previous.manually_adjusted),
        )
        self.selections[section_key] = selection
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

    def _selection_for_save(self, section_key: str) -> tuple[str, bool]:
        selected = self._current_source_selection()
        if selected:
            return selected, self._source_selection_changed()
        selection = self.selections[section_key]
        if selection is None:
            return "", False
        return selection_to_markdown(self.document, selection), bool(selection.manually_adjusted)

    def _source_selection_changed(self) -> bool:
        if self._applied_source_selection_range is None:
            return True
        try:
            start = self.source_text.count("1.0", "sel.first", "chars")[0]
            end = self.source_text.count("1.0", "sel.last", "chars")[0]
        except tk.TclError:
            return False
        return (start, end) != self._applied_source_selection_range

    def _cancel(self) -> None:
        self.result = ManualTenderConfirmationResult(
            requirements=self.confirmed.get("bid_requirements"),
            scoring=self.confirmed.get("scoring_criteria"),
            cancelled=True,
        )
        self.destroy()

    def _expand_previous(self) -> None:
        self._expand_current(previous=True)

    def _expand_next(self) -> None:
        self._expand_current(previous=False)

    def _expand_current(self, *, previous: bool) -> None:
        section_key = self._current_section_key()
        selection = self.selections[section_key]
        if not can_expand_selection(selection):
            messagebox.showinfo("需要手动选择", "未自动定位当前章节，请先在源码区手动选择文本。", parent=self)
            return
        expander = expand_selection_to_previous_block if previous else expand_selection_to_next_block
        self.selections[section_key] = expander(self.document, selection)
        self._render_blocks()
        self._apply_source_selection(self.selections[section_key])
        self._update_status()


def confirm_tender_sections(
    parent,
    *,
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
    **_kwargs,
) -> ManualTenderConfirmationResult:
    dialog = ManualTenderSectionConfirmDialog(parent, conversion, extraction)
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
