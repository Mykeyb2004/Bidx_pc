# New Project Config Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GUI flow for creating a new bid project configuration file from canonical defaults.

**Architecture:** Reuse the existing configuration editor model, validation, YAML rendering, and save-as flow. Add a default `ConfigEditorDocument` factory in `bid_writer/config_editor.py`, add a `new_config` mode to `ConfigEditorDialog`, and expose it from the main project menu.

**Tech Stack:** Python 3, Tkinter/ttk, PyYAML, pytest, uv.

---

## File Structure

- Modify `bid_writer/config_editor.py`
  - Add default editor model construction.
  - Add new unsaved `ConfigEditorDocument` construction.
  - Add new-mode required project identity validation.

- Modify `bid_writer/config_editor_dialog.py`
  - Add `new_config` constructor mode.
  - Load a default document instead of reading an existing YAML in new mode.
  - Route the first save through save-as.

- Modify `bid_writer/gui.py`
  - Add the `新建配置...` menu item.
  - Add `open_new_config_editor()` and reuse existing config switching.

- Modify `tests/test_config_editor.py`
  - Cover default document rendering, `fact_cards` defaults, and new-mode validation.

- Modify `tests/test_config_editor_dialog.py`
  - Cover first-save behavior for new unsaved config documents without creating a real Tk window.

- Create `tests/test_gui_new_config.py`
  - Cover menu wiring and `open_new_config_editor()` behavior without creating a real Tk window.

- Modify `README.md`
  - Document the new GUI entry.

---

### Task 1: Add Default Config Document Tests

**Files:**
- Modify: `tests/test_config_editor.py`
- Modify: `bid_writer/config_editor.py`

- [ ] **Step 1: Write failing tests for the new document factory**

In `tests/test_config_editor.py`, change the imports at the top from:

```python
from pathlib import Path

import yaml

from bid_writer.config_editor import load_config_editor_document
```

to:

```python
import copy
from pathlib import Path

import yaml

from bid_writer.config_editor import (
    create_new_config_editor_document,
    load_config_editor_document,
)
```

Append these tests to the file:

```python
def test_new_config_editor_document_renders_canonical_defaults(tmp_path: Path):
    config_path = tmp_path / "config_新项目.yaml"

    document = create_new_config_editor_document(config_path)
    payload = yaml.safe_load(document.render_yaml())

    assert document.config_path == config_path.resolve()
    assert document.require_project_identity is True
    assert payload["project"] == {
        "root_dir": ".",
        "bidder_name": "",
        "inputs": {
            "outline_file": "./outline.md",
            "bid_requirements_file": "./项目要求/项目采购需求.md",
            "scoring_criteria_file": "./项目要求/评分标准.md",
        },
        "output_dir": "./output",
    }
    assert payload["writing"]["role_file"] == "./roles/example_role.md"
    assert payload["writing"]["target_words"] == {
        "default": 3000,
        "min": 100,
        "max": 15000,
        "step": 100,
        "upper_ratio": 1.15,
    }
    assert payload["writing"]["output_format"] == "纯正文"
    assert payload["writing"]["max_tables_per_section"] == 2
    assert payload["processing"]["path"] == "auto"
    assert payload["models"]["generation"]["model"] == "gpt-4o-mini"
    assert payload["models"]["pruning"]["model"] == "gpt-4o-mini"
    assert payload["models"]["embedding"]["model"] == "text-embedding-3-small"
    assert payload["runtime"]["stream"]["enabled"] is True
    assert payload["runtime"]["trace"]["enabled"] is False
    assert payload["fact_cards"] == {
        "enabled": True,
        "cards": [],
        "chapter_defaults": {},
    }


def test_new_config_editor_document_requires_bidder_name(tmp_path: Path):
    config_path = tmp_path / "config_新项目.yaml"
    document = create_new_config_editor_document(config_path)

    messages = document.validate()

    assert any(
        message.level == "error" and "投标主体名称不能为空" in message.text
        for message in messages
    )


def test_new_config_editor_document_accepts_valid_required_project_fields(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "config_新项目.yaml"
    document = create_new_config_editor_document(config_path)
    model = copy.deepcopy(document.model)
    model["project"]["bidder_name"] = "示例投标单位"
    model["project"]["bid_requirements_file"] = "./bid_requirements.md"
    model["project"]["scoring_criteria_file"] = "./scoring_criteria.md"
    model["processing"]["path"] = "full_context"

    messages = document.validate(model)

    assert not [message for message in messages if message.level == "error"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_editor.py::test_new_config_editor_document_renders_canonical_defaults tests/test_config_editor.py::test_new_config_editor_document_requires_bidder_name tests/test_config_editor.py::test_new_config_editor_document_accepts_valid_required_project_fields -q
```

