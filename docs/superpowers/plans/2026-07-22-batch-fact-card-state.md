# Batch Fact Card State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make batch generation show truthful per-chapter fact-card state and require explicit confirmation before uniformly changing selected chapters.

**Architecture:** Add pure aggregation and atomic patch APIs to `FactCardStore`, expose them through `BidWriter`, and place the tri-state editing UI in `fact_card_dialogs.py`. Keep `MainWindow._get_generation_params` responsible only for choosing the single-chapter panel or the batch summary/editor flow.

**Tech Stack:** Python 3.10+, dataclasses, Tkinter/ttk, PyYAML, pytest, uv

---

### Task 1: Aggregate and patch chapter fact-card state

**Files:**
- Modify: `bid_writer/fact_card_store.py`
- Modify: `bid_writer/main.py`
- Test: `tests/test_fact_cards.py`

- [ ] **Step 1: Write failing aggregate-state tests**

Add tests that create one active global and one active local card, then assert a batch summary reports total chapters, enabled-mode count, and effective card reference counts after applying `should_reference` and global exclusion rules.

- [ ] **Step 2: Run aggregate tests and verify RED**

Run: `uv run pytest tests/test_fact_cards.py -k 'batch_chapter_fact_card' -v`

Expected: FAIL because `summarize_chapter_defaults` and the batch summary dataclasses do not exist.

- [ ] **Step 3: Implement pure summary models and logic**

Add immutable summary models and a `summarize_chapter_defaults(chapter_paths)` method. Count a card only when the chapter mode is not explicitly false; count global cards unless explicitly excluded and local cards only when explicitly selected.

- [ ] **Step 4: Run aggregate tests and verify GREEN**

Run: `uv run pytest tests/test_fact_cards.py -k 'batch_chapter_fact_card' -v`

Expected: PASS.

- [ ] **Step 5: Write failing atomic-patch tests**

Test mode keep/enable/disable, global include/exclude, local include/exclude, preservation of untouched selections, ignored inactive IDs, and exactly one `_save_config_payload` call.

- [ ] **Step 6: Run patch tests and verify RED**

Run: `uv run pytest tests/test_fact_cards.py -k 'apply_batch_chapter_defaults' -v`

Expected: FAIL because the atomic patch API does not exist.

- [ ] **Step 7: Implement atomic patch and BidWriter facade**

Implement:

```python
def apply_batch_chapter_defaults(
    self,
    chapter_paths: Iterable[str],
    *,
    should_reference_fact_cards: bool | None = None,
    card_references: dict[str, bool] | None = None,
) -> dict[str, ChapterFactCardDefaultState]:
    ...
```

Load and normalize once, patch all paths in memory, save once, and return normalized states. Expose matching summarize/apply methods from `BidWriter`.

- [ ] **Step 8: Run store tests and verify GREEN**

Run: `uv run pytest tests/test_fact_cards.py -k 'batch_chapter_fact_card or apply_batch_chapter_defaults' -v`

Expected: PASS.

### Task 2: Build tri-state batch configuration UI

**Files:**
- Modify: `bid_writer/fact_card_dialogs.py`
- Test: `tests/test_fact_card_dialogs.py`

- [ ] **Step 1: Write failing pure-dialog-state tests**

Test labels for `0/N`, `N/N`, and mixed `K/N`, plus conversion of tri-state values into `should_reference_fact_cards` and `card_references` patches.

- [ ] **Step 2: Run dialog-state tests and verify RED**

Run: `uv run pytest tests/test_fact_card_dialogs.py -k 'batch_fact_card' -v`

Expected: FAIL because batch summary formatting and patch conversion do not exist.

- [ ] **Step 3: Implement immutable dialog result and pure helpers**

Define `BatchFactCardDialogResult` and helpers using the literals `keep`, `include`, and `exclude`. Ensure default controls produce an empty patch.

- [ ] **Step 4: Run pure-dialog tests and verify GREEN**

Run: `uv run pytest tests/test_fact_card_dialogs.py -k 'batch_fact_card' -v`

Expected: PASS for helper tests.

- [ ] **Step 5: Write failing window behavior tests**

Cover default “保持各章节”, cancel/no-change behavior, confirmation text, callback failure keeping the window open, and successful apply returning a result.

- [ ] **Step 6: Run window tests and verify RED**

Run: `uv run pytest tests/test_fact_card_dialogs.py -k 'batch_fact_card_config_dialog' -v`

Expected: FAIL because `BatchFactCardConfigDialog` does not exist.

- [ ] **Step 7: Implement the independent configuration window**

Create a modal `BatchFactCardConfigDialog` that renders mode and per-card readonly comboboxes, previews explicit changes, confirms before calling its apply callback, and closes only on success.

- [ ] **Step 8: Run dialog tests and verify GREEN**

Run: `uv run pytest tests/test_fact_card_dialogs.py -k 'batch_fact_card' -v`

Expected: PASS.

### Task 3: Integrate truthful batch state into generation parameters

**Files:**
- Modify: `bid_writer/gui.py`
- Test: `tests/test_generation_params_dialog.py`

- [ ] **Step 1: Write failing batch integration tests**

Assert multi-heading mode does not construct `FactCardSelectionPanel`, renders summary text, offers “统一应用到所选章节…”, defaults the transient ignore checkbox to false, and does not save when “开始扩写” is clicked.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `uv run pytest tests/test_generation_params_dialog.py -v`

Expected: FAIL because the current batch branch creates the single-chapter selection panel and save button.

- [ ] **Step 3: Implement batch summary/editor branch**

In `_get_generation_params`, retain the current single-heading path. For multiple headings, load a summary, render read-only rows, add the transient ignore checkbox, and open `BatchFactCardConfigDialog` from the explicit button. Refresh summary after successful application.

- [ ] **Step 4: Preserve the result tuple contract**

Return `fact_card_mode = not ignore_all_fact_cards` in batch mode and `manual_fact_card_selections = None`. Keep single-heading tuple and automatic reference saving unchanged.

- [ ] **Step 5: Run integration tests and verify GREEN**

Run: `uv run pytest tests/test_generation_params_dialog.py -v`

Expected: PASS.

### Task 4: Documentation and regression verification

**Files:**
- Modify: `README.md`
- Modify: `docs/chapter_expansion_mechanism.md`
- Verify: `docs/config_schema.md`

- [ ] **Step 1: Update behavior documentation**

Document read-only mixed-state summaries, transient ignore semantics, explicit tri-state uniform application, preservation of unchanged fields, and single-save atomicity. Do not change the YAML schema documentation because no fields change.

- [ ] **Step 2: Run focused fact-card and GUI tests**

Run: `uv run pytest tests/test_fact_cards.py tests/test_fact_card_dialogs.py tests/test_generation_params_dialog.py -v`

Expected: PASS.

- [ ] **Step 3: Run adjacent GUI regressions**

Run: `uv run pytest tests/test_gui_context_menu.py tests/test_gui_scaling.py tests/test_gui_new_config.py -v`

Expected: PASS.

- [ ] **Step 4: Verify the real 松滋 configuration**

Run a `uv run python -c` check using the production summary API and assert 46 chapters total and 16 effective references to `fact-card-2`.

- [ ] **Step 5: Run GitNexus change detection**

Run `detect_changes(scope="unstaged")`, review all changed symbols and affected flows, and confirm only the planned fact-card batch UI/store paths plus pre-existing unrelated edits are present.
