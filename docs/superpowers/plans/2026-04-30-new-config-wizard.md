# New Config Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current new-config big form with a dedicated wizard that starts from a tender file, derives project paths, imports or manually selects project materials, saves canonical YAML, and applies the new config.

**Architecture:** Add a pure `new_config_flow.py` module for all path derivation, state, editor-model building, source-file copy planning, and cleanup. Add `new_config_wizard.py` for the Tk wizard UI and keep `config_editor.py` as the single source for canonical config rendering and validation. Extend `tender_import_service.py` only where the wizard needs explicit import directories, source-file tracking, and created-path reporting.

**Tech Stack:** Python 3.10+, Tkinter/ttk, PyYAML through existing config editor code, existing tender import service, `uv run pytest`.

---

## File Structure

- Create `bid_writer/new_config_flow.py`
  - Owns `NewConfigWizardState`, path inference, safe relative path formatting, editor model construction, source copy planning, and cleanup helpers.
  - Contains no Tk imports.
- Create `bid_writer/new_config_wizard.py`
  - Owns `NewConfigWizardDialog`, step navigation, field variables, modal actions, and calls into `new_config_flow.py`, `TenderImportService`, and `ConfigEditorDocument.save()`.
- Modify `bid_writer/tender_import_service.py`
  - Add optional `import_dir` input and `created_paths` output.
  - Keep existing callers working without new arguments.
- Modify `bid_writer/gui.py`
  - Change `open_new_config_editor()` to open `NewConfigWizardDialog`.
  - Keep modal workflow disabling and old-config preservation behavior.
- Modify `tests/test_gui_new_config.py`
  - Update monkeypatch target and assertions for the new wizard class.
- Create `tests/test_new_config_flow.py`
  - Cover path inference, source copy decisions, editor model construction, and cleanup safety.
- Create `tests/test_new_config_wizard.py`
  - Cover step navigation and non-visual dialog behavior through `__new__` plus stub state/widgets.
- Modify `tests/test_tender_import_service.py`
  - Cover explicit import directory and created-path reporting.
- Modify `README.md` and `docs/config_schema.md`
  - Document the new wizard flow after implementation.

## Task 1: Pure Flow Model And Path Inference

**Files:**
- Create: `bid_writer/new_config_flow.py`
- Create: `tests/test_new_config_flow.py`

- [ ] **Step 1: Write failing tests for directory inference**

Add `tests/test_new_config_flow.py`:

```python
from pathlib import Path

from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_initial_state_from_source,
    copy_source_file_if_needed,
    cleanup_created_paths,
    derive_project_name,
    format_relative_path,
    should_copy_source_file,
)


def test_regular_tender_directory_becomes_project_root(tmp_path: Path):
    source = tmp_path / "公共服务满意度招标文件.docx"
    source.write_text("fake", encoding="utf-8")
    current_config = tmp_path / "config.yaml"

    state = build_initial_state_from_source(source, current_config_path=current_config)

    assert state.project_root == tmp_path
    assert state.config_path == tmp_path / "config_公共服务满意度.yaml"
    assert state.requirements_path == tmp_path / "项目要求" / "项目采购需求.md"
    assert state.scoring_path == tmp_path / "项目要求" / "评分标准.md"
    assert state.outline_path == tmp_path / "投标大纲.md"
    assert state.output_dir == tmp_path / "output"
    assert state.should_copy_source is False


def test_materials_directory_itself_becomes_project_root(tmp_path: Path):
    project = tmp_path / "公共服务项目"
    source_dir = project / "招标文件"
    source_dir.mkdir(parents=True)
    source = source_dir / "采购文件.pdf"
    source.write_text("fake", encoding="utf-8")

    state = build_initial_state_from_source(source, current_config_path=tmp_path / "config.yaml")

    assert state.project_root == source_dir
    assert state.should_copy_source is False


def test_downloads_source_directory_becomes_project_root(tmp_path: Path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    source = downloads / "公共服务满意度项目招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    current_config = tmp_path / "workspace" / "config.yaml"
    current_config.parent.mkdir()

    state = build_initial_state_from_source(source, current_config_path=current_config)

    assert state.project_root == downloads
    assert state.should_copy_source is False
    assert state.source_copy_path is None


def test_project_name_strips_common_tender_suffixes():
    assert derive_project_name("公共服务满意度项目招标文件.pdf") == "公共服务满意度项目"
    assert derive_project_name("采购文件") == "新项目"


def test_format_relative_path_prefers_project_relative(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    target = project / "项目要求" / "评分标准.md"

    assert format_relative_path(target, project) == "./项目要求/评分标准.md"


def test_should_copy_source_file_only_for_project_external_sources(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()

    assert should_copy_source_file(project / "招标文件" / "a.pdf", project) is False
    assert should_copy_source_file(tmp_path / "Downloads" / "a.pdf", project) is True


def test_cleanup_created_paths_removes_only_recorded_files_and_empty_dirs(tmp_path: Path):
    keep = tmp_path / "用户已有.md"
    keep.write_text("keep", encoding="utf-8")
    created_dir = tmp_path / "项目要求"
    created_dir.mkdir()
    created_file = created_dir / "评分标准.md"
    created_file.write_text("score", encoding="utf-8")
    nested_keep = created_dir / "用户补充.md"
    nested_keep.write_text("user", encoding="utf-8")

    state = NewConfigWizardState(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=created_file,
        outline_path=tmp_path / "投标大纲.md",
        output_dir=tmp_path / "output",
        bidder_name="",
        created_paths=[created_file, created_dir],
        manual_inputs=False,
    )

    failures = cleanup_created_paths(state)

    assert failures == []
    assert not created_file.exists()
    assert created_dir.exists()
    assert nested_keep.exists()
    assert keep.exists()


def test_copy_source_file_if_needed_copies_external_source_and_records_path(tmp_path: Path):
    source = tmp_path / "Downloads" / "tender.pdf"
    source.parent.mkdir()
    source.write_text("source", encoding="utf-8")
    project = tmp_path / "项目"
    project.mkdir()
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=True,
        source_copy_path=project / "招标文件" / "tender.pdf",
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )

    copied = copy_source_file_if_needed(state)

    assert copied == project / "招标文件" / "tender.pdf"
    assert copied.read_text(encoding="utf-8") == "source"
    assert state.copied_source_path == copied
    assert copied in state.created_paths


def test_copy_source_file_if_needed_skips_project_internal_source(tmp_path: Path):
    project = tmp_path / "项目"
    source = project / "招标文件" / "tender.pdf"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    state = NewConfigWizardState(
        source_path=source,
        project_root=project,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )

    copied = copy_source_file_if_needed(state)

    assert copied is None
    assert state.created_paths == []
```

