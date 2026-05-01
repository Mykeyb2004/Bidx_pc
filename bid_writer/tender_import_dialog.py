"""招标文件导入确认 UI 辅助。"""

from __future__ import annotations

from dataclasses import dataclass
import re
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
    selection_to_markdown,
    validate_selection_markdown,
)
from .tender_section_boundary_config import load_boundary_config
from .tender_section_boundary_detector import detect_boundary_matches


SECTION_LABELS = {
    "bid_requirements": "项目采购需求",
    "scoring_criteria": "评分标准",
}
TOC_DOTTED_RE = re.compile(r"\.{3,}|…{2,}|[.．·]{2,}\s*\d+\s*$")
TOC_PAGE_RE = re.compile(r"^.{2,80}\s+\d{1,4}\s*$")


@dataclass(frozen=True)
class _SourceNavigationRange:
    kind: str
    start_block_id: str
    end_block_id: str
    start: int
    end: int


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
        self._major_navigation_ranges, self._fallback_navigation_ranges = _build_source_navigation_ranges(self.document)

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
        ttk.Button(controls, text="上一章节", command=self._move_previous).grid(row=3, column=0, sticky="ew", pady=3)
        ttk.Button(controls, text="下一章节", command=self._move_next).grid(row=4, column=0, sticky="ew", pady=3)
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

    def _current_source_char_range(self) -> tuple[int, int] | None:
        try:
            start = self.source_text.index("sel.first")
            end = self.source_text.index("sel.last")
        except tk.TclError:
            return None
        start_offset = len(self.source_text.get("1.0", start))
        end_offset = len(self.source_text.get("1.0", end))
        return start_offset, end_offset

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
            start = self.source_text.index("sel.first")
            end = self.source_text.index("sel.last")
        except tk.TclError:
            return False
        expected_start, expected_end = self._applied_source_selection_range
        expected_start_index = self.source_text.index(f"1.0+{expected_start}c")
        expected_end_index = self.source_text.index(f"1.0+{expected_end}c")
        return (start, end) != (expected_start_index, expected_end_index)

    def _cancel(self) -> None:
        self.result = ManualTenderConfirmationResult(
            requirements=self.confirmed.get("bid_requirements"),
            scoring=self.confirmed.get("scoring_criteria"),
            cancelled=True,
        )
        self.destroy()

    def _move_previous(self) -> None:
        self._move_current(previous=True)

    def _move_next(self) -> None:
        self._move_current(previous=False)

    def _move_current(self, *, previous: bool) -> None:
        section_key = self._current_section_key()
        char_range = self._current_source_char_range()
        target = self._adjacent_navigation_range(char_range, previous=previous)
        if target is not None:
            self._apply_source_char_selection(target.start, target.end)
            selected = self._current_source_selection()
            self.selections[section_key] = ManualTenderSectionSelection(
                section_key=section_key,
                markdown=selected,
                start_block_id=None,
                end_block_id=None,
                manually_adjusted=True,
            )
            self._render_blocks()
            self._update_status()
            return

        line_range = self._current_source_line_range()
        if line_range is None:
            messagebox.showinfo("需要手动选择", "请先在源码区选择文本。", parent=self)
            return
        start_line, end_line = line_range
        line_count = end_line - start_line + 1
        total_lines = self._source_text_line_count()
        target_start = start_line - line_count if previous else start_line + line_count
        target_end = target_start + line_count - 1
        if target_start < 1 or target_end > total_lines:
            return

        self._apply_source_line_selection(target_start, target_end)
        selected = self._current_source_selection()
        self.selections[section_key] = ManualTenderSectionSelection(
            section_key=section_key,
            markdown=selected,
            start_block_id=None,
            end_block_id=None,
            manually_adjusted=True,
        )
        self._render_blocks()
        self._update_status()

    def _adjacent_navigation_range(
        self,
        current_range: tuple[int, int] | None,
        *,
        previous: bool,
    ) -> _SourceNavigationRange | None:
        if current_range is None:
            return None
        ranges = self._navigation_ranges_for_current_selection(current_range)
        if not ranges:
            return None
        current_index = _current_navigation_index(ranges, current_range)
        if current_index is None:
            return None
        target_index = current_index - 1 if previous else current_index + 1
        if target_index < 0 or target_index >= len(ranges):
            return None
        return ranges[target_index]

    def _navigation_ranges_for_current_selection(
        self,
        current_range: tuple[int, int],
    ) -> tuple[_SourceNavigationRange, ...]:
        for ranges in (self._major_navigation_ranges, self._fallback_navigation_ranges):
            if any(item.start == current_range[0] and item.end == current_range[1] for item in ranges):
                return ranges
        fallback_containing = [
            item
            for item in self._fallback_navigation_ranges
            if item.start <= current_range[0] and current_range[1] <= item.end
        ]
        if fallback_containing:
            return self._fallback_navigation_ranges
        if self._major_navigation_ranges:
            return self._major_navigation_ranges
        return self._fallback_navigation_ranges

    def _current_source_line_range(self) -> tuple[int, int] | None:
        try:
            start = self.source_text.index("sel.first")
            end = self.source_text.index("sel.last")
        except tk.TclError:
            return None
        start_line = int(start.split(".", 1)[0])
        end_line_text, end_column_text = end.split(".", 1)
        end_line = int(end_line_text)
        if end_column_text == "0" and end_line > start_line:
            end_line -= 1
        return start_line, end_line

    def _source_text_line_count(self) -> int:
        return int(self.source_text.index("end-1c").split(".", 1)[0])

    def _apply_source_line_selection(self, start_line: int, end_line: int) -> None:
        start_index = f"{start_line}.0"
        total_lines = self._source_text_line_count()
        end_index = f"{end_line + 1}.0" if end_line < total_lines else f"{end_line}.end"
        self.source_text.configure(state="normal")
        self.source_text.tag_remove("current_selection", "1.0", "end")
        self.source_text.tag_remove("sel", "1.0", "end")
        self.source_text.tag_add("current_selection", start_index, end_index)
        self.source_text.tag_add("sel", start_index, end_index)
        self.source_text.mark_set("insert", start_index)
        self.source_text.see(start_index)
        self._applied_source_selection_range = None
        self.source_text.configure(state="disabled")

    def _apply_source_char_selection(self, start: int, end: int) -> None:
        start_index = f"1.0+{start}c"
        end_index = f"1.0+{end}c"
        self.source_text.configure(state="normal")
        self.source_text.tag_remove("current_selection", "1.0", "end")
        self.source_text.tag_remove("sel", "1.0", "end")
        self.source_text.tag_add("current_selection", start_index, end_index)
        self.source_text.tag_add("sel", start_index, end_index)
        self.source_text.mark_set("insert", start_index)
        self.source_text.see(start_index)
        self._applied_source_selection_range = None
        self.source_text.configure(state="disabled")


