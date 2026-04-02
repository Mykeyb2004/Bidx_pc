# External Integrations

**Analysis Date:** 2026-04-02

## APIs & External Services

**LLM Inference:**
- OpenAI-compatible chat completions API - Primary content generation for bid sections.
  - SDK/Client: `openai` via `OpenAI(...)` in `bid_writer/ai_writer.py`.
  - Call pattern: `client.chat.completions.create(...)` in `bid_writer/ai_writer.py`.
  - Auth: `BID_WRITER_API_KEY`.
  - Endpoint routing: `BID_WRITER_API_BASE_URL` or `api.base_url` from YAML in `bid_writer/config.py`.
  - Model selection: `BID_WRITER_MODEL` or `api.model` in `bid_writer/config.py`.

**Secondary LLM for Context Pruning:**
- OpenAI-compatible auxiliary model endpoint - Optional requirement-brief and context-pruning model path controlled by `context_pruning.*` and `BID_WRITER_PRUNING_*` in `bid_writer/config.py`.
  - SDK/Client: no separate SDK or secondary client is instantiated; pruning-specific connection settings are exposed only through `bid_writer/config.py`.
  - Auth: `BID_WRITER_PRUNING_API_KEY`.
  - Endpoint routing: `BID_WRITER_PRUNING_API_BASE_URL`.
  - Model selection: `BID_WRITER_PRUNING_MODEL`.
  - Important current-state note: the checked-in `bid_writer/context_pruner.py` implementation is rule-based and excerpt-based; the pruning API settings are part of the configuration contract in `bid_writer/config.py`, but no separate outbound pruning request path is implemented.

**Desktop OS Integration:**
- Native file explorer launcher - `bid_writer/gui.py` uses platform-specific shell commands to open the output directory from the GUI.
  - Client: stdlib `subprocess` in `bid_writer/gui.py`.
  - Auth: Not applicable.

## Data Storage

**Databases:**
- None.
  - Connection: Not applicable.
  - Client: Not applicable.

**File Storage:**
- Local filesystem only.
  - Input files are read from Markdown/YAML paths resolved relative to the selected config in `bid_writer/config.py`.
  - Output sections are written as `.md` files by `bid_writer/file_saver.py`.
  - Optional trace artifacts are written under `log/generation_traces/` or `generation_trace.directory` by `bid_writer/generation_trace.py`.
  - Context-pruning debug dumps are written under `<output.directory>/_context_pruning_debug/` by `bid_writer/context_pruner.py`.
  - Timing logs append to `log/generation_timing.log` via `bid_writer/timing_logger.py`.
  - GUI state persists in `.bid_writer_gui_state.json` via `bid_writer/gui_state.py`.

**Caching:**
- None detected. Context pruning is recomputed in-process; no Redis, disk cache, or memoization store is configured in `bid_writer/context_pruner.py` or `bid_writer/ai_writer.py`.

## Authentication & Identity

**Auth Provider:**
- None for end users.
  - Implementation: local desktop app with no user accounts, sessions, or RBAC.

**API Authentication:**
- Bearer-style API key passed through the OpenAI SDK.
  - Implementation: `BID_WRITER_API_KEY` for the primary model and `BID_WRITER_PRUNING_API_KEY` for the optional pruning model, resolved in `bid_writer/config.py`.

## Monitoring & Observability

**Error Tracking:**
- None external.

**Logs:**
- Local JSONL timing log in `log/generation_timing.log` written by `bid_writer/timing_logger.py`.
- Per-generation trace directories containing JSON and Markdown artifacts written by `bid_writer/generation_trace.py`.
- Optional pruning debug Markdown files written by `bid_writer/context_pruner.py`.

## CI/CD & Deployment

**Hosting:**
- Not applicable. Current code is packaged as a local desktop Python application launched from `run.py` or the `bid-writer` console script.

**CI Pipeline:**
- None detected. No GitHub Actions workflow, GitLab CI config, or other CI manifest is present in the repository root.

## Environment Configuration

**Required env vars:**
- `BID_WRITER_API_KEY` - Required for any remote LLM call.
- `BID_WRITER_API_BASE_URL` - Required when the default `https://api.openai.com/v1` is not the target endpoint.
- `BID_WRITER_MODEL` - Required in practice for deterministic environment setup, although `bid_writer/config.py` provides a default.
- `BID_WRITER_PRUNING_API_KEY`, `BID_WRITER_PRUNING_API_BASE_URL`, `BID_WRITER_PRUNING_MODEL` - Required only when the optional pruning-model path is intentionally configured.

**Secrets location:**
- Supported secret sources are shell environment variables and local `.env.local` files loaded by `bid_writer/config.py`.
- `.env.example` provides the non-secret template.
- `.env.local` files exist in the repo root, but their contents were not inspected.

## File-Based Inputs

**Primary Inputs:**
- Outline Markdown: configured through `inputs.outline_file` or legacy `outline_file` in `bid_writer/config.py`; sample files include `outline.md` and `投标大纲.md`.
- Bid requirements Markdown/text: configured through `inputs.bid_requirements_file`, `inputs.bid_requirements`, or legacy `bid_requirements` in `bid_writer/config.py`; local example material exists in `项目要求/项目采购需求.md`.
- Scoring criteria Markdown/text: configured through `inputs.scoring_criteria_file`, `inputs.scoring_criteria`, or legacy `scoring_criteria` in `bid_writer/config.py`; local example material exists in `项目要求/评分标准.md`.

**External Local-File Touchpoints:**
- `config_公共服务满意度.yaml` points at absolute paths under the user’s `Documents/...` tree for `outline_file`, `bid_requirements`, `scoring_criteria`, and `output.directory`.
- This means the runtime integration boundary is not just repository-local content; planners should expect operator-managed project files outside the repo.

## Persistence Touchpoints

**Generated Content:**
- Markdown section files in `output.directory`, created by `bid_writer/file_saver.py`.

**Optional Metadata Persistence:**
- `bid_writer/file_saver.py` supports YAML front matter through `save_with_metadata(...)`, but the normal `save(...)` path used by the active flow writes plain Markdown content.

**UI State:**
- Last-used config path stored in `.bid_writer_gui_state.json` via `bid_writer/gui_state.py`.

**Trace and Diagnostics:**
- Per-run manifest, prompts, request options, context payloads, outputs, and summaries in directories created by `bid_writer/generation_trace.py`.
- Generation timing telemetry in `log/generation_timing.log` via `bid_writer/timing_logger.py`.
- Context pruning debug files in `<output.directory>/_context_pruning_debug/` via `bid_writer/context_pruner.py`.

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- HTTPS requests to the configured OpenAI-compatible LLM endpoint through the OpenAI SDK in `bid_writer/ai_writer.py`.

## Absent Integrations That Are Implied by Repository Text

**Provider-Specific AI SDKs:**
- Not present. `README.md`, `AGENTS.md`, and `LLM_Integration_Reference.md` discuss Gemini/OpenAI-compatible providers, but the actual implementation only imports the OpenAI SDK in `bid_writer/ai_writer.py`.

**Server-Side Persistence:**
- Not present. There is no database client, ORM, object store SDK, or search index integration in `bid_writer/*.py`.

**User/Auth/Collaboration Backends:**
- Not present. No SSO, OAuth, session store, or multi-user service integration is detected.

**External Observability SaaS:**
- Not present. Logging stays on the local filesystem; no Sentry, Datadog, OpenTelemetry exporter, or cloud log sink is configured.

---

*Integration audit: 2026-04-02*
