# Manual Target Editor Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tender import block preview flow with a manual source selection and target editor confirmation flow for “项目采购需求” and “评分标准”.

**Architecture:** Keep the existing conversion, automatic extraction, mandatory confirmation callback, service-owned writes, overwrite confirmation, and backup behavior. Add a pure source-hint model for automatic extraction ranges, refactor the Tk dialog so automatic extraction only highlights and scrolls the source text, and pass a service-owned `save_section` callback so each “存入” action writes the corresponding file immediately.

**Tech Stack:** Python 3.10+, Tkinter/ttk, pytest, existing `bid_writer.tender_import_*` modules, `uv run`.

---

## File Structure

- Modify `bid_writer/tender_selection_model.py`
  - Add `TenderSourceHint`.
  - Add `build_source_hint()` and `source_hint_to_markdown()`.
  - Keep `build_default_selection()` as a compatibility wrapper for existing tests and callers.

- Modify `bid_writer/tender_import_dialog.py`
  - Replace the rendered “块预览” column with a read-only source Markdown column.
  - Add a right-side editable target Markdown editor.
  - Add a `使用选区` button.
  - Change automatic extraction handling from “default final selection” to “source hint only”.
  - Change save logic to read the target editor and call a service-provided per-section save callback.
  - Keep chapter navigation, validation, cancellation, and `ManualTenderConfirmationResult` output.

- Modify `bid_writer/tender_import_service.py`
  - Pass a `save_section` callback into `confirm_sections`.
  - Keep target-file writes, overwrite confirmation, and `.bak` backup in the service layer.
  - Return partial saved paths when the user cancels after saving one section.

- Modify `tests/test_tender_selection_model.py`
  - Cover source hint construction and source hint Markdown extraction.

- Modify `tests/test_tender_import_dialog.py`
  - Update existing dialog expectations from default auto-save to empty target editor.
  - Add tests for `使用选区`, target editor replacement, edited-content save, empty-target blocking, and navigation not modifying the target editor.

- Modify `tests/test_tender_import_service.py`
  - Cover immediate per-section save callback behavior.
  - Add one report-focused assertion proving edited/manual content and `manually_adjusted=True` are serialized through the service.

---

### Task 1: Add Pure Source Hint Helpers

**Files:**
- Modify: `bid_writer/tender_selection_model.py`
- Modify: `tests/test_tender_selection_model.py`

- [ ] **Step 1: Write failing source hint tests**

Append `build_source_hint` and `source_hint_to_markdown` to the import in `tests/test_tender_selection_model.py`:

```python
from bid_writer.tender_selection_model import (
    TenderSelectionDocument,
    build_default_selection,
    build_source_hint,
    selection_to_markdown,
    source_hint_to_markdown,
    validate_selection_markdown,
)
```

Add these tests after `test_build_default_selection_canonicalizes_reversed_block_ids`:

```python
def test_build_source_hint_maps_extraction_without_creating_manual_selection():
    document = _document()
    extraction = TenderExtractionResult(
        section_key="bid_requirements",
        title="项目采购需求",
        markdown="算法原文",
        start_block_id="h1",
        end_block_id="r2",
        confidence=0.9,
    )

    hint = build_source_hint(document, extraction)

    assert hint is not None
    assert hint.section_key == "bid_requirements"
    assert hint.start_block_id == "h1"
    assert hint.end_block_id == "r2"
    assert "项目采购需求" in source_hint_to_markdown(document, hint)
    assert "评分标准" not in source_hint_to_markdown(document, hint)


def test_build_source_hint_returns_none_for_missing_extraction_or_blocks():
    document = _document()
    missing = TenderExtractionResult("bid_requirements", "需求", "", "missing", "r2", 0.1)

    assert build_source_hint(document, None) is None
    assert build_source_hint(document, missing) is None
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_tender_selection_model.py::test_build_source_hint_maps_extraction_without_creating_manual_selection tests/test_tender_selection_model.py::test_build_source_hint_returns_none_for_missing_extraction_or_blocks -q
```

Expected: FAIL with `ImportError` for `build_source_hint`.

- [ ] **Step 3: Implement `TenderSourceHint` and helpers**

In `bid_writer/tender_selection_model.py`, add this dataclass after `TenderSelectionDocument`:

```python
@dataclass(frozen=True)
class TenderSourceHint:
    section_key: str
    start_block_id: str
    end_block_id: str
```

