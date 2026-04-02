# Codebase Concerns

**Analysis Date:** 2026-04-02

## Tech Debt

**Monolithic GUI workflow:**
- Issue: `bid_writer/gui.py` concentrates window setup, tree rendering, config switching, batch orchestration, preview dialogs, subprocess launching, and thread/queue coordination in one 2145-line module. UI state changes and business flow are tightly coupled, so small feature work tends to touch unrelated code paths.
- Files: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`, `bid_writer/main.py`
- Impact: High regression risk in desktop behavior, difficult code review, and slow onboarding for any change that touches generation flow or tree behavior.
- Fix approach: Split `bid_writer/gui.py` into focused modules for config selection, outline tree rendering, generation dialogs, and batch orchestration; keep `BidWriter` in `bid_writer/main.py` as the non-UI service boundary.

**Documentation and shipped-config drift:**
- Issue: `README.md` tells users to copy `config.example.yaml` to `config.yaml` at lines 63-67, but the repository does not contain `config.example.yaml`. The README also says generation traces default to `output/_generation_traces/` at line 240, while `Config.generation_trace_directory` defaults to `log/generation_traces` in `bid_writer/config.py` lines 635-640.
- Files: `README.md`, `bid_writer/config.py`, `config_公共服务满意度.yaml`
- Impact: Setup instructions are unreliable, operators will look in the wrong place for trace artifacts, and future maintenance has to guess whether docs or code reflect the intended behavior.
- Fix approach: Add a real `config.example.yaml`, align README defaults with `bid_writer/config.py`, and document the checked-in sample config as a machine-specific example rather than a portable starter.

**Committed build artifacts and stale runtime residue:**
- Issue: Compiled files under `bid_writer/__pycache__/` are present in the repository, including artifacts for source files that are no longer present such as `bid_writer/__pycache__/history.cpython-313.pyc` and `bid_writer/__pycache__/terminal_ui.cpython-313.pyc`.
- Files: `bid_writer/__pycache__/__init__.cpython-311.pyc`, `bid_writer/__pycache__/history.cpython-313.pyc`, `bid_writer/__pycache__/terminal_ui.cpython-313.pyc`, `.gitignore`
- Impact: Repository search results are noisier, deleted modules appear to still exist, and binary artifacts create avoidable merge noise.
- Fix approach: Remove tracked `__pycache__` artifacts and keep repository state source-only.

## Known Bugs

**Config switching leaks environment variables across projects:**
- Symptoms: Switching to a second config in the same GUI session can keep using API base URLs, models, or keys loaded from the first config directory instead of the newly selected config's `.env` or `.env.local`.
- Files: `bid_writer/config.py`, `bid_writer/gui.py`
- Trigger: `Config.load()` calls `_load_local_env()` before reading YAML. `_load_local_env()` snapshots the current process environment as `protected_keys` at lines 64-69, and `_load_dotenv_file()` refuses to overwrite any protected key at lines 45-62. `MainWindow.select_and_switch_config()` constructs a fresh `BidWriter` in the same process at lines 1245-1282, so values imported from the first config become effectively permanent for the rest of the session.
- Workaround: Restart the app before switching projects, or export the intended `BID_WRITER_*` variables in the shell before launch so the app uses explicit external values.

**Regeneration can silently overwrite accepted content:**
- Symptoms: Re-running generation for an already completed heading replaces the existing output file without prompting, including content that may have been manually edited after generation.
- Files: `bid_writer/config.py`, `bid_writer/file_saver.py`, `bid_writer/gui.py`, `README.md`
- Trigger: `output_overwrite_existing` defaults to `True` in `bid_writer/config.py` lines 396-402. `FileSaver.save()` writes directly to the standard path when overwrite is enabled at lines 327-368. Batch auto-save uses `self.bid_writer.file_saver.save(heading, content)` at `bid_writer/gui.py` lines 1955-1959, and README documents overwrite as the default at line 243.
- Workaround: Set `output.overwrite_existing: false` in the active config, or manually duplicate preserved outputs before re-running a section.

**Repository bootstrap path is broken for a fresh checkout:**
- Symptoms: A new developer following README setup will fail on `cp config.example.yaml config.yaml` because the referenced source file is missing.
- Files: `README.md`, `bid_writer/gui_state.py`, `run.py`, `config_公共服务满意度.yaml`
- Trigger: README setup lines 63-67 require `config.example.yaml`, while startup code still treats `config.yaml` as the default candidate in `bid_writer/gui_state.py` lines 89-125 and `run.py` line 18. The only checked-in config file is `config_公共服务满意度.yaml`, and it is not a portable default because it contains user-specific absolute paths at lines 84-99.
- Workaround: Copy and edit `config_公共服务满意度.yaml` manually, then pass it with `--config`.

## Security Considerations

**Trace and debug artifacts persist sensitive tender material to disk:**
- Risk: When tracing is enabled, the application writes prompts, selected context, output text, and request metadata to disk. That captures proprietary procurement requirements, scoring standards, user-supplied notes, and generated bid content in a second location outside the main output directory.
- Files: `bid_writer/generation_trace.py`, `config_公共服务满意度.yaml`, `bid_writer/context_pruner.py`
- Current mitigation: `generation_trace.redact_sensitive` only redacts the API base URL down to host level in `bid_writer/generation_trace.py` lines 114-131. It does not redact prompt bodies, requirement excerpts, or generated output. The checked-in config turns on full trace output at `config_公共服务满意度.yaml` lines 74-82, and also enables context debug dumps at lines 54-56. `GenerationTraceSession` writes prompt and context artifacts at lines 196-206 and output files at lines 70-79.
- Recommendations: Default tracing and debug dumps to off in shipped configs, redact or hash additional requirements and requirement excerpts before writing, and separate “developer diagnostics” from “normal operator mode”.

**Absolute local paths are embedded in the tracked sample config:**
- Risk: The checked-in config discloses the author’s local directory layout and project naming conventions, and it encourages users to keep absolute document paths in versioned YAML.
- Files: `config_公共服务满意度.yaml`
- Current mitigation: None in repository content; the sample config stores absolute paths for bid requirements, scoring criteria, outline source, and output directory at lines 84-99.
- Recommendations: Replace absolute paths with repo-relative placeholders in a committed example file and keep workstation-specific paths in ignored local config.

## Performance Bottlenecks

**Tree rendering recomputes generation status recursively for every visible node:**
- Problem: Each tree redraw asks the adapter for both status text and progress per node. For parent nodes, `GUIAdapter.get_heading_generation_status()` walks all descendant leaves every time, with no memoization.
- Files: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`
- Cause: `MainWindow._add_tree_node()` calls `self.adapter.get_status_text(heading)` and `self.adapter.get_progress(heading)` at `bid_writer/gui.py` lines 1092-1103. Both call `get_heading_generation_status()` in `bid_writer/gui_adapter.py` lines 58-115, which recomputes leaf lists and generated counts per node.
- Improvement path: Precompute per-heading generated counts once after `refresh_generated_titles()`, cache subtree totals on the parsed outline, and have filtering read from cached status instead of traversing each subtree repeatedly.

