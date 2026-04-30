# New Config UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the new-config flow so normal users prepare project materials first, then edit or generate an outline without seeing engineering-only state controls.

**Architecture:** Keep the existing config schema and outline locking behavior. Adjust only GUI presentation and validation affordances: new config mode hides lock/role internals, outline-file wording becomes a save-location concept, and outline confirmation is enabled only when the editable outline passes validation.

**Tech Stack:** Python 3, Tkinter/ttk, existing config editor and outline preparation dialogs, `uv run pytest`.

---

## File Structure

- Modify `bid_writer/config_editor.py`: change the default new-project outline path to `./投标大纲.md`.
- Modify `bid_writer/config_editor_dialog.py`: conditionally hide outline lock and outline architect role fields in new-config mode, rename the outline file label for new users, and keep advanced fields visible when editing existing configs.
- Modify `bid_writer/outline_prepare_dialog.py`: add a more task-oriented header, track the confirm button, and disable confirmation when outline validation fails.
- Modify `bid_writer/config_editor_tooltips.py`: align the outline tooltip with “save location / existing outline” wording.
- Modify `README.md` and `docs/config_schema.md`: document the simplified flow.
- Update tests in `tests/test_config_editor.py`, `tests/test_config_editor_dialog.py`, and `tests/test_outline_prepare_dialog.py`.

## Task 1: New Config Defaults And Field Presentation

- [ ] Write failing tests for default `./投标大纲.md`, new-config label text, hidden lock/role controls, and existing-config advanced controls.
- [ ] Run those tests and verify the expected failures.
- [ ] Update defaults and dialog presentation.
- [ ] Re-run focused config editor tests.
- [ ] Commit as `feat: simplify new config outline fields`.

## Task 2: Outline Preparation Confirmation State

- [ ] Write failing tests for confirm button state after invalid and valid outline validation.
- [ ] Run those tests and verify the expected failures.
- [ ] Track the confirm button and update its state whenever outline text is loaded, generated, or validated.
- [ ] Re-run focused outline preparation tests.
- [ ] Commit as `feat: guide outline confirmation state`.

## Task 3: Documentation And Final Verification

- [ ] Update README and config schema docs for the simplified user flow.
- [ ] Run the full relevant test set:

```bash
uv run pytest tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_outline_prepare_dialog.py tests/test_gui_new_config.py tests/test_config_schema.py tests/test_outline_generator.py tests/test_outline_prepare.py -q
```

- [ ] Confirm no unintended tracked changes remain.
- [ ] Commit as `docs: document simplified outline setup flow`.
