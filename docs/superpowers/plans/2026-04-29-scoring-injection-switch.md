# Scoring Injection Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `processing.scoring.enabled` so both `auto` and `full_context` can skip the whole scoring-standard chain.

**Architecture:** `Config` exposes one canonical boolean with legacy fallback. `AIWriter` uses it to skip full-context scoring prompt sections, and `ChapterContextPruner` uses it to avoid scoring parsing, retrieval, classification, and cache writes in pruned paths.

**Tech Stack:** Python, YAML configuration, pytest via `uv run`.

---

### Task 1: Configuration Switch

**Files:**
- Modify: `bid_writer/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] Write failing tests for default `true`, canonical `false`, and legacy fallback.
- [ ] Add `Config.processing_scoring_enabled`.
- [ ] Make `context_pruning_scoring_enabled` depend on `processing_scoring_enabled`.
- [ ] Run `uv run pytest tests/test_config_schema.py -q`.

### Task 2: Prompt Behavior

**Files:**
- Modify: `bid_writer/ai_writer.py`
- Modify: `tests/test_prompt_contract.py`

- [ ] Write failing full-context prompt test proving `## 评分标准参考` is omitted when disabled.
- [ ] Gate full-context scoring section construction on `processing_scoring_enabled`.
- [ ] Keep scoring prompt contract block present but empty when no scoring section exists.
- [ ] Run `uv run pytest tests/test_prompt_contract.py -q`.

### Task 3: Auto Retrieval Behavior

**Files:**
- Modify: `bid_writer/context_pruner.py`
- Modify: `tests/test_context_pruner.py`

- [ ] Write failing auto test proving disabled scoring creates no scoring items, no classifier call, and no cache file.
- [ ] Make `auto` return a non-scoring `ChapterContext` before retrieval/classification.
- [ ] Mark retrieval mode as `path=auto;scoring=off`.
- [ ] Run `uv run pytest tests/test_context_pruner.py -q`.

### Task 4: Editor, Docs, Examples

**Files:**
- Modify: `bid_writer/config_editor.py`
- Modify: `bid_writer/config_editor_dialog.py`
- Modify: `bid_writer/config_editor_tooltips.py`
- Modify: `docs/config_schema.md`
- Modify: `config.example.yaml`
- Modify: `config_公共服务满意度_auto.yaml`

- [ ] Preserve `processing.scoring.enabled` through the config editor model and YAML export.
- [ ] Add a checkbox and tooltip in the processing section.
- [ ] Document the switch and examples.
- [ ] Run focused editor/config tests.
