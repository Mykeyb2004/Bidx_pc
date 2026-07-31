# Generation Failure Workspace State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep chapter generation failures visible after the modal closes and the outline tree redraws.

**Architecture:** Store an in-memory immutable failure snapshot per chapter. Render the workspace from explicit generation, failure, saved-file, or empty state, and clear failures only at defined lifecycle boundaries.

**Tech Stack:** Python 3, Tkinter, pytest, uv, GitNexus

---

### Task 1: Lock The Regression With Tests

**Files:**
- Modify: `tests/test_gui_context_menu.py`
- Modify: `tests/test_gui_scaling.py`

- [x] Add a test that reports a failure, simulates modal close and a later chapter preview, and expects the same failure body.
- [x] Add a test that switches away and previews the failed chapter again.
- [x] Assert that the rendered character count is computed from partial正文 only.
- [x] Run `uv run pytest tests/test_gui_context_menu.py tests/test_gui_scaling.py -q` and confirm the new tests fail because no failure snapshot exists.

Expected state shape used by the tests:

```python
gui.WorkspaceGenerationFailureState(
    feedback=feedback,
    partial_content="已返回正文",
)
```

### Task 2: Implement Failure Snapshot Rendering

**Files:**
- Modify: `bid_writer/gui.py`

- [x] Add `WorkspaceGenerationFailureState` beside `GenerationErrorFeedback`.
- [x] Initialize `self._workspace_generation_failures` in `MainWindow.__init__`.
- [x] Store the snapshot in `_report_generation_failure` before `messagebox.showerror`.
- [x] Make `_show_generation_failure_in_workspace` render `partial_content + diagnostics` deterministically and count only partial正文.
- [x] Make `_show_heading_preview_in_workspace` restore failure state before checking saved files.
- [x] Run the focused preview and report tests and confirm they pass.

Core rendering behavior:

```python
failure_state = self._workspace_generation_failures.get(heading.full_path)
if failure_state is not None:
    self._show_generation_failure_in_workspace(
        heading,
        failure_state.feedback,
        partial_content=failure_state.partial_content,
    )
    return
```

### Task 3: Implement Retry And Partial-Output Lifecycle

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_gui_context_menu.py`

- [x] Add a failing test that constructs a new `GenerationSession` over an existing failure and expects the old snapshot to be removed.
- [x] Add a failing test where non-streaming generation yields one chunk and then raises; expect the chapter buffer to retain that chunk.
- [x] Clear the same chapter's failure in `GenerationSession.__init__`.
- [x] In non-streaming mode, enqueue accumulated partial正文 before the error feedback event.
- [x] Run the two focused tests and confirm RED then GREEN.

### Task 4: Isolate Config And Outline Lifecycles

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_gui_new_config.py`
- Modify: `tests/test_gui_context_menu.py`

- [x] Add a failing assertion that successful config switching clears `_workspace_generation_failures`.
- [x] Add a failing test that successful explicit outline reload clears failures and refreshes the selected preview.
- [x] Clear the map only after config or outline loading succeeds.
- [x] Re-render the selected chapter after an explicit outline reload clears the state.
- [x] Run the focused lifecycle tests and confirm RED then GREEN.

### Task 5: Verification And Scope Review

**Files:**
- Review: `bid_writer/gui.py`
- Review: `tests/test_gui_context_menu.py`
- Review: `tests/test_gui_scaling.py`
- Review: `tests/test_gui_new_config.py`

- [x] Run `uv run pytest tests/test_gui_context_menu.py tests/test_gui_scaling.py tests/test_gui_new_config.py -q`.
- [x] Run the broader GUI test group discovered from `tests/test_gui*.py`.
- [x] Run `git diff --check`.
- [x] Run GitNexus `detect_changes(scope="all")` and confirm only expected GUI flows are affected.
- [x] Review the final diff without reverting unrelated user changes.

GitNexus reports the aggregate dirty worktree as `CRITICAL` because it also contains
pre-existing configuration and responsive-layout edits. The symbols introduced or
modified for this fix affect the expected chapter preview/selection, generation
session, and configuration-switching flows.

No commit step is included because the existing worktree contains unrelated user modifications and the user requested an implementation, not a commit.