def _build_source_navigation_ranges(
    document: TenderSelectionDocument,
) -> tuple[tuple[_SourceNavigationRange, ...], tuple[_SourceNavigationRange, ...]]:
    config = load_boundary_config()
    matches = _filter_navigation_boundary_matches(document.blocks, [
        match
        for match in detect_boundary_matches(document.blocks, config)
        if _is_useful_navigation_match(match.normalized_text, match.rule_name, match.title, match.ordinal)
    ])
    boundary_major_ranges = _source_navigation_ranges_for_kind(document, matches, kind="major")
    heading_major_ranges = _heading_navigation_ranges(document)
    major_ranges = _merge_navigation_ranges(boundary_major_ranges, heading_major_ranges)
    fallback_ranges = _source_navigation_ranges_for_kind(document, matches, kind="fallback")
    return major_ranges, fallback_ranges


def _source_navigation_ranges_for_kind(
    document: TenderSelectionDocument,
    matches,
    *,
    kind: str,
) -> tuple[_SourceNavigationRange, ...]:
    blocks = document.blocks
    kind_matches = sorted([match for match in matches if match.kind == kind], key=lambda item: item.block_index)
    ranges: list[_SourceNavigationRange] = []
    for match in kind_matches:
        next_same = _next_match_index(kind_matches, match.block_index, len(blocks))
        if kind == "fallback":
            major_matches = [item for item in matches if item.kind == "major"]
            next_major = _next_match_index(major_matches, match.block_index, len(blocks))
            end_index = min(next_same, next_major)
        else:
            end_index = next_same
        if end_index <= match.block_index:
            continue
        start_block = blocks[match.block_index]
        end_block = blocks[end_index - 1]
        start_range = document.block_ranges.get(start_block.block_id)
        end_range = document.block_ranges.get(end_block.block_id)
        if start_range is None or end_range is None:
            continue
        ranges.append(
            _SourceNavigationRange(
                kind=kind,
                start_block_id=start_block.block_id,
                end_block_id=end_block.block_id,
                start=start_range.start,
                end=end_range.end,
            )
        )
    return tuple(ranges)


