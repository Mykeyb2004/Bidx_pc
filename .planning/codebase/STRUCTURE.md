# Codebase Structure

**Analysis Date:** 2026-04-02

## Directory Layout

```text
[project-root]/
├── bid_writer/          # Main application package
├── docs/                # Human-facing design and operational docs
├── log/                 # Generated timing logs and trace artifacts
├── output/              # Generated chapter files and merged bid drafts
├── 项目要求/            # Sample input documents used by configs
├── llm_reference_code/  # Reference/prototype code, excluded by `.gitignore`
├── .planning/codebase/  # Generated repository maps for planning agents
├── run.py               # Thin GUI launcher
├── pyproject.toml       # Packaging and CLI entry declaration
├── README.md            # Operator/developer usage guide
├── outline.md           # Default outline input
└── config_公共服务满意度.yaml  # Example project-specific runtime config
```

## Directory Purposes

**`bid_writer/`:**
- Purpose: All runtime application code lives here.
- Contains: GUI orchestration, config loading, outline parsing, prompt assembly, LLM calls, file persistence, and trace/timing logging.
- Key files: `bid_writer/gui.py`, `bid_writer/main.py`, `bid_writer/ai_writer.py`, `bid_writer/config.py`, `bid_writer/outline_parser.py`, `bid_writer/file_saver.py`

**`docs/`:**
- Purpose: Supporting implementation or operations documentation for features already present in code.
- Contains: Markdown docs such as `docs/generation_trace.md`
- Key files: `docs/generation_trace.md`

**`log/`:**
- Purpose: Runtime diagnostics written by the app.
- Contains: `log/generation_timing.log` plus trace subdirectories under `log/generation_traces/` when tracing is enabled or redirected there.
- Key files: `log/generation_timing.log`

**`output/`:**
- Purpose: Generated deliverables rather than source code.
- Contains: Per-heading Markdown outputs, merged bid files, and optional `_generation_traces/` subdirectories.
- Key files: Files are generated at runtime, not fixed in the repo layout.

**`项目要求/`:**
- Purpose: Input material referenced by configuration.
- Contains: Procurement requirements and scoring criteria source documents.
- Key files: `项目要求/项目采购需求.md`, `项目要求/评分标准.md`

**`llm_reference_code/`:**
- Purpose: Separate reference/prototype material for LLM integration, not imported by the main `bid_writer/` package.
- Contains: Standalone config/client examples and `llm_reference_code/README.md`
- Key files: `llm_reference_code/README.md`, `llm_reference_code/ai_client.py`, `llm_reference_code/example_usage.py`

**`.planning/codebase/`:**
- Purpose: Generated architecture/stack/convention/concern maps used by later planning agents.
- Contains: Markdown analysis documents such as `ARCHITECTURE.md` and `STRUCTURE.md`
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`

## Key File Locations

**Entry Points:**
- `run.py`: Preferred local launcher for the desktop GUI.
- `bid_writer/main.py`: Package entry function and the home of `BidWriter`.
- `bid_writer/gui.py`: Actual GUI runtime entry via `run_gui()`.

**Configuration:**
- `pyproject.toml`: Declares dependencies and the `bid-writer = "bid_writer.main:main"` console script.
- `config_公共服务满意度.yaml`: Current checked-in config example/preset.
- `.env.example`: Environment variable template. Do not read secrets from `.env.local`.
- `.bid_writer_gui_state.json`: GUI-only persisted state for the last successful config path.

**Core Logic:**
- `bid_writer/main.py`: Shared runtime service container and merge workflow.
- `bid_writer/ai_writer.py`: Prompt construction, model request execution, streaming, and final output normalization.
- `bid_writer/context_pruner.py`: Optional chapter-level context reduction before model calls.
- `bid_writer/config.py`: Typed configuration and file loading helpers.
- `bid_writer/outline_parser.py`: Heading tree model and Markdown outline parsing.
- `bid_writer/file_saver.py`: Output naming, lookup, save, and section-body reload behavior.
- `bid_writer/gui_adapter.py`: Filesystem-derived completion status mapping for the GUI.
- `bid_writer/generation_trace.py`: Per-generation trace artifact writer.
- `bid_writer/timing_logger.py`: Append-only timing log helper.

**Testing:**
- Not detected: there is no `tests/` directory, no `pytest` configuration, and no `*.test.py` or `*.spec.py` files in the repository.

## Naming Conventions

**Files:**
- Runtime Python modules use lowercase `snake_case` names inside `bid_writer/`: `ai_writer.py`, `outline_parser.py`, `gui_state.py`.
- Root documentation files use descriptive Markdown names and may use Chinese filenames when they are operator-facing inputs or notes: `投标大纲.md`, `多专家系统规划prd.md`, `项目要求/评分标准.md`.
- Generated trace directories use `timestamp__sanitized_title__traceid` naming, as implemented in `bid_writer/generation_trace.py`.

**Directories:**
- Source and runtime directories are short lowercase names: `bid_writer/`, `docs/`, `log/`, `output/`.
- Input-material directories may use domain-specific Chinese names when they are not Python packages: `项目要求/`.

## Where to Add New Code

**New Feature:**
- Primary code: add new reusable logic under `bid_writer/` as a focused module, then wire it into `bid_writer/main.py` or `bid_writer/gui.py` depending on whether it is core workflow or UI behavior.
- Tests: create a new top-level `tests/` directory. No test tree exists yet, so keep it separate from `bid_writer/` instead of mixing test code into production modules.

**New Component/Module:**
- Implementation: place new domain or infrastructure modules beside related peers in `bid_writer/`.
- Placement rule: UI-specific behavior belongs in `bid_writer/gui.py` or a new `bid_writer/gui_*.py` helper; model/prompt logic belongs near `bid_writer/ai_writer.py`; filesystem persistence belongs near `bid_writer/file_saver.py`; config expansion belongs in `bid_writer/config.py`.

**Utilities:**
- Shared helpers: add a dedicated `bid_writer/<utility_name>.py` only when the helper is used by multiple modules. If the logic is only used once, keep it private inside the owning module to avoid a shallow “utils” dumping ground.

## Special Directories

**`output/`:**
- Purpose: Generated user-facing Markdown outputs and, in some runs, `_generation_traces/`.
- Generated: Yes
- Committed: No, it is ignored by `.gitignore`

**`log/`:**
- Purpose: Runtime diagnostics such as `log/generation_timing.log` and optional trace bundles.
- Generated: Yes
- Committed: No, it is ignored by `.gitignore`

**`llm_reference_code/`:**
- Purpose: Standalone reference code, separate from the main application package.
- Generated: No
- Committed: No, it is ignored by `.gitignore`

**`.planning/codebase/`:**
- Purpose: Planner-facing repository maps produced by mapper agents.
- Generated: Yes
- Committed: Not currently tracked in git

**`bid_writer/__pycache__/`:**
- Purpose: Python bytecode cache, not source.
- Generated: Yes
- Committed: Yes in the current repository state, but do not place hand-written code here

## Placement Notes

- Keep executable application code inside `bid_writer/`; root-level Python files should stay thin entry points like `run.py`.
- Keep operator and implementation docs in `docs/` when they describe shipped behavior; avoid scattering new long-form docs across the repo root unless they are project-level materials such as `README.md`.
- Treat `outline.md` and files under `项目要求/` as runtime inputs, not code modules.
- Treat `task_plan.md`, `findings.md`, and `progress.md` as standalone planning artifacts; they are not imported by the application package.

---

*Structure analysis: 2026-04-02*