- [ ] **Step 2: Run tests and verify import failure**

Run:

```bash
uv run pytest tests/test_new_config_flow.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.new_config_flow'`.

- [ ] **Step 3: Implement flow dataclass and inference helpers**

Create `bid_writer/new_config_flow.py`:

```python
"""Pure new-config wizard state and path planning helpers."""

from __future__ import annotations

import copy
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config_editor import ConfigEditorDocument, create_new_config_editor_document


DEFAULT_REQUIREMENTS_RELATIVE = "./项目要求/项目采购需求.md"
DEFAULT_SCORING_RELATIVE = "./项目要求/评分标准.md"
DEFAULT_OUTLINE_RELATIVE = "./投标大纲.md"
DEFAULT_OUTPUT_RELATIVE = "./output"


@dataclass
class NewConfigWizardState:
    source_path: Path | None
    project_root: Path
    config_path: Path
    import_dir: Path | None
    should_copy_source: bool
    source_copy_path: Path | None
    copied_source_path: Path | None
    requirements_path: Path | None
    scoring_path: Path | None
    outline_path: Path
    output_dir: Path
    bidder_name: str
    created_paths: list[Path] = field(default_factory=list)
    manual_inputs: bool = False


def build_initial_state_from_source(source_path: Path, *, current_config_path: Path) -> NewConfigWizardState:
    source = Path(source_path).expanduser().resolve()
    config_path = Path(current_config_path).expanduser().resolve()
    project_name = derive_project_name(source.name)
    project_root = infer_project_root(source, config_path.parent, project_name)
    config_file = config_path.parent / f"config_{project_name}.yaml"
    should_copy = should_copy_source_file(source, project_root)
    source_copy = project_root / "招标文件" / source.name if should_copy else None
    import_dir = project_root / ".bid_writer" / "imports" / "pending"
    return NewConfigWizardState(
        source_path=source,
        project_root=project_root,
        config_path=config_file,
        import_dir=import_dir,
        should_copy_source=should_copy,
        source_copy_path=source_copy,
        copied_source_path=None,
        requirements_path=project_root / "项目要求" / "项目采购需求.md",
        scoring_path=project_root / "项目要求" / "评分标准.md",
        outline_path=project_root / "投标大纲.md",
        output_dir=project_root / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=False,
    )


def build_manual_state(*, project_root: Path, config_path: Path) -> NewConfigWizardState:
    root = Path(project_root).expanduser().resolve()
    config = Path(config_path).expanduser().resolve()
    return NewConfigWizardState(
        source_path=None,
        project_root=root,
        config_path=config,
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=root / "项目要求" / "项目采购需求.md",
        scoring_path=root / "项目要求" / "评分标准.md",
        outline_path=root / "投标大纲.md",
        output_dir=root / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=True,
    )


def infer_project_root(source_path: Path, config_dir: Path, project_name: str) -> Path:
    return source_path.parent


def derive_project_name(filename: str) -> str:
    stem = Path(filename).stem.strip()
    cleaned = re.sub(r"(招标文件|采购文件|招标公告|采购公告|竞争性磋商文件|公开招标文件)$", "", stem).strip(" _-—")
    return cleaned or "新项目"


def should_copy_source_file(source_path: Path, project_root: Path) -> bool:
    source = Path(source_path).expanduser().resolve()
    root = Path(project_root).expanduser().resolve()
    try:
        source.relative_to(root)
        return False
    except ValueError:
        return True


def format_relative_path(path: Path, base_dir: Path) -> str:
    resolved = Path(path).expanduser().resolve()
    base = Path(base_dir).expanduser().resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        return resolved.as_posix()
    return "./" + relative.as_posix()


def register_created_path(state: NewConfigWizardState, path: Path) -> None:
    resolved = Path(path).expanduser().resolve()
    if resolved not in state.created_paths:
        state.created_paths.append(resolved)


def cleanup_created_paths(state: NewConfigWizardState) -> list[Path]:
    failures: list[Path] = []
    for path in reversed(state.created_paths):
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except OSError:
            failures.append(path)
    return failures


def copy_source_file_if_needed(state: NewConfigWizardState) -> Path | None:
    if not state.should_copy_source:
        return None
    if state.source_path is None or state.source_copy_path is None:
        return None
    source = Path(state.source_path).expanduser().resolve()
    target = Path(state.source_copy_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        state.copied_source_path = target
        return target
    shutil.copy2(source, target)
    state.copied_source_path = target
    register_created_path(state, target)
    return target
```