Expected: FAIL with an import error because `create_new_config_editor_document` does not exist.

- [ ] **Step 3: Add default document support**

In `bid_writer/config_editor.py`, update the `ConfigEditorDocument` dataclass by adding `require_project_identity`:

```python
@dataclass
class ConfigEditorDocument:
    config_path: Path
    raw_config: dict[str, Any]
    model: dict[str, Any]
    preserved_extra: dict[str, Any] = field(default_factory=dict)
    env_status: dict[str, ConnectionStatus] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    require_project_identity: bool = False
```

Replace `ConfigEditorDocument.validate()` with:

```python
    def validate(self, model: dict[str, Any] | None = None) -> list[ValidationMessage]:
        return validate_editor_model(
            model or self.model,
            self.config_path,
            self.env_status,
            self.raw_config,
            require_project_identity=self.require_project_identity,
        )
```

Add these functions immediately after `load_config_editor_document()`:

```python
def build_default_editor_model() -> dict[str, Any]:
    return {
        "project": {
            "root_dir": ".",
            "bidder_name": "",
            "outline_file": "./outline.md",
            "bid_requirements_mode": "file",
            "bid_requirements_file": "./项目要求/项目采购需求.md",
            "bid_requirements_text": "",
            "scoring_criteria_mode": "file",
            "scoring_criteria_file": "./项目要求/评分标准.md",
            "scoring_criteria_text": "",
            "output_dir": "./output",
        },
        "writing": {
            "role_mode": "file",
            "role_file": "./roles/example_role.md",
            "role_text": "",
            "target_words_default": 3000,
            "target_words_min": 100,
            "target_words_max": 15000,
            "target_words_step": 100,
            "target_words_upper_ratio": 1.15,
            "output_format": "纯正文",
            "first_line_template": "",
            "allow_markdown_headings": False,
            "allow_english_terms": False,
            "max_tables_per_section": 2,
            "max_mermaid_flowcharts_per_section": 0,
            "summary_title": "",
            "hard_constraints": [],
            "extra_rules": [
                "内容要专业、严谨，符合标书撰写规范",
                "请根据以上任务卡，结合采购需求、评分标准撰写投标正文。",
            ],
        },
        "processing": {
            "path": "auto",
            "project_background": {
                "enabled": True,
                "max_chars": 800,
            },
            "auto": {
                "requirements_top_k": 8,
                "scoring_parse_mode": "auto",
                "scoring_max_rows": 4,
                "retrieval": {
                    "lexical_enabled": True,
                    "vector_enabled": False,
                    "top_k_lexical": 20,
                    "top_k_fused": 30,
                    "top_k_final": 8,
                    "min_fused_score": 0.0,
                },
            },
            "full_context": {
                "chapter_writing_plan": {
                    "enabled": False,
                    "max_chars": 320,
                },
            },
        },
        "models": {
            "generation": {
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 8000,
                "timeout_seconds": 120,
                "max_retries": 3,
                "top_p": "",
                "seed": "",
            },
            "pruning": {
                "model": "gpt-4o-mini",
                "temperature": 0.2,
                "max_tokens": 1200,
                "timeout_seconds": 60,
                "max_retries": 2,
                "top_p": "",
                "seed": "",
            },
            "embedding": {
                "model": "text-embedding-3-small",
                "batch_size": 64,
                "cache_dir": "./output/_embedding_cache",
                "rebuild_on_source_change": True,
                "query_prefix": "",
                "document_prefix": "",
            },
        },
        "runtime": {
            "stream": {
                "enabled": True,
                "idle_timeout_seconds": 12,
            },
            "trace": {
                "enabled": False,
                "directory": "./log/generation_traces",
                "mode": "full",
                "write_prompt": True,
                "write_output": True,
                "write_context": True,
                "write_summary": True,
                "redact_sensitive": True,
            },
            "debug": {
                "context_pruning_dump": False,
            },
            "output": {
                "prefix": "",
                "include_title_header": True,
                "overwrite_existing": True,
                "filename_max_length": 100,
                "empty_filename_fallback": "untitled",
            },
            "merge": {
                "normalize_soft_line_breaks": False,
            },
        },
    }


def create_new_config_editor_document(config_path: str | Path | None = None) -> ConfigEditorDocument:
    path = Path(config_path or "config_新项目.yaml").expanduser().resolve()
    model = build_default_editor_model()
    raw_config = merge_with_preserved(
        build_canonical_config(model),
        {
            "fact_cards": {
                "enabled": True,
                "cards": [],
                "chapter_defaults": {},
            }
        },
    )
    return ConfigEditorDocument(
        config_path=path,
        raw_config=raw_config,
        model=copy.deepcopy(model),
        preserved_extra=extract_preserved_extra(raw_config),
        env_status=detect_connection_status(path, raw_config),
        notes=build_editor_notes(model, raw_config),
        require_project_identity=True,
    )
```