Replace `build_default_selection()` with this implementation and add `build_source_hint()` plus `source_hint_to_markdown()` immediately above `build_default_selection()`:

```python
def build_source_hint(
    document: TenderSelectionDocument,
    extraction: TenderExtractionResult | None,
) -> TenderSourceHint | None:
    if extraction is None:
        return None
    if extraction.start_block_id not in document.block_ranges or extraction.end_block_id not in document.block_ranges:
        return None
    start_block_id, end_block_id = _canonical_block_ids(document, extraction.start_block_id, extraction.end_block_id)
    return TenderSourceHint(
        section_key=extraction.section_key,
        start_block_id=start_block_id,
        end_block_id=end_block_id,
    )


def source_hint_to_markdown(document: TenderSelectionDocument, hint: TenderSourceHint) -> str:
    start_block_id, end_block_id = _canonical_block_ids(document, hint.start_block_id, hint.end_block_id)
    start_range = document.block_ranges.get(start_block_id)
    end_range = document.block_ranges.get(end_block_id)
    if start_range is None or end_range is None:
        return ""
    return document.markdown[start_range.start : end_range.end].strip()


def build_default_selection(
    document: TenderSelectionDocument,
    extraction: TenderExtractionResult | None,
) -> ManualTenderSectionSelection | None:
    hint = build_source_hint(document, extraction)
    if hint is None:
        return None
    markdown = source_hint_to_markdown(document, hint)
    return ManualTenderSectionSelection(
        section_key=hint.section_key,
        markdown=markdown,
        start_block_id=hint.start_block_id,
        end_block_id=hint.end_block_id,
        manually_adjusted=False,
    )
```

- [ ] **Step 4: Run selection model tests**

Run:

```bash
uv run pytest tests/test_tender_selection_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/tender_selection_model.py tests/test_tender_selection_model.py
git commit -m "feat: add tender source hint helpers"
```

Expected: commit succeeds.

---

### Task 2: Change Dialog Initial State to Source Hint Plus Empty Target Editor

**Files:**
- Modify: `bid_writer/tender_import_dialog.py`
- Modify: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Write failing dialog initial-state tests**

In `tests/test_tender_import_dialog.py`, change the import from `bid_writer.tender_selection_model` to include `TenderSourceHint`:

```python
from bid_writer.tender_selection_model import TenderSelectionDocument, TenderSourceHint
```

Replace `test_build_initial_section_selection_uses_extraction_default` with:

```python
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
```

Rename `test_manual_dialog_saves_default_source_selection_without_user_drag` to `test_manual_dialog_starts_with_empty_target_editor_and_source_hint`. Replace its body after dialog creation with:

```python
        assert dialog.target_text.get("1.0", "end-1c") == ""
        assert "项目采购需求" in _selected_text(dialog.source_text)
        assert "服务内容" in _selected_text(dialog.source_text)

        dialog._save_current_section()

        assert dialog.result.cancelled is True
        assert dialog.confirmed == {}
        assert "不能为空" in dialog.status_var.get()
```

- [ ] **Step 2: Run the focused dialog tests and verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_build_initial_section_selection_uses_extraction_as_source_hint_only tests/test_tender_import_dialog.py::test_manual_dialog_starts_with_empty_target_editor_and_source_hint -q
```

Expected: FAIL because `build_initial_section_selection()` still returns `ManualTenderSectionSelection`, and `ManualTenderSectionConfirmDialog` has no `target_text`.

- [ ] **Step 3: Update imports and `build_initial_section_selection()`**

In `bid_writer/tender_import_dialog.py`, replace the `tender_selection_model` import with:

```python
from .tender_selection_model import (
    TenderSelectionDocument,
    TenderSourceHint,
    build_source_hint,
    source_hint_to_markdown,
    validate_selection_markdown,
)
```

Replace `build_initial_section_selection()` with:

```python
def build_initial_section_selection(
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
) -> tuple[TenderSelectionDocument, TenderSourceHint | None, TenderSourceHint | None]:
    document = TenderSelectionDocument.from_blocks(conversion.blocks)
    requirements = build_source_hint(document, extraction.requirements)
    scoring = build_source_hint(document, extraction.scoring)
    return document, requirements, scoring