- [ ] **Step 4: Run flow tests**

Run:

```bash
uv run pytest tests/test_new_config_flow.py -q
```

Expected: PASS for the tests added in this task.

- [ ] **Step 5: Commit**

```bash
git add bid_writer/new_config_flow.py tests/test_new_config_flow.py
git commit -m "feat: add new config path planning"
```

## Task 2: Build Canonical Editor Model From Wizard State

**Files:**
- Modify: `bid_writer/new_config_flow.py`
- Modify: `tests/test_new_config_flow.py`

- [ ] **Step 1: Add failing tests for editor model construction**

Append to `tests/test_new_config_flow.py`:

```python
import yaml

from bid_writer.new_config_flow import build_editor_document_from_state


def test_build_editor_document_uses_relative_project_paths(tmp_path: Path):
    project = tmp_path / "项目"
    project.mkdir()
    config_path = tmp_path / "config_项目.yaml"
    requirements = project / "项目要求" / "项目采购需求.md"
    scoring = project / "项目要求" / "评分标准.md"
    requirements.parent.mkdir()
    requirements.write_text("需求", encoding="utf-8")
    scoring.write_text("评分", encoding="utf-8")

    state = NewConfigWizardState(
        source_path=None,
        project_root=project,
        config_path=config_path,
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=requirements,
        scoring_path=scoring,
        outline_path=project / "投标大纲.md",
        output_dir=project / "output",
        bidder_name="测试公司",
        created_paths=[],
        manual_inputs=True,
    )

    document = build_editor_document_from_state(state)
    payload = yaml.safe_load(document.render_yaml())

    assert payload["project"]["root_dir"] == "./项目"
    assert payload["project"]["bidder_name"] == "测试公司"
    assert payload["project"]["outline_locked"] is False
    assert payload["project"]["inputs"]["outline_file"] == "./投标大纲.md"
    assert payload["project"]["inputs"]["bid_requirements_file"] == "./项目要求/项目采购需求.md"
    assert payload["project"]["inputs"]["scoring_criteria_file"] == "./项目要求/评分标准.md"
    assert payload["project"]["output_dir"] == "./output"


def test_build_editor_document_requires_bidder_identity(tmp_path: Path):
    state = build_manual_state(project_root=tmp_path, config_path=tmp_path / "config.yaml")
    document = build_editor_document_from_state(state)

    messages = document.validate(document.model, config_path=state.config_path)

    assert any(item.level == "error" and "投标主体名称不能为空" in item.text for item in messages)
```

- [ ] **Step 2: Run tests and verify missing function**

Run:

```bash
uv run pytest tests/test_new_config_flow.py::test_build_editor_document_uses_relative_project_paths tests/test_new_config_flow.py::test_build_editor_document_requires_bidder_identity -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `build_editor_document_from_state`.

- [ ] **Step 3: Implement model construction**

Append to `bid_writer/new_config_flow.py`:

```python
def build_editor_document_from_state(state: NewConfigWizardState) -> ConfigEditorDocument:
    document = create_new_config_editor_document(state.config_path)
    model = copy.deepcopy(document.model)
    model["project"]["root_dir"] = format_relative_path(state.project_root, state.config_path.parent)
    model["project"]["bidder_name"] = state.bidder_name.strip()
    model["project"]["outline_locked"] = False
    model["project"]["outline_file"] = format_relative_path(state.outline_path, state.project_root)
    model["project"]["bid_requirements_mode"] = "file"
    model["project"]["bid_requirements_file"] = (
        format_relative_path(state.requirements_path, state.project_root)
        if state.requirements_path is not None
        else DEFAULT_REQUIREMENTS_RELATIVE
    )
    model["project"]["scoring_criteria_mode"] = "file"
    model["project"]["scoring_criteria_file"] = (
        format_relative_path(state.scoring_path, state.project_root)
        if state.scoring_path is not None
        else DEFAULT_SCORING_RELATIVE
    )
    model["project"]["output_dir"] = format_relative_path(state.output_dir, state.project_root)
    document.model = model
    document.require_project_identity = True
    return document