- [ ] **Step 4: Extend validation for required project identity**

Change the `validate_editor_model()` signature in `bid_writer/config_editor.py` from:

```python
def validate_editor_model(
    model: dict[str, Any],
    config_path: Path,
    env_status: dict[str, ConnectionStatus],
    raw_config: dict[str, Any] | None = None,
) -> list[ValidationMessage]:
```

to:

```python
def validate_editor_model(
    model: dict[str, Any],
    config_path: Path,
    env_status: dict[str, ConnectionStatus],
    raw_config: dict[str, Any] | None = None,
    *,
    require_project_identity: bool = False,
) -> list[ValidationMessage]:
```

Inside `validate_editor_model()`, immediately after `root_dir` validation, add:

```python
    if require_project_identity and not _coerce_str(model["project"]["bidder_name"]).strip():
        messages.append(ValidationMessage("error", "投标主体名称不能为空。"))
```

- [ ] **Step 5: Run the focused tests**

Run:

```bash
uv run pytest tests/test_config_editor.py::test_new_config_editor_document_renders_canonical_defaults tests/test_config_editor.py::test_new_config_editor_document_requires_bidder_name tests/test_config_editor.py::test_new_config_editor_document_accepts_valid_required_project_fields -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add bid_writer/config_editor.py tests/test_config_editor.py
git commit -m "feat: add default config editor document"
```

---

### Task 2: Add New Mode to the Config Editor Dialog

**Files:**
- Modify: `tests/test_config_editor_dialog.py`
- Modify: `bid_writer/config_editor_dialog.py`

- [ ] **Step 1: Write failing tests for dialog first-save behavior**

In `tests/test_config_editor_dialog.py`, change the imports from:

```python
from types import SimpleNamespace

import tkinter as tk

from bid_writer.config_editor_dialog import ScrollableSection
```

to:

```python
from pathlib import Path
from types import SimpleNamespace

import tkinter as tk

from bid_writer.config_editor_dialog import ConfigEditorDialog, ScrollableSection
```

Append these tests:

```python
def test_config_editor_dialog_new_config_save_current_uses_save_as_for_unsaved_file(tmp_path: Path):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    calls: list[str] = []
    dialog.is_new_config = True
    dialog.document = SimpleNamespace(config_path=tmp_path / "config_新项目.yaml")
    dialog.active_config_path = tmp_path / "config_新项目.yaml"
    dialog._save_as = lambda: calls.append("save_as")
    dialog._save = lambda **_kwargs: calls.append("save")

    dialog._save_current()

    assert calls == ["save_as"]


def test_config_editor_dialog_existing_config_save_current_saves_active_document(tmp_path: Path):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    calls: list[dict[str, object]] = []
    config_path = tmp_path / "config.yaml"
    dialog.is_new_config = False
    dialog.document = SimpleNamespace(config_path=config_path)
    dialog.active_config_path = config_path
    dialog._save = lambda **kwargs: calls.append(kwargs)

    dialog._save_current()

    assert calls == [{"target_path": config_path, "ask_switch": False}]
```

