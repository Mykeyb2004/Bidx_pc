# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered bid writing system (自动标书撰写系统) that generates professional bid content based on Markdown outlines. The system uses Gemini models to expand headings into comprehensive bid sections with Chinese government document standards.

## Development Commands

### Setup and Run
```bash
# Install dependencies using uv
uv sync

# Run the application directly
uv run python run.py

# Or use the installed command
uv run bid-writer

# Run with custom config
uv run python -m bid_writer.main -c custom_config.yaml
```

### Package Management
```bash
# Add new dependencies
uv add package_name

# Update dependencies
uv lock
uv sync
```

## Architecture Overview

The system follows a modular architecture with clear separation of concerns:

### Core Modules (`bid_writer/`)

1. **main.py** - Application entry point and orchestration
   - `BidWriter` class coordinates all components
   - Manages the main workflow loop and user interactions
   - Handles batch expansion and preview workflow

2. **terminal_ui.py** - Interactive terminal interface using Rich and Questionary
   - Implements hierarchical navigation for outline selection
   - Provides real-time streaming content display
   - Handles pagination for large outline trees
   - Tracks generated files to prevent duplicates

3. **ai_writer.py** - AI content generation engine
   - Builds structured prompts from outline context
   - Integrates bid requirements and scoring criteria automatically
   - Stream responses for real-time display
   - Configurable model parameters (temperature, max_tokens)

4. **outline_parser.py** - Markdown outline parsing
   - Parses nested heading structure (1-3 levels)
   - Builds hierarchical tree of `HeadingNode` objects
   - Provides navigation methods for different heading levels
   - Identifies leaf nodes for expansion

5. **config.py** - Configuration management
   - Loads YAML configuration with environment variable overrides
   - Dynamically loads bid requirements and scoring criteria from files
   - Manages API credentials and model settings
   - Provides hot-reload capability

6. **file_saver.py** - Output file management
   - Sanitizes filenames for filesystem safety
   - Handles duplicate filename conflicts
   - Organizes output in structured directories

7. **history.py** - Tracking and statistics
   - Records all generation attempts with metadata
   - Provides statistics on success rates and word counts
   - Supports historical query and analysis

### Configuration System

The system uses a hierarchical configuration approach:
- **config.yaml**: Main configuration file
- **Environment variables**: Override config file (e.g., `BID_WRITER_API_KEY`)
- **Dynamic file loading**: Bid requirements and scoring criteria can be separate files
- **Outline structure**: Markdown file with nested headings defines bid structure

### Key Workflow

1. User selects headings through hierarchical navigation (Chapter → Section → Subsection)
2. System builds comprehensive prompts including:
   - Outline path context
   - Full bid requirements document
   - Scoring criteria for optimization
   - Additional user requirements
3. AI generates content with streaming display
4. User can preview, modify, or regenerate content
5. Approved content is saved with sanitized filenames
6. All operations logged to history for tracking

## Important Implementation Details

### Document Standards
- Output follows Chinese government document formatting (not Markdown)
- Uses numbered hierarchy: 一、 (level 1), （一） (level 2), 1. (level 3), （1） (level 4)
- Content must be professional, technical, and compliance-focused

### AI Prompt Engineering
- System role defines bid writing expert with 20 years of experience
- Three-part structure: Structure Compliance + Content Injection + Scoring Optimization
- Automatically incorporates scoring criteria keywords for higher scores

### File Management
- Output directory: `./output/` (configurable)
- Filename sanitization removes invalid characters
- Duplicate detection based on content title
- Automatic numbered suffix for conflicts

### Error Handling
- Graceful handling of missing files (config, outline)
- API failure recovery with user feedback
- Keyboard interrupt handling for clean exits

## Testing Notes

No automated test suite currently exists. When testing:
- Use sample outline files with representative structure
- Verify API connectivity and credentials
- Test pagination with large outlines (>10 items per level)
- Verify output file naming and conflict resolution
- Check history recording and statistics calculation
- 使用uv作为包管理器，使用uv run 的形式运行和测试代码
- 使用uv run运行和测试代码