**Output refresh scans the full output directory on each outline sync:**
- Problem: Every outline reload or status refresh reparses every Markdown file in the output directory before repainting the tree.
- Files: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`, `bid_writer/file_saver.py`
- Cause: `_sync_loaded_outline()` triggers `self.adapter.refresh_generated_titles()` at `bid_writer/gui.py` lines 986-1004. `refresh_generated_titles()` iterates every `*.md` file and may parse front matter for each file at `bid_writer/gui_adapter.py` lines 30-56.
- Improvement path: Maintain an indexed manifest keyed by `heading_id`, or refresh incrementally after save/delete operations instead of rescanning the entire output directory.

## Fragile Areas

**Silent exception swallowing hides diagnostics and can fake “success”:**
- Files: `bid_writer/ai_writer.py`, `bid_writer/timing_logger.py`, `bid_writer/gui.py`, `bid_writer/config.py`
- Why fragile: Trace finalization failures are swallowed in `AIWriter._finalize_trace_session_async()` at lines 405-427, timing log write failures are swallowed in `write_timing_log()` at `bid_writer/timing_logger.py` lines 22-36, and multiple GUI/Tk exception paths use bare `pass` in `bid_writer/gui.py`. This makes operational failures hard to distinguish from successful runs.
- Safe modification: Replace silent `pass` blocks with bounded logging to a fallback stderr/file sink, and surface trace/log write failures in the status bar when they affect auditability.
- Test coverage: No automated tests were detected for trace creation, GUI shutdown behavior, or config reload paths.

**Context pruning configuration surface is larger than the implemented behavior:**
- Files: `bid_writer/config.py`, `bid_writer/context_pruner.py`, `bid_writer/ai_writer.py`, `README.md`
- Why fragile: `Config` exposes a full `BID_WRITER_PRUNING_*` API surface at `bid_writer/config.py` lines 552-620, and README documents pruning model settings at lines 79-83 and 238-239. But `ChapterContextPruner` is a rule-based transformer with no client construction or remote calls in `bid_writer/context_pruner.py` lines 100-120, and the only `OpenAI(...)` client in the codebase is the main generation client in `bid_writer/ai_writer.py` lines 69-78.
- Safe modification: Either remove the unused pruning API settings or implement the missing remote-brief path behind an explicit feature flag so operators know what is actually active.
- Test coverage: No tests verify pruning-mode configuration behavior or guard against future code/docs divergence.

## Scaling Limits

**Batch generation is strictly serial and cannot stop an in-flight request:**
- Current capacity: One heading is generated at a time in the desktop process.
- Limit: Total runtime scales linearly with the number of sections, and “停止本轮” only takes effect after the current heading finishes.
- Scaling path: `_do_batch_generate()` processes headings in a for-loop at `bid_writer/gui.py` lines 1318-1380`, and `request_stop_generation()` only flips a flag at lines 1512-1519. Add cancellable request tokens, persist queue state, and support resuming large batches from completed heading IDs instead of re-running manually.