- [ ] **Step 2: Run the dialog tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_editor_dialog.py::test_config_editor_dialog_new_config_save_current_uses_save_as_for_unsaved_file tests/test_config_editor_dialog.py::test_config_editor_dialog_existing_config_save_current_saves_active_document -q
```

Expected: FAIL because `ConfigEditorDialog._save_current()` does not know `is_new_config`.

- [ ] **Step 3: Import the new document factory**

In `bid_writer/config_editor_dialog.py`, update the `config_editor` import from:

```python
from .config_editor import (
    ConfigEditorDocument,
    ConnectionStatus,
    ValidationMessage,
    load_config_editor_document,
    summarize_model,
)
```

to:

```python
from .config_editor import (
    ConfigEditorDocument,
    ConnectionStatus,
    ValidationMessage,
    create_new_config_editor_document,
    load_config_editor_document,
    summarize_model,
)
```

- [ ] **Step 4: Add constructor support for `new_config`**

Change the `ConfigEditorDialog.__init__` signature from:

```python
    def __init__(self, parent: tk.Misc, config_path: str | Path):
```

to:

```python
    def __init__(
        self,
        parent: tk.Misc,
        config_path: str | Path | None = None,
        *,
        new_config: bool = False,
    ):
```

Replace:

```python
        self.active_config_path = Path(config_path).expanduser().resolve()
```

with:

```python
        default_config_path = Path.cwd() / "config_新项目.yaml"
        self.active_config_path = Path(config_path or default_config_path).expanduser().resolve()
        self.is_new_config = new_config
```

Replace:

```python
        self.title("配置编辑器")
```

with:

```python
        self.title("新建配置" if self.is_new_config else "配置编辑器")
```

Replace:

```python
        self._load_document(self.active_config_path)
```

with:

```python
        if self.is_new_config:
            self._load_new_document(self.active_config_path)
        else:
            self._load_document(self.active_config_path)
```

- [ ] **Step 5: Add `_load_new_document()`**

In `bid_writer/config_editor_dialog.py`, insert this method immediately before `_load_document()`:

```python
    def _load_new_document(self, config_path: Path) -> None:
        self.document = create_new_config_editor_document(config_path)
        self.current_file_var.set("当前文件：未保存的新配置")
        self._saved_yaml = ""
        self._populate_vars(self.document.model)
        self._update_connection_panel()
        self._refresh_side_panel()
```

- [ ] **Step 6: Make reload reset the template in new mode**

Replace `_reload_from_disk()` in `bid_writer/config_editor_dialog.py` with:

```python
    def _reload_from_disk(self) -> None:
        if self._has_unsaved_changes():
            message = "当前有未保存变更，确定要恢复默认模板吗？" if self.is_new_config else "当前有未保存变更，确定要从磁盘重新载入吗？"
            if not messagebox.askyesno("确认", message, parent=self):
                return
        if self.is_new_config:
            self._load_new_document(self.active_config_path)
            return
        self._load_document(self.document.config_path if self.document else self.active_config_path)
```

- [ ] **Step 7: Route first save through save-as**

Replace `_save_current()` in `bid_writer/config_editor_dialog.py` with:

```python
    def _save_current(self) -> None:
        if self.is_new_config and self.document is not None and not self.document.config_path.exists():
            self._save_as()
            return
        self._save(target_path=self.document.config_path if self.document else self.active_config_path, ask_switch=False)
```

- [ ] **Step 8: Make `_save_as()` offer `config_新项目.yaml` in new mode**

Replace the first line of `_save_as()`:

```python
        initial_path = self.document.config_path if self.document else self.active_config_path
```

with:

```python
        initial_path = self.document.config_path if self.document else self.active_config_path
        if self.is_new_config:
            initial_path = initial_path.with_name("config_新项目.yaml")
```

- [ ] **Step 9: Mark the dialog as regular editing after save**

In `_save()` in `bid_writer/config_editor_dialog.py`, after:

```python
        self.result["saved_path"] = saved_path
```

add:

```python
        self.is_new_config = False
        self.title("配置编辑器")
```

- [ ] **Step 10: Run focused dialog tests**

Run:

```bash
uv run pytest tests/test_config_editor_dialog.py::test_config_editor_dialog_new_config_save_current_uses_save_as_for_unsaved_file tests/test_config_editor_dialog.py::test_config_editor_dialog_existing_config_save_current_saves_active_document -q
```

Expected: PASS.

- [ ] **Step 11: Run all config editor dialog tests**

Run:

```bash
uv run pytest tests/test_config_editor_dialog.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit Task 2**

Run:

```bash
git add bid_writer/config_editor_dialog.py tests/test_config_editor_dialog.py
git commit -m "feat: support new config editor mode"
```

---

### Task 3: Add Main GUI Entry and Switching Flow