```

- [ ] **Step 4: Replace dialog state fields**

In `ManualTenderSectionConfirmDialog.__init__()`, replace:

```python
self.document, requirements, scoring = build_initial_section_selection(conversion, extraction)
self.selections: dict[str, ManualTenderSectionSelection | None] = {
    "bid_requirements": requirements,
    "scoring_criteria": scoring,
}
```

with:

```python
self.document, requirements, scoring = build_initial_section_selection(conversion, extraction)
self.source_hints: dict[str, TenderSourceHint | None] = {
    "bid_requirements": requirements,
    "scoring_criteria": scoring,
}
```

- [ ] **Step 5: Replace the control buttons and content widgets**

In `_create_widgets()`, replace the existing `save_button` / `取消` button block and the two content frames from `self.save_button = ...` through the end of `source_text.configure(state="disabled")` with:

```python
self.use_selection_button = ttk.Button(controls, text="使用选区", command=self._use_source_selection)
self.use_selection_button.grid(row=5, column=0, sticky="ew", pady=(14, 3))
self.save_button = ttk.Button(controls, text="", command=self._save_current_section)
self.save_button.grid(row=6, column=0, sticky="ew", pady=3)
ttk.Button(controls, text="取消", command=self._cancel).grid(row=7, column=0, sticky="ew", pady=3)

source_frame = ttk.Frame(self, padding=(0, 12, 6, 12))
source_frame.grid(row=0, column=1, sticky="nsew")
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
self.source_text.tag_configure("source_hint", background="#fff2b8")
self.source_text.tag_configure("current_selection", background="#cfe8ff")
self.source_text.configure(state="disabled")

target_frame = ttk.Frame(self, padding=(6, 12, 12, 12))
target_frame.grid(row=0, column=2, sticky="nsew")
target_frame.columnconfigure(0, weight=1)
target_frame.rowconfigure(1, weight=1)
ttk.Label(target_frame, text="目标编辑框").grid(row=0, column=0, sticky="w")
self.target_text = tk.Text(target_frame, wrap="word", undo=True, borderwidth=1, relief="solid")
target_scroll = ttk.Scrollbar(target_frame, orient="vertical", command=self.target_text.yview)
self.target_text.configure(yscrollcommand=target_scroll.set)
self.target_text.grid(row=1, column=0, sticky="nsew")
target_scroll.grid(row=1, column=1, sticky="ns")
```

Remove `_configure_rendered_tags()`, `_render_blocks()`, and `_current_selected_block_ids()` from the class.

- [ ] **Step 6: Replace current-section loading and source hint application**

Replace `_load_current_section()` with:

```python
def _load_current_section(self) -> None:
    section_key = self._current_section_key()
    label = SECTION_LABELS[section_key]
    self.step_label.configure(text=f"{self.current_index + 1}/2：{label}")
    self.save_button.configure(text="存入项目需求" if section_key == "bid_requirements" else "存入评分标准")
    self._clear_target_editor()
    self._apply_source_hint(self.source_hints[section_key])
    self._update_status()
```

Add these helper methods where `_apply_source_selection()` currently lives:

```python
def _clear_target_editor(self) -> None:
    self.target_text.delete("1.0", "end")


def _apply_source_hint(self, hint: TenderSourceHint | None) -> None:
    self.source_text.configure(state="normal")
    self.source_text.tag_remove("source_hint", "1.0", "end")
    self.source_text.tag_remove("sel", "1.0", "end")
    self._applied_source_selection_range = None
    if hint is None:
        self.source_text.see("1.0")
        self.source_text.configure(state="disabled")
        return
    range_start, range_end = self._hint_char_range(hint)
    if range_start is None or range_end is None:
        self.source_text.configure(state="disabled")
        return
    start_index = f"1.0+{range_start}c"
    end_index = f"1.0+{range_end}c"
    self.source_text.tag_add("source_hint", start_index, end_index)
    self.source_text.tag_add("sel", start_index, end_index)
    self.source_text.mark_set("insert", start_index)
    self.source_text.see(start_index)
    self._applied_source_selection_range = (range_start, range_end)
    self.source_text.configure(state="disabled")


def _hint_char_range(self, hint: TenderSourceHint) -> tuple[int | None, int | None]:
    start_range = self.document.block_ranges.get(hint.start_block_id)
    end_range = self.document.block_ranges.get(hint.end_block_id)
    if start_range is None or end_range is None:
        return None, None
    return min(start_range.start, end_range.start), max(start_range.end, end_range.end)
