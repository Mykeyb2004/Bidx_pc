# Task Plan: GUI-Only Refactor

## Goal
Refactor the application to be GUI-only by removing CLI-specific compatibility code and dropping the history JSON feature while keeping the existing GUI behavior working.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints and requirements
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Identify GUI dependencies on CLI-era modules
- [x] Define the GUI-only core shape
- [x] Document decisions with rationale
- **Status:** complete

### Phase 3: Implementation
- [x] Remove history JSON usage and config access
- [x] Remove terminal UI / CLI workflow dependencies from runtime code
- [x] Simplify launch paths to GUI-only flow
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Verify GUI core loads outline and generation status correctly
- [x] Verify GUI launch path still works from command line entry
- [x] Document test results in progress.md
- **Status:** complete

### Phase 5: Delivery
- [x] Review modified files
- [x] Summarize GUI-only changes and remaining cleanup
- [x] Deliver to user
- **Status:** complete

## Key Questions
1. Which GUI behaviors still depend on `TerminalUI` or CLI-centric flow today?
2. What is the smallest GUI-only core that preserves current functionality without terminal/history baggage?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Remove history instead of merely disabling it | The user explicitly said the JSON history feature can go away. |
| Keep a command-line launcher but no terminal workflow | Launching the GUI from `python run.py` or a script is still useful and does not imply CLI feature compatibility. |
| Move generated-file status logic into GUI-facing core/adapter | GUI currently reuses `TerminalUI` internals only for this purpose. |
| Delete terminal/history source files instead of leaving dead modules | It reduces maintenance surface and makes the GUI-only direction explicit. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None so far | 1 | Discovery completed without blocking errors |
| `uv lock` sandbox denial | 1 | Re-ran with escalated permission because `uv` needed access to its cache directory |

## Notes
- Re-read this plan before broad edits.
- Update phase status when implementation and verification complete.
- This task supersedes the earlier CLI-compatible direction.
