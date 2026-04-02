# Phase 1: Prompt Contract & Baseline - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the chapter-generation prompt contract explicit, traceable, and safe for existing configs. This phase defines the structural contract of prompt assembly, the maintainer-facing visibility model, and the compatibility approach for prompt-related configuration. It does not expand prompt quality features outside the current baseline or add new product capabilities.

</domain>

<decisions>
## Implementation Decisions

### Prompt Contract Shape
- **D-01:** Use a hybrid prompt-contract model. Core section ordering, required versus optional sections, section enablement conditions, and compatibility shims stay code-defined.
- **D-02:** Externalize only the business-facing text fragments for sections, such as wording templates, reusable prompt snippets, and explanatory copy.
- **D-03:** Do not externalize section definitions themselves in Phase 1. The system should not depend on fully external section topology to assemble a valid prompt.

### Section Granularity
- **D-04:** The maintainer-facing prompt contract should be presented as a small set of business-level blocks rather than many low-level helper sections.
- **D-05:** The primary human-facing view should stay within roughly 4-6 major blocks so maintainers can understand one generation without reading multiple code paths.

### Trace Visibility
- **D-06:** Keep the current trace baseline in Phase 1 rather than expanding into a larger explainability system.
- **D-07:** For maintainers, the main trace view should show only the 4-6 business-level blocks.
- **D-08:** Preserve fine-grained internal section data underneath the summarized view so debugging and forensic review still have the full detail when needed.

### Compatibility Strategy
- **D-09:** Prompt-related config fields may be reorganized if it materially improves clarity, but every moved or renamed field must keep a compatibility shim.
- **D-10:** Deprecated-field handling should be conservative: existing fields keep working long-term, and the system should emit deprecation warnings rather than forcing migration on a short schedule.

### the agent's Discretion
- Exact naming of the 4-6 business-level blocks.
- Whether summarized block names appear only in trace output or also in code-level prompt assembly abstractions.
- Exact warning format, warning surface, and documentation wording for deprecated config fields.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and constraints
- `.planning/ROADMAP.md` — Phase 1 goal, success criteria, and plan skeleton for Prompt Contract & Baseline.
- `.planning/REQUIREMENTS.md` — `PRMT-01`, `PRMT-02`, and `PRMT-03`, which define the contract visibility and backward-compatibility targets.
- `.planning/PROJECT.md` — Current project constraints: brownfield scope, compatibility requirement, and observability requirement.

### Current prompt and trace behavior
- `docs/generation_trace.md` — Current trace artifact layout and maintainer workflow for inspecting prompt assembly.
- `README.md` — Current documented `prompt.*`, `context_pruning.*`, and `generation_trace.*` configuration surface that future deprecation handling must respect.
- `config_公共服务满意度.yaml` — Real checked-in compatibility baseline showing current prompt, pruning, and trace fields in active use.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bid_writer/ai_writer.py:AIWriter.build_prompt_result` — Existing central prompt assembly path already builds `prompt_sections` and can be refactored into higher-level business blocks.
- `bid_writer/ai_writer.py:AIWriter._append_prompt_section` — Existing section-registration seam for preserving low-level section detail under a summarized contract.
- `bid_writer/ai_writer.py:AIWriter.build_system_prompt` — Existing high-priority constraint assembly point for system-level contract behavior.
- `bid_writer/generation_trace.py:GenerationTraceSession` — Existing structured trace writer that already stores `prompt_sections`, context mode, prompts, and outputs.
- `bid_writer/config.py` prompt and `context_pruning` accessors — Existing compatibility surface for prompt-related config reads and future shim logic.

### Established Patterns
- Prompt orchestration is code-defined in Python helper methods, not template-first.
- Rich traceability is file-based and JSON/Markdown-backed rather than database-backed.
- Config compatibility is currently handled through layered property accessors and fallback logic in `Config`, which supports a conservative migration approach.
- The codebase favors incremental extension of existing modules over introducing a separate orchestration framework.

### Integration Points
- Prompt-contract restructuring will center on `bid_writer/ai_writer.py`.
- Summarized-versus-detailed trace visibility will be implemented through `bid_writer/generation_trace.py`, with possible alignment to `prompt_sections` payload shape.
- Compatibility shims and deprecation warnings will connect through `bid_writer/config.py` and must be validated against `README.md` plus checked-in YAML configs.

</code_context>

<specifics>
## Specific Ideas

- “混合模式” here means code controls contract structure; external files hold wording and prompt snippets.
- “对维护者主视角只看 4-6 个大块” is a hard usability preference for this phase.
- “展示收敛、底层不丢细节” is the governing rule for trace visibility in Phase 1.

</specifics>

<deferred>
## Deferred Ideas

- Richer trace explainability, such as exposing matching reasons, discarded candidates, or full context-selection rationale, belongs to later phases unless Phase 1 work proves it is required just to stabilize the baseline.
- Any broader prompt-quality improvements beyond contract clarity, such as scoring relevance upgrades or output-quality guardrail expansion, remain in later roadmap phases.

</deferred>

---

*Phase: 01-prompt-contract-baseline*
*Context gathered: 2026-04-02*