```

- [ ] **Step 4: Run flow tests**

Run:

```bash
uv run pytest tests/test_new_config_flow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bid_writer/new_config_flow.py tests/test_new_config_flow.py
git commit -m "feat: build config model from wizard state"
```

## Task 3: Tender Import Explicit Paths And Created-Path Reporting

**Files:**
- Modify: `bid_writer/tender_import_service.py`
- Modify: `tests/test_tender_import_service.py`

- [ ] **Step 1: Add failing service tests**

Append to `tests/test_tender_import_service.py`:

```python
def test_import_service_accepts_explicit_import_dir_and_reports_created_paths(tmp_path: Path):
    source = tmp_path / "source" / "tender.docx"
    source.parent.mkdir()
    source.write_text("fake", encoding="utf-8")
    explicit_import_dir = tmp_path / "项目" / ".bid_writer" / "imports" / "fixed-id"
    conversion = type("Conversion", (), {"output_dir": explicit_import_dir})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "ignored-id",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path / "项目",
        import_dir=explicit_import_dir,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: True,
    )

    assert service.converter.calls[0] == (source, explicit_import_dir)
    assert result.import_dir == explicit_import_dir
    assert result.created_paths == (
        result.extraction_report_path,
        result.requirements_path,
        result.scoring_path,
    )


def test_import_service_cancelled_low_confidence_reports_only_report_path(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "fixed-id"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.50),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "fixed-id",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: False,
    )

    assert result.cancelled is True
    assert result.created_paths == (result.extraction_report_path,)
```

- [ ] **Step 2: Run focused tests and verify signature failure**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_import_service_accepts_explicit_import_dir_and_reports_created_paths tests/test_tender_import_service.py::test_import_service_cancelled_low_confidence_reports_only_report_path -q
```

Expected: FAIL because `import_document()` does not accept `import_dir` and `TenderImportResult` has no `created_paths`.

- [ ] **Step 3: Extend service result and import arguments**

Modify `bid_writer/tender_import_service.py`:

```python
@dataclass(frozen=True)
class TenderImportResult:
    requirements_path: Path | None
    scoring_path: Path | None
    relative_requirements_path: str
    relative_scoring_path: str
    import_dir: Path
    extraction_report_path: Path
    extraction: TenderSectionExtraction
    cancelled: bool = False
    created_paths: tuple[Path, ...] = ()
```

Change the `import_document` signature and import directory creation:

```python
    def import_document(
        self,
        *,
        source_path: Path,
        project_root: Path,
        confirm_overwrite: Callable[[Path], bool],
        confirm_low_confidence: Callable[[TenderSectionExtraction], bool],
        import_dir: Path | None = None,
    ) -> TenderImportResult:
        project_root = Path(project_root).expanduser().resolve()
        import_dir = (
            Path(import_dir).expanduser().resolve()
            if import_dir is not None
            else project_root / ".bid_writer" / "imports" / self.import_id_factory()
        )
        import_dir.mkdir(parents=True, exist_ok=True)
```

After writing `report_path`, make the cancelled result include only the report:

```python
            return TenderImportResult(
                requirements_path=None,
                scoring_path=None,
                relative_requirements_path="./项目要求/项目采购需求.md",
                relative_scoring_path="./项目要求/评分标准.md",
                import_dir=import_dir,
                extraction_report_path=report_path,
                extraction=extraction,
                cancelled=True,
                created_paths=(report_path,),
            )
```

Make the success result include all created file paths:

```python
        return TenderImportResult(
            requirements_path=requirements_path,
            scoring_path=scoring_path,
            relative_requirements_path="./项目要求/项目采购需求.md",
            relative_scoring_path="./项目要求/评分标准.md",
            import_dir=import_dir,
            extraction_report_path=report_path,
            extraction=extraction,
            created_paths=(report_path, requirements_path, scoring_path),
        )
```

- [ ] **Step 4: Run import service tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bid_writer/tender_import_service.py tests/test_tender_import_service.py
git commit -m "feat: report tender import created paths"
```

## Task 4: Wizard Dialog Skeleton And Step Navigation

**Files:**
- Create: `bid_writer/new_config_wizard.py`
- Create: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Add failing navigation tests**

Create `tests/test_new_config_wizard.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from bid_writer.new_config_wizard import NewConfigWizardDialog, WIZARD_STEPS


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StubButton:
    def __init__(self):
        self.config_calls = []

    def configure(self, **kwargs):
        self.config_calls.append(kwargs)


def _dialog(tmp_path: Path) -> NewConfigWizardDialog:
    dialog = NewConfigWizardDialog.__new__(NewConfigWizardDialog)
    dialog.current_step_index = 0
    dialog.max_completed_step_index = 0
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.status_var = StubVar("")
    dialog.back_button = StubButton()
    dialog.next_button = StubButton()
    dialog.step_buttons = []
    dialog.step_frames = {}
    dialog.state = SimpleNamespace(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        requirements_path=None,
        scoring_path=None,
        bidder_name="",
    )
    dialog._show_step = lambda: None
    return dialog


def test_wizard_defines_five_steps():
    assert [step.key for step in WIZARD_STEPS] == [
        "source",
        "location",
        "materials",
        "basics",
        "review",
    ]


def test_go_next_advances_when_current_step_valid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: True
    dialog._sync_footer = lambda: None

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 1
    assert dialog.max_completed_step_index == 1


def test_go_next_stays_when_current_step_invalid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: False
    dialog._sync_footer = lambda: None

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 0
    assert dialog.max_completed_step_index == 0


