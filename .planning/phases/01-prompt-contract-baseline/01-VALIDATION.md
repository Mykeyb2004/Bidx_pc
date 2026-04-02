---
phase: 1
slug: prompt-contract-baseline
status: completed
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-02
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none - Phase 1 adds minimal pytest coverage |
| **Quick run command** | `uv run pytest tests/test_prompt_contract.py -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_prompt_contract.py -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | PRMT-01 | analysis | `rg -n "build_prompt_result|_append_prompt_section" bid_writer/ai_writer.py` | ✅ | ✅ green |
| 1-01-02 | 01 | 1 | PRMT-01 | artifact | `rg -n "Prompt Contract|business block|contract" .planning/phases/01-prompt-contract-baseline/01-01-PLAN.md` | ✅ | ✅ green |
| 1-02-01 | 02 | 2 | PRMT-01 | unit | `uv run pytest tests/test_prompt_contract.py -q -k prompt_contract` | ✅ | ✅ green |
| 1-02-02 | 02 | 2 | PRMT-02 | unit | `uv run pytest tests/test_prompt_contract.py -q -k trace` | ✅ | ✅ green |
| 1-03-01 | 03 | 3 | PRMT-03 | unit | `uv run pytest tests/test_prompt_contract.py -q -k config_compat` | ✅ | ✅ green |
| 1-03-02 | 03 | 3 | PRMT-03 | regression | `uv run pytest -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_prompt_contract.py` - prompt contract, trace summary, and config compatibility checks for PRMT-01 through PRMT-03
- [x] `pyproject.toml` - add pytest test dependency or equivalent test group entry
- [x] `tests/fixtures/legacy_prompt_config.yaml` - minimal legacy-style config without new prompt-contract fields

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Maintainer can understand one chapter generation from the artifact layout without reading multiple modules | PRMT-01, PRMT-02 | This is partly a human-clarity judgment, not just file presence | Open one generated trace summary and confirm the business-level prompt blocks, their order, and their source context are understandable from the artifact set alone |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-02
