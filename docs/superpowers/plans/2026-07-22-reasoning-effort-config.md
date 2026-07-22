# Reasoning Effort Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional reasoning-effort controls for chapter and outline generation through environment variables while preserving compatibility when unset.

**Architecture:** `Config` reads independently validated optional reasoning levels from `BID_WRITER_REASONING_EFFORT` and the outline-specific variable. The two primary Chat Completions request builders add `reasoning_effort` only when their respective setting is configured; generation traces record the same non-sensitive value.

**Tech Stack:** Python, `openai` Chat Completions API, pytest, uv.

---

### Task 1: Define configuration and request behavior with tests

**Files:**
- Modify: `tests/test_config_schema.py`
- Modify: `tests/test_outline_generator.py`
- Create: `tests/test_reasoning_effort.py`

- [ ] **Step 1: Write tests for environment parsing and request propagation.**
- [ ] **Step 2: Run focused tests and confirm they fail because the properties/fields do not exist.**

### Task 2: Implement optional reasoning-effort configuration

**Files:**
- Modify: `bid_writer/config.py:475-558`
- Modify: `bid_writer/ai_writer.py:316-330`
- Modify: `bid_writer/outline_generator.py:160-180`
- Modify: `bid_writer/generation_trace.py:125-139`

- [ ] **Step 1: Add validated optional properties and outline fallback.**
- [ ] **Step 2: Add conditional `reasoning_effort` fields to primary generation requests.**
- [ ] **Step 3: Include the field in sanitized trace request metadata.**
- [ ] **Step 4: Run focused tests and confirm they pass.**

### Task 3: Document environment configuration

**Files:**
- Modify: `.env.example`
- Modify: `docs/config_schema.md`
- Modify: `bid_writer/env_local_prompt.py`

- [ ] **Step 1: Document accepted levels, defaults, fallback, and compatibility behavior.**
- [ ] **Step 2: Update missing-environment prompts with the optional settings.**

### Task 4: Verify, inspect, and integrate

**Files:**
- All files above

- [ ] **Step 1: Run the complete test suite with `uv run pytest -q`.**
- [ ] **Step 2: Run GitNexus `detect_changes` against this worktree and review affected flows.**
- [ ] **Step 3: Commit the feature branch only after verification succeeds.**
- [ ] **Step 4: Merge the feature branch into `main` without overwriting existing user edits.**
