---
phase: 01-prompt-contract-baseline
plan: "03"
subsystem: testing
tags:
  - pytest
  - prompt
  - regression
  - compatibility
requires: []
provides:
  - offline fixture configs for legacy and current prompt-contract scenarios
  - pytest regression coverage for prompt building and trace serialization
  - maintainer README entry for prompt-contract regression workflow
affects:
  - future-maintainer-workflow
  - prompt-evaluation
  - generation-trace
  - config-compatibility
tech-stack:
  added:
    - pytest
  patterns:
    - regression tests use offline fixture workspaces instead of project-specific live files
    - prompt contract tests monkeypatch the OpenAI client and verify trace artifacts directly
key-files:
  created:
    - tests/fixtures/outline.md
    - tests/fixtures/bid_requirements.md
    - tests/fixtures/scoring_criteria.md
    - tests/fixtures/legacy_prompt_config.yaml
    - tests/fixtures/current_prompt_config.yaml
    - tests/test_prompt_contract.py
  modified:
    - pyproject.toml
    - uv.lock
    - README.md
key-decisions:
  - "Install pytest as a uv dev dependency and lock it so `uv run pytest` is reproducible in this repo."
  - "Use offline fixture configs plus monkeypatched OpenAI construction so prompt-contract tests never depend on network access or external bid files."
patterns-established:
  - "Legacy and current config shapes are validated through fixture workspaces copied into tmp paths."
  - "Trace regression checks assert both prompt_contract and prompt_sections in the same payload."
requirements-completed: [PRMT-03]
duration: 4 min
completed: 2026-04-02
---

# Phase 1 Plan 03: Prompt Contract Compatibility Coverage Summary

**Pytest-based offline regression workflow for legacy YAML compatibility and prompt-contract trace coverage**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-02T17:24:07+08:00
- **Completed:** 2026-04-02T17:27:59+08:00
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Added pytest to the uv workflow and created offline outline/requirements/scoring/config fixtures for deterministic regression checks.
- Added `tests/test_prompt_contract.py` covering legacy config prompt construction, ordered contract blocks, and trace payload persistence of both `prompt_contract` and `prompt_sections`.
- Documented the maintainer-facing prompt contract regression entry point in `README.md`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add pytest and offline config fixtures for prompt-contract coverage** - `ff4a77e` (chore)
2. **Task 2: Add deterministic tests for compatibility and trace contract behavior** - `23604fe` (test)
3. **Task 3: Document the compatibility guarantee and regression command** - `3e65acd` (docs)

**Plan metadata:** pending until the plan-completion docs commit.

## Files Created/Modified
- `pyproject.toml` - Adds uv-managed pytest development dependency.
- `uv.lock` - Locks pytest and supporting packages for reproducible local test runs.
- `tests/fixtures/legacy_prompt_config.yaml` - Minimal legacy-style config without new prompt-contract fields.
- `tests/fixtures/current_prompt_config.yaml` - Current-style config exercising prompt, pruning, and trace surfaces.
- `tests/test_prompt_contract.py` - Regression tests for prompt build compatibility and trace serialization.
- `README.md` - Maintainer instructions for prompt contract regression checks.

## Decisions Made
- Use `uv run pytest` as the maintained regression entry point for prompt-contract checks.
- Keep tests offline by copying fixture files into temporary workspaces and monkeypatching OpenAI client construction.
- Verify `prompt_contract` and `prompt_sections` together so the new summary layer cannot silently replace the raw detail layer.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 now has automated proof that old YAML configs still build prompts and that the new summary layer preserves the old raw trace layer.
- Phase-level verification can mark Prompt Contract requirements complete with concrete test evidence, not only doc/code inspection.

## Self-Check: PASSED

- `uv run pytest tests/test_prompt_contract.py -q` passed.
- `uv run pytest -q` passed.
- `README.md` contains the exact regression command `uv run pytest tests/test_prompt_contract.py -q`.

---
*Phase: 01-prompt-contract-baseline*
*Completed: 2026-04-02*
