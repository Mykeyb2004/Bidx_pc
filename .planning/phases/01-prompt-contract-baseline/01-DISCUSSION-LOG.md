# Phase 1: Prompt Contract & Baseline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-02
**Phase:** 01-Prompt Contract & Baseline
**Areas discussed:** Prompt Contract Shape, Section Granularity, Trace Visibility, Compatibility Strategy

---

## Prompt Contract Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Code-defined skeleton | Keep section order, enablement, and wording in code | |
| External-template driven | Move prompt structure and wording out to external templates | |
| Hybrid | Keep section structure in code, externalize wording and reusable snippets | ✓ |

**User's choice:** Hybrid
**Notes:** User confirmed the intended boundary: code owns section order, required versus optional rules, enablement conditions, and compatibility shim behavior; external files may hold wording templates and prompt snippets, but section definitions themselves should not be externalized in Phase 1.

---

## Section Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Business-level large blocks | Maintainers see a small set of high-level prompt blocks | ✓ |
| Current fine-grained sections | Maintainers inspect many lower-level helper sections directly | |
| Two-layer equal emphasis | Show both large blocks and low-level sections as co-equal primary views | |

**User's choice:** Business-level large blocks
**Notes:** User wants the maintainer primary view to stay within roughly 4-6 business-level blocks rather than exposing the current fine-grained assembly shape as the default mental model.

---

## Trace Visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Keep current baseline | Do not expand Phase 1 into a larger explainability system | |
| Summarized maintainer view + preserved low-level trace | Main trace view shows large blocks; underlying detailed sections remain available | ✓ |
| Expand explainability now | Add explicit match reasons, dropped candidates, and richer causal trace in Phase 1 | |

**User's choice:** Summarized maintainer view + preserved low-level trace
**Notes:** User first said “保持”, then clarified the desired meaning: maintainers should mainly see 4-6 big blocks, while the system must retain fine-grained section data for debugging and audit review.

---

## Compatibility Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Conservative | Reorganize if needed, but old fields keep working with deprecation warnings | ✓ |
| Transitional | Reorganize with a limited migration window and later removal plan | |
| Strong governance | Reorganize aggressively and push users to migrate quickly | |

**User's choice:** Conservative
**Notes:** User allows prompt-related field cleanup only if every moved or renamed field has a compatibility shim plus deprecation notice. Existing fields should continue to work long-term rather than being put on a short forced-migration schedule.

---

## the agent's Discretion

- Exact names for the 4-6 business-level prompt blocks.
- Whether the summarized block model is implemented as a new abstraction layer or as a trace-only presentation layer over existing low-level sections.
- Exact warning message format and where deprecation notices are surfaced.

## Deferred Ideas

- Richer context-selection explainability, including match reasons and filtered-candidate visibility, is deferred to later phases unless Phase 1 baseline work exposes it as a blocker.
