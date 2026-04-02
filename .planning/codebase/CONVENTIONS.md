# Coding Conventions

**Analysis Date:** 2026-04-02

## Naming Patterns

**Files:**
- Use `snake_case.py` module names throughout `bid_writer/`, matching files such as `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, `bid_writer/gui_state.py`, and `bid_writer/generation_trace.py`.
- Keep top-level entrypoints minimal and explicitly named: `run.py` launches the GUI, and `bid_writer/main.py` exposes the package entrypoint plus the shared `BidWriter` service object.
- Place planning documents under `.planning/codebase/` and operational artifacts under `log/` or `output/`, not inside `bid_writer/`.

**Functions:**
- Use `snake_case` for functions and methods across the codebase, including public service methods such as `Config.get_outline_content()` in `bid_writer/config.py`, `AIWriter.prepare_generation()` in `bid_writer/ai_writer.py`, and UI callbacks such as `MainWindow.batch_generate()` in `bid_writer/gui.py`.
- Prefix non-public helpers with `_`, especially when they are internal parsing, prompt-building, or UI plumbing methods. This is consistent in `bid_writer/config.py`, `bid_writer/file_saver.py`, `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, and `bid_writer/gui.py`.
- Use `on_*` names for Tkinter event handlers and dialog actions in `bid_writer/gui.py`, for example `on_tree_open_close()`, `on_ok()`, and `on_cancel()`.

**Variables:**
- Use descriptive English identifiers for runtime state, even when user-facing text is Chinese. Examples include `selected_headings`, `min_words_default`, `trace_session`, and `generated_leaf_count` in `bid_writer/gui.py` and `bid_writer/ai_writer.py`.
- Use widget-specific prefixes in the GUI layer: `btn_*` for buttons, `*_text` for `StringVar` display state, `*_var` for mutable Tk variables, and `tree_*` for tree-specific state in `bid_writer/gui.py`.
- Use uppercase module constants for regexes, filenames, and defaults, as shown by `STATE_FILENAME` in `bid_writer/gui_state.py`, `_LOG_PATH` in `bid_writer/timing_logger.py`, and multiple compiled regex constants in `bid_writer/context_pruner.py` and `bid_writer/ai_writer.py`.

**Types:**
- Use `PascalCase` for classes and dataclasses, including `BidWriter` in `bid_writer/main.py`, `FileSaver` in `bid_writer/file_saver.py`, `GUIAdapter` in `bid_writer/gui_adapter.py`, `HeadingNode` in `bid_writer/outline_parser.py`, and result/state records such as `MergedBidResult`, `GUIState`, `PromptBuildResult`, and `PreparedGeneration`.
- Prefer modern built-in generics and union syntax where available, e.g. `list[str]`, `dict[str, Any]`, and `tuple[str, Optional[str], Optional[str]]` in `bid_writer/config.py`, `bid_writer/file_saver.py`, and `bid_writer/ai_writer.py`.

## Code Style

**Formatting:**
- No formatter configuration is detected in `pyproject.toml`, `.prettierrc*`, `ruff.toml`, or `black`/`isort` settings. Preserve the existing handwritten style instead of introducing a new tool-specific style ad hoc.
- Use 4-space indentation and keep docstrings on modules, classes, and most public methods. This pattern is consistent across `bid_writer/main.py`, `bid_writer/config.py`, `bid_writer/file_saver.py`, `bid_writer/gui.py`, and `bid_writer/context_pruner.py`.
- Keep user-facing strings and docstrings in Chinese when the feature is user-facing, but keep code identifiers in English. `bid_writer/gui.py` and `README.md` establish this mixed-language convention.
- Keep lines grouped by responsibility with blank lines between setup blocks, helper blocks, and return blocks. Small helper methods are common; very long methods are concentrated in `bid_writer/gui.py`.

**Linting:**
- No lint configuration is detected. Future code should still follow the repository’s de facto rules:
  - Keep imports grouped as standard library first, then third-party, then local imports, as seen in `bid_writer/config.py`, `bid_writer/main.py`, and `bid_writer/ai_writer.py`.
  - Keep private helpers near the public method they support when the module is small (`bid_writer/gui_state.py`, `bid_writer/timing_logger.py`), and group related helper families together in larger modules (`bid_writer/config.py`, `bid_writer/ai_writer.py`).
  - Avoid introducing new stylistic one-offs in files that already have a stable pattern.

## Import Organization

**Order:**
1. Standard library imports such as `argparse`, `os`, `re`, `threading`, `queue`, `json`, and `pathlib.Path`.
2. Third-party imports such as `yaml` in `bid_writer/config.py` and `openai.OpenAI` in `bid_writer/ai_writer.py`.
3. Local package imports such as `from .config import Config` and `from .outline_parser import HeadingNode`.

