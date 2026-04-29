# Release Package Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows release package that includes the executable, default configuration files, role/gate prompt files, sample inputs, and a user-facing software manual.

**Architecture:** Keep the application code unchanged. Add a root-level manual for end users and update the GitHub Actions artifact preparation step so the packaged zip mirrors the runtime file layout expected by the app.

**Tech Stack:** GitHub Actions, PowerShell, Python project managed by uv.

---

### Task 1: Add User Manual

**Files:**
- Create: `软件说明书.md`

- [ ] **Step 1: Write the manual**

Create a Chinese manual for ordinary Windows users. It must cover package contents, first-time initialization, `.env.local` model setup, configuration file setup, input files, launch flow, chapter generation, output directory, and common problems.

- [ ] **Step 2: Check readability**

Run: `sed -n '1,260p' 软件说明书.md`

Expected: The manual contains no secret values and gives concrete setup steps.

### Task 2: Update Windows Artifact Bundle

**Files:**
- Modify: `.github/workflows/build-windows-exe.yml`

- [ ] **Step 1: Include runtime companion files**

Update `Prepare artifact bundle` to copy:

- `dist/bid-writer.exe`
- `config.example.yaml`
- `config.yaml` generated from `config.example.yaml`
- `.env.example`
- `README.md`
- `软件说明书.md`
- `启动命令.txt`
- `outline.md`
- `roles/system_gate_rules.md`
- `roles/通用投标角色.md`
- `roles/example_role.md`
- `项目要求/项目采购需求.md`
- `项目要求/评分标准.md`
- Empty `output`, `log`, and `caches` directories

- [ ] **Step 2: Avoid private files**

Do not copy `.env`, `.env.local`, `history.json`, `.bid_writer_gui_state.json`, `.worktrees`, existing generated `output` content, or local-project `config_*.yaml`.

### Task 3: Validate

**Files:**
- Verify: `.github/workflows/build-windows-exe.yml`
- Verify: `软件说明书.md`

- [ ] **Step 1: Run YAML/doc tests**

Run: `uv run pytest tests/test_config_schema.py tests/test_gui_state.py -q`

Expected: All selected tests pass.

- [ ] **Step 2: Review diff**

Run: `git diff -- .github/workflows/build-windows-exe.yml 软件说明书.md docs/superpowers/plans/2026-04-29-release-package-manual.md`

Expected: Diff only includes the manual, plan, and release bundle changes.
