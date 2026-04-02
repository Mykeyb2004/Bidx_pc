# Testing Patterns

**Analysis Date:** 2026-04-02

## Test Framework

**Runner:**
- Not detected.
- Config: Not detected in `pytest.ini`, `tox.ini`, `noxfile.py`, `conftest.py`, or any `tests/` directory under the repository root.

**Assertion Library:**
- Not detected.

**Run Commands:**
```bash
uv run python -m compileall bid_writer run.py   # Syntax-only validation that currently succeeds
uv run python run.py --config config.yaml        # Manual GUI smoke run if local config and Tk are available
uv run bid-writer --config config.yaml           # Package entrypoint smoke run
```

## Current Validation Reality

- Validation is primarily manual and GUI-driven. `README.md`, `run.py`, and `bid_writer/gui.py` define the current workflow as starting the desktop application, loading a config file, selecting outline leaves, generating content, previewing output, and optionally merging chapters.
- There are no committed automated tests, fixtures, or test helpers under `tests/` or next to source modules in `bid_writer/`.
- A lightweight machine check exists via bytecode compilation. `uv run python -m compileall bid_writer run.py` completes successfully in the current workspace and is the only repository-wide verification command confirmed during this analysis.
- Observability for manual debugging exists through `bid_writer/timing_logger.py` and `bid_writer/generation_trace.py`, which write timing events and generation traces under `log/`. These logs support diagnosis but are not assertions.

## Test File Organization

**Location:**
- Not detected. No current convention is enforced by existing tests.
- Practical location for new tests: create a top-level `tests/` package, matching the repository instruction in `AGENTS.md` and keeping test code out of `bid_writer/`.

**Naming:**
- Not detected.
- Practical baseline: use `tests/test_<module>.py` for module-focused tests such as `tests/test_config.py` and `tests/test_file_saver.py`.

**Structure:**
```text
tests/
├── test_config.py
├── test_outline_parser.py
├── test_file_saver.py
├── test_gui_state.py
├── test_bid_writer_merge.py
└── test_ai_writer.py
```

## Test Structure

**Suite Organization:**
```python
# Not detected in the current repository.
# Use module-level pytest functions for pure logic modules and small test classes only when shared setup is clearer.
```

**Patterns:**
- Setup pattern: not detected.
- Teardown pattern: not detected.
- Assertion pattern: not detected.
- Current manual validation pattern is stateful and user-facing:
  - Load config through `bid_writer/gui.py` or `run.py`
  - Verify outline parsing via tree rendering from `bid_writer/outline_parser.py`
  - Generate content through `bid_writer/ai_writer.py`
  - Confirm saved files and generated status through `bid_writer/file_saver.py` and `bid_writer/gui_adapter.py`
  - Merge generated sections through `BidWriter.merge_generated_sections()` in `bid_writer/main.py`

## Mocking

**Framework:** Not detected

**Patterns:**
```python
# Not detected in the current repository.
```

**What to Mock:**
- Mock `openai.OpenAI` calls in `bid_writer/ai_writer.py`; network-backed generation should not run in unit tests.
- Mock or monkeypatch filesystem locations for `bid_writer/file_saver.py`, `bid_writer/gui_state.py`, `bid_writer/timing_logger.py`, and `bid_writer/generation_trace.py` so tests use temporary directories.
- Mock `messagebox`, `filedialog`, and Tk widget shells only in narrow GUI tests; keep most coverage below `bid_writer/gui.py`.

**What NOT to Mock:**
- Do not mock pure parsing and normalization logic in `bid_writer/outline_parser.py`, `bid_writer/config.py` helper methods, `bid_writer/file_saver.py` filename/metadata helpers, or `BidWriter.merge_generated_sections()` path-order logic unless the dependency is truly external.
- Do not mock the data shape of `HeadingNode`; construct real `HeadingNode` trees or parse real outline text instead.

## Fixtures and Factories

**Test Data:**
```python
# Not detected in the current repository.
# Grounded recommendation:
# - store sample Markdown outlines as text fixtures
# - store small YAML configs in tmp paths during tests
# - generate saved chapter files through FileSaver instead of hand-writing filenames
```