def _next_match_index(matches, start_index: int, default: int) -> int:
    later = [match.block_index for match in matches if match.block_index > start_index]
    return min(later) if later else default


def _heading_navigation_ranges(document: TenderSelectionDocument) -> tuple[_SourceNavigationRange, ...]:
    if not any(block.source_type == "docx" for block in document.blocks):
        return ()
    heading_indexes = [
        index
        for index, block in enumerate(document.blocks)
        if block.heading_level is not None and _is_useful_heading_navigation_block(block)
    ]
    if not heading_indexes:
        return ()
    top_level = min(document.blocks[index].heading_level for index in heading_indexes)
    top_heading_indexes = [
        index for index in heading_indexes if document.blocks[index].heading_level == top_level
    ]
    ranges: list[_SourceNavigationRange] = []
    for position, start_index in enumerate(top_heading_indexes):
        end_index = top_heading_indexes[position + 1] if position + 1 < len(top_heading_indexes) else len(document.blocks)
        start_block = document.blocks[start_index]
        end_block = document.blocks[end_index - 1]
        start_range = document.block_ranges.get(start_block.block_id)
        end_range = document.block_ranges.get(end_block.block_id)
        if start_range is None or end_range is None:
            continue
        ranges.append(
            _SourceNavigationRange(
                kind="heading",
                start_block_id=start_block.block_id,
                end_block_id=end_block.block_id,
                start=start_range.start,
                end=end_range.end,
            )
        )
    return tuple(ranges)


def _merge_navigation_ranges(
    primary: tuple[_SourceNavigationRange, ...],
    secondary: tuple[_SourceNavigationRange, ...],
) -> tuple[_SourceNavigationRange, ...]:
    merged = list(primary)
    for candidate in secondary:
        if any(item.start == candidate.start for item in merged):
            continue
        merged.append(candidate)
    return tuple(sorted(merged, key=lambda item: item.start))


def _current_navigation_index(
    ranges: tuple[_SourceNavigationRange, ...],
    current_range: tuple[int, int],
) -> int | None:
    for index, item in enumerate(ranges):
        if item.start == current_range[0] and item.end == current_range[1]:
            return index
    overlaps = [
        (index, _overlap_size(item.start, item.end, current_range[0], current_range[1]))
        for index, item in enumerate(ranges)
    ]
    overlaps = [(index, size) for index, size in overlaps if size > 0]
    if not overlaps:
        return None
    return max(overlaps, key=lambda item: item[1])[0]


def _overlap_size(left_start: int, left_end: int, right_start: int, right_end: int) -> int:
    return max(0, min(left_end, right_end) - max(left_start, right_start))


def _is_useful_navigation_match(normalized_text: str, rule_name: str, title: str, ordinal: str) -> bool:
    del ordinal
    text = normalized_text.strip()
    if not text or re.fullmatch(r"\d+", text):
        return False
    if rule_name == "volume_or_book" and not title.strip():
        return False
    if rule_name in {"appendix", "appendix_table"} and not title.strip():
        return False
    return True


def _filter_navigation_boundary_matches(blocks, matches):
    matches_by_index: dict[int, list] = {}
    for match in matches:
        matches_by_index.setdefault(match.block_index, []).append(match)

    filtered: list = []
    in_toc_region = False
    for index, block in enumerate(blocks):
        if _is_toc_header_block(block):
            in_toc_region = True
            continue
        if in_toc_region and block.heading_level is not None:
            in_toc_region = False
        if _is_toc_like_block(block, in_toc_region=in_toc_region):
            continue
        filtered.extend(matches_by_index.get(index, []))
    return filtered


def _is_toc_header_block(block) -> bool:
    text = str(block.heading_title or block.text or "").strip()
    return re.sub(r"[\s　]+", "", text) == "目录"


def _is_toc_like_block(block, *, in_toc_region: bool = False) -> bool:
    text = str(block.text or "").strip()
    if _is_toc_header_block(block):
        return True
    if in_toc_region and TOC_PAGE_RE.search(text):
        return True
    return bool(TOC_DOTTED_RE.search(text)) and len(text) <= 80


def _is_useful_heading_navigation_block(block) -> bool:
    text = str(block.heading_title or block.text or "").strip()
    if not text:
        return False
    if _is_toc_header_block(block):
        return False
    if re.match(r"^[一二三四五六七八九十百千万]+[、.．]", text):
        return False
    if re.match(r"^[0-9０-９]+(?:\s*[.．、]|\s)", text):
        return False
    return True


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
