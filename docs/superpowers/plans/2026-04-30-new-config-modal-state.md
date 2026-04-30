# New Config Modal State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent users from accidentally operating the old project while the new-config workflow is open or incomplete.

**Architecture:** Keep the old project loaded until a new config is fully accepted. Add a lightweight modal-workflow flag in `MainWindow` that reuses existing action-state synchronization to disable old-project actions, then restore those actions when the modal workflow closes.

**Tech Stack:** Python 3, Tkinter/ttk, existing GUI tests, `uv run pytest`.

---

## Tasks

- [x] Add tests showing old-project buttons, menus, search, and filters are disabled while `is_modal_workflow_active` is true.
- [x] Add tests showing `open_new_config_editor()` enters the modal workflow state and restores it after the dialog closes.
- [x] Add tests showing cancelled new-config and cancelled outline-preparation flows keep the old config active with explicit status text.
- [x] Implement `MainWindow.is_modal_workflow_active` and `_set_modal_workflow_active()`.
- [x] Wire the flag into `update_action_states()`.
- [x] Wrap `open_new_config_editor()` in modal workflow state handling.
- [x] Run GUI-focused regressions.