**Location:**
- Not detected.
- Practical baseline:
  - Inline small text fixtures directly in `tests/test_outline_parser.py` and `tests/test_config.py`
  - Put larger fixture files under `tests/fixtures/` if they need to mirror real outline or YAML files

## Coverage

**Requirements:** None enforced

**View Coverage:**
```bash
# Not applicable until a test runner is added
```

## Test Types

**Unit Tests:**
- Not currently used.
- Highest-value first targets are deterministic modules:
  - `bid_writer/outline_parser.py` for heading depth, parent/child links, leaf selection, and context strings
  - `bid_writer/config.py` for YAML loading, env override precedence, inline-vs-file content loading, and path resolution
  - `bid_writer/file_saver.py` for filename sanitization, stable `heading_id`, legacy filename compatibility, front matter stripping, and merge-body loading
  - `bid_writer/gui_state.py` for startup candidate ordering and invalid-state fallback
  - `bid_writer/context_pruner.py` for scoring row routing and requirement block selection on representative Chinese text inputs

**Integration Tests:**
- Not currently used.
- The most practical integration seam is `BidWriter` in `bid_writer/main.py` because it wires `Config`, `AIWriter`, `FileSaver`, and `parse_outline()` together.
- Add integration tests for:
  - `BidWriter.load_outline()` with a temporary config and outline file
  - `BidWriter.merge_generated_sections()` to verify heading ordering, skipped missing sections, and CRLF normalization behavior
  - `AIWriter.prepare_generation()` plus `finalize_generation()` with a mocked OpenAI client and a real `Config`

**E2E Tests:**
- Not used.
- Full GUI E2E is not the best first step because `bid_writer/gui.py` is large, Tkinter-specific, and environment-sensitive.
- A minimal smoke test for `run.py --help` or package importability is cheaper than automating full widget flows initially.

## Practical Recommendations

- Add `pytest` as a dev dependency in `pyproject.toml` and standardize on `uv run pytest` as the default test command. This matches the repository’s existing `uv` workflow and avoids inventing a second package manager.
- Start with pure-logic coverage before touching Tkinter:
  - `tests/test_outline_parser.py`
  - `tests/test_config.py`
  - `tests/test_file_saver.py`
  - `tests/test_gui_state.py`
- Add one integration module, `tests/test_bid_writer_merge.py`, that builds a temporary config, outline file, and output directory to validate the highest-value orchestration path without calling the network.
- Add one mocked AI module, `tests/test_ai_writer.py`, focused on:
  - request option assembly in `AIWriter.prepare_generation()`
  - stream idle-timeout behavior in `_stream_expand_raw()`
  - format repair and trace finalization in `finalize_generation()`
- Treat `bid_writer/gui.py` as a late-stage target. For now, cover it indirectly through `GUIAdapter` in `bid_writer/gui_adapter.py` and by keeping logic extracted below the widget layer.
- Keep `uv run python -m compileall bid_writer run.py` as a pre-test smoke command even after pytest is added, because it cheaply catches syntax/import regressions across every module.

## Common Patterns

**Async Testing:**
```python
# Not detected.
# Practical target: test AI stream code by feeding a fake iterator into the mocked OpenAI response
# and asserting the collected chunks plus timeout/error handling in `bid_writer/ai_writer.py`.
```

**Error Testing:**
```python
# Not detected.
# Practical target: assert explicit failure modes such as:
# - FileNotFoundError from `Config.load()` / `Config.get_outline_content()`
# - ValueError / RuntimeError from `BidWriter.merge_generated_sections()`
# - fallback-to-default behavior in `load_gui_state()` and metadata readers
```

## Missing Critical Coverage

- `bid_writer/gui.py` has no automated protection despite containing most user interaction, state transitions, and threading coordination.
- `bid_writer/ai_writer.py` has no tests around streaming, timeout behavior, post-processing, or trace finalization, even though it handles the most failure-prone external integration.
- `bid_writer/context_pruner.py` has no regression coverage for Chinese-text heuristics and regex-heavy routing logic.
- `bid_writer/file_saver.py` and `bid_writer/gui_adapter.py` have no coverage for legacy filename compatibility, which directly affects whether previously generated chapters are detected.
- `bid_writer/config.py` has no test coverage for `.env` precedence and path resolution, both of which determine startup correctness.

---

*Testing analysis: 2026-04-02*