```

Remove `_apply_source_selection()` and `_selection_char_range()`.

- [ ] **Step 7: Update status text**

Replace `build_confirmation_status()` with:

```python
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
```

Replace `_update_status()` with:

```python
def _update_status(self, warnings: list[str] | None = None) -> None:
    section_key = self._current_section_key()
    self.status_var.set(build_confirmation_status(section_key, self.source_hints[section_key], warnings or []))
```

Update `test_build_confirmation_status_includes_warnings()` to use `TenderSourceHint`:

```python
def test_build_confirmation_status_includes_warnings():
    hint = TenderSourceHint("scoring_criteria", "s0", "s1")
    status = build_confirmation_status("scoring_criteria", hint, ["当前内容可能不是评分标准，请确认。"])

    assert "评分标准" in status
    assert "已跳到疑似章节" in status
    assert "可能不是评分标准" in status
```

- [ ] **Step 8: Run focused dialog tests**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_build_initial_section_selection_uses_extraction_as_source_hint_only tests/test_tender_import_dialog.py::test_manual_dialog_starts_with_empty_target_editor_and_source_hint tests/test_tender_import_dialog.py::test_build_confirmation_status_mentions_missing_auto_location tests/test_tender_import_dialog.py::test_build_confirmation_status_includes_warnings -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add bid_writer/tender_import_dialog.py tests/test_tender_import_dialog.py
git commit -m "feat: initialize tender confirmation target editor"
```

Expected: commit succeeds.

---

### Task 3: Implement `使用选区` and Target-Editor Save Semantics

**Files:**
- Modify: `bid_writer/tender_import_dialog.py`
- Modify: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Write failing target editor behavior tests**

Add these tests after `test_manual_dialog_starts_with_empty_target_editor_and_source_hint`:

```python
def test_manual_dialog_use_selection_replaces_target_editor():
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

        dialog._use_source_selection()

        assert "项目采购需求" in dialog.target_text.get("1.0", "end-1c")
        assert "服务内容" in dialog.target_text.get("1.0", "end-1c")

        dialog._apply_source_char_selection(0, len("## 项目采购需求"))
        dialog._use_source_selection()

        assert dialog.target_text.get("1.0", "end-1c") == "## 项目采购需求"
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

        dialog._use_source_selection()
        dialog.target_text.insert("end", "\n\n人工补充说明。")
        dialog._save_current_section()
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
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_manual_dialog_use_selection_replaces_target_editor tests/test_tender_import_dialog.py::test_manual_dialog_saves_edited_target_editor_content -q
```

Expected: FAIL because `ManualTenderSectionConfirmDialog.__init__()` does not accept `save_section`, `_use_source_selection()` does not exist, and `_save_current_section()` still reads the source selection.

- [ ] **Step 3: Add save callback plumbing and target editor helpers**

In `bid_writer/tender_import_dialog.py`, add this import near the top:

```python
from collections.abc import Callable
```

Change the dialog constructor signature from:

```python
def __init__(
    self,
    parent,
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
) -> None:
```

to:

```python
def __init__(
    self,
    parent,
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
    *,
    save_section: Callable[[ManualTenderSectionSelection], None] | None = None,
) -> None:
```

After `self.result = ManualTenderConfirmationResult(cancelled=True)`, add:

```python
self.save_section = save_section
```

In `ManualTenderSectionConfirmDialog`, add these methods before `_save_current_section()`:

```python
def _use_source_selection(self) -> None:
    selected = self._current_source_selection()
    if not selected:
        messagebox.showinfo("需要手动选择", "请先在源文区选择文本。", parent=self)
        return
    self.target_text.delete("1.0", "end")
    self.target_text.insert("1.0", selected)
    self.target_text.focus_set()
    self._update_status()


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
```

Replace `confirm_tender_sections()` with:

```python
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
```

- [ ] **Step 4: Replace save source logic**

Replace `_save_current_section()` with:

```python
def _save_current_section(self) -> None:
    section_key = self._current_section_key()
    markdown = self._target_editor_markdown()
    warnings = validate_selection_markdown(section_key, markdown)
    blocking = [warning for warning in warnings if "不能为空" in warning]
    if blocking:
        self._update_status(blocking)
        messagebox.showwarning("选区不能为空", blocking[0], parent=self)
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
```

