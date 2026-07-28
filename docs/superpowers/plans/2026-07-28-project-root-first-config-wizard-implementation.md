# Project-Root-First Config Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the new config wizard so the user first selects an existing project root, all default project paths derive from that root, and new configs always initialize a valid node writing-plan JSON file.

**Architecture:** Put path derivation and serialization in `bid_writer/new_config_flow.py`, keep all JSON v1 creation and validation in `bid_writer/writing_plan_store.py`, and keep Tk dialogs as orchestration layers. Add one small shared path-purpose module so the wizard and config editor use the same strict file filters and extension checks.

**Tech Stack:** Python 3.10+, Tkinter/ttk, PyYAML, pytest, uv, GitNexus/codebase-memory MCP for code intelligence.

---

## Pre-Flight

**Spec:** `docs/superpowers/specs/2026-07-28-project-root-first-config-wizard-design.md`

**Impact Summary Already Checked:**
- `NewConfigWizardState`: LOW, 1 direct upstream dependency.
- `build_editor_document_from_state`: LOW, 1 direct caller.
- `NewConfigWizardDialog._sync_state_from_fields`: LOW, 4 direct callers.
- `NewConfigWizardDialog._save_and_apply`: LOW, no indexed upstream callers in stale GitNexus result.
- `WritingPlanStore`: LOW, 2 direct upstream dependencies.
- `ConfigEditorDialog._browse_path`: HIGH, 1 direct caller but affects project, processing, and runtime path sections. Treat Task 7 as high-risk and keep it tightly tested.

**Before Editing Any Symbol:**
- Run GitNexus impact again from the execution worktree because the index was 17 commits behind during planning:

```bash
env GITNEXUS_LBUG_EXTENSION_INSTALL=auto gitnexus analyze --repair-fts
```

- Then run focused impact checks before each task that edits code:

```bash
# Use MCP when available; examples:
impact({target: "build_state_from_project_root", direction: "upstream", repo: "Bidx_pc"})
impact({target: "NewConfigWizardDialog._browse_path", direction: "upstream", repo: "Bidx_pc"})
```

If GitNexus reports HIGH or CRITICAL for a task, pause and report the blast radius before editing.

## File Structure

### Create

- `bid_writer/path_purposes.py`
  - Single source of truth for supported path purposes, strict file dialog filters, suffix validation, and project-relative display rules used by the wizard and config editor.

### Modify

- `bid_writer/new_config_flow.py`
  - Add project-root-first defaults, `writing_plan_path`, config filename sanitization, default path rebasing, and project-root serialization as `"."`.
- `bid_writer/new_config_wizard.py`
  - Reorder steps, defer state creation until root validation, add writing-plan controls/status, apply strict filters, coordinate writing-plan initialization before config save, and rollback only newly created plan files on config save failure.
- `bid_writer/writing_plan_store.py`
  - Add a public non-overwriting initialization API that validates existing JSON v1 or creates the canonical empty JSON v1 atomically.
- `bid_writer/config_editor.py`
  - Add extension and existing writing-plan validation to `validate_editor_model()` while preserving empty and missing-path compatibility for existing configs.
- `bid_writer/config_editor_dialog.py`
  - Use strict file filters through `path_purposes.py`; keep project-internal writing-plan paths relative and project-external paths absolute.
- `docs/config_schema.md`
  - Document project-root-first wizard behavior, default writing-plan creation, path serialization, and strict filters.
- `README.md`
  - Update the new-config workflow description.
- `config.example.yaml`
  - Align example writing-plan path with the desired default if product chooses `./撰写计划.json`; keep tests in sync.
- `config_*.yaml`
  - Update project examples only if their documented writing-plan defaults should match the new canonical examples.

### Test

- `tests/test_new_config_flow.py`
- `tests/test_new_config_wizard.py`
- `tests/test_writing_plan_store.py`
- `tests/test_config_editor.py`
- `tests/test_config_editor_dialog.py`
- Create: `tests/test_path_purposes.py`

---

### Task 1: Shared Path Purposes

**Files:**
- Create: `bid_writer/path_purposes.py`
- Test: `tests/test_path_purposes.py`

- [ ] **Step 1: Write failing tests for strict filters and suffix validation**

Create `tests/test_path_purposes.py`:

```python
from pathlib import Path

import pytest

from bid_writer.path_purposes import (
    PathPurpose,
    file_dialog_options,
    require_supported_suffix,
)


def test_file_dialog_options_never_include_all_files() -> None:
    for purpose in PathPurpose:
        options = file_dialog_options(purpose)
        assert ("全部文件", "*.*") not in options.filetypes


def test_dialog_filters_match_business_purposes() -> None:
    assert file_dialog_options(PathPurpose.TENDER).filetypes == (
        ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
        ("PDF", "*.pdf"),
        ("Word", "*.docx *.doc"),
        ("Excel", "*.xlsx *.xls"),
    )
    assert file_dialog_options(PathPurpose.MARKDOWN).filetypes == (("Markdown", "*.md"),)
    assert file_dialog_options(PathPurpose.JSON).filetypes == (("JSON", "*.json"),)
    assert file_dialog_options(PathPurpose.YAML).filetypes == (("YAML", "*.yaml *.yml"),)


@pytest.mark.parametrize(
    ("purpose", "path"),
    [
        (PathPurpose.TENDER, Path("招标文件.pdf")),
        (PathPurpose.TENDER, Path("招标文件.docx")),
        (PathPurpose.TENDER, Path("招标文件.doc")),
        (PathPurpose.TENDER, Path("招标文件.xlsx")),
        (PathPurpose.TENDER, Path("招标文件.xls")),
        (PathPurpose.MARKDOWN, Path("采购需求.md")),
        (PathPurpose.JSON, Path("撰写计划.json")),
        (PathPurpose.YAML, Path("config.yaml")),
        (PathPurpose.YAML, Path("config.yml")),
    ],
)
def test_require_supported_suffix_accepts_supported_extensions(
    purpose: PathPurpose,
    path: Path,
) -> None:
    require_supported_suffix(path, purpose, label="测试文件")


def test_require_supported_suffix_rejects_wrong_extension() -> None:
    with pytest.raises(ValueError, match="节点撰写计划文件必须是 .json 文件"):
        require_supported_suffix(Path("撰写计划.txt"), PathPurpose.JSON, label="节点撰写计划文件")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_path_purposes.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.path_purposes'`.

- [ ] **Step 3: Implement `bid_writer/path_purposes.py`**

Add:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PathPurpose(str, Enum):
    TENDER = "tender"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"


@dataclass(frozen=True)
class FileDialogOptions:
    filetypes: tuple[tuple[str, str], ...]
    defaultextension: str | None = None


_SUFFIXES: dict[PathPurpose, tuple[str, ...]] = {
    PathPurpose.TENDER: (".pdf", ".docx", ".doc", ".xlsx", ".xls"),
    PathPurpose.MARKDOWN: (".md",),
    PathPurpose.JSON: (".json",),
    PathPurpose.YAML: (".yaml", ".yml"),
}

_DIALOG_OPTIONS: dict[PathPurpose, FileDialogOptions] = {
    PathPurpose.TENDER: FileDialogOptions(
        filetypes=(
            ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
            ("PDF", "*.pdf"),
            ("Word", "*.docx *.doc"),
            ("Excel", "*.xlsx *.xls"),
        )
    ),
    PathPurpose.MARKDOWN: FileDialogOptions(
        filetypes=(("Markdown", "*.md"),),
        defaultextension=".md",
    ),
    PathPurpose.JSON: FileDialogOptions(
        filetypes=(("JSON", "*.json"),),
        defaultextension=".json",
    ),
    PathPurpose.YAML: FileDialogOptions(
        filetypes=(("YAML", "*.yaml *.yml"),),
        defaultextension=".yaml",
    ),
}


def supported_suffixes(purpose: PathPurpose) -> tuple[str, ...]:
    return _SUFFIXES[purpose]


def file_dialog_options(purpose: PathPurpose) -> FileDialogOptions:
    return _DIALOG_OPTIONS[purpose]


