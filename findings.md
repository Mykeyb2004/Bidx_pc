# Findings & Decisions

## Requirements
- The application can now be treated as GUI-only.
- CLI compatibility code can be removed rather than preserved.
- The history JSON feature can be removed entirely.
- The user explicitly invoked `planning-with-files`, so task state should be persisted in project files.

## Research Findings
- `gui.py` uses `BidWriter` only as a core service holder for config, parser, AI client, file saver, and output status.
- `GUIAdapter` currently reaches into `TerminalUI` internals for `_generated_titles`, `_refresh_generated_titles()`, and `get_heading_generation_status()`.
- `main.py` still contains the old terminal workflow (`run_expansion`, `expand_with_preview`, `batch_expand`, `start_expansion_flow`, menu loop, history display).
- `history.py` is only referenced from `main.py` and `terminal_ui*.py`, not from the active GUI flow.
- `run.py` still exposes a `--gui` flag even though the user now wants the product to be GUI-only.
- Output status scanning must account for `output.prefix`; otherwise generated-file detection breaks when a prefix is configured.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Replace CLI workflow code with a small GUI-oriented core | The GUI already owns selection, confirmation, and preview flows. |
| Remove `HistoryManager` usage instead of leaving dead config | Keeps the codebase aligned with the user's stated product direction. |
| Keep `BidWriter` as the shared core object for now | It minimizes churn in `gui.py` while still letting terminal-only logic be removed. |
| Keep extra keys in existing config files harmlessly ignored | This avoids risky config migration logic while still allowing GUI-only cleanup. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `session-catchup.py` returned no output | Proceeded with a fresh planning setup since no unsynced context was reported. |
| Validation updated tracked `__pycache__` files | Restored only the `.pyc` files that were unchanged before this task, leaving unrelated pre-existing modifications intact. |
| `uv lock` could not access `~/.cache/uv` in sandbox | Re-ran with escalation and updated `uv.lock` successfully. |

## Resources
- `/Users/zhangqijin/PycharmProjects/BidX_simple/bid_writer/main.py`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/bid_writer/gui.py`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/bid_writer/gui_adapter.py`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/bid_writer/config.py`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/run.py`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/pyproject.toml`
- `/Users/zhangqijin/PycharmProjects/BidX_simple/config.example.yaml`

## Visual/Browser Findings
- No browser or image-based findings in this task.
