# Fact Card Library List Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Convert the fact card library window into a list-only browser with new/edit actions that open a reusable single-card editor dialog.

**Architecture:** Keep `FactCardStore.save_library_cards()` unchanged and orchestrate create/edit from the GUI by submitting the complete library draft list. Refactor `ManualFactCardDialog` to accept optional initial draft/title text, and refactor `FactCardLibraryDialog` so it returns an action result instead of an edited full-library draft list.

**Tech Stack:** Python 3.13, Tkinter/ttk, pytest, uv.

---

### Task 1: Document Approved Behavior

**Files:**
- Create: `docs/superpowers/specs/2026-04-26-fact-card-library-list-edit-design.md`
- Create: `docs/superpowers/plans/2026-04-26-fact-card-library-list-edit.md`

- [x] **Step 1: Save the design and plan documents**

Write the approved behavior into the spec and this implementation plan.

- [x] **Step 2: Review for ambiguity**

Confirm the documents state that only `name`, `category`, `scope`, `enforcement`, and `content` are editable, while source metadata is preserved.

### Task 2: Add Dialog Unit Tests

**Files:**
- Modify: `tests/test_fact_card_dialogs.py`

- [x] **Step 1: Write failing tests**

Add tests for:

```python
def test_manual_fact_card_dialog_accepts_initial_draft_for_editing():
    initial = FactCardDraft(
        card_id="extract-a",
        name="服务承诺",
        content="7x24小时响应",
        category="承诺",
        scope="local",
        enforcement="reference",
    )

    assert fact_card_dialogs.ManualFactCardDialog._initial_drafts(initial)[0] == initial
```

```python
def test_fact_card_library_dialog_builds_edit_action_from_selected_card():
    card = FactCard(
        id="card-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        scope="global",
        enforcement="strong",
        source=FactCardSource(type="manual"),
    )
    dialog = fact_card_dialogs.FactCardLibraryDialog.__new__(fact_card_dialogs.FactCardLibraryDialog)
    dialog.cards = [card]
    dialog.tree = SimpleNamespace(selection=lambda: ("card-a",))

    dialog._on_edit()

    assert dialog.result == fact_card_dialogs.FactCardLibraryDialogResult(action="edit", card=card)
```

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_fact_card_dialogs.py::test_manual_fact_card_dialog_accepts_initial_draft_for_editing tests/test_fact_card_dialogs.py::test_fact_card_library_dialog_builds_edit_action_from_selected_card -q`

Expected: FAIL because the new helper/result type does not exist yet.

### Task 3: Refactor Dialogs

**Files:**
- Modify: `bid_writer/fact_card_dialogs.py`

- [x] **Step 1: Implement reusable single-card dialog inputs**

Update `ManualFactCardDialog.__init__` to accept optional `initial_draft`, `title`, `heading_text`, and `description`. Add `_initial_drafts(initial_draft)` that returns the passed draft when editing, otherwise returns the blank default draft.

- [x] **Step 2: Add library dialog result type**

Add:

```python
@dataclass(frozen=True)
class FactCardLibraryDialogResult:
    action: str
    card: FactCard | None = None
```

- [x] **Step 3: Make library dialog list-only**

Remove the embedded `FactCardDraftEditor` and “保存卡片库” button. Store the tree as `self.tree`, insert rows with `iid=card.id`, bind `<Double-1>` to edit, and add buttons “新建卡片”“编辑卡片”“关闭”.

- [x] **Step 4: Run dialog tests**

Run: `uv run pytest tests/test_fact_card_dialogs.py -q`

Expected: PASS.

### Task 4: Update Main Window Orchestration

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_fact_card_dialogs.py`

- [x] **Step 1: Write failing main-window tests**

Add tests for editing an existing card and creating a new card from the library action. Each test should assert that `save_fact_card_library()` receives all existing cards, with only the target card changed or a new draft appended.

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_fact_card_dialogs.py::test_mainwindow_fact_card_library_edit_preserves_other_cards_and_source tests/test_fact_card_dialogs.py::test_mainwindow_fact_card_library_new_appends_to_library -q`

Expected: FAIL because `open_fact_card_library_dialog()` still expects full-library drafts from the library dialog.

- [x] **Step 3: Implement action handling**

Update `MainWindow.open_fact_card_library_dialog()` to:

1. Open the list-only library dialog in a loop.
2. On `new`, call `open_manual_fact_card_dialog()`.
3. On `edit`, open `ManualFactCardDialog` with the selected card converted through `FactCardLibraryDialog._build_library_drafts([card])[0]`.
4. Save by replacing the matching full-library draft and calling `save_fact_card_library()`.
5. Reopen or refresh the list so repeated edits see current data.

- [x] **Step 4: Run main-window tests**

Run: `uv run pytest tests/test_fact_card_dialogs.py -q`

Expected: PASS.

### Task 5: Verification

**Files:**
- No code changes.

- [x] **Step 1: Run targeted tests**

Run: `uv run pytest tests/test_fact_card_dialogs.py tests/test_fact_cards.py -q`

Expected: PASS.

- [x] **Step 2: Check git diff**

Run: `git diff --stat`

Expected: Changes are limited to fact card dialog/gui tests, dialog/gui implementation, and the two docs.