**Files:**
- Create: `tests/test_gui_new_config.py`
- Modify: `bid_writer/gui.py`

- [ ] **Step 1: Write failing tests for the menu and command behavior**

Create `tests/test_gui_new_config.py` with:

```python
from pathlib import Path
from types import SimpleNamespace

from bid_writer.gui import MainWindow


class FakeMenu:
    def __init__(self):
        self.items: list[tuple[str, object]] = []
        self.separators = 0

    def add_command(self, *, label: str, command):
        self.items.append((label, command))

    def add_separator(self):
        self.separators += 1


def test_project_menu_includes_new_config_entry():
    window = SimpleNamespace(
        open_new_config_editor=lambda: None,
        select_and_switch_config=lambda: None,
        open_config_editor=lambda: None,
        reload_outline=lambda: None,
        refresh_status=lambda: None,
        open_output_dir=lambda: None,
        quit=lambda: None,
    )
    menu = FakeMenu()

    MainWindow._populate_project_menu(window, menu)

    labels = [label for label, _command in menu.items]
    assert labels[:3] == ["新建配置...", "切换配置...", "编辑当前配置..."]


def test_open_new_config_editor_switches_to_saved_config(monkeypatch, tmp_path: Path):
    current_config = tmp_path / "config.yaml"
    saved_config = tmp_path / "config_新项目.yaml"
    calls: list[tuple[Path, bool]] = []
    captured: dict[str, object] = {}

    class FakeDialog:
        result = {"apply_path": saved_config}

        def __init__(self, parent, config_path=None, *, new_config=False):
            captured["parent"] = parent
            captured["config_path"] = config_path
            captured["new_config"] = new_config

    window = SimpleNamespace(
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(config_path=current_config),
        ),
        wait_window=lambda _dialog: None,
        _switch_to_config_path=lambda path, force_reload=False: calls.append((path, force_reload)),
    )

    monkeypatch.setattr("bid_writer.config_editor_dialog.ConfigEditorDialog", FakeDialog)

    MainWindow.open_new_config_editor(window)

    assert captured == {
        "parent": window,
        "config_path": tmp_path / "config_新项目.yaml",
        "new_config": True,
    }
    assert calls == [(saved_config.resolve(), False)]
```

- [ ] **Step 2: Run the GUI tests to verify they fail**

Run:

```bash
uv run pytest tests/test_gui_new_config.py -q
```

Expected: FAIL because `MainWindow.open_new_config_editor` does not exist and the menu does not include the new entry.

- [ ] **Step 3: Add the menu item**

In `bid_writer/gui.py`, replace `_populate_project_menu()` with:

```python
    def _populate_project_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="新建配置...", command=self.open_new_config_editor)
        menu.add_command(label="切换配置...", command=self.select_and_switch_config)
        menu.add_command(label="编辑当前配置...", command=self.open_config_editor)
        menu.add_separator()
        menu.add_command(label="重载大纲", command=self.reload_outline)
        menu.add_command(label="扫描输出状态", command=self.refresh_status)
        menu.add_separator()
        menu.add_command(label="打开输出目录", command=self.open_output_dir)
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)
```

- [ ] **Step 4: Add `open_new_config_editor()`**

In `bid_writer/gui.py`, insert this method immediately before `open_config_editor()`:

```python
    def open_new_config_editor(self):
        """打开新建配置的可视化编辑器。"""
        from .config_editor_dialog import ConfigEditorDialog

        default_path = self.bid_writer.config.config_path.parent / "config_新项目.yaml"
        dialog = ConfigEditorDialog(self, default_path, new_config=True)
        self.wait_window(dialog)

        apply_path = dialog.result.get("apply_path")
        if not apply_path:
            return

        apply_resolved = Path(apply_path).expanduser().resolve()
        current_resolved = self.bid_writer.config.config_path.resolve()
        self._switch_to_config_path(
            apply_resolved,
            force_reload=(apply_resolved == current_resolved),
        )
```

- [ ] **Step 5: Run focused GUI tests**

Run:

```bash
uv run pytest tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add bid_writer/gui.py tests/test_gui_new_config.py
git commit -m "feat: add new config menu entry"
```

---

### Task 4: Update User Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the GUI usage notes**

In `README.md`, in the `## 使用流程` list, replace item 1:

```markdown
1. 启动后，程序会按“显式参数 -> 上次成功配置 -> `config.yaml` -> 当前目录下其它 `config*.yaml`”的顺序寻找配置文件。
```