def require_supported_suffix(path: str | Path, purpose: PathPurpose, *, label: str) -> None:
    suffixes = supported_suffixes(purpose)
    actual = Path(path).suffix.lower()
    if actual not in suffixes:
        if len(suffixes) == 1:
            expected = f"{suffixes[0]} 文件"
        else:
            expected = " / ".join(suffixes) + " 文件"
        raise ValueError(f"{label}必须是 {expected}：{path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_path_purposes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/path_purposes.py tests/test_path_purposes.py
git commit -m "feat: add strict path purpose helpers"
```

### Task 2: Project-Root-First State Defaults

**Files:**
- Modify: `bid_writer/new_config_flow.py`
- Test: `tests/test_new_config_flow.py`

- [ ] **Step 1: Write failing tests for root-first defaults**

Add these tests near the existing `build_manual_state` tests in `tests/test_new_config_flow.py`:

```python
def test_build_state_from_project_root_derives_all_default_paths(tmp_path: Path):
    project = tmp_path / "公共服务项目"
    project.mkdir()

    state = build_state_from_project_root(project)

    assert state.source_path is None
    assert state.project_root == project
    assert state.config_path == project / "config_公共服务项目.yaml"
    assert state.import_dir == project / ".bid_writer" / "imports" / "pending"
    assert state.requirements_path == project / "项目要求" / "项目采购需求.md"
    assert state.scoring_path == project / "项目要求" / "评分标准.md"
    assert state.outline_path == project / "投标大纲.md"
    assert state.writing_plan_path == project / "撰写计划.json"
    assert state.output_dir == project / "output"
    assert state.manual_inputs is True


def test_build_state_from_project_root_sanitizes_config_filename(tmp_path: Path):
    project = tmp_path / ' 公共:服务*项目 '
    project.mkdir()

    state = build_state_from_project_root(project)

    assert state.config_path == project / "config_公共_服务_项目.yaml"


def test_build_state_from_project_root_uses_new_project_fallback(tmp_path: Path):
    project = tmp_path / "   "
    project.mkdir()

    state = build_state_from_project_root(project)

    assert state.config_path == project / "config_新项目.yaml"
```

Update imports at the top of the file:

```python
from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_editor_document_from_state,
    build_initial_state_from_source,
    build_manual_state,
    build_state_from_project_root,
    copy_source_file_if_needed,
    cleanup_created_paths,
    derive_project_name,
    format_relative_path,
    infer_project_root,
    register_created_path,
    should_copy_source_file,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_flow.py::test_build_state_from_project_root_derives_all_default_paths tests/test_new_config_flow.py::test_build_state_from_project_root_sanitizes_config_filename tests/test_new_config_flow.py::test_build_state_from_project_root_uses_new_project_fallback -q
```

Expected: FAIL with `ImportError` or `NameError` for `build_state_from_project_root`.

- [ ] **Step 3: Implement root-first defaults**

Before editing, run:

```bash
# GitNexus MCP preferred:
impact({target: "NewConfigWizardState", direction: "upstream", repo: "Bidx_pc"})
impact({target: "build_manual_state", direction: "upstream", repo: "Bidx_pc"})
```

Modify `bid_writer/new_config_flow.py`:

```python
import re
```

Add the field to `NewConfigWizardState` between `outline_path` and `output_dir`:

```python
    writing_plan_path: Path
```

Add constants after `DEFAULT_SCORING_RELATIVE`:

```python
DEFAULT_OUTLINE_FILENAME = "投标大纲.md"
DEFAULT_WRITING_PLAN_FILENAME = "撰写计划.json"
DEFAULT_OUTPUT_DIRNAME = "output"
DEFAULT_IMPORT_DIR = Path(".bid_writer") / "imports" / "pending"
```

Add:

```python
def sanitize_config_name(name: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name)
    sanitized = re.sub(r"[_\s]+", "_", sanitized).strip(" ._")
    return sanitized or "新项目"


def build_state_from_project_root(project_root: str | Path) -> NewConfigWizardState:
    root = Path(project_root)
    config_stem = sanitize_config_name(root.name)
    return NewConfigWizardState(
        source_path=None,
        project_root=root,
        config_path=root / f"config_{config_stem}.yaml",
        import_dir=root / DEFAULT_IMPORT_DIR,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=root / "项目要求" / "项目采购需求.md",
        scoring_path=root / "项目要求" / "评分标准.md",
        outline_path=root / DEFAULT_OUTLINE_FILENAME,
        writing_plan_path=root / DEFAULT_WRITING_PLAN_FILENAME,
        output_dir=root / DEFAULT_OUTPUT_DIRNAME,
        bidder_name="",
        created_paths=[],
        manual_inputs=True,
    )
```

Update `build_initial_state_from_source()` and `build_manual_state()` to set `writing_plan_path`:

```python
        outline_path=project_root / DEFAULT_OUTLINE_FILENAME,
        writing_plan_path=project_root / DEFAULT_WRITING_PLAN_FILENAME,
        output_dir=project_root / DEFAULT_OUTPUT_DIRNAME,
```

For `build_manual_state()` use:

```python
        import_dir=root / DEFAULT_IMPORT_DIR,
```

- [ ] **Step 4: Update existing direct state constructions in tests**

In `tests/test_new_config_flow.py`, every direct `NewConfigWizardState(...)` must include:

```python
        writing_plan_path=project / "撰写计划.json",
```

or, for tests where `project_root=tmp_path`:

```python
        writing_plan_path=tmp_path / "撰写计划.json",
```

Use the local variable that matches the test's `project_root`.

- [ ] **Step 5: Run the focused test file**

Run:

```bash
uv run pytest tests/test_new_config_flow.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/new_config_flow.py tests/test_new_config_flow.py
git commit -m "feat: derive new config state from project root"
```

### Task 3: Root-Relative Serialization Including Writing Plan

**Files:**
- Modify: `bid_writer/new_config_flow.py`
- Test: `tests/test_new_config_flow.py`

- [ ] **Step 1: Write failing tests for canonical serialization**

Add these tests near `test_build_editor_document_uses_relative_project_paths`:

```python
def test_build_editor_document_saves_root_dir_as_dot_when_config_inside_project(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    state = build_state_from_project_root(project)
    state.bidder_name = "测试公司"

    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert payload["project"]["root_dir"] == "."


def test_build_editor_document_writes_default_writing_plan_file(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    state = build_state_from_project_root(project)
    state.bidder_name = "测试公司"

    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert payload["project"]["inputs"]["writing_plan_file"] == "./撰写计划.json"


def test_build_editor_document_preserves_project_external_writing_plan_as_absolute(tmp_path: Path):
    project = tmp_path / "项目"
    external = tmp_path / "shared" / "writing-plan.json"
    external.parent.mkdir()
    external.write_text('{"version": 1, "items": []}', encoding="utf-8")
    project.mkdir()
    state = build_state_from_project_root(project)
    state.bidder_name = "测试公司"
    state.writing_plan_path = external

    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert payload["project"]["inputs"]["writing_plan_file"] == str(external)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_flow.py::test_build_editor_document_saves_root_dir_as_dot_when_config_inside_project tests/test_new_config_flow.py::test_build_editor_document_writes_default_writing_plan_file tests/test_new_config_flow.py::test_build_editor_document_preserves_project_external_writing_plan_as_absolute -q
```

Expected: first test may FAIL with `./` or another relative value, and second FAIL because `writing_plan_file` is absent.

- [ ] **Step 3: Implement serialization**

Before editing, run:

```bash
impact({target: "build_editor_document_from_state", direction: "upstream", repo: "Bidx_pc"})
```

In `build_editor_document_from_state()`, replace the root assignment:

```python
    model["project"]["root_dir"] = "."
```

Add writing plan assignment after outline:

```python
    model["project"]["writing_plan_file"] = format_relative_path(
        state.writing_plan_path,
        state.project_root,
    )
```

Keep `format_relative_path()` unchanged so project-external files stay absolute and project-internal files become `./...`.

- [ ] **Step 4: Update changed existing assertion**

In `test_build_editor_document_uses_relative_project_paths`, update:

```python
    assert payload["project"]["root_dir"] == "."
    assert payload["project"]["inputs"]["writing_plan_file"] == "./撰写计划.json"
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_new_config_flow.py tests/test_config_editor.py::test_config_editor_round_trips_writing_plan_file_as_managed_input -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/new_config_flow.py tests/test_new_config_flow.py
git commit -m "feat: serialize wizard paths relative to project root"
```

### Task 4: Writing Plan Store Initialization API

**Files:**
- Modify: `bid_writer/writing_plan_store.py`
- Test: `tests/test_writing_plan_store.py`

- [ ] **Step 1: Write failing tests for initialize behavior**

Add imports:

```python
from bid_writer.writing_plan_store import (
    InitializeWritingPlanResult,
    WritingPlanExternalModificationError,
    WritingPlanItem,
    WritingPlanSnapshot,
    WritingPlanStore,
    WritingPlanStoreError,
    WritingPlanValidationError,
    extract_node_number,
)
```

Add tests after `test_load_snapshot_returns_empty_snapshot_for_missing_file`:

```python
def test_initialize_creates_canonical_empty_json_v1(tmp_path) -> None:
    path = tmp_path / "撰写计划.json"

    result = WritingPlanStore(path).initialize()

    assert result == InitializeWritingPlanResult(created=True, snapshot=WritingPlanStore(path).load_snapshot())
    assert path.read_bytes() == b'{\n  "version": 1,\n  "items": []\n}\n'


def test_initialize_reuses_valid_existing_file_without_changing_bytes(tmp_path) -> None:
    path = tmp_path / "撰写计划.json"
    raw = b'{"version":1,"items":[]}'
    path.write_bytes(raw)

    result = WritingPlanStore(path).initialize()

    assert result.created is False
    assert result.snapshot.items == ()
    assert path.read_bytes() == raw


def test_initialize_rejects_invalid_existing_file_without_overwriting(tmp_path) -> None:
    path = tmp_path / "撰写计划.json"
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(WritingPlanValidationError, match="JSON"):
        WritingPlanStore(path).initialize()

    assert path.read_text(encoding="utf-8") == "not-json"


def test_initialize_missing_parent_is_not_created_unless_direct_parent_exists(tmp_path) -> None:
    path = tmp_path / "missing" / "撰写计划.json"

    with pytest.raises(WritingPlanStoreError, match="父目录不存在"):
        WritingPlanStore(path).initialize()

    assert not path.exists()
    assert not path.parent.exists()


def test_initialize_does_not_overwrite_file_created_during_race(tmp_path, monkeypatch) -> None:
    path = tmp_path / "撰写计划.json"
    race_raw = b'{"version": 1, "items": [{"node": "1.1", "writing_plan": "外部"}]}'
    original_open = writing_plan_store.os.open

    def racing_open(filename, flags, mode=0o777):
        path.write_bytes(race_raw)
        raise FileExistsError(str(filename))

    monkeypatch.setattr(writing_plan_store.os, "open", racing_open)

    result = WritingPlanStore(path).initialize()

    assert result.created is False
    assert result.snapshot.items == (WritingPlanItem(node="1.1", writing_plan="外部"),)
    assert path.read_bytes() == race_raw
    monkeypatch.setattr(writing_plan_store.os, "open", original_open)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_writing_plan_store.py::test_initialize_creates_canonical_empty_json_v1 tests/test_writing_plan_store.py::test_initialize_reuses_valid_existing_file_without_changing_bytes tests/test_writing_plan_store.py::test_initialize_rejects_invalid_existing_file_without_overwriting tests/test_writing_plan_store.py::test_initialize_missing_parent_is_not_created_unless_direct_parent_exists tests/test_writing_plan_store.py::test_initialize_does_not_overwrite_file_created_during_race -q
```

Expected: FAIL with missing `InitializeWritingPlanResult` or `initialize`.

- [ ] **Step 3: Add result dataclass and canonical raw helper**

Before editing, run:

```bash
impact({target: "WritingPlanStore", direction: "upstream", repo: "Bidx_pc"})
```

In `bid_writer/writing_plan_store.py`, add after `WritingPlanCoverage`:

```python
@dataclass(frozen=True)
class InitializeWritingPlanResult:
    created: bool
    snapshot: WritingPlanSnapshot
```

Add near the regex constants:

```python
_EMPTY_PAYLOAD = {"version": 1, "items": []}
```

Add a private helper above `WritingPlanStore`:

```python
def _dumps_payload(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
```

Replace the existing save payload dump with:

```python
        raw = _dumps_payload(payload)
```

- [ ] **Step 4: Implement `initialize()` without overwriting**

Add to `WritingPlanStore` before `load_snapshot()`:

```python
    def initialize(self) -> InitializeWritingPlanResult:
        raw = self._read_bytes()
        if raw is not None:
            return InitializeWritingPlanResult(
                created=False,
                snapshot=self._snapshot_from_raw(raw),
            )

        if not self.path.parent.exists():
            raise WritingPlanStoreError(f"撰写计划文件父目录不存在：{self.path.parent}")
        if not self.path.parent.is_dir():
            raise WritingPlanStoreError(f"撰写计划文件父路径不是目录：{self.path.parent}")

        raw = _dumps_payload(_EMPTY_PAYLOAD)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            existing_raw = self._read_bytes()
            if existing_raw is None:
                raise WritingPlanExternalModificationError(
                    f"撰写计划文件创建状态已变化，请重试：{self.path}"
                )
            return InitializeWritingPlanResult(
                created=False,
                snapshot=self._snapshot_from_raw(existing_raw),
            )
        except OSError as exc:
            raise WritingPlanStoreError(f"无法创建撰写计划文件：{self.path}") from exc

        try:
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            self._fsync_parent_directory()
        except Exception as exc:
            with suppress(OSError):
                self.path.unlink()
            raise WritingPlanStoreError(f"无法创建撰写计划文件：{self.path}") from exc

        return InitializeWritingPlanResult(
            created=True,
            snapshot=WritingPlanSnapshot(
                items=(),
                fingerprint=hashlib.sha256(raw).hexdigest(),
            ),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_writing_plan_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/writing_plan_store.py tests/test_writing_plan_store.py
git commit -m "feat: initialize writing plan stores safely"
```

### Task 5: Wizard Root Step and Deferred State Creation

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Write failing tests for step order and empty initial root**

Add tests near `test_constructor_builds_initial_wizard_shell`:

```python
def test_wizard_steps_start_with_project_location() -> None:
    assert [step.key for step in new_config_wizard.WIZARD_STEPS] == [
        "location",
        "source",
        "materials",
        "basics",
        "review",
    ]


def test_constructor_starts_without_confirmed_project_root(tmp_path: Path):
    dialog = _dialog(tmp_path)

    assert dialog.state is None
    assert dialog.vars["project_root"].get() == ""
    assert dialog.vars["config_path"].get() == ""
    assert dialog.config_summary_var.get() == "先选择项目根目录"
```

The existing `_dialog()` helper currently expects `dialog.state` to be a full state. Update it so it can make a root-confirmed dialog by default:

```python
def _dialog(tmp_path: Path, *, initialize_state: bool = True):
    dialog = NewConfigWizardDialog.__new__(NewConfigWizardDialog)
    dialog.parent_window = StubParent()
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.current_step_index = 0
    dialog.max_completed_step_index = 0
    dialog._import_in_progress = False
    dialog._tooltips = []
    dialog.step_buttons = []
    dialog.step_frames = {}
    dialog.vars = {
        "source_path": StubVar(""),
        "project_root": StubVar(""),
        "config_path": StubVar(""),
        "requirements_path": StubVar(""),
        "scoring_path": StubVar(""),
        "outline_source": StubVar("generate"),
        "outline_path": StubVar(""),
        "writing_plan_path": StubVar(""),
        "output_dir": StubVar(""),
        "bidder_name": StubVar(""),
    }
    dialog.status_var = StubVar("")
    dialog.config_summary_var = StubVar("")
    dialog.source_hint_var = StubVar("")
    dialog.import_status_var = StubVar("")
    dialog.review_summary_var = StubVar("")
    dialog.outline_path_label_var = StubVar("大纲保存位置")
    dialog.outline_path_action_var = StubVar("选择保存位置...")
    dialog.outline_path_hint_var = StubVar("")
    dialog.state = None
    if initialize_state:
        dialog.state = build_state_from_project_root(tmp_path)
        NewConfigWizardDialog._sync_fields_from_state(dialog)
    dialog.destroy = lambda: None
    return dialog
```

Update tests that need the constructor-empty behavior to call `_dialog(tmp_path, initialize_state=False)`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_wizard_steps_start_with_project_location tests/test_new_config_wizard.py::test_constructor_starts_without_confirmed_project_root -q
```

Expected: FAIL because current order starts with `source`, and constructor creates a full manual state.

- [ ] **Step 3: Change imports and state type**

Before editing, run:

```bash
impact({target: "NewConfigWizardDialog.__init__", direction: "upstream", repo: "Bidx_pc"})
impact({target: "NewConfigWizardDialog._sync_fields_from_state", direction: "upstream", repo: "Bidx_pc"})
impact({target: "NewConfigWizardDialog._sync_state_from_fields", direction: "upstream", repo: "Bidx_pc"})
```

In `bid_writer/new_config_wizard.py`, update imports from `new_config_flow`:

```python
from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_editor_document_from_state,
    build_state_from_project_root,
    cleanup_created_paths,
    copy_source_file_if_needed,
    register_created_path,
    should_copy_source_file,
)
```

Remove `build_initial_state_from_source` and `build_manual_state` imports after all usages are replaced.

- [ ] **Step 4: Reorder steps**

Replace `WIZARD_STEPS`:

```python
WIZARD_STEPS = [
    WizardStep("location", "项目位置"),
    WizardStep("source", "招标文件"),
    WizardStep("materials", "项目资料"),
    WizardStep("basics", "基础设置"),
    WizardStep("review", "保存确认"),
]
```

- [ ] **Step 5: Update constructor to defer state creation**

In `__init__`, replace initial state creation with:

```python
        self.initial_config_path = Path(config_path or "config_新项目.yaml").expanduser().resolve()
        self.result: dict[str, Path | None] = {"saved_path": None, "apply_path": None}
```

and:

```python
        self.state: NewConfigWizardState | None = None
```

After creating string vars and status vars, do not call `_sync_fields_from_state()`. Instead set:

```python
        self.config_summary_var.set("先选择项目根目录")
```

- [ ] **Step 6: Add state guard helper**

Add this method near `_sync_fields_from_state()`:

```python
    def _require_state(self) -> NewConfigWizardState:
        if self.state is None:
            raise ValueError("请先选择一个现有项目根目录。")
        return self.state
```

- [ ] **Step 7: Include writing-plan var**

In `_create_vars()`, add:

```python
            "writing_plan_path": tk.StringVar(value=""),
```

- [ ] **Step 8: Update `_sync_fields_from_state()`**

Replace the method body:

```python
    def _sync_fields_from_state(self) -> None:
        if self.state is None:
            self.vars["source_path"].set("")
            self.vars["project_root"].set("")
            self.vars["config_path"].set("")
            self.vars["requirements_path"].set("")
            self.vars["scoring_path"].set("")
            self.vars["outline_path"].set("")
            self.vars["writing_plan_path"].set("")
            self.vars["output_dir"].set("")
            self.vars["bidder_name"].set("")
            if hasattr(self, "config_summary_var"):
                self.config_summary_var.set("先选择项目根目录")
            return

        self.vars["source_path"].set("" if self.state.source_path is None else str(self.state.source_path))
        self.vars["project_root"].set(str(self.state.project_root))
        self.vars["config_path"].set(str(self.state.config_path))
        self.vars["requirements_path"].set("" if self.state.requirements_path is None else str(self.state.requirements_path))
        self.vars["scoring_path"].set("" if self.state.scoring_path is None else str(self.state.scoring_path))
        self.vars["outline_source"].set(getattr(self.state, "outline_source", self.vars["outline_source"].get() or "generate"))
        self.vars["outline_path"].set(str(self.state.outline_path))
        self.vars["writing_plan_path"].set(str(self.state.writing_plan_path))
        self.vars["output_dir"].set(str(self.state.output_dir))
        self.vars["bidder_name"].set(self.state.bidder_name)
        if hasattr(self, "config_summary_var"):
            self.config_summary_var.set(f"目标配置：{self.state.config_path}")
        self._sync_outline_source_ui()
        self._sync_source_hint()
```

- [ ] **Step 9: Add root confirmation helper**

Add after `_sync_state_from_fields()`:

```python
    def _confirm_project_root_from_var(self) -> bool:
        root_value = self.vars["project_root"].get().strip()
        if not root_value:
            messagebox.showerror("路径无效", "项目根目录不能为空。", parent=self)
            return False

        root = Path(root_value).expanduser().resolve()
        if not root.exists():
            messagebox.showerror("路径无效", f"项目根目录不存在：{root}", parent=self)
            return False
        if not root.is_dir():
            messagebox.showerror("路径无效", f"项目根目录不是目录：{root}", parent=self)
            return False

        previous_state = self.state
        next_state = build_state_from_project_root(root)
        if previous_state is not None:
            self._carry_over_state_for_new_root(previous_state, next_state)
        self.state = next_state
        self._sync_fields_from_state()
        if self.state.config_path.exists():
            messagebox.showerror(
                "配置已存在",
                f"默认配置文件已经存在：{self.state.config_path}\n请打开已有配置或选择其他项目根目录。",
                parent=self,
            )
            return False
        return True
```

- [ ] **Step 10: Add carry-over helper**

Add:

```python
    def _carry_over_state_for_new_root(
        self,
        previous: NewConfigWizardState,
        current: NewConfigWizardState,
    ) -> None:
        current.source_path = previous.source_path
        current.copied_source_path = previous.copied_source_path
        current.bidder_name = previous.bidder_name
        current.created_paths = previous.created_paths
        current.manual_inputs = previous.manual_inputs

        old_defaults = build_state_from_project_root(previous.project_root)
        if previous.requirements_path != old_defaults.requirements_path:
            current.requirements_path = previous.requirements_path
        if previous.scoring_path != old_defaults.scoring_path:
            current.scoring_path = previous.scoring_path
        if previous.outline_path != old_defaults.outline_path:
            current.outline_path = previous.outline_path
        if previous.writing_plan_path != old_defaults.writing_plan_path:
            current.writing_plan_path = previous.writing_plan_path
        if previous.output_dir != old_defaults.output_dir:
            current.output_dir = previous.output_dir

        if current.source_path is not None:
            current.should_copy_source = should_copy_source_file(current.source_path, current.project_root)
            current.source_copy_path = (
                current.project_root / "招标文件" / current.source_path.name
                if current.should_copy_source
                else None
            )
            current.import_dir = current.project_root / ".bid_writer" / "imports" / "pending"
        else:
            current.should_copy_source = False
            current.source_copy_path = None
            current.import_dir = current.project_root / ".bid_writer" / "imports" / "pending"
```

- [ ] **Step 11: Update `_sync_state_from_fields()` to require confirmed state**

At the top:

```python
        state = self._require_state()
        previous_project_root = state.project_root
```

Replace all `self.state.` reads/writes in this method with `state.`.

Parse writing plan:

```python
            writing_plan_path = self._path_from_var("writing_plan_path")
```

Assign it:

```python
        state.writing_plan_path = writing_plan_path
```

Keep source copy recalculation based on `state`.

- [ ] **Step 12: Update `_show_step()` for pre-state location step**

Replace the first line:

```python
        if self.state is not None:
            self._sync_state_from_fields(silent=True)
```

- [ ] **Step 13: Update location validation**

In `_validate_current_step()`, compute `step_key` before syncing:

```python
        step_key = WIZARD_STEPS[self.current_step_index].key
        if step_key == "location":
            return self._confirm_project_root_from_var()
```

Then keep the existing sync for other steps:

```python
        try:
            self._sync_state_from_fields()
        except ValueError as exc:
            messagebox.showerror("路径无效", str(exc), parent=self)
            return False
```

Remove the old `if step_key == "location"` block.

- [ ] **Step 14: Run focused tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_wizard_steps_start_with_project_location tests/test_new_config_wizard.py::test_constructor_starts_without_confirmed_project_root tests/test_new_config_wizard.py::test_project_root_change_rebases_default_material_paths tests/test_new_config_wizard.py::test_project_root_change_preserves_custom_material_paths -q
```

Expected: PASS after updating tests for `dialog.state is None` where needed.

- [ ] **Step 15: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: start new config wizard from project root"
```

### Task 6: Source Selection No Longer Rebuilds Root

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Write failing tests for source selection**

Replace the old `test_select_source_file_rebuilds_state_and_moves_to_location` with:

```python
def test_select_source_file_updates_source_without_changing_project_root(monkeypatch, tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    external = tmp_path / "downloads" / "公共服务满意度项目招标文件.pdf"
    external.parent.mkdir()
    external.write_text("fake", encoding="utf-8")
    dialog = _dialog(project)
    dialog.current_step_index = 1

    monkeypatch.setattr(
        "bid_writer.new_config_wizard.filedialog.askopenfilename",
        lambda **_kwargs: str(external),
    )

    NewConfigWizardDialog._select_source_file(dialog)

    assert dialog.state.project_root == project
    assert dialog.state.config_path == project / "config_项目.yaml"
    assert dialog.state.source_path == external
    assert dialog.state.should_copy_source is True
    assert dialog.state.source_copy_path == project / "招标文件" / external.name
    assert dialog.current_step_index == 1
```

Add:

```python
def test_select_project_internal_source_does_not_copy(monkeypatch, tmp_path: Path):
    project = tmp_path / "项目"
    source = project / "招标文件" / "采购文件.pdf"
    source.parent.mkdir(parents=True)
    source.write_text("fake", encoding="utf-8")
    dialog = _dialog(project)
    dialog.current_step_index = 1

    monkeypatch.setattr(
        "bid_writer.new_config_wizard.filedialog.askopenfilename",
        lambda **_kwargs: str(source),
    )

    NewConfigWizardDialog._select_source_file(dialog)

    assert dialog.state.project_root == project
    assert dialog.state.source_path == source
    assert dialog.state.should_copy_source is False
    assert dialog.state.source_copy_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_select_source_file_updates_source_without_changing_project_root tests/test_new_config_wizard.py::test_select_project_internal_source_does_not_copy -q
```

Expected: FAIL because `_select_source_file()` still calls `build_initial_state_from_source()`.

- [ ] **Step 3: Update source selection**

Before editing:

```bash
impact({target: "NewConfigWizardDialog._select_source_file", direction: "upstream", repo: "Bidx_pc"})
```

Replace the bottom of `_select_source_file()` after suffix validation:

```python
        state = self._require_state()
        state.source_path = selected_path
        state.manual_inputs = False
        state.should_copy_source = should_copy_source_file(selected_path, state.project_root)
        state.source_copy_path = (
            state.project_root / "招标文件" / selected_path.name
            if state.should_copy_source
            else None
        )
        state.import_dir = state.project_root / ".bid_writer" / "imports" / "pending"
        self.vars["source_path"].set(str(selected_path))
        self._sync_fields_from_state()
        self.current_step_index = max(self.current_step_index, 1)
        self.max_completed_step_index = max(self.max_completed_step_index, self.current_step_index)
        self._show_step()
```

- [ ] **Step 4: Update manual source action**

In `_skip_source_selection()`, use:

```python
        state = self._require_state()
        self.vars["source_path"].set("")
        state.source_path = None
        state.import_dir = state.project_root / ".bid_writer" / "imports" / "pending"
        state.should_copy_source = False
        state.source_copy_path = None
        state.manual_inputs = True
```

Do not move back to location; keep:

```python
        self.current_step_index = max(self.current_step_index, 1)
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS or failures only in tests that still assume source-first order; update those expectations to the new step order.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: keep project root stable when selecting source"
```

### Task 7: Wizard Writing Plan Controls, Rebase, and Strict Filters

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Write failing tests for writing-plan UI state and filters**

Add:

```python
def test_project_root_change_rebases_default_writing_plan_and_preserves_custom(tmp_path: Path):
    old_root = tmp_path / "旧项目"
    new_root = tmp_path / "新项目"
    old_root.mkdir()
    new_root.mkdir()
    dialog = _dialog(old_root)
    custom = tmp_path / "shared" / "custom-plan.json"
    custom.parent.mkdir()
    custom.write_text('{"version": 1, "items": []}', encoding="utf-8")

    dialog.vars["project_root"].set(str(new_root))
    NewConfigWizardDialog._confirm_project_root_from_var(dialog)
    assert dialog.state.writing_plan_path == new_root / "撰写计划.json"

    dialog.vars["writing_plan_path"].set(str(custom))
    NewConfigWizardDialog._sync_state_from_fields(dialog)
    dialog.vars["project_root"].set(str(old_root))
    NewConfigWizardDialog._confirm_project_root_from_var(dialog)

    assert dialog.state.writing_plan_path == custom


def test_wizard_browse_writing_plan_uses_json_filter(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    captured = {}
    selected = tmp_path / "plans" / "writing-plan.json"
    selected.parent.mkdir()
    selected.write_text('{"version": 1, "items": []}', encoding="utf-8")

    def fake_open(**kwargs):
        captured.update(kwargs)
        return str(selected)

    monkeypatch.setattr("bid_writer.new_config_wizard.filedialog.askopenfilename", fake_open)

    NewConfigWizardDialog._browse_path(dialog, "writing_plan_path", "json")

    assert captured["filetypes"] == [("JSON", "*.json")]
    assert ("全部文件", "*.*") not in captured["filetypes"]
    assert dialog.vars["writing_plan_path"].get() == str(selected)


def test_wrong_writing_plan_extension_blocks_basics_step(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = [step.key for step in new_config_wizard.WIZARD_STEPS].index("basics")
    dialog.vars["bidder_name"].set("测试公司")
    dialog.vars["writing_plan_path"].set(str(tmp_path / "撰写计划.txt"))
    shown_errors = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.showerror",
        lambda *args, **kwargs: shown_errors.append(args),
    )

    assert NewConfigWizardDialog._validate_current_step(dialog) is False
    assert shown_errors and ".json" in shown_errors[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_project_root_change_rebases_default_writing_plan_and_preserves_custom tests/test_new_config_wizard.py::test_wizard_browse_writing_plan_uses_json_filter tests/test_new_config_wizard.py::test_wrong_writing_plan_extension_blocks_basics_step -q
```

Expected: FAIL because `writing_plan_path` UI and JSON filter are absent.

- [ ] **Step 3: Import strict path helpers**

Before editing:

```bash
impact({target: "NewConfigWizardDialog._browse_path", direction: "upstream", repo: "Bidx_pc"})
impact({target: "NewConfigWizardDialog._build_basics_step", direction: "upstream", repo: "Bidx_pc"})
```

Add imports:

```python
from bid_writer.path_purposes import PathPurpose, file_dialog_options, require_supported_suffix
```

- [ ] **Step 4: Add writing-plan controls**

In `_build_basics_step()`, after `_add_outline_path_row(...)` add:

```python
        self._add_path_row(
            outline_box,
            1,
            "节点撰写计划文件",
            "writing_plan_path",
            browse_kind="json",
            tooltip_key="new_config.basics.writing_plan_path",
        )
```

Move output row from `2` to `3`:

```python
        self._add_path_row(outline_box, 3, "输出目录", "output_dir", browse_kind="dir", tooltip_key="new_config.basics.output_dir")
```

- [ ] **Step 5: Rebase writing-plan defaults**

Replace `_rebase_default_material_paths()` with a generic helper:

```python
    def _rebase_default_project_paths(
        self,
        *,
        previous_project_root: Path,
        project_root: Path,
        requirements_path: Path | None,
        scoring_path: Path | None,
        outline_path: Path,
        writing_plan_path: Path,
        output_dir: Path,
    ) -> tuple[Path | None, Path | None, Path, Path, Path]:
        if previous_project_root == project_root:
            return requirements_path, scoring_path, outline_path, writing_plan_path, output_dir

        old_defaults = build_state_from_project_root(previous_project_root)
        new_defaults = build_state_from_project_root(project_root)
        if requirements_path == old_defaults.requirements_path:
            requirements_path = new_defaults.requirements_path
            self.vars["requirements_path"].set(str(requirements_path))
        if scoring_path == old_defaults.scoring_path:
            scoring_path = new_defaults.scoring_path
            self.vars["scoring_path"].set(str(scoring_path))
        if outline_path == old_defaults.outline_path:
            outline_path = new_defaults.outline_path
            self.vars["outline_path"].set(str(outline_path))
        if writing_plan_path == old_defaults.writing_plan_path:
            writing_plan_path = new_defaults.writing_plan_path
            self.vars["writing_plan_path"].set(str(writing_plan_path))
        if output_dir == old_defaults.output_dir:
            output_dir = new_defaults.output_dir
            self.vars["output_dir"].set(str(output_dir))
        return requirements_path, scoring_path, outline_path, writing_plan_path, output_dir
```

Update `_sync_state_from_fields()` to call this helper and assign all returned paths.

- [ ] **Step 6: Apply strict filters in wizard browsing**

In `_select_source_file()`, replace hard-coded filetypes:

```python
        options = file_dialog_options(PathPurpose.TENDER)
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择招标文件",
            filetypes=list(options.filetypes),
        )
```

In `_browse_path()`, add:

```python
        options = None
```

For existing outline:

```python
                options = file_dialog_options(PathPurpose.MARKDOWN)
                selected = filedialog.askopenfilename(
                    parent=self,
                    title="选择已有 Markdown 大纲",
                    initialdir=str(initial_dir),
                    filetypes=list(options.filetypes),
                )
```

For generated outline save:

```python
                options = file_dialog_options(PathPurpose.MARKDOWN)
                selected = filedialog.asksaveasfilename(
                    parent=self,
                    title="选择大纲保存位置",
                    initialdir=str(initial_dir),
                    initialfile=Path(current_value).name if current_value else "投标大纲.md",
                    defaultextension=options.defaultextension,
                    filetypes=list(options.filetypes),
                )
```

For JSON:

```python
        elif browse_kind == "json":
            options = file_dialog_options(PathPurpose.JSON)
            selected = filedialog.askopenfilename(
                parent=self,
                title="选择节点撰写计划 JSON",
                initialdir=str(initial_dir),
                filetypes=list(options.filetypes),
            )
```

Keep directory browsing unchanged.

- [ ] **Step 7: Validate manual suffixes**

Add helper:

```python
    def _validate_path_suffixes(self) -> None:
        state = self._require_state()
        if state.source_path is not None:
            require_supported_suffix(state.source_path, PathPurpose.TENDER, label="招标文件")
        if state.requirements_path is not None:
            require_supported_suffix(state.requirements_path, PathPurpose.MARKDOWN, label="采购需求文件")
        if state.scoring_path is not None:
            require_supported_suffix(state.scoring_path, PathPurpose.MARKDOWN, label="评分标准文件")
        require_supported_suffix(state.outline_path, PathPurpose.MARKDOWN, label="投标大纲文件")
        require_supported_suffix(state.writing_plan_path, PathPurpose.JSON, label="节点撰写计划文件")
```

Call this inside `_validate_current_step()` after `_sync_state_from_fields()`:

```python
        try:
            self._validate_path_suffixes()
        except ValueError as exc:
            messagebox.showerror("路径格式无效", str(exc), parent=self)
            return False
```

- [ ] **Step 8: Run tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_path_purposes.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: add wizard writing plan path controls"
```

### Task 8: Writing Plan Save Flow and Rollback

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Write failing tests for initialize-before-save**

Add:

```python
def test_save_and_apply_initializes_missing_writing_plan_before_config_save(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"].set("测试公司")
    writing_plan = tmp_path / "撰写计划.json"
    saved = tmp_path / "config_项目.yaml"
    order = []
    destroyed = []

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return []

        def save(self, model=None, *, target_path=None, create_backup=True):
            order.append(("save", writing_plan.exists()))
            return saved

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    dialog.destroy = lambda: destroyed.append(True)

    NewConfigWizardDialog._save_and_apply(dialog)

    assert order == [("save", True)]
    assert writing_plan.read_text(encoding="utf-8") == '{\n  "version": 1,\n  "items": []\n}\n'
    assert dialog.result == {"saved_path": saved, "apply_path": saved}
    assert destroyed == [True]


def test_save_and_apply_reuses_existing_writing_plan_without_overwriting(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"].set("测试公司")
    raw = '{"version":1,"items":[]}'
    dialog.state.writing_plan_path.write_text(raw, encoding="utf-8")

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return []

        def save(self, model=None, *, target_path=None, create_backup=True):
            return target_path

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    dialog.destroy = lambda: None

    NewConfigWizardDialog._save_and_apply(dialog)

    assert dialog.state.writing_plan_path.read_text(encoding="utf-8") == raw


def test_config_save_failure_rolls_back_only_new_writing_plan(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"].set("测试公司")
    writing_plan = dialog.state.writing_plan_path
    shown_errors = []

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return []

        def save(self, model=None, *, target_path=None, create_backup=True):
            raise OSError("disk full")

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.showerror",
        lambda *args, **kwargs: shown_errors.append(args),
    )

    NewConfigWizardDialog._save_and_apply(dialog)

    assert not writing_plan.exists()
    assert dialog.result == {"saved_path": None, "apply_path": None}
    assert shown_errors and "disk full" in shown_errors[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_save_and_apply_initializes_missing_writing_plan_before_config_save tests/test_new_config_wizard.py::test_save_and_apply_reuses_existing_writing_plan_without_overwriting tests/test_new_config_wizard.py::test_config_save_failure_rolls_back_only_new_writing_plan -q
```

Expected: FAIL because `_save_and_apply()` does not call `WritingPlanStore.initialize()`.

- [ ] **Step 3: Import store**

Before editing:

```bash
impact({target: "NewConfigWizardDialog._save_and_apply", direction: "upstream", repo: "Bidx_pc"})
```

Add:

```python
from bid_writer.writing_plan_store import WritingPlanStore, WritingPlanStoreError
```

- [ ] **Step 4: Add initialize helper**

Add near `_save_and_apply()`:

```python
    def _initialize_writing_plan(self) -> bool:
        state = self._require_state()
        result = WritingPlanStore(state.writing_plan_path).initialize()
        if result.created:
            register_created_path(state, state.writing_plan_path)
        return result.created
```

- [ ] **Step 5: Update `_save_and_apply()` save order**

Replace the method:

```python
    def _save_and_apply(self) -> None:
        created_plan_path: Path | None = None
        try:
            self._sync_state_from_fields()
            self._validate_path_suffixes()
            state = self._require_state()
            if not state.project_root.exists() or not state.project_root.is_dir():
                raise ValueError(f"项目根目录不存在或不是目录：{state.project_root}")
            document = build_editor_document_from_state(state)
            messages = document.validate(document.model, config_path=state.config_path)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return

        errors = [item.text for item in messages if item.level == "error"]
        if errors:
            messagebox.showerror("校验失败", "\n".join(errors), parent=self)
            return

        try:
            if self._initialize_writing_plan():
                created_plan_path = self._require_state().writing_plan_path
            saved_path = document.save(document.model, target_path=self._require_state().config_path, create_backup=True)
        except Exception as exc:
            if created_plan_path is not None:
                with suppress(OSError):
                    created_plan_path.unlink()
                state = self._require_state()
                state.created_paths = [path for path in state.created_paths if path != created_plan_path]
            messagebox.showerror("保存失败", str(exc), parent=self)
            return

        self.result["saved_path"] = saved_path
        self.result["apply_path"] = saved_path
        self.destroy()
```

Add `from contextlib import suppress` at the top.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_writing_plan_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: initialize writing plan during wizard save"
```

### Task 9: Review Summary and Project-External Markers

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Write failing review summary test**

Add:

```python
def test_review_summary_lists_writing_plan_status_and_external_references(tmp_path: Path):
    project = tmp_path / "项目"
    external_requirements = tmp_path / "shared" / "采购需求.md"
    external_plan = tmp_path / "shared" / "撰写计划.json"
    external_requirements.parent.mkdir()
    external_requirements.write_text("需求", encoding="utf-8")
    external_plan.write_text('{"version": 1, "items": []}', encoding="utf-8")
    dialog = _dialog(project)
    dialog.state.requirements_path = external_requirements
    dialog.state.writing_plan_path = external_plan

    NewConfigWizardDialog._sync_review_summary(dialog)

    summary = dialog.review_summary_var.get()
    assert f"节点撰写计划：{external_plan}（复用，项目外文件）" in summary
    assert f"采购需求：{external_requirements}（项目外文件）" in summary
    assert "项目外引用：" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_review_summary_lists_writing_plan_status_and_external_references -q
```

Expected: FAIL because summary does not mention writing-plan status or external references.

- [ ] **Step 3: Add path label helpers**

Before editing:

```bash
impact({target: "NewConfigWizardDialog._sync_review_summary", direction: "upstream", repo: "Bidx_pc"})
```

Add:

```python
    def _is_project_external(self, path: Path | None) -> bool:
        if path is None:
            return False
        state = self._require_state()
        try:
            path.resolve(strict=False).relative_to(state.project_root.resolve(strict=False))
        except ValueError:
            return True
        return False

    def _format_review_path(self, path: Path | None) -> str:
        if path is None:
            return "未填写"
        suffix = "（项目外文件）" if self._is_project_external(path) else ""
        return f"{path}{suffix}"

    def _format_writing_plan_status(self) -> str:
        state = self._require_state()
        status = "复用" if state.writing_plan_path.exists() else "新建"
        external = "，项目外文件" if self._is_project_external(state.writing_plan_path) else ""
        return f"{state.writing_plan_path}（{status}{external}）"
```

- [ ] **Step 4: Replace `_sync_review_summary()`**

Use:

```python
    def _sync_review_summary(self) -> None:
        if not hasattr(self, "review_summary_var") or self.state is None:
            return
        created = "\n".join(f"- {path}" for path in self.state.created_paths) or "- 暂无"
        outline_source = self.vars["outline_source"].get().strip() or "generate"
        outline_source_text = "已有 Markdown 大纲" if outline_source == "existing" else "生成后保存"
        source_copy = (
            f"{self.state.source_path} -> {self.state.source_copy_path}"
            if self.state.should_copy_source and self.state.source_path is not None
            else "无需复制"
        )
        external_refs = [
            str(path)
            for path in (
                self.state.requirements_path,
                self.state.scoring_path,
                self.state.outline_path,
                self.state.writing_plan_path,
            )
            if self._is_project_external(path)
        ]
        external_block = "\n".join(f"- {path}" for path in external_refs) or "- 暂无"
        self.review_summary_var.set(
            "\n".join(
                [
                    f"项目根目录：{self.state.project_root}",
                    f"配置文件：{self.state.config_path}",
                    f"招标文件复制：{source_copy}",
                    f"大纲来源：{outline_source_text}",
                    f"采购需求：{self._format_review_path(self.state.requirements_path)}",
                    f"评分标准：{self._format_review_path(self.state.scoring_path)}",
                    f"投标大纲：{self._format_review_path(self.state.outline_path)}",
                    f"节点撰写计划：{self._format_writing_plan_status()}",
                    f"输出目录：{self.state.output_dir}",
                    "项目外引用：",
                    external_block,
                    "可清理的本次生成内容：",
                    created,
                ]
            )
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: show writing plan status in wizard review"
```

### Task 10: Config Editor Strict Filters

**Files:**
- Modify: `bid_writer/config_editor_dialog.py`
- Test: `tests/test_config_editor_dialog.py`

- [ ] **Step 1: Write failing tests for config editor file filters**

Add:

```python
def test_config_editor_writing_plan_browse_uses_json_filter(monkeypatch, tmp_path: Path):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {"project.writing_plan_file": StubVar("./撰写计划.json")}
    dialog._current_project_root = lambda: tmp_path
    dialog._current_config_dir = lambda: tmp_path
    dialog._display_relative_path = ConfigEditorDialog._display_relative_path.__get__(dialog, ConfigEditorDialog)
    selected = tmp_path / "plans" / "撰写计划.json"
    selected.parent.mkdir()
    selected.write_text('{"version": 1, "items": []}', encoding="utf-8")
    captured = {}

    def fake_open(**kwargs):
        captured.update(kwargs)
        return str(selected)

    monkeypatch.setattr(config_editor_dialog.filedialog, "askopenfilename", fake_open)

    ConfigEditorDialog._browse_path(dialog, "project.writing_plan_file", "file", "project")

    assert captured["filetypes"] == [("JSON", "*.json")]
    assert ("全部文件", "*.*") not in captured["filetypes"]
    assert dialog.vars["project.writing_plan_file"].get() == "./plans/撰写计划.json"


def test_config_editor_markdown_and_yaml_filters_are_strict(monkeypatch, tmp_path: Path):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {"project.outline_file": StubVar("./投标大纲.md")}
    dialog._current_project_root = lambda: tmp_path
    dialog._current_config_dir = lambda: tmp_path
    dialog._display_relative_path = ConfigEditorDialog._display_relative_path.__get__(dialog, ConfigEditorDialog)
    selected = tmp_path / "投标大纲.md"
    selected.write_text("# 大纲", encoding="utf-8")
    captured = {}

    monkeypatch.setattr(
        config_editor_dialog.filedialog,
        "askopenfilename",
        lambda **kwargs: captured.setdefault("open", kwargs) or str(selected),
    )

    ConfigEditorDialog._browse_path(dialog, "project.outline_file", "file", "project")

    assert captured["open"]["filetypes"] == [("Markdown", "*.md")]
    assert ("全部文件", "*.*") not in captured["open"]["filetypes"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_editor_dialog.py::test_config_editor_writing_plan_browse_uses_json_filter tests/test_config_editor_dialog.py::test_config_editor_markdown_and_yaml_filters_are_strict -q
```

Expected: FAIL because `_browse_path()` has no path-purpose awareness.

- [ ] **Step 3: Add path purpose mapping**

Before editing:

```bash
impact({target: "ConfigEditorDialog._browse_path", direction: "upstream", repo: "Bidx_pc"})
```

Add import:

```python
from bid_writer.path_purposes import PathPurpose, file_dialog_options
```

Add module-level mapping after imports:

```python
_PATH_PURPOSE_BY_KEY = {
    "project.outline_generation.role_file": PathPurpose.MARKDOWN,
    "project.outline_file": PathPurpose.MARKDOWN,
    "project.writing_plan_file": PathPurpose.JSON,
    "project.bid_requirements_file": PathPurpose.MARKDOWN,
    "project.scoring_criteria_file": PathPurpose.MARKDOWN,
    "writing.role_file": PathPurpose.MARKDOWN,
}
```

- [ ] **Step 4: Update `_browse_path()`**

Replace the file branch:

```python
        if browse_kind == "dir":
            selected = filedialog.askdirectory(parent=self, initialdir=initial_dir)
        else:
            purpose = _PATH_PURPOSE_BY_KEY.get(key)
            if purpose is None:
                selected = filedialog.askopenfilename(parent=self, initialdir=initial_dir)
            else:
                options = file_dialog_options(purpose)
                selected = filedialog.askopenfilename(
                    parent=self,
                    initialdir=initial_dir,
                    filetypes=list(options.filetypes),
                )
```

Keep relative display unchanged:

```python
        selected_path = Path(selected).resolve()
        self.vars[key].set(self._display_relative_path(selected_path, base_dir))
```

- [ ] **Step 5: Update Save As YAML filter only if needed**

`_save_as()` already has:

```python
filetypes=[("YAML", "*.yaml *.yml")]
```

Keep it. Do not add `"全部文件"`.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_config_editor_dialog.py tests/test_path_purposes.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add bid_writer/config_editor_dialog.py tests/test_config_editor_dialog.py
git commit -m "feat: use strict filters in config editor"
```

### Task 11: Config Editor Writing Plan Validation

**Files:**
- Modify: `bid_writer/config_editor.py`
- Test: `tests/test_config_editor.py`

- [ ] **Step 1: Write failing tests for validation**

Add:

```python
def test_config_editor_validation_rejects_existing_invalid_writing_plan(tmp_path: Path):
    _write_project_files(tmp_path)
    invalid = tmp_path / "撰写计划.json"
    invalid.write_text("not-json", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试公司"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
    writing_plan_file: "./撰写计划.json"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate(document.model, config_path=config_path)

    assert any(item.level == "error" and "撰写计划文件必须为有效 JSON" in item.text for item in messages)


def test_config_editor_validation_allows_empty_and_missing_writing_plan_for_compatibility(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试公司"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    document.model["project"]["writing_plan_file"] = ""
    messages = document.validate(document.model, config_path=config_path)
    assert not any("撰写计划" in item.text for item in messages if item.level == "error")

    document.model["project"]["writing_plan_file"] = "./missing-plan.json"
    messages = document.validate(document.model, config_path=config_path)
    assert not any("撰写计划" in item.text for item in messages if item.level == "error")


def test_config_editor_validation_rejects_wrong_writing_plan_extension(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试公司"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
    writing_plan_file: "./撰写计划.txt"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate(document.model, config_path=config_path)

    assert any(item.level == "error" and ".json" in item.text for item in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_editor.py::test_config_editor_validation_rejects_existing_invalid_writing_plan tests/test_config_editor.py::test_config_editor_validation_allows_empty_and_missing_writing_plan_for_compatibility tests/test_config_editor.py::test_config_editor_validation_rejects_wrong_writing_plan_extension -q
```

Expected: FAIL because writing-plan file validation is absent.

- [ ] **Step 3: Add imports**

Before editing:

```bash
impact({target: "validate_editor_model", direction: "upstream", repo: "Bidx_pc"})
```

In `bid_writer/config_editor.py`, add:

```python
from bid_writer.path_purposes import PathPurpose, require_supported_suffix
from bid_writer.writing_plan_store import WritingPlanStore, WritingPlanStoreError
```

- [ ] **Step 4: Add writing-plan validation block**

In `validate_editor_model()`, after outline validation and before procurement/scoring loop, add:

```python
    writing_plan_value = _coerce_str(model["project"].get("writing_plan_file", "")).strip()
    if writing_plan_value:
        try:
            require_supported_suffix(writing_plan_value, PathPurpose.JSON, label="节点撰写计划文件")
        except ValueError as exc:
            messages.append(ValidationMessage("error", str(exc)))
        else:
            writing_plan_path = _resolve_path(writing_plan_value, root_dir)
            if writing_plan_path.exists():
                try:
                    WritingPlanStore(writing_plan_path).load_snapshot()
                except WritingPlanStoreError as exc:
                    messages.append(ValidationMessage("error", str(exc)))
```

This preserves:
- Empty field compatibility.
- Missing non-empty path compatibility.
- Existing invalid file blocked before save.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_config_editor.py tests/test_config_schema.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/config_editor.py tests/test_config_editor.py
git commit -m "feat: validate configured writing plan files"
```

### Task 12: Config Examples and Documentation

**Files:**
- Modify: `docs/config_schema.md`
- Modify: `README.md`
- Modify: `config.example.yaml`
- Modify: `config_*.yaml` if tests require updated examples
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Decide canonical example filename**

Use the design default `./撰写计划.json` for new wizard-generated configs. Update `config.example.yaml` if the example should now match the wizard default:

```yaml
    writing_plan_file: ./撰写计划.json
```

If the product intentionally wants English examples to remain `./writing-plan.json`, keep `config.example.yaml` unchanged and update only docs to say the wizard default is `./撰写计划.json`. The design says "默认启用 `./撰写计划.json`", so prefer changing the example.

- [ ] **Step 2: Write or update config schema tests**

In `tests/test_config_schema.py`, update:

```python
def test_config_example_documents_relative_writing_plan_file():
    example_path = REPO_ROOT / "config.example.yaml"

    payload = yaml.safe_load(example_path.read_text(encoding="utf-8"))

    writing_plan_file = payload["project"]["inputs"]["writing_plan_file"]
    assert writing_plan_file == "./撰写计划.json"
    assert not Path(writing_plan_file).is_absolute()
```

Add:

```python
def test_config_schema_docs_describe_project_root_first_wizard():
    docs = (REPO_ROOT / "docs" / "config_schema.md").read_text(encoding="utf-8")

    assert "新建配置向导会先要求选择一个已存在的项目根目录" in docs
    assert "project.inputs.writing_plan_file" in docs
    assert "./撰写计划.json" in docs
    assert "文件选择器不会提供“全部文件”选项" in docs
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_schema.py::test_config_example_documents_relative_writing_plan_file tests/test_config_schema.py::test_config_schema_docs_describe_project_root_first_wizard -q
```

Expected: FAIL until docs/example are updated.

- [ ] **Step 4: Update `config.example.yaml`**

Change:

```yaml
    writing_plan_file: ./writing-plan.json
```

to:

```yaml
    writing_plan_file: ./撰写计划.json
```

- [ ] **Step 5: Update `docs/config_schema.md`**

Replace the paragraph under `project` that currently says the wizard derives root from tender file:

```markdown
GUI 新建配置向导会先要求选择一个已存在的项目根目录。配置文件默认保存为 `project.root_dir/config_<项目文件夹名>.yaml`，保存后的 YAML 使用 `project.root_dir: "."`。采购需求、评分标准、大纲、节点撰写计划和输出目录的默认值都从该项目根目录派生。选择招标文件只会更新来源文件、复制目标和导入目录，不会重新推导或覆盖项目根目录。
```

In section `3.1.2 节点撰写计划文件`, add after the first paragraph:

```markdown
新建配置向导默认写入 `project.inputs.writing_plan_file: "./撰写计划.json"`。保存并应用时，如果该文件不存在，向导会在已确认的项目根目录下创建规范空 JSON v1；如果文件已存在且合法，则原样复用；如果文件已存在但不是合法 JSON v1，则阻止保存配置且不会覆盖。用户选择项目外 JSON 时会直接引用原文件，不复制。
```

Add a short strict-filter paragraph under path rules:

```markdown
GUI 文件选择器按字段严格过滤扩展名：招标文件仅 `.pdf/.docx/.doc/.xlsx/.xls`，Markdown 资源仅 `.md`，节点撰写计划仅 `.json`，配置文件仅 `.yaml/.yml`。文件选择器不会提供“全部文件”选项；手工输入路径仍会在保存前独立校验扩展名。
```

- [ ] **Step 6: Update `README.md` new config workflow**

Replace the two bullets that say new config starts from tender file with:

```markdown
- “新建配置...”会打开新建配置向导。第一步先选择一个已存在的项目根目录，配置文件默认保存为该目录下的 `config_<项目文件夹名>.yaml`，采购需求、评分标准、投标大纲、节点撰写计划和输出目录也都会默认放在该目录下。
- 选择项目根目录后，可以选择招标文件自动抽取资料，也可以手动创建。招标文件位于项目外时，向导会在保存过程中复制到项目根目录的 `招标文件/` 下；选择招标文件不会改变已经确认的项目根目录。
- 新建配置默认启用 `./撰写计划.json`。保存并应用时，向导会创建缺失的空 JSON v1 文件，或复用已有合法文件；已有非法 JSON 会阻止保存，避免覆盖用户资料。
```

Under "新建配置中导入招标文件", replace the opening sentence with:

```markdown
在“项目 -> 新建配置...”向导中，先选择项目根目录，再选择或跳过招标文件。选择招标文件后，向导只更新来源文件和导入目标，不会重新推导项目根目录。
```

- [ ] **Step 7: Update project examples if needed**

Check examples:

```bash
find . -maxdepth 1 -name 'config_*.yaml' -print
```

If a config already has a project-specific Chinese writing-plan file, keep it. If a test asserts a specific value, update tests and examples consistently. Do not rewrite unrelated config fields.

- [ ] **Step 8: Run tests**

Run:

```bash
uv run pytest tests/test_config_schema.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add docs/config_schema.md README.md config.example.yaml tests/test_config_schema.py
git add config_*.yaml
git commit -m "docs: document project-root-first config defaults"
```

If no `config_*.yaml` files changed, omit that `git add` line.

### Task 13: Wizard Import and Existing Tests Cleanup

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Test: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Run the full wizard test file**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: Some legacy tests may fail because they assumed:
- Source step first.
- Initial state always exists.
- `project_root.mkdir(parents=True, exist_ok=True)` can create a project root.
- File dialogs include `"全部文件"`.

- [ ] **Step 2: Fix import flow to respect existing root**

Before editing:

```bash
impact({target: "NewConfigWizardDialog._run_import", direction: "upstream", repo: "Bidx_pc"})
```

In `_run_import()`, replace implicit root creation:

```python
        self.state.project_root.mkdir(parents=True, exist_ok=True)
```

with:

```python
        state = self._require_state()
        if not state.project_root.exists() or not state.project_root.is_dir():
            messagebox.showerror("路径无效", f"项目根目录不存在或不是目录：{state.project_root}", parent=self)
            return
```

Keep import subdirectories created by `TenderImportService` as existing behavior.

- [ ] **Step 3: Update source and manual tests to start from location-confirmed dialog**

For tests that exercise source/materials/basics/review directly, keep using `_dialog(tmp_path)` with `initialize_state=True`.

For constructor tests, use `_dialog(tmp_path, initialize_state=False)`.

For tests that expect step index values, replace numeric literals with:

```python
source_index = [step.key for step in new_config_wizard.WIZARD_STEPS].index("source")
location_index = [step.key for step in new_config_wizard.WIZARD_STEPS].index("location")
```

- [ ] **Step 4: Update file filter assertions**

Replace any expected filetypes containing `"全部文件"` with the strict lists from `path_purposes.py`, for example:

```python
assert captured["filetypes"] == [("Markdown", "*.md")]
```

- [ ] **Step 5: Update cancellation tests for nullable state**

If `_cancel()` references `self.state.created_paths`, make it tolerant:

```python
        if self.state is None or not self.state.created_paths:
            self.destroy()
            return
```

Add test:

```python
def test_cancel_before_project_root_confirmation_destroys_without_cleanup_prompt(tmp_path: Path, monkeypatch):
    dialog = _dialog(tmp_path, initialize_state=False)
    calls = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.askyesnocancel",
        lambda *args, **kwargs: calls.append(args),
    )
    dialog.destroy = lambda: calls.append(("destroy",))

    NewConfigWizardDialog._cancel(dialog)

    assert calls == [("destroy",)]
```

- [ ] **Step 6: Run wizard tests again**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "test: update wizard coverage for root-first flow"
```

### Task 14: Integration Regression

**Files:**
- No code changes expected unless tests reveal defects.

- [ ] **Step 1: Run targeted suite**

Run:

```bash
uv run pytest tests/test_new_config_flow.py tests/test_new_config_wizard.py tests/test_writing_plan_store.py tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_path_purposes.py tests/test_config_schema.py -q
```

Expected: PASS.

- [ ] **Step 2: Fix any targeted failures with TDD-sized patches**

For each failure:
- Reproduce the single failing test.
- Explain whether it is a test expectation update or product bug.
- Make the smallest code or test change.
- Re-run the single test.
- Re-run the targeted suite.

Do not batch unrelated failures into one opaque commit.

- [ ] **Step 3: Run full suite**

Run:

```bash
uv run pytest
```

Expected: PASS.

- [ ] **Step 4: Run GitNexus change detection**

Run:

```bash
detect_changes({scope: "compare", base_ref: "main", repo: "Bidx_pc"})
```

Expected:
- Changed symbols limited to `new_config_flow`, `new_config_wizard`, `writing_plan_store`, `config_editor`, `config_editor_dialog`, docs/config examples, and tests.
- No unexpected generation/runtime execution flows affected beyond config loading/editing.

- [ ] **Step 5: Manual smoke test**

Run the GUI:

```bash
uv run python run.py
```

Manual checks:
- Open "新建配置...".
- Confirm first step is "项目位置" and root field is empty.
- Select an existing empty project directory.
- Confirm config path becomes `root/config_<folder>.yaml`.
- Continue without tender file.
- Select or create valid Markdown material files.
- Confirm writing plan path defaults to `root/撰写计划.json`.
- Save and apply.
- Verify config YAML contains:

```yaml
project:
  root_dir: "."
  inputs:
    writing_plan_file: "./撰写计划.json"
```

- Verify `root/撰写计划.json` contains:

```json
{
  "version": 1,
  "items": []
}
```

- [ ] **Step 6: Final commit if manual fixes were needed**

If Task 14 produced code/docs changes:

```bash
git add <changed-files>
git commit -m "fix: stabilize project-root-first wizard regression"
```

If no changes were needed, do not create an empty commit.

---

## Final Verification Checklist

- [ ] New wizard first step requires an existing project root.
- [ ] Wizard opening state does not derive paths from current config dir or program dir.
- [ ] Config path is `project_root/config_<sanitized_folder_name>.yaml`.
- [ ] Saved canonical YAML uses `project.root_dir: "."`.
- [ ] Selecting a tender file never changes project root.
- [ ] External tender files are copied to `project_root/招标文件/<name>` during existing import flow.
- [ ] Requirements, scoring, outline, writing plan, and output defaults all derive from project root.
- [ ] Project-internal input/output paths serialize as `./...` with POSIX separators.
- [ ] Project-external input files serialize as absolute paths, not `../...`.
- [ ] New config writes non-empty `project.inputs.writing_plan_file`.
- [ ] Missing writing-plan file is created as canonical JSON v1 before config save.
- [ ] Existing valid writing-plan file is reused byte-for-byte.
- [ ] Existing invalid writing-plan file blocks save and is not overwritten.
- [ ] Config save failure removes only the writing-plan file created by this save attempt.
- [ ] Config editor keeps empty and missing writing-plan path compatibility.
- [ ] Config editor blocks existing invalid writing-plan JSON.
- [ ] All file dialogs use strict supported filters and no `"全部文件"` option.
- [ ] `uv run pytest` passes.
- [ ] `detect_changes({scope: "compare", base_ref: "main"})` has expected scope.

## Self-Review Notes

Spec coverage:
- Root-first wizard: Tasks 2, 3, 5, 6, 7, 13.
- Writing-plan lifecycle: Tasks 4, 7, 8, 9, 11.
- Strict file filters: Tasks 1, 7, 10, 11.
- Config editor compatibility: Tasks 10, 11.
- Serialization rules: Tasks 2, 3, 12.
- Rollback behavior: Task 8.
- Docs and examples: Task 12.
- Regression and GitNexus: Task 14.

Placeholder scan:
- No banned placeholder patterns were found.
- Every implementation task includes concrete tests, code snippets, commands, expected results, and commit command.

Risk notes:
- `ConfigEditorDialog._browse_path` was HIGH in GitNexus impact. The plan constrains this to a data-driven key-to-purpose mapping and tests two representative project paths. If execution impact remains HIGH, report the blast radius before Task 10 edits.
- The GitNexus index was stale during planning. Re-run analysis in the execution worktree before editing and run `detect_changes()` before final handoff or commit stack completion.
