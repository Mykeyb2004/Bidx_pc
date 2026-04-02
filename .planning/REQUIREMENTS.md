# Requirements: 自动标书撰写系统

**Defined:** 2026-04-02
**Core Value:** 在不增加操作负担的前提下，让每个章节都能稳定生成贴合招标要求、结构规范、可直接交付的正文

## v1 Requirements

### Prompt Contract

- [ ] **PRMT-01**: Maintainer can identify the exact prompt sections and ordering used for one chapter generation without tracing multiple code paths manually.
- [ ] **PRMT-02**: Maintainer can see, in generation artifacts, which context blocks fed each prompt section for the selected chapter.
- [ ] **PRMT-03**: Existing YAML configs still produce a valid generation prompt when new prompt-optimization fields are absent.

### Context Routing

- [ ] **CTXT-01**: For a selected chapter, the final prompt includes only chapter-relevant outline scope instead of broad unrelated sections.
- [ ] **CTXT-02**: For a selected chapter, requirement excerpts or requirement briefs can be traced back to concrete source text.
- [ ] **CTXT-03**: For a selected chapter, scoring items included in the prompt are limited to directly relevant matches and expose why they matched.

### Output Quality

- [ ] **QUAL-01**: Generated long-form chapter text uses formal numbered hierarchy when the content contains multiple sections, tables, or parallel measures.
- [ ] **QUAL-02**: Generated chapter text respects configured constraints for bidder name, Markdown headings, English terms, summary heading, and table count.
- [ ] **QUAL-03**: When generated text breaks prompt contract rules, the system records the specific issue category for review instead of failing silently.

### Evaluation Workflow

- [ ] **EVAL-01**: Maintainer can run a repeatable prompt-evaluation workflow against a representative set of chapters.
- [ ] **EVAL-02**: Evaluation output stores prompt artifacts, model output, and pass/fail judgment in one place for side-by-side comparison.
- [ ] **EVAL-03**: Maintainer can compare prompt revisions and tell whether quality changes came from context routing, prompt wording, or output guardrails.

### Integration Safety

- [ ] **INTG-01**: GUI batch generation, preview, save, and merge workflows continue to work after prompt-optimization changes.
- [ ] **INTG-02**: Future maintainers can understand the prompt-optimization workflow from repository docs without reverse-engineering the codebase first.

## v2 Requirements

### Advanced Prompting

- **ADVP-01**: Maintainer can run A/B comparisons across multiple prompt strategies in one command.
- **ADVP-02**: System can use judge-model or rubric-based scoring to rank prompt outputs automatically.

### Product Expansion

- **PROD-01**: Operator can tune prompt strategy from the GUI instead of editing YAML files.
- **PROD-02**: System can support multi-expert or multi-pass chapter generation flows when single-pass prompting no longer meets quality targets.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web application rewrite | Not required to improve prompt quality in the current desktop workflow |
| Full GUI redesign | Interface overhaul does not directly solve prompt relevance or output quality |
| Model-provider migration | Prompt-system optimization should be validated before changing inference infrastructure |
| Fully automatic scoring/judge pipeline in v1 | Useful later, but not necessary to establish the first stable prompt-tuning loop |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PRMT-01 | Phase 1 | Pending |
| PRMT-02 | Phase 1 | Pending |
| PRMT-03 | Phase 1 | Pending |
| CTXT-01 | Phase 2 | Pending |
| CTXT-02 | Phase 2 | Pending |
| CTXT-03 | Phase 2 | Pending |
| QUAL-01 | Phase 3 | Pending |
| QUAL-02 | Phase 3 | Pending |
| QUAL-03 | Phase 3 | Pending |
| EVAL-01 | Phase 4 | Pending |
| EVAL-02 | Phase 4 | Pending |
| EVAL-03 | Phase 4 | Pending |
| INTG-01 | Phase 5 | Pending |
| INTG-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-02 after initial definition*