**GUI responsiveness depends on local Tk event processing and long-lived worker coordination:**
- Current capacity: Suitable for one interactive operator on one machine.
- Limit: Large outlines plus long streaming responses amplify the cost of repeated tree refreshes, modal dialogs, and per-heading window creation in `bid_writer/gui.py`.
- Scaling path: Move generation job orchestration out of the window class, reuse a single progress surface, and keep the GUI as a thin client over resumable background tasks.

## Dependencies at Risk

**`openai` is loosely pinned with no compatibility guardrails:**
- Risk: `pyproject.toml` accepts any `openai>=1.0.0` release with no upper bound, while the app depends on specific `chat.completions.create(...)` request and streaming behavior in `bid_writer/ai_writer.py`.
- Impact: A future SDK change can break generation or streaming semantics without repository-level tests catching it first.
- Migration plan: Pin to a known-good minor series, add a smoke test for sync and streaming completion flows, and only upgrade after verifying both desktop and trace behaviors.

## Missing Critical Features

**Automated tests and CI are absent:**
- Problem: No `tests/` directory, no `pytest`/`tox` config, and no CI configuration were detected. `pyproject.toml` only defines runtime dependencies and packaging metadata.
- Blocks: Safe refactoring of `bid_writer/gui.py`, validation of config reload behavior, regression checks for output overwrite policy, and confidence in future SDK upgrades.

**Portable starter configuration is missing:**
- Problem: The repository lacks a runnable, machine-neutral config example. The only checked-in config, `config_公共服务满意度.yaml`, is tied to one user’s absolute filesystem paths.
- Blocks: Fast onboarding, reproducible local setup, and reliable issue reproduction across machines.

**No structured recovery for partially completed large batches:**
- Problem: Batch progress is shown in the UI, but there is no persisted job state, resume marker, or per-heading retry queue beyond whatever files already happened to save.
- Blocks: Safe execution of long multi-section jobs on unstable networks or after user interruption.

## Test Coverage Gaps

**Config loading and config switching:**
- What's not tested: `.env` precedence, reload behavior, and cross-config switching within one process.
- Files: `bid_writer/config.py`, `bid_writer/gui.py`, `bid_writer/gui_state.py`
- Risk: Incorrect credentials or endpoints can be used silently after a config switch.
- Priority: High

**Output persistence and overwrite safety:**
- What's not tested: Stable `heading_id` path selection, overwrite-vs-version behavior, metadata compatibility, and merge output correctness.
- Files: `bid_writer/file_saver.py`, `bid_writer/main.py`
- Risk: Manual edits can be lost and wrong files can be picked during preview or merge.
- Priority: High

**Trace logging and sensitive-data handling:**
- What's not tested: Redaction boundaries, trace write failures, async finalization, and debug-dump exposure.
- Files: `bid_writer/generation_trace.py`, `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`
- Risk: Confidential content can be written unexpectedly, and audit artifacts can fail silently.
- Priority: High

**GUI rendering and large-outline behavior:**
- What's not tested: Status/filter rendering cost, stop-request behavior, preview/save flow, and config-switch regressions.
- Files: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`, `bid_writer/outline_parser.py`
- Risk: Large real-world outlines can become slow or fragile with no regression signal.
- Priority: Medium

---

*Concerns audit: 2026-04-02*
