# Prompt Contract

## Current prompt assembly path

Phase 1 keeps the prompt assembly skeleton code-defined in `bid_writer/ai_writer.py`.
The current chapter prompt is assembled inside `AIWriter.build_prompt_result(...)` in this exact order:

1. `task_card`
2. `structure_contract`
3. optional `first_line_rule`
4. pruned-context branch:
   - `scope_reference`
   - optional `scoring_focus`
   - `requirement_brief` or `requirement_points`
5. full-context branch:
   - `full_outline`
   - optional `bid_requirements`
   - optional `scoring_criteria`
6. optional `additional_requirements`
7. optional `extra_rules`

The system prompt is assembled separately in `AIWriter.build_system_prompt()`. It combines:

- `Config.role`
- bidder naming constraints from `prompt_bidder_name`
- heading and language constraints from `prompt_allow_markdown_headings` and `prompt_allow_english_terms`
- additional hard constraints from `prompt_hard_constraints`

This means the final generation contract is already split into two prompt kinds:

- system prompt: highest-priority role and hard constraints
- user prompt: task card, structure guidance, context blocks, and optional user additions

## Current low-level prompt sections

The current low-level section ids are the source-of-truth inputs for Phase 1 rollup:

| Section id | Source | When it appears |
|------------|--------|-----------------|
| `task_card` | `AIWriter._build_task_card(...)` | always |
| `structure_contract` | `AIWriter._build_structure_contract_section()` | always |
| `first_line_rule` | `AIWriter._format_first_line(...)` | only when `prompt.first_line_template` is non-empty |
| `scope_reference` | `AIWriter._build_scope_reference(...)` | pruned mode only |
| `scoring_focus` | `AIWriter._build_scoring_focus_section(...)` | pruned mode and matched scoring items exist |
| `requirement_brief` | `pruned_context.requirement_brief` | pruned mode and requirement brief exists |
| `requirement_points` | `pruned_context.requirement_seed` | pruned mode when brief is absent but seed exists |
| `full_outline` | `Config.get_outline_content()` | full-context mode only |
| `bid_requirements` | `Config.bid_requirements` | full-context mode when requirements text exists |
| `scoring_criteria` | `Config.scoring_criteria` | full-context mode when scoring text exists |
| `additional_requirements` | end-user input | only when the operator enters extra requirements |
| `extra_rules` | `AIWriter._build_extra_rules_section()` | only when `prompt.extra_rules` is non-empty |

The raw `prompt_sections` list is already captured during assembly and must remain available in Phase 1.

## Current trace artifact surface

The current trace contract is implemented by `GenerationTraceSession` in `bid_writer/generation_trace.py`.

`GenerationTraceSession._build_context_payload()` currently writes:

- `context_mode`
- `context_pruning_enabled`
- `prompt_sections`
- `prompt_lengths`
- `pruned_context` or `full_context`

Other current artifacts remain stable and are already documented in `docs/generation_trace.md`:

- `manifest.json`
- `01_heading.json`
- `02_context_assembly.json`
- `03_prompt_system.md`
- `04_prompt_user.md`
- `05_request_options.json`
- `06_generation_output.md`
- `07_summary.md`

The current maintainer workflow is:

1. open `07_summary.md`
2. inspect `04_prompt_user.md`
3. inspect `02_context_assembly.json`
4. inspect `06_generation_output.md`

Phase 1 must improve the primary maintainer view without removing this raw-layer workflow.

## Current config compatibility surface

The active public config surface is broader than a single YAML shape and must stay compatible.

### Current public config families

- `prompt.*`
- `context_pruning.*`
- `generation_trace.*`
- root-level `outline_file`
- root-level `bid_requirements`
- root-level `scoring_criteria`
- root-level `bid_requirements_file`
- root-level `scoring_criteria_file`
- `inputs.*` fallbacks

### Current compatibility behavior

`Config` uses `_get_first_defined(...)` and related helpers to support both current and older shapes.
Important compatibility seams include:

- `inputs.outline_file` and root-level `outline_file`
- `inputs.bid_requirements` / `inputs.bid_requirements_file` and root-level alternatives
- `inputs.scoring_criteria` / `inputs.scoring_criteria_file` and root-level alternatives
- inline text and inline file-path detection via `_extract_inline_file_path(...)`
- default values for `prompt.*`, `context_pruning.*`, and `generation_trace.*`

`README.md` and `config_公共服务满意度.yaml` together define the compatibility baseline that Phase 1 must preserve.

## Phase 1 business blocks

Phase 1 introduces a summarized maintainer-facing contract with these exact block ids:

1. `system_constraints`
2. `chapter_task`
3. `structure_rules`
4. `chapter_scope`
5. `requirement_context`
6. `scoring_context`

These are business-level blocks for maintainers. They do not replace the raw `prompt_sections` layer.

### Block intent

| Block id | Prompt kind | Maintainer question it answers |
|----------|-------------|--------------------------------|
| `system_constraints` | system | Which hard constraints define the global writing contract? |
| `chapter_task` | user | What chapter is being written and what operator-specific input applies? |
| `structure_rules` | user | Which structural formatting rules shape the chapter output? |
| `chapter_scope` | user | What outline boundary defines this chapter’s scope? |
| `requirement_context` | user | Which requirement text or requirement-derived points feed this chapter? |
| `scoring_context` | user | Which scoring items are being optimized for this chapter? |

## Rollup and provenance rules

Phase 1 rollup is defined from existing section ids and system-prompt sources.

### `system_constraints`

- source: `AIWriter.build_system_prompt()`
- source_context:
  - `Config.role`
  - `prompt_bidder_name`
  - `prompt_allow_markdown_headings`
  - `prompt_allow_english_terms`
  - `prompt_hard_constraints`

### `chapter_task`

- section_names:
  - `task_card`
  - `additional_requirements`
- source_context:
  - current `HeadingNode`
  - `min_words`
  - operator `additional_requirements`
  - `prompt.output_format`
  - bidder name and focus-term derivation inputs

### `structure_rules`

- section_names:
  - `structure_contract`
  - `first_line_rule`
  - `extra_rules`
- source_context:
  - `prompt.first_line_template`
  - `prompt.extra_rules`
  - structure-contract helper output

### `chapter_scope`

- section_names:
  - `scope_reference` or `full_outline`
- source_context:
  - `context_mode`
  - pruned local outline context or complete outline text
  - current heading parent/sibling boundary information

### `requirement_context`

- section_names:
  - `requirement_brief`
  - `requirement_points`
  - `bid_requirements`
- source_context:
  - `pruned_context.requirement_brief`
  - `pruned_context.requirement_seed`
  - `Config.bid_requirements`
  - requirement selection mode implied by pruning/full-context branch

### `scoring_context`

- section_names:
  - `scoring_focus`
  - `scoring_criteria`
- source_context:
  - matched `pruned_context.scoring_items`
  - `Config.scoring_criteria`
  - current scoring routing branch

## Preservation rules

Phase 1 preserves the raw `prompt_sections` layer exactly as the low-level forensic record.
The new summarized contract is an additive presentation layer:

- maintainers first see the six business blocks
- low-level `prompt_sections` remains available unchanged
- `source_context` must be shown for every business block
- trace artifacts should expose both levels side by side rather than forcing one view

## Implementation guidance for Phase 1

- Keep ordering, defaults, enablement conditions, and compatibility shims code-defined.
- Do not externalize section topology in Phase 1.
- Preserve current trace filenames and raw context payloads.
- Add the summary layer conservatively so existing trace-inspection habits keep working.
- Treat `README.md` and checked-in YAML configs as public compatibility contracts, not just examples.
