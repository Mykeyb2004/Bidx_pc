# Architecture

**Analysis Date:** 2026-04-02

## Pattern Overview

**Overall:** Stateful single-package desktop application with a Tkinter presentation layer, a thin application-service core, and file-based infrastructure.

**Key Characteristics:**
- `bid_writer/gui.py` owns the primary runtime loop, user interaction flow, and most orchestration visible to operators.
- `bid_writer/main.py` centralizes shared runtime services in `BidWriter`, so UI code talks to one composite application object instead of constructing dependencies ad hoc.
- The filesystem is part of the runtime model: `bid_writer/config.py` loads YAML and `.env` files, `bid_writer/file_saver.py` persists generated chapters, and status is re-derived by rescanning `output/`.

## Layers

**Bootstrap / Process Entry:**
- Purpose: Parse CLI arguments, choose a config file, and start the GUI process.
- Location: `run.py`, `bid_writer/main.py`, `pyproject.toml`
- Contains: Thin wrappers around `bid_writer.gui.run_gui()` and the `bid-writer` console script declaration.
- Depends on: `bid_writer.gui`, `argparse`
- Used by: End users launching `uv run python run.py` or `uv run bid-writer`

**Desktop UI Layer:**
- Purpose: Render the outline tree, collect generation parameters, drive batch workflows, and translate exceptions into dialogs and status text.
- Location: `bid_writer/gui.py`
- Contains: `MainWindow`, `ConfigSelectionDialog`, `GenerationWindow`, tree filtering, progress display, preview dialogs, merge prompts, and OS-specific “open output directory” behavior.
- Depends on: `tkinter`, `threading`, `queue`, `bid_writer.main.BidWriter`, `bid_writer.gui_adapter.GUIAdapter`, `bid_writer.gui_state`
- Used by: The process entry points in `run.py` and `bid_writer/main.py`

**UI Bridge / Persisted UI State:**
- Purpose: Keep GUI-specific derived state out of the core services.
- Location: `bid_writer/gui_adapter.py`, `bid_writer/gui_state.py`
- Contains: Output status scanning, heading completion aggregation, last-used-config persistence in `.bid_writer_gui_state.json`
- Depends on: `bid_writer.main.BidWriter`, `bid_writer.file_saver.FileSaver`, `bid_writer.outline_parser.HeadingNode`
- Used by: `bid_writer/gui.py`

**Application Core:**
- Purpose: Own the long-lived service graph and expose high-level operations the GUI can call.
- Location: `bid_writer/main.py`
- Contains: `BidWriter`, `MergedBidResult`, config reload, outline loading, merge of generated sections
- Depends on: `bid_writer.config.Config`, `bid_writer.ai_writer.AIWriter`, `bid_writer.file_saver.FileSaver`, `bid_writer.outline_parser.parse_outline`
- Used by: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`

**Generation and Prompting Services:**
- Purpose: Build prompts, call the LLM, post-process output, and optionally emit detailed trace artifacts.
- Location: `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, `bid_writer/generation_trace.py`, `bid_writer/timing_logger.py`
- Contains: `AIWriter`, `ChapterContextPruner`, `GenerationTraceLogger`, `GenerationTraceSession`, JSON timing log writes to `log/generation_timing.log`
- Depends on: `openai.OpenAI`, `bid_writer.config.Config`, `bid_writer.outline_parser.HeadingNode`
- Used by: `bid_writer/main.BidWriter`, `bid_writer/gui.py`

**Domain Parsing and File Infrastructure:**
- Purpose: Represent the outline tree and map logical headings to stable files on disk.
- Location: `bid_writer/outline_parser.py`, `bid_writer/file_saver.py`, `bid_writer/config.py`
- Contains: `HeadingNode`, `OutlineParser`, filename sanitization, heading ID generation, config coercion, outline/requirements/scoring file reads
- Depends on: `pathlib`, `yaml`, `hashlib`, `re`
- Used by: Nearly every other module in `bid_writer/`

## Data Flow

**Startup and Outline Load:**

