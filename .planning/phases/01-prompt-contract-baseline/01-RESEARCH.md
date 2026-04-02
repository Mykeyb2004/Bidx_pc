# Phase 1: Prompt Contract & Baseline - Research

**Date:** 2026-04-02
**Phase:** 01 Prompt Contract & Baseline
**Goal:** Make the chapter-generation prompt contract explicit, traceable, and safe for existing configs.

## Research Question

What does the team need to know to plan Phase 1 well without regressing current prompt generation behavior?

## Current-State Findings

### Prompt assembly is already centralized enough for an incremental refactor

- `bid_writer/ai_writer.py:build_prompt_result` is the existing prompt-assembly spine.
- `bid_writer/ai_writer.py:_append_prompt_section` already creates a low-level section list, which is the safest seam for introducing a higher-level prompt contract without rebuilding generation from scratch.
- `bid_writer/ai_writer.py:build_system_prompt` already separates high-priority system constraints from user-prompt content, which suggests the contract should model system and user prompt blocks distinctly.

### Trace artifacts already capture enough low-level data to support a summarized view

- `bid_writer/generation_trace.py:GenerationTraceSession._build_context_payload` already writes `prompt_sections`, `context_mode`, and context payloads into trace artifacts.
- The current trace shape records section names and character counts, but it does not expose a maintainer-facing 4-6 block contract.
- Because the raw section list already exists, Phase 1 should add a summarized business-block layer on top of the existing trace rather than replacing the low-level data.

### Config compatibility depends on preserving today’s mixed old/new access patterns

- `bid_writer/config.py` uses `_get_first_defined(...)` and layered property accessors heavily, which is already the project’s compatibility mechanism.
- `README.md` documents the current `prompt.*`, `context_pruning.*`, and `generation_trace.*` fields as active public surface area.
- `config_公共服务满意度.yaml` proves real checked-in configs already rely on current keys like `prompt.hard_constraints`, `prompt.extra_rules`, `prompt.summary_title`, `context_pruning.*`, and `generation_trace.*`.
- Phase 1 should treat `README.md` plus checked-in YAML as compatibility baselines, not just the Python code.

### There is no automated test harness yet

- The repository currently has no `tests/` directory.
- `pyproject.toml` declares only runtime dependencies (`pyyaml`, `openai`) and no test framework.
- That means compatibility coverage and prompt-contract regression checks must either add a minimal pytest harness in this phase or rely entirely on manual checks. Given `PRMT-03`, a minimal automated harness is the safer planning choice.

## Recommended Contract Shape

### Preferred implementation model

Use a two-layer prompt contract:

1. **Internal assembly layer** in `bid_writer/ai_writer.py`
   - Keeps the real assembly order, defaults, enablement conditions, and compatibility shims code-defined.
   - Produces the final system/user prompt exactly as today, but through explicit block definitions.

2. **Maintainer-facing contract layer** in trace/debug artifacts
   - Groups low-level prompt sections into 4-6 business blocks.
   - Preserves the existing low-level `prompt_sections` list for debugging.
   - Adds enough metadata for maintainers to see which source context fed each high-level block.

This directly matches the phase decisions in `01-CONTEXT.md`: summarized maintainer view, preserved low-level detail, conservative compatibility.

### Likely block model for Phase 1

The exact labels remain discretionary, but the code points suggest a stable contract around blocks like:

- System constraints / role
- Chapter task card
- Chapter boundary / local outline context
- Requirement context
- Scoring focus
- Additional writing requirements / formatting controls

The plan should keep these as business-level abstractions and avoid exposing every helper subsection as a primary public concept.

## Planning Implications

### Plan 1 should be an audit-and-contract-definition slice, not an implementation grab bag

The first plan needs to map the current prompt assembly path, define the target block contract, and pin how low-level sections roll up into high-level blocks. Without that, implementation work will drift into ad hoc renaming.

### Plan 2 should focus on contract-producing code and trace output together

`PRMT-01` and `PRMT-02` are tightly coupled:

- maintainers must understand ordering and sections
- artifacts must show which context fed which section

That means the explicit contract model and trace presentation should be planned together, even if implemented across separate tasks inside one plan.

### Plan 3 should own compatibility coverage explicitly

`PRMT-03` is not just “don’t break old configs.” The plan needs concrete checks against:

- current `README.md`-documented config surface
- current checked-in YAML config behavior
- missing optional prompt-optimization fields

This work should include warnings/shims if fields are reorganized, plus automated or scripted coverage proving older configs still load.

## Risks To Plan Around

### Risk: Trace refactor accidentally becomes an explainability project

The phase context explicitly defers richer explainability. Plans should limit Phase 1 to:

- summarized block view
- mapping from block to source context
- preservation of detailed raw section data

They should avoid broader “why this excerpt matched” or “why other candidates were rejected” work.

### Risk: Business-level block names diverge from real code seams

If the block contract is invented too abstractly, execution will create a naming layer that does not map back to actual assembly helpers. The plan should require reading `ai_writer.py` and using the current section sources as ground truth before naming the public blocks.

### Risk: Compatibility is verified only by code inspection

Because there is no test harness yet, execution may otherwise stop at “properties still exist.” The plan should require at least one regression-style automated check using real config fixtures.

### Risk: Trace payload changes break downstream maintainer workflow

`docs/generation_trace.md` defines a current artifact-viewing workflow. Any changes to trace structure should preserve the existing files and add new fields conservatively rather than replacing the documented layout.

## Recommended Plan Split

Use the roadmap’s three-plan structure as three vertical slices:

1. **01-01 Audit + contract definition**
   - document current prompt path
   - define the target high-level block contract and rollup rules
   - identify affected code + trace surfaces

2. **01-02 Contract implementation + trace visibility**
   - make ordering/defaults/enablement explicit in code
   - emit business-block trace summary while preserving low-level section data
   - keep system/user prompt outputs behaviorally compatible

3. **01-03 Compatibility coverage**
   - add minimal automated regression harness
   - validate old YAML shapes and absent new fields
   - document deprecation/warning behavior if any field names move

This is mostly sequential because Plan 2 depends on the contract defined in Plan 1, and Plan 3 should verify the stabilized implementation from Plan 2.

## Validation Architecture

### Suggested verification strategy for this phase

- Add a minimal `pytest` harness under `tests/` in Phase 1.
- Prefer prompt-construction and config-loading tests over full model-call integration tests.
- Verify prompt-contract behavior through deterministic unit-style checks on `AIWriter.build_prompt_result`, `AIWriter.build_system_prompt`, and trace payload generation.
- Use checked-in YAML configs plus intentionally minimal fixture configs to prove compatibility when prompt-related fields are absent.

### High-value automated checks

- A prompt-build test that asserts the maintainer-facing block contract exists in a stable order for a representative chapter.
- A trace test that asserts high-level business blocks and low-level `prompt_sections` both appear in the saved context payload.
- A config-compatibility test that loads an existing YAML config and a reduced legacy-style config without new fields and confirms prompt construction still succeeds.

### What not to validate in this phase

- Real API generation quality
- Model output semantics
- Full GUI workflow end-to-end

Those belong to later phases or broader integration verification. Phase 1 validation should stay focused on prompt contract clarity, trace visibility, and compatibility safety.

## Planning Bottom Line

Phase 1 is best planned as an incremental refactor around existing seams, not a rewrite:

- `ai_writer.py` is the contract assembly seam
- `generation_trace.py` is the visibility seam
- `config.py` plus real YAML files are the compatibility seam

The plans should protect those seams explicitly, add a summarized contract layer instead of replacing low-level detail, and introduce a minimal automated regression harness so compatibility claims are provable.