Remove `_selection_for_save()` and `_source_selection_changed()` from the class.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_manual_dialog_use_selection_replaces_target_editor tests/test_tender_import_dialog.py::test_manual_dialog_saves_edited_target_editor_content tests/test_tender_import_dialog.py::test_manual_dialog_starts_with_empty_target_editor_and_source_hint -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/tender_import_dialog.py tests/test_tender_import_dialog.py
git commit -m "feat: save tender confirmation target editor content"
```

Expected: commit succeeds.

---

### Task 4: Keep Chapter Navigation Source-Only

**Files:**
- Modify: `bid_writer/tender_import_dialog.py`
- Modify: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Update navigation test expectations**

In `test_manual_dialog_chapter_buttons_move_source_selection_by_detected_boundaries()`, replace the assertions after `dialog._move_next()`:

```python
        assert _selected_text(dialog.source_text).lstrip().startswith("## 第二章 评分标准")
        assert "10分" in _selected_text(dialog.source_text)
        assert "第三章 合同条款" not in _selected_text(dialog.source_text)
        assert dialog.target_text.get("1.0", "end-1c") == ""
```

Keep the existing assertions after `dialog._move_previous()` and add:

```python
        assert dialog.target_text.get("1.0", "end-1c") == ""
```

Add this test after it:

```python
def test_manual_dialog_navigation_does_not_overwrite_existing_target_editor():
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        extraction = TenderSectionExtraction(
            requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r3", 0.91),
            scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
        )
        dialog = ManualTenderSectionConfirmDialog(root, _uneven_chapter_conversion(), extraction)
        dialog.target_text.insert("1.0", "用户已经整理好的目标内容")

        dialog._move_next()

        assert dialog.target_text.get("1.0", "end-1c") == "用户已经整理好的目标内容"
        assert _selected_text(dialog.source_text).lstrip().startswith("## 第二章 评分标准")
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        root.destroy()
```

- [ ] **Step 2: Run focused navigation tests and verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_manual_dialog_chapter_buttons_move_source_selection_by_detected_boundaries tests/test_tender_import_dialog.py::test_manual_dialog_navigation_does_not_overwrite_existing_target_editor -q
```

Expected: FAIL because `_move_current()` still writes to `self.selections` and calls `_render_blocks()`.

- [ ] **Step 3: Simplify `_move_current()` to source-only behavior**

Replace `_move_current()` with:

```python
def _move_current(self, *, previous: bool) -> None:
    char_range = self._current_source_char_range()
    target = self._adjacent_navigation_range(char_range, previous=previous)
    if target is not None:
        self._apply_source_char_selection(target.start, target.end)
        self._update_status()
        return

    line_range = self._current_source_line_range()
    if line_range is None:
        messagebox.showinfo("需要手动选择", "请先在源文区选择文本。", parent=self)
        return
    start_line, end_line = line_range
    line_count = end_line - start_line + 1
    total_lines = self._source_text_line_count()
    target_start = start_line - line_count if previous else start_line + line_count
    target_end = target_start + line_count - 1
    if target_start < 1 or target_end > total_lines:
        return

    self._apply_source_line_selection(target_start, target_end)
    self._update_status()
```

- [ ] **Step 4: Run navigation tests**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py::test_manual_dialog_chapter_buttons_move_source_selection_by_detected_boundaries tests/test_tender_import_dialog.py::test_manual_dialog_navigation_does_not_overwrite_existing_target_editor -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/tender_import_dialog.py tests/test_tender_import_dialog.py
git commit -m "fix: keep tender chapter navigation source only"
```

Expected: commit succeeds.

---

### Task 5: Add Immediate Per-Section Service Save Callback

**Files:**
- Modify: `bid_writer/tender_import_service.py`
- Modify: `tests/test_tender_import_service.py`

- [ ] **Step 1: Write failing partial-save service test**

Add this test after `test_import_service_stops_when_manual_confirmation_cancelled()`:

```python
def test_import_service_keeps_section_saved_before_manual_confirmation_cancel(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "算法需求", "r1", "r2", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "算法评分", "s1", "s2", 0.90),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    def confirm_sections(**kwargs):
        selection = ManualTenderSectionSelection(
            "bid_requirements",
            "# 项目采购需求\n\n已经存入的需求",
            None,
            None,
            manually_adjusted=True,
        )
        kwargs["save_section"](selection)
        return ManualTenderConfirmationResult(requirements=selection, scoring=None, cancelled=True)

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_sections=confirm_sections,
    )

    requirements_path = tmp_path / "项目要求" / "项目采购需求.md"
    scoring_path = tmp_path / "项目要求" / "评分标准.md"
    assert result.cancelled is True
    assert result.requirements_path == requirements_path
    assert result.scoring_path is None
    assert requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n已经存入的需求"
    assert not scoring_path.exists()
    assert requirements_path in result.created_paths