1. `run.py` or the `bid_writer.main:main` console entry parses `--config` and calls `bid_writer.gui.run_gui()`.
2. `bid_writer/gui.py` uses `_build_startup_bid_writer()` plus `bid_writer/gui_state.py:get_startup_config_candidates()` to resolve the first usable config file.
3. `bid_writer/main.py:BidWriter.__init__()` constructs `Config`, then rebuilds `AIWriter` and `FileSaver` from that config.
4. `BidWriter.load_outline()` reads the outline via `bid_writer/config.py:get_outline_content()` and parses it with `bid_writer/outline_parser.py:parse_outline()`.
5. `bid_writer/gui.py:MainWindow._sync_loaded_outline()` refreshes the tree, rescans generated files through `GUIAdapter`, updates counters, and persists the chosen config with `remember_last_config()`.

**Chapter Generation:**

1. `bid_writer/gui.py:MainWindow.batch_generate()` collects selected leaf `HeadingNode` objects from the tree and prompts for additional requirements plus minimum word count.
2. `MainWindow._do_batch_generate()` iterates those headings sequentially on the GUI thread, while each chapter’s model call runs in a background thread created inside `GenerationWindow.start_generation()`.
3. `bid_writer/ai_writer.py:AIWriter.prepare_generation()` builds the prompt and request payload. When `context_pruning` is enabled, it first calls `bid_writer/context_pruner.py:ChapterContextPruner.build_context()` to reduce the amount of outline, requirements, and scoring text passed downstream.
4. `AIWriter.expand_raw()` calls `OpenAI(...).chat.completions.create(...)` using either streaming or non-streaming mode.
5. The generation worker streams chunks through a `queue.Queue`; `GenerationWindow._check_queue()` polls that queue on the Tk main thread and updates the popup text widget.
6. After raw output arrives, `AIWriter.finalize_generation()` performs lightweight normalization and asynchronously finalizes trace artifacts through `GenerationTraceSession.finalize()`.
7. `bid_writer/file_saver.py:FileSaver.save()` writes the chapter Markdown into `output/` using a sanitized title plus a stable heading hash.
8. `GUIAdapter.refresh_generated_titles()` rescans `output/*.md`, making the filesystem the source of truth for “已完成 / 部分完成 / 未生成”.

**Merge of Saved Chapters:**

1. `bid_writer/gui.py:MainWindow.merge_generated_sections()` asks for an output title and delegates to `BidWriter.merge_generated_sections()`.
2. `BidWriter.merge_generated_sections()` walks `parser.get_deepest_headings()` in outline order.
3. For each leaf heading, `FileSaver.find_existing_filepath()` resolves the newest saved file, then `FileSaver.load_section_body()` removes front matter and repeated title headings.
4. `BidWriter.merge_generated_sections()` rebuilds parent headings in Markdown order and writes a single merged file back through `FileSaver.save()`.

**State Management:**
- Long-lived mutable state lives in `bid_writer/main.py:BidWriter` and `bid_writer/gui.py:MainWindow`.
- Derived UI state such as completion counts and icon/status mapping lives in `bid_writer/gui_adapter.py`.
- Cross-thread communication is limited to the popup generation path in `bid_writer/gui.py`, where a `queue.Queue` transfers tokens and completion signals back to the Tk main thread.
- Persistent state is file-backed rather than database-backed: `.bid_writer_gui_state.json`, `output/*.md`, `log/generation_timing.log`, and optional trace directories under `log/generation_traces/` or `output/_generation_traces/`.

## Key Abstractions

**`HeadingNode`:**
- Purpose: Represents one parsed Markdown heading plus its parent/child relationships and full outline path.
- Examples: `bid_writer/outline_parser.py`, consumers in `bid_writer/gui.py`, `bid_writer/context_pruner.py`, `bid_writer/file_saver.py`
- Pattern: Mutable tree node dataclass passed by reference across UI, prompt building, and file persistence.

