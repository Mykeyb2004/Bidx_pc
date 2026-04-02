# Roadmap: 自动标书撰写系统

## Overview

This roadmap upgrades the existing desktop bid-writing system from “prompt features exist” to “prompt optimization is structured, observable, and repeatable.” The work starts by making prompt assembly explicit and backward-compatible, then tightens context routing, strengthens output guardrails, adds a sample-based evaluation loop, and ends by hardening the operator workflow with integration checks and documentation.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Prompt Contract & Baseline** - Make prompt assembly explicit, inspectable, and backward-compatible.
- [ ] **Phase 2: Context Routing Precision** - Reduce irrelevant outline, requirement, and scoring context for each chapter.
- [ ] **Phase 3: Output Guardrails Hardening** - Enforce structure and constraint compliance more reliably.
- [ ] **Phase 4: Prompt Evaluation Loop** - Add repeatable sample-based comparison and judgment workflow.
- [ ] **Phase 5: Integration Safety & Docs** - Preserve operator workflows and document the optimization system for future tuning.

## Phase Details

### Phase 1: Prompt Contract & Baseline
**Goal**: Make the chapter-generation prompt contract explicit, traceable, and safe for existing configs.
**Depends on**: Nothing (first phase)
**Requirements**: [PRMT-01, PRMT-02, PRMT-03]
**Success Criteria** (what must be TRUE):
  1. Maintainer can inspect one chapter generation and understand prompt sections plus ordering without reading multiple modules.
  2. Generation artifacts show which prompt sections were assembled for the selected chapter and what context fed them.
  3. Existing config files without new prompt fields still load and generate successfully.
**Plans**: 3 plans

Plans:
- [x] 01-01: Audit current prompt assembly path and define the target prompt contract.
- [x] 01-02: Refactor prompt-section construction so ordering, labels, and defaults are explicit.
- [ ] 01-03: Add backward-compatibility coverage for existing YAML prompt configs.

### Phase 2: Context Routing Precision
**Goal**: Ensure each chapter prompt receives only the outline, requirement, and scoring context it actually needs.
**Depends on**: Phase 1
**Requirements**: [CTXT-01, CTXT-02, CTXT-03]
**Success Criteria** (what must be TRUE):
  1. Selected chapters no longer receive broad unrelated outline scope in the final prompt by default.
  2. Requirement excerpts and briefs can be traced to concrete source text during prompt review.
  3. Scoring-item matches shown in prompt artifacts are directly relevant to the current chapter and explain why they were selected.
**Plans**: 3 plans

Plans:
- [ ] 02-01: Rework local outline and chapter-boundary heuristics for prompt assembly.
- [ ] 02-02: Improve requirement excerpt and brief selection with source-trace visibility.
- [ ] 02-03: Tighten scoring-item relevance matching and matching-reason output.

### Phase 3: Output Guardrails Hardening
**Goal**: Strengthen prompt constraints and post-generation checks so generated text is structurally compliant and easier to review.
**Depends on**: Phase 2
**Requirements**: [QUAL-01, QUAL-02, QUAL-03]
**Success Criteria** (what must be TRUE):
  1. Multi-block chapter outputs reliably use formal numbered hierarchy instead of loose prose.
  2. Bidder name, Markdown-heading, English-term, summary-title, and table-count rules are applied consistently from config.
  3. When output violates prompt contract rules, the system records specific issue categories for review.
**Plans**: 3 plans

Plans:
- [ ] 03-01: Tighten structure and numbering guardrails in system/user prompt construction.
- [ ] 03-02: Expand post-generation issue detection and normalization around configured constraints.
- [ ] 03-03: Verify constraint handling across representative formatting edge cases.

### Phase 4: Prompt Evaluation Loop
**Goal**: Add a repeatable workflow for comparing prompt revisions on representative chapters and judging quality shifts.
**Depends on**: Phase 3
**Requirements**: [EVAL-01, EVAL-02, EVAL-03]
**Success Criteria** (what must be TRUE):
  1. Maintainer can run prompt evaluation on a stable set of sample chapters without reconstructing prompts manually.
  2. Evaluation output stores prompt artifacts, generated content, and judgment results together for comparison.
  3. Reviewers can classify whether quality changes came from context routing, prompt wording, or guardrail behavior.
**Plans**: 3 plans

Plans:
- [ ] 04-01: Define representative chapter samples and pass/fail review rubric.
- [ ] 04-02: Build an evaluation runner that captures prompt artifacts and outputs in one result set.
- [ ] 04-03: Add revision-comparison reporting that highlights the source of quality change.

### Phase 5: Integration Safety & Docs
**Goal**: Ship prompt-optimization improvements without breaking user-facing desktop workflows and document the system for future maintainers.
**Depends on**: Phase 4
**Requirements**: [INTG-01, INTG-02]
**Success Criteria** (what must be TRUE):
  1. GUI batch generation, preview, save, and merge workflows still work after prompt-system changes.
  2. Repository documentation explains the prompt-optimization path, debug artifacts, and future tuning entry points.
  3. Future prompt iterations can start from documented artifacts instead of reverse-engineering the generation path again.
**Plans**: 2 plans

Plans:
- [ ] 05-01: Run integration checks across batch generation, preview, save, and merge flows.
- [ ] 05-02: Refresh prompt-tuning and generation-trace documentation for future maintainers.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Prompt Contract & Baseline | 2/3 | In Progress | - |
| 2. Context Routing Precision | 0/3 | Not started | - |
| 3. Output Guardrails Hardening | 0/3 | Not started | - |
| 4. Prompt Evaluation Loop | 0/3 | Not started | - |
| 5. Integration Safety & Docs | 0/2 | Not started | - |