```

- [ ] **Step 2: Run the focused service test and verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_import_service_keeps_section_saved_before_manual_confirmation_cancel -q
```

Expected: FAIL with `KeyError: 'save_section'` because `TenderImportService.import_document()` does not pass the callback yet.

- [ ] **Step 3: Add saved-target tracking helpers in `import_document()`**

In `bid_writer/tender_import_service.py`, add `ManualTenderSectionSelection` to the import from `.tender_import_models`:

```python
from .tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderSectionExtraction,
    dump_extraction_report,
)
```

In `bid_writer/tender_import_service.py`, after `requirements_path` and `scoring_path` are defined, add:

```python
        saved_targets: dict[str, Path] = {}
        backup_paths: list[Path] = []

        def save_section(selection: ManualTenderSectionSelection) -> None:
            if selection.section_key == "bid_requirements":
                target_path = requirements_path
            elif selection.section_key == "scoring_criteria":
                target_path = scoring_path
            else:
                raise TenderImportError(f"未知资料类型：{selection.section_key}")
            target_dir.mkdir(parents=True, exist_ok=True)
            backup_path = self._plan_target_write(target_path, confirm_overwrite)
            written_backup = self._write_planned_target(target_path, selection.markdown, backup_path)
            saved_targets[selection.section_key] = target_path
            if written_backup is not None:
                backup_paths.append(written_backup)
```

Update the `confirm_sections()` call to pass this callback:

```python
        confirmation = confirm_sections(
            conversion=conversion,
            extraction=extraction,
            requirements_path=requirements_path,
            scoring_path=scoring_path,
            save_section=save_section,
        )
```

- [ ] **Step 4: Preserve existing complete-result fallback writes**

Replace the current cancellation block and the target-file writing block after the final report write with:

```python
        if confirmation.cancelled or confirmation.requirements is None or confirmation.scoring is None:
            return TenderImportResult(
                requirements_path=saved_targets.get("bid_requirements"),
                scoring_path=saved_targets.get("scoring_criteria"),
                relative_requirements_path="./项目要求/项目采购需求.md",
                relative_scoring_path="./项目要求/评分标准.md",
                import_dir=import_dir,
                extraction_report_path=report_path,
                extraction=extraction,
                cancelled=True,
                created_paths=(
                    *self._conversion_created_paths(conversion, import_dir),
                    report_path,
                    *backup_paths,
                    *saved_targets.values(),
                ),
            )

        missing_requirements = "bid_requirements" not in saved_targets
        missing_scoring = "scoring_criteria" not in saved_targets
        target_dir.mkdir(parents=True, exist_ok=True)
        if missing_requirements and missing_scoring:
            requirements_backup = self._plan_target_write(requirements_path, confirm_overwrite)
            scoring_backup = self._plan_target_write(scoring_path, confirm_overwrite)
            requirements_written_backup = self._write_planned_target(
                requirements_path,
                confirmation.requirements.markdown,
                requirements_backup,
            )
            scoring_written_backup = self._write_planned_target(
                scoring_path,
                confirmation.scoring.markdown,
                scoring_backup,
            )
            saved_targets["bid_requirements"] = requirements_path
            saved_targets["scoring_criteria"] = scoring_path
            backup_paths.extend(
                path for path in (requirements_written_backup, scoring_written_backup) if path is not None
            )
        else:
            if missing_requirements:
                save_section(confirmation.requirements)
            if missing_scoring:
                save_section(confirmation.scoring)
```

In the final successful `TenderImportResult`, set `created_paths` to:

```python
                created_paths=(
                    *self._conversion_created_paths(conversion, import_dir),
                    report_path,
                    *backup_paths,
                    requirements_path,
                    scoring_path,
                ),
```

Keep `requirements_path=requirements_path`, `scoring_path=scoring_path`, and `cancelled=False` in that final result.

