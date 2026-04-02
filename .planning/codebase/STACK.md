# Technology Stack

**Analysis Date:** 2026-04-02

## Languages

**Primary:**
- Python `>=3.10` - Application runtime and all executable code in `bid_writer/*.py`, `run.py`, and packaging metadata in `pyproject.toml`.

**Secondary:**
- YAML - Runtime configuration in `config_公共服务满意度.yaml` and serialization support in `bid_writer/config.py` and `bid_writer/file_saver.py`.
- Markdown - Primary content/input format for outlines, bid requirements, scoring criteria, and generated output in `outline.md`, `投标大纲.md`, `项目要求/*.md`, `bid_writer/outline_parser.py`, and `bid_writer/file_saver.py`.
- TOML - Packaging and dependency declaration in `pyproject.toml`; resolved dependency lock in `uv.lock`.
- JSON - GUI state and logging artifacts in `bid_writer/gui_state.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py`.

## Runtime

**Environment:**
- CPython `>=3.10` - Declared in `pyproject.toml`.
- Desktop local process with stdlib Tk support - `bid_writer/gui.py` imports `tkinter`/`ttk` and includes Tcl/Tk environment bootstrap logic via `TCL_LIBRARY` and `TK_LIBRARY`.

**Package Manager:**
- `uv` - Installation and execution flow is documented in `README.md` and `AGENTS.md`.
- Lockfile: present in `uv.lock`.

**Entry Commands:**
- `uv run python run.py` - GUI launcher defined by `run.py`.
- `uv run bid-writer` - Console script entry declared in `pyproject.toml` as `bid_writer.main:main`.
- `uv run python -m bid_writer.main -c <config>` - Module entry path supported by `bid_writer/main.py`.

## Frameworks

**Core:**
- Stdlib `tkinter` / `ttk` - Desktop GUI in `bid_writer/gui.py`.
- OpenAI Python SDK `2.9.0` - LLM client in `bid_writer/ai_writer.py`, locked in `uv.lock`.
- PyYAML `6.0.3` - YAML config parsing and front-matter serialization in `bid_writer/config.py` and `bid_writer/file_saver.py`, locked in `uv.lock`.

**Testing:**
- Not detected. No `pytest`, `unittest` suite, `tests/` package, or test runner config is present in `pyproject.toml` or the repository tree.

**Build/Dev:**
- Hatchling - Build backend configured in `pyproject.toml`.
- `argparse` - CLI argument parsing in `run.py` and `bid_writer/main.py`.
- `dataclasses`, `threading`, `queue`, `pathlib` - Core implementation patterns across `bid_writer/ai_writer.py`, `bid_writer/gui.py`, `bid_writer/main.py`, and `bid_writer/context_pruner.py`.

## Key Dependencies

**Critical:**
- `openai` `2.9.0` - Only network-facing SDK; used to call `chat.completions.create(...)` in `bid_writer/ai_writer.py`.
- `pyyaml` `6.0.3` - Required for config loading in `bid_writer/config.py` and optional YAML front matter in `bid_writer/file_saver.py`.

**Infrastructure:**
- `httpx` `0.28.1`, `httpcore` `1.0.9`, `h11` `0.16.0`, `anyio` `4.12.0`, `sniffio` `1.3.1`, `certifi` `2025.11.12`, `idna` `3.11` - HTTP transport chain pulled in through `openai`, locked in `uv.lock`.
- `pydantic` `2.12.5`, `pydantic-core` `2.41.5`, `annotated-types` `0.7.0`, `typing-extensions` `4.15.0`, `typing-inspection` `0.4.2`, `jiter` `0.12.0`, `distro` `1.9.0`, `tqdm` `4.67.1` - OpenAI SDK support dependencies locked in `uv.lock`.

## Configuration

**Environment:**
- Runtime config is loaded from YAML via `bid_writer/config.py`.
- `bid_writer/config.py` loads `.env` and then `.env.local` from the selected config file directory, without overriding variables already present in the parent shell.
- `.env.example` documents the supported environment contract.
- `.env.local` and `.env.local_oMlx` are present in the repository root; contents were not inspected.
- Primary env vars: `BID_WRITER_API_BASE_URL`, `BID_WRITER_API_KEY`, `BID_WRITER_MODEL`, `BID_WRITER_TEMPERATURE`, `BID_WRITER_MAX_TOKENS`, `BID_WRITER_TIMEOUT_SECONDS`, `BID_WRITER_MAX_RETRIES`, `BID_WRITER_TOP_P`, `BID_WRITER_SEED`, `BID_WRITER_STREAM_IDLE_TIMEOUT_SECONDS`.
- Optional pruning-model env vars: `BID_WRITER_PRUNING_API_BASE_URL`, `BID_WRITER_PRUNING_API_KEY`, `BID_WRITER_PRUNING_MODEL`, `BID_WRITER_PRUNING_TEMPERATURE`, `BID_WRITER_PRUNING_MAX_TOKENS`, `BID_WRITER_PRUNING_TIMEOUT_SECONDS`, `BID_WRITER_PRUNING_MAX_RETRIES`, `BID_WRITER_PRUNING_TOP_P`, `BID_WRITER_PRUNING_SEED`.

**Build:**
- Build config lives in `pyproject.toml`.
- Dependency lock lives in `uv.lock`.
- No Dockerfile, container orchestration config, Node toolchain, or frontend bundler config is detected in the repository root.

## Packaging

**Python Package:**
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

**Development:**
- Python `>=3.10`.
- `uv` installed locally.
- A Python build with Tcl/Tk support available to `tkinter`; `bid_writer/gui.py` attempts to repair `TCL_LIBRARY` and `TK_LIBRARY` automatically for `uv`-managed interpreters.
- Network access to an OpenAI-compatible HTTPS endpoint configured through YAML or environment variables.

**Production:**
- The codebase is set up as a local desktop application, not a deployed web service.
- Expected deployment target is a user workstation with filesystem access for reading local Markdown/YAML inputs and writing outputs/logs.

---

*Stack analysis: 2026-04-02*
