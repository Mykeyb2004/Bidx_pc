# New Config Wizard UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the new-config wizard feel like a clear two-path workflow, with better step names, clearer prompts, more visible progress state, and less crowded layout.

**Architecture:** Keep the change focused inside `bid_writer/new_config_wizard.py` and its tests. Add small UI helper methods for the source-path branch cards, sidebar step-state labels, and summary copy so the widget logic stays testable without a live Tk root. Do not touch config schema, tender import behavior, or the main window flow.

**Tech Stack:** Python 3, Tkinter/ttk, pytest, `uv run`.

---

## File Structure

- Modify `bid_writer/new_config_wizard.py`
  - Update step titles and explanatory copy.
  - Rework the first step into an explicit choice between import and manual creation.
  - Add visible current/completed state in the sidebar.
  - Tighten the review summary and outline-source hint text.
- Modify `tests/test_new_config_wizard.py`
  - Lock the new step labels, sidebar state labels, source-branch wording, and summary text.
- Modify `tests/test_gui_new_config.py` only if the changed step titles or wizard copy affects existing GUI assumptions.

## Task 1: Write Failing UX Tests

**Files:**
- Modify: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Add tests for the new wizard vocabulary and sidebar state**

Add tests that assert the wizard now communicates the flow in user-facing language:

```python
def test_wizard_steps_use_user_facing_titles():
    assert [step.title for step in WIZARD_STEPS] == [
        "选择起点",
        "项目位置",
        "资料整理",
        "基础设置",
        "保存确认",
    ]


def test_sync_footer_shows_sidebar_step_state(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2
    dialog.max_completed_step_index = 3

    NewConfigWizardDialog._sync_footer(dialog)

    assert [var.get() for var in dialog.step_state_vars] == [
        "已完成",
        "已完成",
        "当前",
        "已完成",
        "未开始",
    ]
```

Add tests for the first-step branch copy and the tightened review summary:

```python
def test_source_hint_mentions_manual_creation_when_no_tender_selected(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["source_path"].set("")
    dialog.state.source_path = None
    dialog.state.manual_inputs = True

    NewConfigWizardDialog._sync_source_hint(dialog)

    assert "手动创建" in dialog.source_hint_var.get()


def test_review_summary_mentions_outline_source_and_output_dir(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["outline_source"].set("existing")
    dialog.state.output_dir = tmp_path / "results"

    NewConfigWizardDialog._sync_review_summary(dialog)

    assert "大纲来源：已有 Markdown 大纲" in dialog.review_summary_var.get()
    assert f"输出目录：{tmp_path / 'results'}" in dialog.review_summary_var.get()
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: FAIL until the new labels, sidebar state variables, and copy updates are implemented.

## Task 2: Implement The Wizard Polish

**Files:**
- Modify: `bid_writer/new_config_wizard.py`

- [ ] **Step 1: Update the step model and first-step layout**

Implement the new step names and the source-selection branch cards:

```python
WIZARD_STEPS = [
    WizardStep("source", "选择起点"),
    WizardStep("location", "项目位置"),
    WizardStep("materials", "资料整理"),
    WizardStep("basics", "基础设置"),
    WizardStep("review", "保存确认"),
]
```

Make `_build_source_step()` render two clear choices:

```python
import_card = ttk.Labelframe(choice_row, text="从招标文件开始", padding=(12, 10))
manual_card = ttk.Labelframe(choice_row, text="直接手动创建", padding=(12, 10))
```

Keep the existing selection handlers, but rewrite the button text and helper copy so the user can immediately tell which path they are choosing.

- [ ] **Step 2: Make sidebar progress visible**

Add a `StringVar` per step and update `_sync_footer()` so the sidebar shows `已完成 / 当前 / 未开始` next to each step button.

- [ ] **Step 3: Tighten the remaining step copy**

Rephrase the descriptions for the location, materials, basics, and review steps so they describe what the user is actually doing, not internal state. Group the basics step into clearer sections so the outline choice and output path are visually separated from the bidder name field.

- [ ] **Step 4: Refine hint and summary text**

Update `_sync_source_hint()`, `_sync_outline_source_ui()`, and `_sync_review_summary()` so they mention the manual fallback, the selected outline mode, and the final output directory more plainly.

- [ ] **Step 5: Run the implementation tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS.

## Task 3: Broaden Verification

**Files:**
- Modify only if needed: `tests/test_gui_new_config.py`

- [ ] **Step 1: Run the wizard and GUI tests together**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_gui_new_config.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py tests/test_gui_new_config.py docs/superpowers/plans/2026-05-02-new-config-wizard-ux.md
git commit -m "feat: polish new config wizard ux"
```

Expected: commit succeeds.