**Path Aliases:**
- Not detected. Imports are all relative within `bid_writer/`, for example `from .main import BidWriter` in `bid_writer/gui.py` and `from .context_pruner import ChapterContextPruner` in `bid_writer/ai_writer.py`.

## Error Handling

**Patterns:**
- Raise explicit exceptions for blocking configuration and filesystem failures in lower layers, for example `FileNotFoundError` in `bid_writer/config.py` and `bid_writer/gui.py`, `RuntimeError` and `ValueError` in `bid_writer/main.py`, and `TimeoutError` in `bid_writer/ai_writer.py`.
- Return safe defaults for non-critical parsing or metadata failures. `bid_writer/config.py` returns `None`, `[]`, or fallback defaults for malformed values; `bid_writer/file_saver.py` returns `{}` for unreadable metadata and `None` for missing matches; `bid_writer/gui_state.py` falls back to a fresh `GUIState()` on invalid JSON.
- Convert exceptions into user-visible dialogs in the GUI layer instead of leaking tracebacks to the user. `bid_writer/gui.py` uses `messagebox.showerror()`, `showwarning()`, and `showinfo()` for recoverable user flows.
- Preserve lightweight CLI behavior in entrypoints: `bid_writer/main.py` prints an error and exits non-zero for startup failures, and handles `KeyboardInterrupt` cleanly.
- Finalize trace artifacts on generation failure in `bid_writer/ai_writer.py` rather than dropping error context completely.

**Consistency Smells:**
- Broad `except Exception` blocks appear in `bid_writer/gui.py`, `bid_writer/ai_writer.py`, `bid_writer/main.py`, and `bid_writer/timing_logger.py`. Keep them only at user-boundary or logging-boundary seams; avoid extending this pattern into pure logic code.
- Some failures are silent by design. `bid_writer/timing_logger.py` swallows all logging errors, and `bid_writer/file_saver.py` suppresses metadata parse failures. This keeps the UI responsive but reduces diagnosability.
- Error strategy varies by layer: low-level config helpers tend to return fallbacks, while orchestration methods raise. Preserve that split instead of mixing `None` returns and exceptions inside the same new API.

## State Management

**Patterns:**
- Keep durable business services on `BidWriter` in `bid_writer/main.py`. It owns `Config`, `AIWriter`, and `FileSaver`, and rebuilds them together via `_rebuild_services()`.
- Keep GUI state in `MainWindow` instance attributes in `bid_writer/gui.py`, not in a separate store. Important flags include `is_generating`, `stop_requested`, `visible_leaf_count`, `generated_leaf_count`, `tree_node_map`, and `tree_view_state`.
- Use small dataclasses for structured state passed across layers: `TreeViewState` in `bid_writer/gui.py`, `GUIState` in `bid_writer/gui_state.py`, `MergedBidResult` in `bid_writer/main.py`, and prompt/result dataclasses in `bid_writer/ai_writer.py`.
- Bridge background work back into Tk only through `queue.Queue` plus `after()` polling. `MainWindow.GenerationWindow` in `bid_writer/gui.py` is the established thread-safe pattern for stream updates.
- Persist only UI session state to disk. `bid_writer/gui_state.py` stores `last_config_path` in `.bid_writer_gui_state.json`; generated-output status is recomputed by scanning files in `bid_writer/gui_adapter.py` rather than restored from a separate history database.

## Logging

**Framework:** Custom file-based logging

**Patterns:**
- Use `write_timing_log()` in `bid_writer/timing_logger.py` for JSON-lines timing events under `log/generation_timing.log`.
- Use `GenerationTraceLogger` and `GenerationTraceSession` in `bid_writer/generation_trace.py` for structured per-generation artifacts under `log/generation_traces/`.
- Prefer writing logs and traces from service code (`bid_writer/ai_writer.py`, `bid_writer/gui.py`) instead of sprinkling `print()` statements. The only remaining console output is top-level CLI error/status text in `bid_writer/main.py`.
- Treat logging as best-effort. Logging failures must not block generation or UI interaction.

## History And Output Tracking

**Patterns:**
- There is no dedicated `history.py` module in the current repository. Future work should treat `bid_writer/gui_adapter.py`, `bid_writer/file_saver.py`, `bid_writer/gui_state.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py` as the effective history/output-tracking surface.
- Use file existence plus stable `heading_id` matching in `bid_writer/file_saver.py` and `bid_writer/gui_adapter.py` to determine whether a section is generated.
- Use YAML front matter only for traceable save flows such as `FileSaver.save_with_metadata()` in `bid_writer/file_saver.py`; standard output files from `FileSaver.save()` intentionally remain clean Markdown.
- Keep generated artifacts out of source modules. `output/`, `log/`, and `.bid_writer_gui_state.json` are already separated from `bid_writer/`.