- [ ] **Step 5: Run service tests affected by save timing**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_import_service_keeps_section_saved_before_manual_confirmation_cancel tests/test_tender_import_service.py::test_import_service_confirms_all_overwrites_before_writing_targets tests/test_tender_import_service.py::test_import_service_writes_outputs_and_report -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/tender_import_service.py tests/test_tender_import_service.py
git commit -m "feat: save tender sections during confirmation"
```

Expected: commit succeeds.

---

### Task 6: Verify Service Reporting for Edited Manual Content

**Files:**
- Modify: `tests/test_tender_import_service.py`

- [ ] **Step 1: Add a service report assertion test**

Add this test after `test_import_service_writes_outputs_and_report()`:

```python
def test_import_service_report_records_edited_manual_confirmation(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type(
        "Conversion",
        (),
        {
            "source_path": source,
            "output_dir": tmp_path / ".bid_writer" / "imports" / "import-test",
            "converted_markdown_path": tmp_path / ".bid_writer" / "imports" / "import-test" / "converted.md",
            "conversion_map_path": tmp_path / ".bid_writer" / "imports" / "import-test" / "conversion_map.json",
            "blocks": [],
            "warnings": (),
        },
    )()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "算法需求", "r1", "r2", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "算法评分", "s1", "s2", 0.90),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(
            requirements=ManualTenderSectionSelection(
                "bid_requirements",
                "# 项目采购需求\n\n编辑后的需求",
                None,
                None,
                manually_adjusted=True,
            ),
            scoring=ManualTenderSectionSelection(
                "scoring_criteria",
                "# 评分标准\n\n编辑后的评分",
                None,
                None,
                manually_adjusted=True,
            ),
        ),
    )

    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["manual_confirmation"]["requirements"]["markdown"] == "# 项目采购需求\n\n编辑后的需求"
    assert report["manual_confirmation"]["requirements"]["manually_adjusted"] is True
    assert report["manual_confirmation"]["requirements"]["start_block_id"] is None
    assert report["manual_confirmation"]["scoring"]["markdown"] == "# 评分标准\n\n编辑后的评分"
    assert report["manual_confirmation"]["scoring"]["manually_adjusted"] is True
```

- [ ] **Step 2: Run the focused service test**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_import_service_report_records_edited_manual_confirmation -q
```

Expected: PASS. This behavior is already supported by the service; the test locks the contract.

- [ ] **Step 3: Commit**

Run:

```bash
git add tests/test_tender_import_service.py
git commit -m "test: cover edited tender confirmation report"
```

Expected: commit succeeds.

---

### Task 7: Full Regression and Cleanup

**Files:**
- Modify only if a test reveals a real defect in files touched by Tasks 1-6.

- [ ] **Step 1: Run focused tender import tests**

Run:

```bash
uv run pytest tests/test_tender_selection_model.py tests/test_tender_import_dialog.py tests/test_tender_import_service.py -q
```

Expected: PASS, or Tk-dependent tests SKIP only when Tk is unavailable.

- [ ] **Step 2: Run broader relevant tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_config_editor_tender_import.py tests/test_tender_import_models.py -q
```

Expected: PASS, or Tk-dependent tests SKIP only when Tk is unavailable.

- [ ] **Step 3: Scan for stale block preview user-facing text**

Run:

```bash
rg -n "块预览|已根据自动定位默认选中|源码区选择文本|选区不能为空" bid_writer tests docs/superpowers/specs/2026-05-01-manual-target-editor-confirmation-design.md
```

Expected:

- No `块预览` match in `bid_writer/tender_import_dialog.py`.
- No `已根据自动定位默认选中` match in `bid_writer/tender_import_dialog.py`.
- `选区不能为空` may remain as an existing validation message if the UI still uses that title.
- The design spec may still mention `块预览` as historical context and acceptance criteria.

- [ ] **Step 4: Run final status check**

Run:

```bash
git status --short
```

Expected: clean worktree.

- [ ] **Step 5: Commit any cleanup fix**

If Step 1, Step 2, or Step 3 required a code or test fix, run:

```bash
git add bid_writer tests
git commit -m "chore: finalize tender target editor confirmation"
```

Expected: commit succeeds. If no files changed after Step 4, skip this commit.

---

## Self-Review

- Spec coverage: the plan covers source-only automatic hints, removal of the block preview entry point, empty target editor startup, `使用选区` replacement behavior, target-editor-only saving, chapter navigation that does not edit the target, immediate per-step service writes through `save_section`, service report serialization, and validation behavior.
- Scope: the plan does not rewrite extraction algorithms, original PDF/Word preview, generation flow, config schema, or file saver behavior.
- Type consistency: `TenderSourceHint` is only used for source hints; `ManualTenderSectionSelection` remains the serialized final confirmation result.