**`BidWriter`:**
- Purpose: Aggregates runtime services and exposes app-level operations.
- Examples: `bid_writer/main.py`
- Pattern: Service-container facade used by the GUI instead of a separate dependency injection framework.

**`GUIAdapter`:**
- Purpose: Convert saved files on disk into UI-facing completion state and progress summaries.
- Examples: `bid_writer/gui_adapter.py`
- Pattern: Thin adapter around `BidWriter` plus cached heading IDs; no direct model or prompt logic.

**`PreparedGeneration` / `PromptBuildResult` / `FinalizeResult`:**
- Purpose: Separate prompt construction, raw generation, and post-processing into explicit handoff objects.
- Examples: `bid_writer/ai_writer.py`
- Pattern: Dataclass-based pipeline stages rather than large tuples or dicts.

**`GenerationTraceSession`:**
- Purpose: Represent one chapter generation’s trace directory and its artifact lifecycle.
- Examples: `bid_writer/generation_trace.py`
- Pattern: Session object with eager initial artifact writes and a later `finalize()` call.

**`FileSaver`:**
- Purpose: Encapsulate filename policy, stable heading IDs, metadata parsing, and load/save behavior.
- Examples: `bid_writer/file_saver.py`
- Pattern: Filesystem repository object; callers hand it `HeadingNode` objects rather than manipulating paths directly.

**`Config`:**
- Purpose: Normalize YAML settings, environment overrides, and path resolution into typed properties.
- Examples: `bid_writer/config.py`
- Pattern: Property-based configuration access instead of schema objects or pydantic models.

## Entry Points

**GUI Launcher Script:**
- Location: `run.py`
- Triggers: `uv run python run.py [--config ...]`
- Responsibilities: Parse CLI args and forward them to `bid_writer.gui.run_gui()`

**Package CLI Entry:**
- Location: `pyproject.toml`, `bid_writer/main.py`
- Triggers: `uv run bid-writer [--config ...]`
- Responsibilities: Register the `bid-writer` script and provide `main()` as the package-level entry point

**GUI Runtime Entry:**
- Location: `bid_writer/gui.py`
- Triggers: Imported by `run.py` and `bid_writer/main.py`, or executed directly via `python -m`
- Responsibilities: Ensure Tk runtime availability, resolve a startup config, instantiate `MainWindow`, and run `mainloop()`

## Error Handling

**Strategy:** Let lower-level modules raise ordinary Python exceptions, then catch them at the GUI or process boundary and convert them into status messages, message boxes, or clean exits.

**Patterns:**
- `bid_writer/main.py:BidWriter.load_outline()` traps parsing and file errors, stores `last_error_message`, and returns `False` so the GUI can keep running.
- `bid_writer/gui.py` catches config-loading, outline-loading, merge, and generation errors close to the user interaction point and surfaces them through `messagebox` plus `status_text`.
- `bid_writer/ai_writer.py` and `bid_writer/generation_trace.py` treat trace finalization and timing logs as best-effort side effects; logging failures do not fail the generation request.
- `bid_writer/gui.py:GenerationWindow` sends exceptions from the background generation thread back to the Tk thread through `queue.Queue` rather than mutating widgets from worker threads.

## Cross-Cutting Concerns

**Logging:** Structured timing events append to `log/generation_timing.log` via `bid_writer/timing_logger.py`. Richer per-generation artifact bundles are emitted by `bid_writer/generation_trace.py` when `generation_trace.enabled` is true.

**Validation:** `bid_writer/config.py` coerces booleans, ints, floats, optional values, and relative paths; `bid_writer/outline_parser.py` validates headings by regex; `bid_writer/gui.py` only allows generation from leaf headings; `bid_writer/file_saver.py` sanitizes filenames and strips front matter/title wrappers when reloading saved content.

**Authentication:** There is no end-user auth layer. Model credentials are loaded from environment variables and optional local `.env` files by `bid_writer/config.py`, then passed into `openai.OpenAI(...)` inside `bid_writer/ai_writer.py`.

---

*Architecture analysis: 2026-04-02*