with:

```markdown
1. 启动后，程序会按“显式参数 -> 上次成功配置 -> `config.yaml` -> 当前目录下其它 `config*.yaml`”的顺序寻找配置文件；新项目可以在“项目 -> 新建配置...”中从默认模板创建新的 `config_*.yaml`。
```

In the same section, replace the configuration editor note:

```markdown
- “编辑当前配置”已可使用，但对 `legacy_rule / hybrid_extract / mixed` 配置的可视化编辑仍不完整；这类配置若在编辑器中直接保存，当前会按 `auto` 路径标准化导出，因此更适合继续直接维护 YAML
```

with:

```markdown
- “新建配置...”会打开默认模板并要求填写项目根目录、投标主体、大纲、采购需求和评分标准文件；保存成功后可立即切换到新配置
- “编辑当前配置”已可使用，但对 `legacy_rule / hybrid_extract / mixed` 配置的可视化编辑仍不完整；这类配置若在编辑器中直接保存，当前会按 `auto` 路径标准化导出，因此更适合继续直接维护 YAML
```

- [ ] **Step 2: Verify the README diff**

Run:

```bash
git diff -- README.md
```

Expected: diff shows only the new GUI configuration creation notes.

- [ ] **Step 3: Commit Task 4**

Run:

```bash
git add README.md
git commit -m "docs: describe new config creation flow"
```

---

### Task 5: Run Full Regression and Inspect Diffs

**Files:**
- Verify: `bid_writer/config_editor.py`
- Verify: `bid_writer/config_editor_dialog.py`
- Verify: `bid_writer/gui.py`
- Verify: `tests/test_config_editor.py`
- Verify: `tests/test_config_editor_dialog.py`
- Verify: `tests/test_gui_new_config.py`
- Verify: `README.md`

- [ ] **Step 1: Run configuration editor tests**

Run:

```bash
uv run pytest tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 2: Run nearby GUI state regression tests**

Run:

```bash
uv run pytest tests/test_gui_state.py -q
```

Expected: PASS.

- [ ] **Step 3: Run config schema regression tests**

Run:

```bash
uv run pytest tests/test_config_schema.py -q
```

Expected: PASS.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff --stat HEAD
git diff -- bid_writer/config_editor.py bid_writer/config_editor_dialog.py bid_writer/gui.py README.md
```

Expected:

- `config_editor.py` contains default model creation, new document creation, and required bidder validation.
- `config_editor_dialog.py` contains only new-mode branching and first-save behavior.
- `gui.py` contains the new menu item and `open_new_config_editor()`.
- `README.md` contains the new GUI entry explanation.

- [ ] **Step 5: Commit any verification fixes**

If Step 1, Step 2, Step 3, and Step 4 reveal small corrections, make the corrections and commit them:

```bash
git add bid_writer/config_editor.py bid_writer/config_editor_dialog.py bid_writer/gui.py tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_gui_new_config.py README.md
git commit -m "fix: polish new config creation flow"
```

If there are no changes after verification, skip this commit.

---

## Self-Review

Spec coverage:

- New GUI entry: Task 3 adds `新建配置...`.
- Reuse existing editor: Task 2 adds `new_config=True` to `ConfigEditorDialog`.
- Default canonical model: Task 1 adds `build_default_editor_model()` and tests YAML output.
- Required fields: Task 1 adds bidder-name validation; existing validation covers root, outline, procurement requirements, and scoring criteria paths.
- Save-as by default: Task 2 routes first save through `_save_as()`.
- Save then switch: Task 3 reuses `_switch_to_config_path()` when `apply_path` is returned.
- `fact_cards` default: Task 1 tests and implements preserved default block.
- Docs: Task 4 updates README.
- Regression: Task 5 runs focused and nearby tests.

Placeholder scan:

- This plan has no placeholder markers.
- Every code-changing step includes exact code or exact replacement text.
- Every test command includes an expected outcome.

Type consistency:

- `ConfigEditorDocument.require_project_identity` is a boolean field used by `ConfigEditorDocument.validate()`.
- `validate_editor_model(..., require_project_identity=False)` keeps existing callers compatible.
- `ConfigEditorDialog(..., new_config=True)` is passed from `MainWindow.open_new_config_editor()`.
- `open_new_config_editor()` mirrors `open_config_editor()` and passes `force_reload` for same-path saves.