## CLI And UI Patterns

**CLI/Entrypoints:**
- Keep `run.py` and `bid_writer/main.py` as thin launchers that parse arguments and delegate to `bid_writer.gui.run_gui()`.
- Add new command-line options in one place only. `run.py` and `bid_writer/main.py` already overlap on `--config`; avoid expanding that duplication without first consolidating the argument surface.

**Tkinter UI:**
- Contain Tk-specific widget construction, event binding, dialogs, and `messagebox` calls inside `bid_writer/gui.py`.
- Keep model/service code out of widget classes. `GUIAdapter` in `bid_writer/gui_adapter.py` is the current read-oriented façade between the tree UI and `BidWriter`.
- When adding asynchronous UI behavior, follow the nested `GenerationWindow` pattern in `bid_writer/gui.py`: worker thread produces queue events, main thread updates widgets.
- Update UI affordances together after state changes by calling `update_action_states()`, `update_stats()`, and `status_text.set(...)`, as done in outline reload, generation, and merge flows in `bid_writer/gui.py`.

## Comments

**When to Comment:**
- Use short Chinese comments to clarify non-obvious intent, especially around GUI control flow, filename compatibility, and prompt-format repair. Examples appear in `bid_writer/gui.py`, `bid_writer/file_saver.py`, and `bid_writer/ai_writer.py`.
- Prefer comments that explain why a branch exists, such as compatibility behavior or Tk/runtime workarounds, instead of repeating the code literally.

**JSDoc/TSDoc:**
- Not applicable. Python docstrings are the primary inline documentation mechanism.

## Function Design

**Size:**
- Small utility modules keep functions compact and single-purpose, as in `bid_writer/gui_state.py` and `bid_writer/timing_logger.py`.
- Large workflow code currently accumulates inside `MainWindow` in `bid_writer/gui.py` and helper-heavy services such as `AIWriter` in `bid_writer/ai_writer.py`. Future changes should prefer extracting cohesive helpers or secondary modules instead of extending already-long UI methods.

**Parameters:**
- Use explicit typed parameters with defaults for user-configurable behavior, for example `PreparedGeneration` fields in `bid_writer/ai_writer.py`, `FileSaver.__init__()` in `bid_writer/file_saver.py`, and `Config` accessors in `bid_writer/config.py`.
- Pass domain objects like `HeadingNode` through service boundaries rather than flattening them early. This is consistent across `bid_writer/main.py`, `bid_writer/file_saver.py`, `bid_writer/gui_adapter.py`, and `bid_writer/ai_writer.py`.

**Return Values:**
- Use typed dataclasses or tuples when multiple values travel together, such as `MergedBidResult` in `bid_writer/main.py`, `PromptBuildResult` and `FinalizeResult` in `bid_writer/ai_writer.py`, and tuple returns in `bid_writer/gui_state.py` and `bid_writer/file_saver.py`.
- Return strings as status codes only at UI orchestration seams. `_generate_with_preview()` in `bid_writer/gui.py` returns `"success"`, `"skip"`, or `"failed"`; avoid spreading this pattern into deeper service APIs.

## Module Design

**Exports:**
- Keep modules explicit and direct. There are no barrel modules; consumers import from concrete files such as `bid_writer/config.py`, `bid_writer/ai_writer.py`, and `bid_writer/file_saver.py`.
- Preserve the current boundary split:
  - `run.py` and `bid_writer/main.py` for startup and shared orchestration.
  - `bid_writer/gui.py` for Tkinter-only concerns.
  - `bid_writer/gui_adapter.py` for tree/status adaptation.
  - `bid_writer/config.py` for YAML and env resolution.
  - `bid_writer/outline_parser.py`, `bid_writer/file_saver.py`, and `bid_writer/gui_state.py` for focused utility logic.
  - `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py` for generation, context shaping, and observability.

**Barrel Files:**
- Not used. `bid_writer/__init__.py` exists but does not act as a re-export hub.

## Consistency Risks To Watch

- `bid_writer/gui.py` is the dominant hotspot for UI behavior and state. Add new dialogs or tree logic cautiously and prefer extraction before more feature growth.
- `README.md` and `AGENTS.md` still describe terminal/history-oriented modules that are not present in the current tree, while the actual implementation is GUI-first. Future planning should trust the code in `bid_writer/` over stale narrative docs.
- `pyproject.toml` declares only `pyyaml` and `openai`, but the repository workflow also depends on Tk support at runtime. Treat GUI availability as an implicit platform requirement when changing setup or tests.
- `bid_writer/__pycache__/` exists in the working tree while `.gitignore` only ignores `/__pycache__/` at the repository root. Avoid relying on cache files and extend ignore rules if this repository starts enforcing cleanliness checks.

---

*Convention analysis: 2026-04-02*