<!-- GSD:project-start source:PROJECT.md -->
## Project

**自动标书撰写系统**

这是一个基于 Python + Tkinter 的桌面版标书撰写工具。系统读取 Markdown 大纲、招标需求和评分标准，为用户选中的章节生成可直接进入标书正文的内容，并将结果保存到本地文件。当前工作的重点不是重做产品形态，而是在现有生成链路上系统优化提示词、上下文裁剪和质量验证闭环。

**Core Value:** 在不增加操作负担的前提下，让每个章节都能稳定生成贴合招标要求、结构规范、可直接交付的正文。

### Constraints

- **Tech stack**: 保持 Python + Tkinter + OpenAI Python SDK 现有桌面架构。 — 用户目标是优化生成效果，而不是迁移技术栈。
- **Workflow**: 运行、测试与调试统一通过 `uv run`。 — 仓库约定已明确要求使用 `uv`。
- **Document standard**: 输出必须符合中文政府采购/标书正文风格。 — 这是产品的核心质量标准，不能在调优中弱化。
- **Compatibility**: 现有配置文件需要继续可用。 — brownfield 优化不能要求用户重写所有 YAML。
- **Observability**: 调优结果必须可通过 trace 或样本对比回看。 — 仅凭主观感觉改 prompt 会导致回归不可控。
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python `>=3.10` - Application runtime and all executable code in `bid_writer/*.py`, `run.py`, and packaging metadata in `pyproject.toml`.
- YAML - Runtime configuration in `config_公共服务满意度.yaml` and serialization support in `bid_writer/config.py` and `bid_writer/file_saver.py`.
- Markdown - Primary content/input format for outlines, bid requirements, scoring criteria, and generated output in `outline.md`, `投标大纲.md`, `项目要求/*.md`, `bid_writer/outline_parser.py`, and `bid_writer/file_saver.py`.
- TOML - Packaging and dependency declaration in `pyproject.toml`; resolved dependency lock in `uv.lock`.
- JSON - GUI state and logging artifacts in `bid_writer/gui_state.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py`.
## Runtime
- CPython `>=3.10` - Declared in `pyproject.toml`.
- Desktop local process with stdlib Tk support - `bid_writer/gui.py` imports `tkinter`/`ttk` and includes Tcl/Tk environment bootstrap logic via `TCL_LIBRARY` and `TK_LIBRARY`.
- `uv` - Installation and execution flow is documented in `README.md` and `AGENTS.md`.
- Lockfile: present in `uv.lock`.
- `uv run python run.py` - GUI launcher defined by `run.py`.
- `uv run bid-writer` - Console script entry declared in `pyproject.toml` as `bid_writer.main:main`.
- `uv run python -m bid_writer.main -c <config>` - Module entry path supported by `bid_writer/main.py`.
## Frameworks
- Stdlib `tkinter` / `ttk` - Desktop GUI in `bid_writer/gui.py`.
- OpenAI Python SDK `2.9.0` - LLM client in `bid_writer/ai_writer.py`, locked in `uv.lock`.
- PyYAML `6.0.3` - YAML config parsing and front-matter serialization in `bid_writer/config.py` and `bid_writer/file_saver.py`, locked in `uv.lock`.
- Not detected. No `pytest`, `unittest` suite, `tests/` package, or test runner config is present in `pyproject.toml` or the repository tree.
- Hatchling - Build backend configured in `pyproject.toml`.
- `argparse` - CLI argument parsing in `run.py` and `bid_writer/main.py`.
- `dataclasses`, `threading`, `queue`, `pathlib` - Core implementation patterns across `bid_writer/ai_writer.py`, `bid_writer/gui.py`, `bid_writer/main.py`, and `bid_writer/context_pruner.py`.
## Key Dependencies
- `openai` `2.9.0` - Only network-facing SDK; used to call `chat.completions.create(...)` in `bid_writer/ai_writer.py`.
- `pyyaml` `6.0.3` - Required for config loading in `bid_writer/config.py` and optional YAML front matter in `bid_writer/file_saver.py`.
- `httpx` `0.28.1`, `httpcore` `1.0.9`, `h11` `0.16.0`, `anyio` `4.12.0`, `sniffio` `1.3.1`, `certifi` `2025.11.12`, `idna` `3.11` - HTTP transport chain pulled in through `openai`, locked in `uv.lock`.
- `pydantic` `2.12.5`, `pydantic-core` `2.41.5`, `annotated-types` `0.7.0`, `typing-extensions` `4.15.0`, `typing-inspection` `0.4.2`, `jiter` `0.12.0`, `distro` `1.9.0`, `tqdm` `4.67.1` - OpenAI SDK support dependencies locked in `uv.lock`.
## Configuration
- Runtime config is loaded from YAML via `bid_writer/config.py`.
- `bid_writer/config.py` loads `.env` and then `.env.local` from the selected config file directory, without overriding variables already present in the parent shell.
- `.env.example` documents the supported environment contract.
- `.env.local` and `.env.local_oMlx` are present in the repository root; contents were not inspected.
- Primary env vars: `BID_WRITER_API_BASE_URL`, `BID_WRITER_API_KEY`, `BID_WRITER_MODEL`, `BID_WRITER_TEMPERATURE`, `BID_WRITER_MAX_TOKENS`, `BID_WRITER_TIMEOUT_SECONDS`, `BID_WRITER_MAX_RETRIES`, `BID_WRITER_TOP_P`, `BID_WRITER_SEED`, `BID_WRITER_STREAM_IDLE_TIMEOUT_SECONDS`.
- Optional pruning-model env vars: `BID_WRITER_PRUNING_API_BASE_URL`, `BID_WRITER_PRUNING_API_KEY`, `BID_WRITER_PRUNING_MODEL`, `BID_WRITER_PRUNING_TEMPERATURE`, `BID_WRITER_PRUNING_MAX_TOKENS`, `BID_WRITER_PRUNING_TIMEOUT_SECONDS`, `BID_WRITER_PRUNING_MAX_RETRIES`, `BID_WRITER_PRUNING_TOP_P`, `BID_WRITER_PRUNING_SEED`.
- Build config lives in `pyproject.toml`.
- Dependency lock lives in `uv.lock`.
- No Dockerfile, container orchestration config, Node toolchain, or frontend bundler config is detected in the repository root.
## Packaging
- Distribution name: `bid-writer` in `pyproject.toml`.
- Package directory: `bid_writer/`.
- Version: `1.0.0` in `pyproject.toml` and `bid_writer/__init__.py`.
- Wheel packaging target: `bid_writer` via Hatchling in `pyproject.toml`.
## Notable Tooling
- `bid_writer/ai_writer.py` supports both streaming and synchronous completions, with post-processing and timeout handling around the OpenAI client.
- `bid_writer/context_pruner.py` performs rule-based local context reduction before generation; it does not add a separate dependency beyond the existing OpenAI-compatible API contract.
- `bid_writer/generation_trace.py` writes structured per-generation artifacts under `log/generation_traces/` by default, or a configured directory from YAML.
- `bid_writer/timing_logger.py` appends JSONL timing events to `log/generation_timing.log`.
- `bid_writer/file_saver.py` writes generated Markdown sections to the configured output directory and optionally supports YAML front matter.
- `bid_writer/gui_state.py` persists GUI state in `.bid_writer_gui_state.json` at the working-directory root.
## Platform Requirements
- Python `>=3.10`.
- `uv` installed locally.
- A Python build with Tcl/Tk support available to `tkinter`; `bid_writer/gui.py` attempts to repair `TCL_LIBRARY` and `TK_LIBRARY` automatically for `uv`-managed interpreters.
- Network access to an OpenAI-compatible HTTPS endpoint configured through YAML or environment variables.
- The codebase is set up as a local desktop application, not a deployed web service.
- Expected deployment target is a user workstation with filesystem access for reading local Markdown/YAML inputs and writing outputs/logs.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` module names throughout `bid_writer/`, matching files such as `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, `bid_writer/gui_state.py`, and `bid_writer/generation_trace.py`.
- Keep top-level entrypoints minimal and explicitly named: `run.py` launches the GUI, and `bid_writer/main.py` exposes the package entrypoint plus the shared `BidWriter` service object.
- Place planning documents under `.planning/codebase/` and operational artifacts under `log/` or `output/`, not inside `bid_writer/`.
- Use `snake_case` for functions and methods across the codebase, including public service methods such as `Config.get_outline_content()` in `bid_writer/config.py`, `AIWriter.prepare_generation()` in `bid_writer/ai_writer.py`, and UI callbacks such as `MainWindow.batch_generate()` in `bid_writer/gui.py`.
- Prefix non-public helpers with `_`, especially when they are internal parsing, prompt-building, or UI plumbing methods. This is consistent in `bid_writer/config.py`, `bid_writer/file_saver.py`, `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, and `bid_writer/gui.py`.
- Use `on_*` names for Tkinter event handlers and dialog actions in `bid_writer/gui.py`, for example `on_tree_open_close()`, `on_ok()`, and `on_cancel()`.
- Use descriptive English identifiers for runtime state, even when user-facing text is Chinese. Examples include `selected_headings`, `min_words_default`, `trace_session`, and `generated_leaf_count` in `bid_writer/gui.py` and `bid_writer/ai_writer.py`.
- Use widget-specific prefixes in the GUI layer: `btn_*` for buttons, `*_text` for `StringVar` display state, `*_var` for mutable Tk variables, and `tree_*` for tree-specific state in `bid_writer/gui.py`.
- Use uppercase module constants for regexes, filenames, and defaults, as shown by `STATE_FILENAME` in `bid_writer/gui_state.py`, `_LOG_PATH` in `bid_writer/timing_logger.py`, and multiple compiled regex constants in `bid_writer/context_pruner.py` and `bid_writer/ai_writer.py`.
- Use `PascalCase` for classes and dataclasses, including `BidWriter` in `bid_writer/main.py`, `FileSaver` in `bid_writer/file_saver.py`, `GUIAdapter` in `bid_writer/gui_adapter.py`, `HeadingNode` in `bid_writer/outline_parser.py`, and result/state records such as `MergedBidResult`, `GUIState`, `PromptBuildResult`, and `PreparedGeneration`.
- Prefer modern built-in generics and union syntax where available, e.g. `list[str]`, `dict[str, Any]`, and `tuple[str, Optional[str], Optional[str]]` in `bid_writer/config.py`, `bid_writer/file_saver.py`, and `bid_writer/ai_writer.py`.
## Code Style
- No formatter configuration is detected in `pyproject.toml`, `.prettierrc*`, `ruff.toml`, or `black`/`isort` settings. Preserve the existing handwritten style instead of introducing a new tool-specific style ad hoc.
- Use 4-space indentation and keep docstrings on modules, classes, and most public methods. This pattern is consistent across `bid_writer/main.py`, `bid_writer/config.py`, `bid_writer/file_saver.py`, `bid_writer/gui.py`, and `bid_writer/context_pruner.py`.
- Keep user-facing strings and docstrings in Chinese when the feature is user-facing, but keep code identifiers in English. `bid_writer/gui.py` and `README.md` establish this mixed-language convention.
- Keep lines grouped by responsibility with blank lines between setup blocks, helper blocks, and return blocks. Small helper methods are common; very long methods are concentrated in `bid_writer/gui.py`.
- No lint configuration is detected. Future code should still follow the repository’s de facto rules:
## Import Organization
- Not detected. Imports are all relative within `bid_writer/`, for example `from .main import BidWriter` in `bid_writer/gui.py` and `from .context_pruner import ChapterContextPruner` in `bid_writer/ai_writer.py`.
## Error Handling
- Raise explicit exceptions for blocking configuration and filesystem failures in lower layers, for example `FileNotFoundError` in `bid_writer/config.py` and `bid_writer/gui.py`, `RuntimeError` and `ValueError` in `bid_writer/main.py`, and `TimeoutError` in `bid_writer/ai_writer.py`.
- Return safe defaults for non-critical parsing or metadata failures. `bid_writer/config.py` returns `None`, `[]`, or fallback defaults for malformed values; `bid_writer/file_saver.py` returns `{}` for unreadable metadata and `None` for missing matches; `bid_writer/gui_state.py` falls back to a fresh `GUIState()` on invalid JSON.
- Convert exceptions into user-visible dialogs in the GUI layer instead of leaking tracebacks to the user. `bid_writer/gui.py` uses `messagebox.showerror()`, `showwarning()`, and `showinfo()` for recoverable user flows.
- Preserve lightweight CLI behavior in entrypoints: `bid_writer/main.py` prints an error and exits non-zero for startup failures, and handles `KeyboardInterrupt` cleanly.
- Finalize trace artifacts on generation failure in `bid_writer/ai_writer.py` rather than dropping error context completely.
- Broad `except Exception` blocks appear in `bid_writer/gui.py`, `bid_writer/ai_writer.py`, `bid_writer/main.py`, and `bid_writer/timing_logger.py`. Keep them only at user-boundary or logging-boundary seams; avoid extending this pattern into pure logic code.
- Some failures are silent by design. `bid_writer/timing_logger.py` swallows all logging errors, and `bid_writer/file_saver.py` suppresses metadata parse failures. This keeps the UI responsive but reduces diagnosability.
- Error strategy varies by layer: low-level config helpers tend to return fallbacks, while orchestration methods raise. Preserve that split instead of mixing `None` returns and exceptions inside the same new API.
## State Management
- Keep durable business services on `BidWriter` in `bid_writer/main.py`. It owns `Config`, `AIWriter`, and `FileSaver`, and rebuilds them together via `_rebuild_services()`.
- Keep GUI state in `MainWindow` instance attributes in `bid_writer/gui.py`, not in a separate store. Important flags include `is_generating`, `stop_requested`, `visible_leaf_count`, `generated_leaf_count`, `tree_node_map`, and `tree_view_state`.
- Use small dataclasses for structured state passed across layers: `TreeViewState` in `bid_writer/gui.py`, `GUIState` in `bid_writer/gui_state.py`, `MergedBidResult` in `bid_writer/main.py`, and prompt/result dataclasses in `bid_writer/ai_writer.py`.
- Bridge background work back into Tk only through `queue.Queue` plus `after()` polling. `MainWindow.GenerationWindow` in `bid_writer/gui.py` is the established thread-safe pattern for stream updates.
- Persist only UI session state to disk. `bid_writer/gui_state.py` stores `last_config_path` in `.bid_writer_gui_state.json`; generated-output status is recomputed by scanning files in `bid_writer/gui_adapter.py` rather than restored from a separate history database.
## Logging
- Use `write_timing_log()` in `bid_writer/timing_logger.py` for JSON-lines timing events under `log/generation_timing.log`.
- Use `GenerationTraceLogger` and `GenerationTraceSession` in `bid_writer/generation_trace.py` for structured per-generation artifacts under `log/generation_traces/`.
- Prefer writing logs and traces from service code (`bid_writer/ai_writer.py`, `bid_writer/gui.py`) instead of sprinkling `print()` statements. The only remaining console output is top-level CLI error/status text in `bid_writer/main.py`.
- Treat logging as best-effort. Logging failures must not block generation or UI interaction.
## History And Output Tracking
- There is no dedicated `history.py` module in the current repository. Future work should treat `bid_writer/gui_adapter.py`, `bid_writer/file_saver.py`, `bid_writer/gui_state.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py` as the effective history/output-tracking surface.
- Use file existence plus stable `heading_id` matching in `bid_writer/file_saver.py` and `bid_writer/gui_adapter.py` to determine whether a section is generated.
- Use YAML front matter only for traceable save flows such as `FileSaver.save_with_metadata()` in `bid_writer/file_saver.py`; standard output files from `FileSaver.save()` intentionally remain clean Markdown.
- Keep generated artifacts out of source modules. `output/`, `log/`, and `.bid_writer_gui_state.json` are already separated from `bid_writer/`.
## CLI And UI Patterns
- Keep `run.py` and `bid_writer/main.py` as thin launchers that parse arguments and delegate to `bid_writer.gui.run_gui()`.
- Add new command-line options in one place only. `run.py` and `bid_writer/main.py` already overlap on `--config`; avoid expanding that duplication without first consolidating the argument surface.
- Contain Tk-specific widget construction, event binding, dialogs, and `messagebox` calls inside `bid_writer/gui.py`.
- Keep model/service code out of widget classes. `GUIAdapter` in `bid_writer/gui_adapter.py` is the current read-oriented façade between the tree UI and `BidWriter`.
- When adding asynchronous UI behavior, follow the nested `GenerationWindow` pattern in `bid_writer/gui.py`: worker thread produces queue events, main thread updates widgets.
- Update UI affordances together after state changes by calling `update_action_states()`, `update_stats()`, and `status_text.set(...)`, as done in outline reload, generation, and merge flows in `bid_writer/gui.py`.
## Comments
- Use short Chinese comments to clarify non-obvious intent, especially around GUI control flow, filename compatibility, and prompt-format repair. Examples appear in `bid_writer/gui.py`, `bid_writer/file_saver.py`, and `bid_writer/ai_writer.py`.
- Prefer comments that explain why a branch exists, such as compatibility behavior or Tk/runtime workarounds, instead of repeating the code literally.
- Not applicable. Python docstrings are the primary inline documentation mechanism.
## Function Design
- Small utility modules keep functions compact and single-purpose, as in `bid_writer/gui_state.py` and `bid_writer/timing_logger.py`.
- Large workflow code currently accumulates inside `MainWindow` in `bid_writer/gui.py` and helper-heavy services such as `AIWriter` in `bid_writer/ai_writer.py`. Future changes should prefer extracting cohesive helpers or secondary modules instead of extending already-long UI methods.
- Use explicit typed parameters with defaults for user-configurable behavior, for example `PreparedGeneration` fields in `bid_writer/ai_writer.py`, `FileSaver.__init__()` in `bid_writer/file_saver.py`, and `Config` accessors in `bid_writer/config.py`.
- Pass domain objects like `HeadingNode` through service boundaries rather than flattening them early. This is consistent across `bid_writer/main.py`, `bid_writer/file_saver.py`, `bid_writer/gui_adapter.py`, and `bid_writer/ai_writer.py`.
- Use typed dataclasses or tuples when multiple values travel together, such as `MergedBidResult` in `bid_writer/main.py`, `PromptBuildResult` and `FinalizeResult` in `bid_writer/ai_writer.py`, and tuple returns in `bid_writer/gui_state.py` and `bid_writer/file_saver.py`.
- Return strings as status codes only at UI orchestration seams. `_generate_with_preview()` in `bid_writer/gui.py` returns `"success"`, `"skip"`, or `"failed"`; avoid spreading this pattern into deeper service APIs.
## Module Design
- Keep modules explicit and direct. There are no barrel modules; consumers import from concrete files such as `bid_writer/config.py`, `bid_writer/ai_writer.py`, and `bid_writer/file_saver.py`.
- Preserve the current boundary split:
- Not used. `bid_writer/__init__.py` exists but does not act as a re-export hub.
## Consistency Risks To Watch
- `bid_writer/gui.py` is the dominant hotspot for UI behavior and state. Add new dialogs or tree logic cautiously and prefer extraction before more feature growth.
- `README.md` and `AGENTS.md` still describe terminal/history-oriented modules that are not present in the current tree, while the actual implementation is GUI-first. Future planning should trust the code in `bid_writer/` over stale narrative docs.
- `pyproject.toml` declares only `pyyaml` and `openai`, but the repository workflow also depends on Tk support at runtime. Treat GUI availability as an implicit platform requirement when changing setup or tests.
- `bid_writer/__pycache__/` exists in the working tree while `.gitignore` only ignores `/__pycache__/` at the repository root. Avoid relying on cache files and extend ignore rules if this repository starts enforcing cleanliness checks.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- `bid_writer/gui.py` owns the primary runtime loop, user interaction flow, and most orchestration visible to operators.
- `bid_writer/main.py` centralizes shared runtime services in `BidWriter`, so UI code talks to one composite application object instead of constructing dependencies ad hoc.
- The filesystem is part of the runtime model: `bid_writer/config.py` loads YAML and `.env` files, `bid_writer/file_saver.py` persists generated chapters, and status is re-derived by rescanning `output/`.
## Layers
- Purpose: Parse CLI arguments, choose a config file, and start the GUI process.
- Location: `run.py`, `bid_writer/main.py`, `pyproject.toml`
- Contains: Thin wrappers around `bid_writer.gui.run_gui()` and the `bid-writer` console script declaration.
- Depends on: `bid_writer.gui`, `argparse`
- Used by: End users launching `uv run python run.py` or `uv run bid-writer`
- Purpose: Render the outline tree, collect generation parameters, drive batch workflows, and translate exceptions into dialogs and status text.
- Location: `bid_writer/gui.py`
- Contains: `MainWindow`, `ConfigSelectionDialog`, `GenerationWindow`, tree filtering, progress display, preview dialogs, merge prompts, and OS-specific “open output directory” behavior.
- Depends on: `tkinter`, `threading`, `queue`, `bid_writer.main.BidWriter`, `bid_writer.gui_adapter.GUIAdapter`, `bid_writer.gui_state`
- Used by: The process entry points in `run.py` and `bid_writer/main.py`
- Purpose: Keep GUI-specific derived state out of the core services.
- Location: `bid_writer/gui_adapter.py`, `bid_writer/gui_state.py`
- Contains: Output status scanning, heading completion aggregation, last-used-config persistence in `.bid_writer_gui_state.json`
- Depends on: `bid_writer.main.BidWriter`, `bid_writer.file_saver.FileSaver`, `bid_writer.outline_parser.HeadingNode`
- Used by: `bid_writer/gui.py`
- Purpose: Own the long-lived service graph and expose high-level operations the GUI can call.
- Location: `bid_writer/main.py`
- Contains: `BidWriter`, `MergedBidResult`, config reload, outline loading, merge of generated sections
- Depends on: `bid_writer.config.Config`, `bid_writer.ai_writer.AIWriter`, `bid_writer.file_saver.FileSaver`, `bid_writer.outline_parser.parse_outline`
- Used by: `bid_writer/gui.py`, `bid_writer/gui_adapter.py`
- Purpose: Build prompts, call the LLM, post-process output, and optionally emit detailed trace artifacts.
- Location: `bid_writer/ai_writer.py`, `bid_writer/context_pruner.py`, `bid_writer/generation_trace.py`, `bid_writer/timing_logger.py`
- Contains: `AIWriter`, `ChapterContextPruner`, `GenerationTraceLogger`, `GenerationTraceSession`, JSON timing log writes to `log/generation_timing.log`
- Depends on: `openai.OpenAI`, `bid_writer.config.Config`, `bid_writer.outline_parser.HeadingNode`
- Used by: `bid_writer/main.BidWriter`, `bid_writer/gui.py`
- Purpose: Represent the outline tree and map logical headings to stable files on disk.
- Location: `bid_writer/outline_parser.py`, `bid_writer/file_saver.py`, `bid_writer/config.py`
- Contains: `HeadingNode`, `OutlineParser`, filename sanitization, heading ID generation, config coercion, outline/requirements/scoring file reads
- Depends on: `pathlib`, `yaml`, `hashlib`, `re`
- Used by: Nearly every other module in `bid_writer/`
## Data Flow
- Long-lived mutable state lives in `bid_writer/main.py:BidWriter` and `bid_writer/gui.py:MainWindow`.
- Derived UI state such as completion counts and icon/status mapping lives in `bid_writer/gui_adapter.py`.
- Cross-thread communication is limited to the popup generation path in `bid_writer/gui.py`, where a `queue.Queue` transfers tokens and completion signals back to the Tk main thread.
- Persistent state is file-backed rather than database-backed: `.bid_writer_gui_state.json`, `output/*.md`, `log/generation_timing.log`, and optional trace directories under `log/generation_traces/` or `output/_generation_traces/`.
## Key Abstractions
- Purpose: Represents one parsed Markdown heading plus its parent/child relationships and full outline path.
- Examples: `bid_writer/outline_parser.py`, consumers in `bid_writer/gui.py`, `bid_writer/context_pruner.py`, `bid_writer/file_saver.py`
- Pattern: Mutable tree node dataclass passed by reference across UI, prompt building, and file persistence.
- Purpose: Aggregates runtime services and exposes app-level operations.
- Examples: `bid_writer/main.py`
- Pattern: Service-container facade used by the GUI instead of a separate dependency injection framework.
- Purpose: Convert saved files on disk into UI-facing completion state and progress summaries.
- Examples: `bid_writer/gui_adapter.py`
- Pattern: Thin adapter around `BidWriter` plus cached heading IDs; no direct model or prompt logic.
- Purpose: Separate prompt construction, raw generation, and post-processing into explicit handoff objects.
- Examples: `bid_writer/ai_writer.py`
- Pattern: Dataclass-based pipeline stages rather than large tuples or dicts.
- Purpose: Represent one chapter generation’s trace directory and its artifact lifecycle.
- Examples: `bid_writer/generation_trace.py`
- Pattern: Session object with eager initial artifact writes and a later `finalize()` call.
- Purpose: Encapsulate filename policy, stable heading IDs, metadata parsing, and load/save behavior.
- Examples: `bid_writer/file_saver.py`
- Pattern: Filesystem repository object; callers hand it `HeadingNode` objects rather than manipulating paths directly.
- Purpose: Normalize YAML settings, environment overrides, and path resolution into typed properties.
- Examples: `bid_writer/config.py`
- Pattern: Property-based configuration access instead of schema objects or pydantic models.
## Entry Points
- Location: `run.py`
- Triggers: `uv run python run.py [--config ...]`
- Responsibilities: Parse CLI args and forward them to `bid_writer.gui.run_gui()`
- Location: `pyproject.toml`, `bid_writer/main.py`
- Triggers: `uv run bid-writer [--config ...]`
- Responsibilities: Register the `bid-writer` script and provide `main()` as the package-level entry point
- Location: `bid_writer/gui.py`
- Triggers: Imported by `run.py` and `bid_writer/main.py`, or executed directly via `python -m`
- Responsibilities: Ensure Tk runtime availability, resolve a startup config, instantiate `MainWindow`, and run `mainloop()`
## Error Handling
- `bid_writer/main.py:BidWriter.load_outline()` traps parsing and file errors, stores `last_error_message`, and returns `False` so the GUI can keep running.
- `bid_writer/gui.py` catches config-loading, outline-loading, merge, and generation errors close to the user interaction point and surfaces them through `messagebox` plus `status_text`.
- `bid_writer/ai_writer.py` and `bid_writer/generation_trace.py` treat trace finalization and timing logs as best-effort side effects; logging failures do not fail the generation request.
- `bid_writer/gui.py:GenerationWindow` sends exceptions from the background generation thread back to the Tk thread through `queue.Queue` rather than mutating widgets from worker threads.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