def test_go_back_moves_to_previous_step(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2
    dialog._sync_footer = lambda: None

    NewConfigWizardDialog._go_back(dialog)

    assert dialog.current_step_index == 1
```

- [ ] **Step 2: Run tests and verify missing module**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.new_config_wizard'`.

- [ ] **Step 3: Implement wizard constants and navigation skeleton**

Create `bid_writer/new_config_wizard.py`:

```python
"""Tkinter new-config wizard."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config_editor import create_new_config_editor_document
from .gui import _bootstyle_kwargs, _compute_screen_limited_dialog_size, _set_centered_window_geometry, apply_window_surface, setup_gui_theme
from .new_config_flow import NewConfigWizardState, build_initial_state_from_source, build_manual_state


@dataclass(frozen=True)
class WizardStep:
    key: str
    label: str
    hint: str


WIZARD_STEPS = (
    WizardStep("source", "招标文件", "选择来源"),
    WizardStep("location", "项目位置", "确认根目录"),
    WizardStep("materials", "资料抽取", "采购需求 / 评分"),
    WizardStep("basics", "基础信息", "主体 / 大纲"),
    WizardStep("review", "保存应用", "检查并进入项目"),
)


class NewConfigWizardDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config_path: str | Path | None = None):
        super().__init__(parent)
        self.parent_window = parent
        self.style = setup_gui_theme(self)
        apply_window_surface(self)
        self.result: dict[str, Any] = {"saved_path": None, "apply_path": None}
        self.current_step_index = 0
        self.max_completed_step_index = 0
        initial_config_path = Path(config_path or "config_新项目.yaml").expanduser().resolve()
        self.state = build_manual_state(
            project_root=initial_config_path.parent,
            config_path=initial_config_path,
        )
        self.status_var = tk.StringVar(value="第 1 步，共 5 步")
        self.vars: dict[str, tk.Variable] = {}
        self.step_buttons: list[ttk.Button] = []
        self.step_frames: dict[str, ttk.Frame] = {}
        self.title("新建配置向导")
        size = _compute_screen_limited_dialog_size(
            desired_width=1040,
            desired_height=760,
            min_width=920,
            min_height=680,
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, size.width, size.height)
        self.minsize(size.min_width, size.min_height)
        self.transient(parent)
        self.grab_set()
        self._create_variables()
        self._create_widgets()
        self._sync_fields_from_state()
        self._show_step()
        self._sync_footer()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _create_variables(self) -> None:
        self.vars["source_path"] = tk.StringVar()
        self.vars["project_root"] = tk.StringVar()
        self.vars["config_path"] = tk.StringVar()
        self.vars["requirements_path"] = tk.StringVar()
        self.vars["scoring_path"] = tk.StringVar()
        self.vars["outline_path"] = tk.StringVar()
        self.vars["output_dir"] = tk.StringVar()
        self.vars["bidder_name"] = tk.StringVar()

    def _go_next(self) -> None:
        if self.current_step_index == len(WIZARD_STEPS) - 1:
            self._save_and_apply()
            return
        if not self._validate_current_step():
            return
        self.current_step_index += 1
        self.max_completed_step_index = max(self.max_completed_step_index, self.current_step_index)
        self._show_step()
        self._sync_footer()

    def _go_back(self) -> None:
        if self.current_step_index <= 0:
            return
        self.current_step_index -= 1
        self._show_step()
        self._sync_footer()

    def _validate_current_step(self) -> bool:
        step_key = WIZARD_STEPS[self.current_step_index].key
        if step_key == "source":
            return True
        if step_key == "location":
            return bool(str(self.vars["project_root"].get()).strip())
        if step_key == "materials":
            return bool(str(self.vars["requirements_path"].get()).strip()) and bool(str(self.vars["scoring_path"].get()).strip())
        if step_key == "basics":
            return bool(str(self.vars["bidder_name"].get()).strip())
        return True
```

Also add placeholder UI methods in the same file so the class can instantiate:

```python
    def _create_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body = ttk.Frame(self, padding=16)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(body, padding=(0, 0, 12, 0))
        sidebar.grid(row=0, column=0, sticky="ns")
        content = ttk.Frame(body)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        for index, step in enumerate(WIZARD_STEPS):
            button = ttk.Button(sidebar, text=f"{index + 1}. {step.label}", command=lambda i=index: self._jump_to_step(i))
            button.pack(fill=tk.X, pady=4)
            self.step_buttons.append(button)
            frame = ttk.Frame(content, padding=12)
            frame.grid(row=0, column=0, sticky="nsew")
            self.step_frames[step.key] = frame
        self._build_source_step(self.step_frames["source"])
        self._build_location_step(self.step_frames["location"])
        self._build_materials_step(self.step_frames["materials"])
        self._build_basics_step(self.step_frames["basics"])
        self._build_review_step(self.step_frames["review"])
        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        actions = ttk.Frame(footer)
        actions.grid(row=0, column=1, sticky="e")
        self.back_button = ttk.Button(actions, text="上一步", command=self._go_back, **_bootstyle_kwargs("secondary"))
        self.back_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="取消", command=self._cancel, **_bootstyle_kwargs("secondary")).pack(side=tk.LEFT, padx=(0, 8))
        self.next_button = ttk.Button(actions, text="下一步", command=self._go_next, **_bootstyle_kwargs("primary"))
        self.next_button.pack(side=tk.LEFT)

    def _jump_to_step(self, index: int) -> None:
        if index > self.max_completed_step_index:
            return
        self.current_step_index = index
        self._show_step()
        self._sync_footer()

    def _show_step(self) -> None:
        active_key = WIZARD_STEPS[self.current_step_index].key
        for key, frame in self.step_frames.items():
            if key == active_key:
                frame.tkraise()

    def _sync_footer(self) -> None:
        self.status_var.set(f"第 {self.current_step_index + 1} 步，共 {len(WIZARD_STEPS)} 步")
        self.back_button.configure(state=tk.DISABLED if self.current_step_index == 0 else tk.NORMAL)
        self.next_button.configure(text="保存并应用" if self.current_step_index == len(WIZARD_STEPS) - 1 else "下一步")
```

- [ ] **Step 4: Run wizard navigation tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: add new config wizard shell"
```

## Task 5: Wizard Fields, Import Actions, Save, And Cancel Cleanup

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Modify: `tests/test_new_config_wizard.py`
- Modify: `bid_writer/new_config_flow.py`

- [ ] **Step 1: Add failing tests for save and cleanup behavior**

Append to `tests/test_new_config_wizard.py`:

```python
def test_save_and_apply_sets_result_from_document(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"] = StubVar("测试公司")
    dialog.vars["project_root"] = StubVar(str(tmp_path))
    dialog.vars["config_path"] = StubVar(str(tmp_path / "config_测试.yaml"))
    dialog.vars["requirements_path"] = StubVar(str(tmp_path / "项目要求" / "项目采购需求.md"))
    dialog.vars["scoring_path"] = StubVar(str(tmp_path / "项目要求" / "评分标准.md"))
    dialog.vars["outline_path"] = StubVar(str(tmp_path / "投标大纲.md"))
    dialog.vars["output_dir"] = StubVar(str(tmp_path / "output"))
    saved = tmp_path / "config_测试.yaml"

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return []

        def save(self, model=None, *, target_path=None, create_backup=True):
            return saved

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    dialog.destroy = lambda: None

    NewConfigWizardDialog._save_and_apply(dialog)

    assert dialog.result == {"saved_path": saved, "apply_path": saved}


def test_cancel_with_created_paths_can_cleanup(monkeypatch, tmp_path: Path):
    created = tmp_path / "created.md"
    created.write_text("created", encoding="utf-8")
    dialog = _dialog(tmp_path)
    dialog.state.created_paths = [created]
    questions = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.askyesnocancel",
        lambda *args, **kwargs: questions.append(args) or False,
    )
    dialog.destroy = lambda: questions.append(("destroy",))

    NewConfigWizardDialog._cancel(dialog)

    assert not created.exists()
    assert ("destroy",) in questions
```

- [ ] **Step 2: Run focused tests and verify missing methods**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_save_and_apply_sets_result_from_document tests/test_new_config_wizard.py::test_cancel_with_created_paths_can_cleanup -q
```

Expected: FAIL because `_save_and_apply()` and `_cancel()` are incomplete or missing.

- [ ] **Step 3: Implement field sync, save, and cancel cleanup**

Modify imports in `bid_writer/new_config_wizard.py`:

```python
from .new_config_flow import (
    NewConfigWizardState,
    build_editor_document_from_state,
    build_initial_state_from_source,
    build_manual_state,
    cleanup_created_paths,
    copy_source_file_if_needed,
)
```

Add these methods:

```python
    def _sync_fields_from_state(self) -> None:
        self.vars["source_path"].set("" if self.state.source_path is None else str(self.state.source_path))
        self.vars["project_root"].set(str(self.state.project_root))
        self.vars["config_path"].set(str(self.state.config_path))
        self.vars["requirements_path"].set("" if self.state.requirements_path is None else str(self.state.requirements_path))
        self.vars["scoring_path"].set("" if self.state.scoring_path is None else str(self.state.scoring_path))
        self.vars["outline_path"].set(str(self.state.outline_path))
        self.vars["output_dir"].set(str(self.state.output_dir))
        self.vars["bidder_name"].set(self.state.bidder_name)

    def _sync_state_from_fields(self) -> None:
        self.state.project_root = Path(str(self.vars["project_root"].get())).expanduser().resolve()
        self.state.config_path = Path(str(self.vars["config_path"].get())).expanduser().resolve()
        requirements = str(self.vars["requirements_path"].get()).strip()
        scoring = str(self.vars["scoring_path"].get()).strip()
        self.state.requirements_path = Path(requirements).expanduser().resolve() if requirements else None
        self.state.scoring_path = Path(scoring).expanduser().resolve() if scoring else None
        self.state.outline_path = Path(str(self.vars["outline_path"].get())).expanduser().resolve()
        self.state.output_dir = Path(str(self.vars["output_dir"].get())).expanduser().resolve()
        self.state.bidder_name = str(self.vars["bidder_name"].get()).strip()

    def _save_and_apply(self) -> None:
        self._sync_state_from_fields()
        document = build_editor_document_from_state(self.state)
        messages = document.validate(document.model, config_path=self.state.config_path)
        errors = [item for item in messages if item.level == "error"]
        if errors:
            messagebox.showerror("校验失败", "\n".join(item.text for item in errors), parent=self)
            return
        try:
            saved_path = document.save(document.model, target_path=self.state.config_path, create_backup=True)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.result["saved_path"] = saved_path
        self.result["apply_path"] = saved_path
        self.destroy()

    def _cancel(self) -> None:
        if not getattr(self.state, "created_paths", []):
            self.destroy()
            return
        choice = messagebox.askyesnocancel(
            "取消新建配置",
            "本次向导已经生成了一些资料。选择“是”保留资料，选择“否”清理本次生成内容，选择“取消”返回向导。",
            parent=self,
        )
        if choice is None:
            return
        if choice is False:
            failures = cleanup_created_paths(self.state)
            if failures:
                messagebox.showerror("清理失败", "\n".join(str(path) for path in failures), parent=self)
                return
        self.destroy()
```

- [ ] **Step 4: Implement source selection and import action**

Add source selection:

```python
    def _select_source_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择招标文件",
            filetypes=[
                ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx *.doc"),
                ("Excel", "*.xlsx *.xls"),
                ("全部文件", "*.*"),
            ],
        )
        if not selected:
            return
        self.state = build_initial_state_from_source(Path(selected), current_config_path=self.state.config_path)
        self._sync_fields_from_state()
        self.max_completed_step_index = max(self.max_completed_step_index, 1)
        self.current_step_index = 1
        self._show_step()
        self._sync_footer()
```

Add import action:

```python
    def _run_import(self) -> None:
        from .tender_import_dialog import confirm_low_confidence
        from .tender_import_service import TenderImportError, TenderImportService

        self._sync_state_from_fields()
        if self.state.source_path is None:
            messagebox.showwarning("缺少招标文件", "请先选择招标文件，或手动选择采购需求和评分标准文件。", parent=self)
            return
        try:
            copy_source_file_if_needed(self.state)
            result = TenderImportService().import_document(
                source_path=self.state.source_path,
                project_root=self.state.project_root,
                import_dir=self.state.import_dir,
                confirm_overwrite=lambda path: messagebox.askyesno("确认覆盖", f"{path.name} 已存在且非空。是否覆盖并生成 .bak 备份？", parent=self),
                confirm_low_confidence=lambda extraction: confirm_low_confidence(self, extraction),
            )
        except TenderImportError as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        if result.cancelled:
            self.state.created_paths.extend(path for path in result.created_paths if path not in self.state.created_paths)
            return
        self.state.requirements_path = result.requirements_path
        self.state.scoring_path = result.scoring_path
        self.state.created_paths.extend(path for path in result.created_paths if path not in self.state.created_paths)
        self._sync_fields_from_state()
```

Wire buttons in `_build_source_step()` and `_build_materials_step()`:

```python
    def _build_source_step(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="选择招标文件", style="SectionTitle.TLabel").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.vars["source_path"]).pack(fill=tk.X, pady=(10, 8))
        ttk.Button(frame, text="选择招标文件...", command=self._select_source_file, **_bootstyle_kwargs("primary")).pack(anchor="w")

    def _build_location_step(self, frame: ttk.Frame) -> None:
        for label, key in (("项目根目录", "project_root"), ("配置文件保存位置", "config_path")):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=self.vars[key]).pack(fill=tk.X, pady=(2, 8))

    def _build_materials_step(self, frame: ttk.Frame) -> None:
        ttk.Button(frame, text="开始抽取", command=self._run_import, **_bootstyle_kwargs("primary")).pack(anchor="w", pady=(0, 10))
        for label, key in (("采购需求文件", "requirements_path"), ("评分标准文件", "scoring_path")):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=self.vars[key]).pack(fill=tk.X, pady=(2, 8))
```

Add basics and review minimal builders:

```python
    def _build_basics_step(self, frame: ttk.Frame) -> None:
        for label, key in (("投标主体名称", "bidder_name"), ("大纲保存位置 / 已有大纲文件", "outline_path"), ("输出目录", "output_dir")):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=self.vars[key]).pack(fill=tk.X, pady=(2, 8))

    def _build_review_step(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="保存前请确认配置路径、资料文件和大纲路径。").pack(anchor="w")
```

- [ ] **Step 5: Run wizard tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py bid_writer/new_config_flow.py
git commit -m "feat: save new config wizard output"
```

## Task 6: Wire Main Window To The New Wizard

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_gui_new_config.py`

- [ ] **Step 1: Update failing GUI tests to expect `NewConfigWizardDialog`**

In `tests/test_gui_new_config.py`, replace `FakeConfigEditorDialog` classes in new-config tests with `FakeNewConfigWizardDialog`, and change monkeypatch lines to:

```python
monkeypatch.setattr("bid_writer.new_config_wizard.NewConfigWizardDialog", FakeNewConfigWizardDialog)
```

For `test_open_new_config_editor_uses_default_path_next_to_current_config`, assert:

```python
assert created == [
    {"parent": fake_window, "config_path": expected_path}
]
```

The fake class constructor should be:

```python
class FakeNewConfigWizardDialog:
    def __init__(self, parent, config_path):
        created.append({"parent": parent, "config_path": config_path})
        self.result = {"apply_path": expected_path}
```

- [ ] **Step 2: Run focused GUI tests and verify failure**

Run:

```bash
uv run pytest tests/test_gui_new_config.py::test_open_new_config_editor_uses_default_path_next_to_current_config tests/test_gui_new_config.py::test_open_new_config_editor_ignores_cancelled_dialog -q
```

Expected: FAIL because `MainWindow.open_new_config_editor()` still imports `ConfigEditorDialog`.

- [ ] **Step 3: Modify `open_new_config_editor()`**

In `bid_writer/gui.py`, replace the import and dialog construction:

```python
    def open_new_config_editor(self):
        """打开新配置创建向导。"""
        from .new_config_wizard import NewConfigWizardDialog

        current_config_path = self.bid_writer.config.config_path.resolve()
        default_path = current_config_path.parent / "config_新项目.yaml"
        self._set_modal_workflow_active(True, "正在新建配置，当前项目暂未切换")
        try:
            dialog = NewConfigWizardDialog(self, default_path)
            self.wait_window(dialog)
        finally:
            self._set_modal_workflow_active(False)

        apply_path = dialog.result.get("apply_path")
        if not apply_path:
            self.status_text.set(f"已取消新建配置，仍在使用：{current_config_path.name}")
            return

        apply_resolved = Path(apply_path).expanduser().resolve()
        self._switch_to_config_path(
            apply_resolved,
            force_reload=(apply_resolved == current_config_path),
        )
```

- [ ] **Step 4: Run GUI new-config tests**

Run:

```bash
uv run pytest tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bid_writer/gui.py tests/test_gui_new_config.py
git commit -m "feat: open new config wizard from project menu"
```

## Task 7: Documentation And Regression Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/config_schema.md`

- [ ] **Step 1: Update README new-config workflow text**

In `README.md`, replace the current new-config note under “使用流程” with:

```markdown
- “新建配置...”会打开新建配置向导。默认从选择招标文件开始，系统会把项目根目录设置为招标文件所在目录，并据此推导配置文件保存位置、资料目录、输出目录和大纲路径；用户确认后可自动抽取采购需求和评分标准。抽取失败时可手动选择采购需求和评分标准文件。
```

Update “新建配置中导入招标文件” first paragraph to:

```markdown
在“项目 -> 新建配置...”向导中，第一步可以选择一个招标文件。向导会先把项目根目录设置为招标文件所在目录并让用户确认，确认后再转换招标文件、抽取“项目采购需求”和“评分标准”，并写入配置引用的独立 Markdown 文件。
```

- [ ] **Step 2: Update config schema documentation**

In `docs/config_schema.md`, add this paragraph near the project path explanation:

```markdown
GUI 新建配置向导会根据招标文件位置生成这些路径。选择招标文件后，`project.root_dir` 默认设置为该招标文件所在目录，并尽量相对配置文件保存；`project.inputs.*` 和 `project.output_dir` 会尽量相对 `project.root_dir` 保存。
```

- [ ] **Step 3: Run focused regression tests**

Run:

```bash
uv run pytest tests/test_new_config_flow.py tests/test_new_config_wizard.py tests/test_tender_import_service.py tests/test_gui_new_config.py tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_config_editor_tender_import.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS. If a GUI test is skipped because Tk is unavailable, record the skip line in the final implementation summary.

- [ ] **Step 5: Review git status**

Run:

```bash
git status --short
```

Expected: only intended changes in `bid_writer/`, `tests/`, `README.md`, and `docs/config_schema.md`. `.superpowers/` may remain untracked from the brainstorming visual companion and must not be staged.

- [ ] **Step 6: Commit**

```bash
git add bid_writer/new_config_flow.py bid_writer/new_config_wizard.py bid_writer/tender_import_service.py bid_writer/gui.py tests/test_new_config_flow.py tests/test_new_config_wizard.py tests/test_tender_import_service.py tests/test_gui_new_config.py README.md docs/config_schema.md
git commit -m "docs: document new config wizard flow"
```

## Self-Review

- Spec coverage:
  - Starts from tender file: Task 1 and Task 5.
  - Directory inference and Downloads/Desktop handling: Task 1.
  - Manual mode: Task 1 `build_manual_state()` and Task 5 material fields.
  - Low-confidence import confirmation: existing service behavior preserved in Task 3 and Task 5.
  - Failed extraction manual fallback: Task 5 leaves editable requirements/scoring file fields after import errors.
  - Source-file smart management: Task 1 plans and tests copy target behavior; Task 5 calls `copy_source_file_if_needed()` before import.
  - Cancel cleanup: Task 1 cleanup helper and Task 5 dialog behavior.
  - Save/apply and outline-preparation reuse: Task 6 keeps existing `_switch_to_config_path()` behavior.
- Placeholder scan:
  - This plan contains no `TBD`, `TODO`, or unspecified “handle later” items.
- Type consistency:
  - `NewConfigWizardState` uses `requirements_path` and `scoring_path`; tests and wizard methods use the same names.
  - Dialog result remains `{"saved_path": ..., "apply_path": ...}` to match `MainWindow.open_new_config_editor()`.
