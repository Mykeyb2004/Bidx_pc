# Fact Card Library Reextract Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make fact card library editing reuse the chapter extraction workspace and allow re-extraction for chapter-derived cards.

**Architecture:** Add a library-edit flavor of the extraction workspace that can either call a chapter extraction callback or operate as manual-edit-only. Keep whole-library persistence safe by updating the current card through the existing full-library draft merge path, with a store helper to preserve source metadata while updating extraction instructions.

**Tech Stack:** Python 3.13, Tkinter/ttk, pytest, uv.

---

### Task 1: Document Behavior

**Files:**
- Create: `docs/superpowers/specs/2026-04-26-fact-card-library-reextract-edit-design.md`
- Create: `docs/superpowers/plans/2026-04-26-fact-card-library-reextract-edit.md`

- [x] **Step 1: Write the approved behavior**

Record that chapter-derived cards may be re-extracted from their source chapter, while manual cards use the same workspace style without re-extraction.

### Task 2: Add Failing Tests

**Files:**
- Modify: `tests/test_fact_card_dialogs.py`
- Modify: `tests/test_fact_cards.py`

- [x] **Step 1: Add GUI orchestration tests**

Add tests proving `_edit_fact_card_from_library()` opens the extraction workspace for a chapter-derived card, passes the saved extraction instruction, and saves only the edited card.

- [x] **Step 2: Add store/source preservation tests**

Add tests proving library-card single updates preserve source metadata and can update `source.extraction_instruction`.

### Task 3: Implement Store Helper

**Files:**
- Modify: `bid_writer/fact_card_store.py`
- Modify: `bid_writer/main.py`

- [x] **Step 1: Add single-card library update helper**

Implement a helper that accepts a `FactCardDraft` and optional source override. It should build the full-library draft set, replace the matching card by ID, preserve other cards, and preserve or override source metadata.

### Task 4: Implement Reextract Editing

**Files:**
- Modify: `bid_writer/fact_card_dialogs.py`
- Modify: `bid_writer/gui.py`

- [x] **Step 1: Add library edit workspace result**

Return the selected draft and extraction instruction from the workspace.

- [x] **Step 2: Open extraction workspace from library edit**

Use source chapter path and saved instruction for chapter-derived cards. Disable re-extraction for manual cards while keeping the same visual structure.

### Task 5: Verify

**Files:**
- No production changes.

- [x] **Step 1: Run focused tests**

Run `uv run pytest tests/test_fact_card_dialogs.py tests/test_fact_cards.py -q`.

- [x] **Step 2: Compile GUI modules**

Run `uv run python -m compileall bid_writer`.
