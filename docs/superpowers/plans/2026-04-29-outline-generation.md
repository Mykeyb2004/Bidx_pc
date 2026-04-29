# Outline Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GUI outline preparation stage where users can load or generate an H4 bid outline before locking it and entering chapter expansion.

**Architecture:** Runtime config gains outline lock and outline-model properties. A new `OutlineGenerator` owns model prompting and output cleaning. A new `OutlinePrepareDialog` owns the editable text workflow, while `MainWindow` gates config switching and generation behind `project.outline_locked`.

**Tech Stack:** Python 3, Tkinter/ttk, PyYAML, OpenAI-compatible SDK, existing `uv run pytest` test workflow.

---

## File Structure

- Modify `bid_writer/config.py`: expose `outline_locked`, outline-generation role path, and `BID_WRITER_OUTLINE_*` model settings with fallback to正文扩写 settings.
- Modify `bid_writer/config_editor.py`: include outline lock and outline-generation role in the editor model, canonical YAML, managed schema, validation, and summary.
- Modify `bid_writer/config_editor_dialog.py`: show outline lock and architect role fields in the project section and preserve them through save.
- Create `bid_writer/outline_generator.py`: build prompt, call the outline model, clean Markdown heading output, and validate H4 structure.
- Create `bid_writer/outline_prepare.py`: testable helpers for reading/writing outline files and flipping `project.outline_locked`.
- Create `bid_writer/outline_prepare_dialog.py`: editable GUI window for loading, generating, validating, and confirming an outline.
- Modify `bid_writer/gui.py`: open outline preparation for unlocked configs, add the menu entry, and block switching when preparation is cancelled.
- Modify `tests/test_config_schema.py`, `tests/test_config_editor.py`, `tests/test_config_editor_dialog.py`, `tests/test_gui_new_config.py`.
- Create `tests/test_outline_generator.py`, `tests/test_outline_prepare.py`, `tests/test_outline_prepare_dialog.py`.
- Modify `config.example.yaml`, `.env.example`, `docs/config_schema.md`, and active sample `config_*.yaml` files.

## Task 1: Runtime Config And Canonical Schema

**Files:**
- Modify: `bid_writer/config.py`
- Modify: `bid_writer/config_editor.py`
- Modify: `bid_writer/config_editor_dialog.py`
- Test: `tests/test_config_schema.py`
- Test: `tests/test_config_editor.py`
- Test: `tests/test_config_editor_dialog.py`

- [ ] **Step 1: Write failing runtime config tests**

Append these tests to `tests/test_config_schema.py`:

```python
def test_outline_lock_defaults_true_for_existing_configs(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}\n", encoding="utf-8")

    config = Config(str(config_path))

    assert config.outline_locked is True


def test_outline_lock_can_be_disabled_for_new_project_flow(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  outline_locked: false
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_locked is False


def test_outline_generation_role_file_resolves_from_config_dir(tmp_path: Path):
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    role_file = roles_dir / "标书架构师.md"
    role_file.write_text("架构师角色", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  outline_generation:
    role_file: "./roles/标书架构师.md"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_generation_role_file == str(role_file)


def test_outline_model_settings_prefer_outline_env_and_fallback_to_generation(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_API_BASE_URL",
        "BID_WRITER_API_KEY",
        "BID_WRITER_MODEL",
        "BID_WRITER_TEMPERATURE",
        "BID_WRITER_MAX_TOKENS",
        "BID_WRITER_TIMEOUT_SECONDS",
        "BID_WRITER_MAX_RETRIES",
        "BID_WRITER_TOP_P",
        "BID_WRITER_SEED",
        "BID_WRITER_OUTLINE_API_BASE_URL",
        "BID_WRITER_OUTLINE_API_KEY",
        "BID_WRITER_OUTLINE_MODEL",
        "BID_WRITER_OUTLINE_TEMPERATURE",
        "BID_WRITER_OUTLINE_MAX_TOKENS",
        "BID_WRITER_OUTLINE_TIMEOUT_SECONDS",
        "BID_WRITER_OUTLINE_MAX_RETRIES",
        "BID_WRITER_OUTLINE_TOP_P",
        "BID_WRITER_OUTLINE_SEED",
    ):
        monkeypatch.delenv(key, raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "BID_WRITER_API_BASE_URL=https://generation.example/v1",
                "BID_WRITER_API_KEY=generation-key",
                "BID_WRITER_MODEL=generation-model",
                "BID_WRITER_TEMPERATURE=0.7",
                "BID_WRITER_MAX_TOKENS=10000",
                "BID_WRITER_TIMEOUT_SECONDS=120",
                "BID_WRITER_MAX_RETRIES=3",
                "BID_WRITER_TOP_P=0.9",
                "BID_WRITER_SEED=100",
                "BID_WRITER_OUTLINE_MODEL=outline-model",
                "BID_WRITER_OUTLINE_TEMPERATURE=0.25",
                "BID_WRITER_OUTLINE_MAX_TOKENS=4321",
            ]
        ),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_api_base_url == "https://generation.example/v1"
    assert config.outline_api_key == "generation-key"
    assert config.outline_model == "outline-model"
    assert config.outline_temperature == 0.25
    assert config.outline_max_tokens == 4321
    assert config.outline_timeout_seconds == 120
    assert config.outline_max_retries == 3
    assert config.outline_top_p == 0.9
    assert config.outline_seed == 100
```

- [ ] **Step 2: Write failing config editor tests**

Append these tests to `tests/test_config_editor.py`:

```python
def test_new_config_defaults_to_unlocked_outline_generation_role(tmp_path: Path):
    document = create_new_config_editor_document(tmp_path / "config_新项目.yaml")
    payload = yaml.safe_load(document.render_yaml())

    assert document.model["project"]["outline_locked"] is False
    assert document.model["project"]["outline_generation"]["role_file"] == "./roles/标书架构师.md"
    assert payload["project"]["outline_locked"] is False
    assert payload["project"]["outline_generation"]["role_file"] == "./roles/标书架构师.md"


def test_config_editor_preserves_outline_generation_fields(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试投标主体"
  outline_locked: true
  outline_generation:
    role_file: "./roles/custom_architect.md"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    payload = yaml.safe_load(document.render_yaml())

    assert document.model["project"]["outline_locked"] is True
    assert document.model["project"]["outline_generation"]["role_file"] == "./roles/custom_architect.md"
    assert payload["project"]["outline_locked"] is True
    assert payload["project"]["outline_generation"]["role_file"] == "./roles/custom_architect.md"


def test_unlocked_outline_config_allows_missing_outline_file(tmp_path: Path):
    (tmp_path / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (tmp_path / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  outline_locked: false
  inputs:
    outline_file: "./missing_outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

writing:
  role: "你是一位专业的标书撰写专家。"

processing:
  path: "full_context"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate()

    assert not any(item.level == "error" and "大纲文件不存在" in item.text for item in messages)


def test_locked_outline_config_requires_existing_outline_file(tmp_path: Path):
    (tmp_path / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (tmp_path / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  outline_locked: true
  inputs:
    outline_file: "./missing_outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

writing:
  role: "你是一位专业的标书撰写专家。"

processing:
  path: "full_context"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate()

    assert any(item.level == "error" and "大纲文件不存在" in item.text for item in messages)
```

Append this focused dialog model test to `tests/test_config_editor_dialog.py`:

```python
def test_config_editor_project_section_collects_outline_generation_fields():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.document = SimpleNamespace(model={"models": {}})
    dialog.vars = {
        "project.root_dir": StubVar("."),
        "project.bidder_name": StubVar("测试投标主体"),
        "project.outline_locked": StubVar(False),
        "project.outline_generation.role_file": StubVar("./roles/标书架构师.md"),
        "project.outline_file": StubVar("./outline.md"),
        "project.bid_requirements_mode": StubVar("file"),
        "project.bid_requirements_file": StubVar("./bid_requirements.md"),
        "project.scoring_criteria_mode": StubVar("file"),
        "project.scoring_criteria_file": StubVar("./scoring_criteria.md"),
        "project.output_dir": StubVar("./output"),
        "writing.role_mode": StubVar("file"),
        "writing.role_file": StubVar("./roles/通用投标角色.md"),
        "writing.target_words.default": StubVar("1500"),
        "writing.target_words.min": StubVar("100"),
        "writing.target_words.max": StubVar("12000"),
        "writing.target_words.step": StubVar("100"),
        "writing.target_words.upper_ratio": StubVar("1.15"),
        "writing.max_tables_per_section": StubVar("2"),
        "writing.max_mermaid_flowcharts_per_section": StubVar("1"),
        "processing.path": StubVar("auto"),
        "processing.scoring.enabled": StubVar(True),
        "processing.project_background.enabled": StubVar(True),
        "processing.project_background.max_chars": StubVar("800"),
        "processing.project_background.h2.precompute_on_batch": StubVar(True),
        "processing.project_background.h2.generate_missing_on_single": StubVar(True),
        "processing.project_background.h2.max_evidence_blocks": StubVar("6"),
        "processing.project_background.h2.max_evidence_chars": StubVar("2400"),
        "processing.project_background.h2.content_mode": StubVar("excerpts"),
        "processing.project_background.h2.min_evidence_blocks": StubVar("1"),
        "processing.project_background.h2.fallback": StubVar("raw_evidence"),
        "processing.project_background.h2.cache_dir": StubVar("./caches/project_background_h2"),
        "processing.full_context.chapter_writing_plan.enabled": StubVar(False),
        "processing.full_context.chapter_writing_plan.max_chars": StubVar("320"),
        "processing.auto.scoring_parse_mode": StubVar("auto"),
        "processing.auto.scoring_max_rows": StubVar("4"),
        "processing.auto.retrieval.lexical_enabled": StubVar(True),
        "processing.auto.retrieval.vector_enabled": StubVar(False),
        "processing.auto.retrieval.top_k_lexical": StubVar("20"),
        "processing.auto.retrieval.top_k_fused": StubVar("30"),
        "processing.auto.retrieval.top_k_final": StubVar("8"),
        "processing.auto.retrieval.min_fused_score": StubVar("0.0"),
        "runtime.stream.enabled": StubVar(True),
        "runtime.stream.idle_timeout_seconds": StubVar("12"),
        "runtime.trace.enabled": StubVar(True),
        "runtime.trace.directory": StubVar("./log/generation_traces"),
        "runtime.trace.mode": StubVar("full"),
        "runtime.trace.write_prompt": StubVar(True),
        "runtime.trace.write_output": StubVar(True),
        "runtime.trace.write_context": StubVar(True),
        "runtime.trace.write_summary": StubVar(True),
        "runtime.trace.redact_sensitive": StubVar(True),
        "runtime.debug.context_pruning_dump": StubVar(True),
        "runtime.output.prefix": StubVar(""),
        "runtime.output.include_title_header": StubVar(True),
        "runtime.output.overwrite_existing": StubVar(True),
        "runtime.output.filename_max_length": StubVar("100"),
        "runtime.output.empty_filename_fallback": StubVar("未命名"),
        "runtime.merge.normalize_soft_line_breaks": StubVar(True),
    }
    dialog.text_widgets = {
        "project.bid_requirements_text": StubText(""),
        "project.scoring_criteria_text": StubText(""),
        "writing.role_text": StubText(""),
        "writing.extra_rules_text": StubText(""),
    }

    model = ConfigEditorDialog._collect_model(dialog)

    assert model["project"]["outline_locked"] is False
    assert model["project"]["outline_generation"]["role_file"] == "./roles/标书架构师.md"
```

If `StubText` is not present in `tests/test_config_editor_dialog.py`, add this helper near the existing `StubVar` helper:

```python
class StubText:
    def __init__(self, value: str):
        self.value = value

    def get(self, *_args):
        return self.value
```

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_config_schema.py::test_outline_lock_defaults_true_for_existing_configs tests/test_config_schema.py::test_outline_lock_can_be_disabled_for_new_project_flow tests/test_config_schema.py::test_outline_generation_role_file_resolves_from_config_dir tests/test_config_schema.py::test_outline_model_settings_prefer_outline_env_and_fallback_to_generation tests/test_config_editor.py::test_new_config_defaults_to_unlocked_outline_generation_role tests/test_config_editor.py::test_config_editor_preserves_outline_generation_fields tests/test_config_editor.py::test_unlocked_outline_config_allows_missing_outline_file tests/test_config_editor.py::test_locked_outline_config_requires_existing_outline_file tests/test_config_editor_dialog.py::test_config_editor_project_section_collects_outline_generation_fields -q
```

Expected: FAIL because the config properties and editor model fields do not exist yet.

- [ ] **Step 4: Implement runtime config properties**

In `bid_writer/config.py`, add these properties near the existing generation model properties:

```python
    def _get_outline_env_str(self, outline_key: str, fallback_key: str, default: str = "") -> str:
        value = self._get_env_str(outline_key)
        if value is not None:
            return value
        fallback = self._get_env_str(fallback_key)
        if fallback is not None:
            return fallback
        return default

    def _get_outline_env_int(self, outline_key: str, fallback_key: str, default: int) -> int:
        value = self._get_env_int(outline_key)
        if value is not None:
            return value
        fallback = self._get_env_int(fallback_key)
        return fallback if fallback is not None else default

    def _get_outline_env_float(self, outline_key: str, fallback_key: str, default: float) -> float:
        value = self._get_env_float(outline_key)
        if value is not None:
            return value
        fallback = self._get_env_float(fallback_key)
        return fallback if fallback is not None else default

    @property
    def outline_locked(self) -> bool:
        return self._get_bool(("project", "outline_locked"), default=True)

    @property
    def outline_generation_role_file(self) -> str:
        value = self._get_first_defined(
            ("project", "outline_generation", "role_file"),
            default="./roles/标书架构师.md",
        )
        return str(self._resolve_path(str(value).strip() or "./roles/标书架构师.md"))

    @property
    def outline_api_base_url(self) -> str:
        return self._get_outline_env_str(
            "BID_WRITER_OUTLINE_API_BASE_URL",
            "BID_WRITER_API_BASE_URL",
            "https://api.openai.com/v1",
        )

    @property
    def outline_api_key(self) -> str:
        return self._get_outline_env_str("BID_WRITER_OUTLINE_API_KEY", "BID_WRITER_API_KEY", "")

    @property
    def outline_model(self) -> str:
        return self._get_outline_env_str("BID_WRITER_OUTLINE_MODEL", "BID_WRITER_MODEL", "gpt-5.4")

    @property
    def outline_temperature(self) -> float:
        return self._get_outline_env_float("BID_WRITER_OUTLINE_TEMPERATURE", "BID_WRITER_TEMPERATURE", 0.3)

    @property
    def outline_max_tokens(self) -> int:
        return self._get_outline_env_int("BID_WRITER_OUTLINE_MAX_TOKENS", "BID_WRITER_MAX_TOKENS", 6000)

    @property
    def outline_timeout_seconds(self) -> int:
        return self._get_outline_env_int("BID_WRITER_OUTLINE_TIMEOUT_SECONDS", "BID_WRITER_TIMEOUT_SECONDS", 120)

    @property
    def outline_max_retries(self) -> int:
        return self._get_outline_env_int("BID_WRITER_OUTLINE_MAX_RETRIES", "BID_WRITER_MAX_RETRIES", 3)

    @property
    def outline_top_p(self) -> Optional[float]:
        value = self._get_env_float("BID_WRITER_OUTLINE_TOP_P")
        return value if value is not None else self.api_top_p

    @property
    def outline_seed(self) -> Optional[int]:
        value = self._get_env_int("BID_WRITER_OUTLINE_SEED")
        return value if value is not None else self.api_seed
```

- [ ] **Step 5: Implement canonical editor model fields**

In `bid_writer/config_editor.py`, update `build_default_editor_model()` project block to include:

```python
            "outline_locked": False,
            "outline_generation": {
                "role_file": "./roles/标书架构师.md",
            },
```

In `normalize_raw_config_to_editor_model()`, add these keys to the returned `project` dictionary:

```python
            "outline_locked": _coerce_bool(
                _first_defined(raw_config, ("project", "outline_locked"), default=True),
                default=True,
            ),
            "outline_generation": {
                "role_file": _coerce_str(
                    _first_defined(
                        raw_config,
                        ("project", "outline_generation", "role_file"),
                        default="./roles/标书架构师.md",
                    )
                ).strip() or "./roles/标书架构师.md",
            },
```

In `build_canonical_config()`, add these fields to the returned `project` payload:

```python
            "outline_locked": bool(model["project"]["outline_locked"]),
            "outline_generation": {
                "role_file": (
                    model["project"]["outline_generation"]["role_file"].strip()
                    or "./roles/标书架构师.md"
                ),
            },
```

In `_ROOT_MANAGED_SCHEMA`, add these under `"project"`:

```python
        "outline_locked": True,
        "outline_generation": {
            "role_file": True,
        },
```

In `summarize_model()`, add this line after the bidder line:

```python
        f"大纲状态 = {'已锁定' if model['project']['outline_locked'] else '待确认'}",
```

In `_add_cross_platform_path_warnings()`, add:

```python
        ("project.outline_generation.role_file", model["project"].get("outline_generation", {}).get("role_file", "")),
```

In `validate_editor_model()`, add this role path warning after the main writing role check:

```python
    outline_role_file = _coerce_str(
        model["project"].get("outline_generation", {}).get("role_file", "./roles/标书架构师.md")
    ).strip() or "./roles/标书架构师.md"
    outline_role_path = _resolve_path(outline_role_file, config_path.parent)
    if not outline_role_path.exists():
        messages.append(ValidationMessage("warning", f"大纲生成角色文件当前不存在：{outline_role_path}"))
```

Also change the existing outline-file validation so unlocked configs can be saved before `outline_file` exists:

```python
    outline_path = _resolve_path(model["project"]["outline_file"] or "./outline.md", root_dir)
    if not outline_path.exists():
        if bool(model["project"].get("outline_locked", True)):
            messages.append(ValidationMessage("error", f"大纲文件不存在：{outline_path}"))
        else:
            messages.append(ValidationMessage("warning", f"大纲文件暂不存在，将在大纲准备阶段创建：{outline_path}"))
```

- [ ] **Step 6: Add the config editor dialog fields**

In `bid_writer/config_editor_dialog.py`, add variables in `_create_variables()`:

```python
        add_var("project.outline_locked", tk.BooleanVar())
        add_var("project.outline_generation.role_file", tk.StringVar())
```

In `_build_project_section()`, add an outline section after the basic project fields:

```python
        outline = ttk.LabelFrame(content, text="大纲准备", padding=12)
        outline.pack(fill=tk.X, pady=(0, 12))
        self._add_check_row(outline, 0, "大纲已锁定", "project.outline_locked")
        self._add_path_row(
            outline,
            1,
            "大纲生成角色文件",
            "project.outline_generation.role_file",
            browse_kind="file",
            relative_to="config",
        )
        outline.columnconfigure(1, weight=1)
```

Keep the existing `"输入资源"` frame below this new outline section.

In `_populate_vars()`, add:

```python
            "project.outline_locked": model["project"]["outline_locked"],
            "project.outline_generation.role_file": model["project"]["outline_generation"]["role_file"],
```

In `_collect_model()`, add:

```python
                "outline_locked": bool(self.vars["project.outline_locked"].get()),
                "outline_generation": {
                    "role_file": self.vars["project.outline_generation.role_file"].get().strip(),
                },
```

- [ ] **Step 7: Run tests until task passes**

Run:

```bash
uv run pytest tests/test_config_schema.py::test_outline_lock_defaults_true_for_existing_configs tests/test_config_schema.py::test_outline_lock_can_be_disabled_for_new_project_flow tests/test_config_schema.py::test_outline_generation_role_file_resolves_from_config_dir tests/test_config_schema.py::test_outline_model_settings_prefer_outline_env_and_fallback_to_generation tests/test_config_editor.py::test_new_config_defaults_to_unlocked_outline_generation_role tests/test_config_editor.py::test_config_editor_preserves_outline_generation_fields tests/test_config_editor.py::test_unlocked_outline_config_allows_missing_outline_file tests/test_config_editor.py::test_locked_outline_config_requires_existing_outline_file tests/test_config_editor_dialog.py::test_config_editor_project_section_collects_outline_generation_fields -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add bid_writer/config.py bid_writer/config_editor.py bid_writer/config_editor_dialog.py tests/test_config_schema.py tests/test_config_editor.py tests/test_config_editor_dialog.py
git commit -m "feat: add outline config fields"
```

## Task 2: Outline Generator Service

**Files:**
- Create: `bid_writer/outline_generator.py`
- Test: `tests/test_outline_generator.py`

- [ ] **Step 1: Write failing outline generator tests**

Create `tests/test_outline_generator.py` with:

```python
from pathlib import Path

import pytest

from bid_writer.config import Config
from bid_writer.outline_generator import (
    OutlineGenerationError,
    OutlineGenerator,
    clean_outline_response,
    validate_outline_text,
)


def _write_config(tmp_path: Path) -> Path:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "标书架构师.md").write_text("你是标书架构师。", encoding="utf-8")
    (tmp_path / "outline.md").write_text("# 旧大纲\n## 旧章节\n### 旧小节\n#### 旧单元\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text("采购需求：需要满意度调查服务。", encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准：项目理解 10 分；实施方案 30 分。", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试投标主体"
  outline_locked: false
  outline_generation:
    role_file: "./roles/标书架构师.md"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_prompt_contains_inputs_and_h4_contract(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    generator = OutlineGenerator(config)

    prompt = generator.build_user_prompt()

    assert "测试投标主体" in prompt
    assert "满意度调查服务" in prompt
    assert "项目理解 10 分" in prompt
    assert "标题层级必须固定到 H4" in prompt
    assert "不得输出 ##### 或更深层级标题" in prompt


def test_clean_outline_response_keeps_headings_and_downgrades_deeper_levels():
    result = clean_outline_response(
        """
```markdown
# 项目
说明文字
## 项目理解
### 需求分析
##### 采购需求响应
```
""".strip()
    )

    assert result.outline_text == "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n"
    assert result.warnings == ["已将 1 个 H5/H6 标题降级为 H4。"]


def test_validate_outline_text_requires_h4_leaf_units():
    messages = validate_outline_text("# 项目\n## 章\n### 节\n")

    assert any(item.level == "error" and "至少包含 1 个 H4" in item.text for item in messages)


def test_missing_architect_role_file_blocks_generation(tmp_path: Path):
    config_path = _write_config(tmp_path)
    (tmp_path / "roles" / "标书架构师.md").unlink()
    config = Config(str(config_path))

    with pytest.raises(OutlineGenerationError, match="大纲生成角色文件不存在"):
        OutlineGenerator(config).generate()


def test_generate_uses_fake_client_and_returns_clean_outline(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeMessage:
        content = "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake_client = FakeClient()

    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: fake_client)
    result = generator.generate()

    assert result.outline_text.endswith("#### 采购需求响应\n")
    call = fake_client.chat.completions.calls[0]
    assert call["model"] == config.outline_model
    assert call["temperature"] == config.outline_temperature
    assert call["max_tokens"] == config.outline_max_tokens
    assert call["stream"] is False
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_outline_generator.py -q
```

Expected: FAIL because `bid_writer.outline_generator` does not exist.

- [ ] **Step 3: Implement `bid_writer/outline_generator.py`**

Create `bid_writer/outline_generator.py` with:

```python
"""
标书大纲生成服务。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from .config import Config
from .config_editor import ValidationMessage
from .outline_parser import parse_outline


@dataclass(frozen=True)
class OutlineGenerationResult:
    outline_text: str
    warnings: list[str] = field(default_factory=list)


class OutlineGenerationError(RuntimeError):
    """大纲生成无法继续。"""


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*```")


def clean_outline_response(raw_text: str) -> OutlineGenerationResult:
    lines: list[str] = []
    downgraded = 0
    in_fence = False

    for raw_line in raw_text.splitlines():
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        match = _HEADING_RE.match(raw_line.strip())
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title:
            continue
        if level > 4:
            level = 4
            downgraded += 1
        lines.append(f"{'#' * level} {title}")

    warnings: list[str] = []
    if downgraded:
        warnings.append(f"已将 {downgraded} 个 H5/H6 标题降级为 H4。")
    outline_text = "\n".join(lines).strip()
    return OutlineGenerationResult(
        outline_text=(outline_text + "\n") if outline_text else "",
        warnings=warnings,
    )


def validate_outline_text(outline_text: str) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []
    raw_heading_levels: list[int] = []

    for line_number, raw_line in enumerate(outline_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _HEADING_RE.match(stripped)
        if not match:
            messages.append(ValidationMessage("warning", f"第 {line_number} 行不是 Markdown 标题，将不会进入大纲树。"))
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        raw_heading_levels.append(level)
        if not title:
            messages.append(ValidationMessage("error", f"第 {line_number} 行标题为空。"))
        if level > 4:
            messages.append(ValidationMessage("error", f"第 {line_number} 行为 H{level}，大纲固定到 H4，不允许 H5/H6。"))

    parser = parse_outline(outline_text)
    headings = parser.get_all_headings()
    if not headings:
        messages.append(ValidationMessage("error", "大纲至少需要 1 个 Markdown 标题。"))
        return messages
    if not any(heading.level == 1 for heading in headings):
        messages.append(ValidationMessage("error", "大纲至少需要 1 个 H1 项目总标题。"))
    if not any(heading.level == 4 for heading in headings):
        messages.append(ValidationMessage("error", "大纲至少包含 1 个 H4 具体写作单元。"))
    for heading in headings:
        if not heading.children and heading.level != 4:
            messages.append(ValidationMessage("error", f"叶子节点必须是 H4：{heading.full_path}"))
    if raw_heading_levels and max(raw_heading_levels) <= 4 and not any(item.level == "error" for item in messages):
        messages.append(ValidationMessage("info", f"已识别 {len(headings)} 个标题节点。"))
    return messages


class OutlineGenerator:
    def __init__(
        self,
        config: Config,
        *,
        client_factory: Optional[Callable[..., OpenAI]] = None,
    ):
        self.config = config
        self.client_factory = client_factory or OpenAI

    def generate(self) -> OutlineGenerationResult:
        role = self._load_role()
        bid_requirements = self.config.bid_requirements.strip()
        scoring_criteria = self.config.scoring_criteria.strip()
        if not bid_requirements and not scoring_criteria:
            raise OutlineGenerationError("采购需求和评分标准均为空，无法生成大纲。")

        client = self.client_factory(
            base_url=self.config.outline_api_base_url,
            api_key=self.config.outline_api_key,
            timeout=self.config.outline_timeout_seconds,
            max_retries=self.config.outline_max_retries,
        )
        options = {
            "model": self.config.outline_model,
            "temperature": self.config.outline_temperature,
            "max_tokens": self.config.outline_max_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": role},
                {"role": "user", "content": self.build_user_prompt()},
            ],
        }
        if self.config.outline_top_p is not None:
            options["top_p"] = self.config.outline_top_p
        if self.config.outline_seed is not None:
            options["seed"] = self.config.outline_seed

        try:
            response = client.chat.completions.create(**options)
        except Exception as exc:
            raise OutlineGenerationError(f"大纲生成请求失败：{type(exc).__name__}: {exc}") from exc

        raw_text = self._extract_response_text(response)
        if not raw_text.strip():
            raise OutlineGenerationError("大纲生成返回为空。")
        result = clean_outline_response(raw_text)
        if not result.outline_text.strip():
            raise OutlineGenerationError("大纲生成结果中未识别到 Markdown 标题。")
        return result

    def _load_role(self) -> str:
        role_path = Path(self.config.outline_generation_role_file)
        if not role_path.exists():
            raise OutlineGenerationError(f"大纲生成角色文件不存在：{role_path}")
        return role_path.read_text(encoding="utf-8").strip()

    def build_user_prompt(self) -> str:
        bidder_name = self.config.prompt_bidder_name or "当前投标主体"
        project_title = self._infer_project_title()
        bid_requirements = self.config.bid_requirements.strip() or "（未提供采购需求）"
        scoring_criteria = self.config.scoring_criteria.strip() or "（未提供评分标准）"
        return "\n\n".join(
            [
                "## 当前任务",
                f"请为{bidder_name}的“{project_title}”生成投标文件目录大纲。",
                "## 采购需求",
                bid_requirements,
                "## 评分标准",
                scoring_criteria,
                "## 输出契约",
                "\n".join(
                    [
                        "你只输出 Markdown 标题大纲，不输出正文、说明、前言、代码块或补充解释。",
                        "标题层级必须固定到 H4：",
                        "# 项目或标书总标题",
                        "## 一级章，优先对应评分大项或标书一级章",
                        "### 二级节，承接一级章下的核心板块",
                        "#### 具体写作单元，作为后续章节扩写的叶子节点",
                        "每个 ### 下至少包含 1 个 ####。",
                        "不得输出 ##### 或更深层级标题。",
                        "标题应保留评分标准中的关键词原词，目录顺序原则上遵循评分标准顺序。",
                        "如果评分标准缺失，则依据采购需求提炼目录逻辑。",
                    ]
                ),
            ]
        )

    def _infer_project_title(self) -> str:
        try:
            outline_text = self.config.get_outline_content()
        except Exception:
            return "投标文件"
        parser = parse_outline(outline_text)
        for heading in parser.get_all_headings():
            if heading.level == 1 and heading.title.strip():
                return heading.title.strip()
        return "投标文件"

    @staticmethod
    def _extract_response_text(response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", "")
                else:
                    text = getattr(item, "text", "")
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return str(content or "")
```

- [ ] **Step 4: Run generator tests**

Run:

```bash
uv run pytest tests/test_outline_generator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add bid_writer/outline_generator.py tests/test_outline_generator.py
git commit -m "feat: add outline generator"
```

## Task 3: Outline Preparation File Helpers

**Files:**
- Create: `bid_writer/outline_prepare.py`
- Test: `tests/test_outline_prepare.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_outline_prepare.py` with:

```python
from pathlib import Path

import pytest
import yaml

from bid_writer.config import Config
from bid_writer.outline_prepare import (
    OutlinePrepareError,
    confirm_outline_and_lock,
    load_existing_outline,
    set_outline_locked,
)


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "requirements.md").write_text("采购需求", encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  outline_locked: false
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_load_existing_outline_returns_empty_when_file_missing(tmp_path: Path):
    config = Config(str(_write_project(tmp_path)))

    assert load_existing_outline(config) == ""


def test_confirm_outline_writes_file_and_locks_config(tmp_path: Path):
    config_path = _write_project(tmp_path)
    config = Config(str(config_path))

    confirm_outline_and_lock(
        config,
        "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n",
    )

    assert (tmp_path / "outline.md").read_text(encoding="utf-8").endswith("#### 采购需求响应\n")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["project"]["outline_locked"] is True


def test_confirm_outline_blocks_h3_leaf(tmp_path: Path):
    config = Config(str(_write_project(tmp_path)))

    with pytest.raises(OutlinePrepareError, match="叶子节点必须是 H4"):
        confirm_outline_and_lock(config, "# 项目\n## 章节\n### 未细化小节\n")


def test_set_outline_locked_preserves_existing_project_fields(tmp_path: Path):
    config_path = _write_project(tmp_path)

    set_outline_locked(config_path, True)

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["project"]["root_dir"] == "."
    assert payload["project"]["outline_locked"] is True
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_outline_prepare.py -q
```

Expected: FAIL because `bid_writer.outline_prepare` does not exist.

- [ ] **Step 3: Implement `bid_writer/outline_prepare.py`**

Create `bid_writer/outline_prepare.py` with:

```python
"""
大纲准备阶段的文件读写与锁定辅助函数。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .outline_generator import validate_outline_text


class OutlinePrepareError(RuntimeError):
    """大纲准备无法继续。"""


def outline_path(config: Config) -> Path:
    return Path(config.outline_file).expanduser().resolve()


def load_existing_outline(config: Config) -> str:
    path = outline_path(config)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def set_outline_locked(config_path: str | Path, locked: bool) -> None:
    path = Path(config_path).expanduser().resolve()
    payload: dict[str, Any]
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        payload = {}
    project = payload.setdefault("project", {})
    if not isinstance(project, dict):
        raise OutlinePrepareError("配置文件中的 project 字段不是对象，无法写入 outline_locked。")
    project["outline_locked"] = bool(locked)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip() + "\n",
        encoding="utf-8",
    )


def confirm_outline_and_lock(config: Config, outline_text: str) -> Path:
    messages = validate_outline_text(outline_text)
    errors = [message.text for message in messages if message.level == "error"]
    if errors:
        raise OutlinePrepareError("\n".join(errors))

    path = outline_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = outline_text.strip() + "\n"
    path.write_text(normalized, encoding="utf-8")
    set_outline_locked(config.config_path, True)
    return path
```

- [ ] **Step 4: Run helper tests**

Run:

```bash
uv run pytest tests/test_outline_prepare.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add bid_writer/outline_prepare.py tests/test_outline_prepare.py
git commit -m "feat: add outline preparation helpers"
```

## Task 4: Outline Preparation Dialog

**Files:**
- Create: `bid_writer/outline_prepare_dialog.py`
- Test: `tests/test_outline_prepare_dialog.py`

- [ ] **Step 1: Write failing dialog tests**

Create `tests/test_outline_prepare_dialog.py` with:

```python
from pathlib import Path
from types import SimpleNamespace

from bid_writer.config import Config
from bid_writer.outline_prepare_dialog import OutlinePrepareDialog


class FakeText:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value

    def get(self, *_args):
        return self.value


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _write_config(tmp_path: Path) -> Path:
    (tmp_path / "outline.md").write_text("# 项目\n## 章\n### 节\n#### 单元\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text("采购需求", encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  outline_locked: false
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _dialog(config: Config) -> OutlinePrepareDialog:
    dialog = OutlinePrepareDialog.__new__(OutlinePrepareDialog)
    dialog.config = config
    dialog.result = {"confirmed": False}
    dialog.outline_text = FakeText()
    dialog.status_var = FakeVar()
    dialog.validation_var = FakeVar()
    dialog.destroy = lambda: None
    return dialog


def test_load_existing_outline_sets_text(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    OutlinePrepareDialog._load_existing_outline(dialog)

    assert dialog.outline_text.get("1.0", "end").startswith("# 项目")
    assert "已读取已有大纲" in dialog.status_var.get()


def test_validate_current_text_reports_h4_error(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 项目\n## 章\n### 节\n")

    ok = OutlinePrepareDialog._validate_current_text(dialog)

    assert ok is False
    assert "至少包含 1 个 H4" in dialog.validation_var.get()


def test_confirm_writes_outline_and_marks_result(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 新项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n")

    OutlinePrepareDialog._confirm(dialog)

    assert dialog.result["confirmed"] is True
    assert (tmp_path / "outline.md").read_text(encoding="utf-8").startswith("# 新项目")
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_outline_prepare_dialog.py -q
```

Expected: FAIL because `bid_writer.outline_prepare_dialog` does not exist.

- [ ] **Step 3: Implement `bid_writer/outline_prepare_dialog.py`**

Create `bid_writer/outline_prepare_dialog.py` with:

```python
"""
大纲准备窗口。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import Config
from .config_editor_dialog import (
    CONFIG_EDITOR_DEFAULT_HEIGHT,
    CONFIG_EDITOR_DEFAULT_WIDTH,
    _bootstyle_kwargs,
    _compute_screen_limited_dialog_size,
    _set_centered_window_geometry,
    apply_window_surface,
    setup_gui_theme,
    style_text_widget,
)
from .outline_generator import OutlineGenerationError, OutlineGenerator, validate_outline_text
from .outline_prepare import OutlinePrepareError, confirm_outline_and_lock, load_existing_outline


class OutlinePrepareDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config: Config):
        super().__init__(parent)
        self.config = config
        self.result = {"confirmed": False}
        self.style = setup_gui_theme(self)
        apply_window_surface(self)
        self.title("大纲准备")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=CONFIG_EDITOR_DEFAULT_WIDTH,
            desired_height=CONFIG_EDITOR_DEFAULT_HEIGHT,
            min_width=900,
            min_height=680,
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        self.status_var = tk.StringVar(value="请准备并确认投标大纲")
        self.validation_var = tk.StringVar(value="")
        self._build_widgets()
        self._load_existing_outline()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="大纲准备", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"大纲文件：{self.config.outline_file}", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        body = ttk.Frame(self, padding=(16, 0, 16, 10))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.outline_text = tk.Text(body, wrap=tk.WORD)
        style_text_widget(self.outline_text)
        y_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.outline_text.yview)
        self.outline_text.configure(yscrollcommand=y_scroll.set)
        self.outline_text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")

        validation = ttk.Label(
            body,
            textvariable=self.validation_var,
            justify=tk.LEFT,
            wraplength=900,
            style="Muted.TLabel",
        )
        validation.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="读取已有大纲", command=self._load_existing_outline, **_bootstyle_kwargs("secondary")).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="生成大纲", command=self._generate_outline, **_bootstyle_kwargs("secondary")).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="确认大纲并进入扩写", command=self._confirm, **_bootstyle_kwargs("primary")).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="取消", command=self._cancel, **_bootstyle_kwargs("secondary")).grid(row=0, column=3, padx=(8, 0))

    def _set_text(self, value: str) -> None:
        self.outline_text.delete("1.0", tk.END)
        self.outline_text.insert("1.0", value or "")

    def _current_text(self) -> str:
        return self.outline_text.get("1.0", tk.END).strip()

    def _load_existing_outline(self) -> None:
        content = load_existing_outline(self.config)
        self._set_text(content)
        self.status_var.set("已读取已有大纲" if content.strip() else "当前大纲文件不存在或为空")
        self._validate_current_text()

    def _generate_outline(self) -> None:
        self.status_var.set("正在生成大纲...")
        thread = threading.Thread(target=self._run_generate_outline, daemon=True)
        thread.start()

    def _run_generate_outline(self) -> None:
        try:
            result = OutlineGenerator(self.config).generate()
        except OutlineGenerationError as exc:
            self.after(0, lambda: self._show_generation_error(str(exc)))
            return
        self.after(0, lambda: self._apply_generated_outline(result.outline_text, result.warnings))

    def _show_generation_error(self, message: str) -> None:
        self.status_var.set("大纲生成失败")
        messagebox.showerror("大纲生成失败", message, parent=self)

    def _apply_generated_outline(self, outline_text: str, warnings: list[str]) -> None:
        self._set_text(outline_text)
        self.status_var.set("大纲生成完成")
        self.validation_var.set("\n".join(warnings))
        self._validate_current_text()

    def _validate_current_text(self) -> bool:
        messages = validate_outline_text(self._current_text())
        prefix = {"error": "[错误]", "warning": "[警告]", "info": "[信息]"}
        self.validation_var.set("\n".join(f"{prefix.get(item.level, '[信息]')} {item.text}" for item in messages))
        return not any(item.level == "error" for item in messages)

    def _confirm(self) -> None:
        if not self._validate_current_text():
            messagebox.showerror("大纲校验失败", self.validation_var.get(), parent=self)
            return
        try:
            confirm_outline_and_lock(self.config, self._current_text())
        except OutlinePrepareError as exc:
            messagebox.showerror("保存大纲失败", str(exc), parent=self)
            return
        self.result["confirmed"] = True
        self.status_var.set("大纲已确认")
        self.destroy()

    def _cancel(self) -> None:
        self.result["confirmed"] = False
        self.destroy()
```

- [ ] **Step 4: Run dialog tests**

Run:

```bash
uv run pytest tests/test_outline_prepare_dialog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add bid_writer/outline_prepare_dialog.py tests/test_outline_prepare_dialog.py
git commit -m "feat: add outline preparation dialog"
```

## Task 5: Main GUI Flow Integration

**Files:**
- Modify: `bid_writer/gui.py`
- Test: `tests/test_gui_new_config.py`

- [ ] **Step 1: Write failing GUI integration tests**

Update `tests/test_gui_new_config.py`.

First update the existing `_fake_window()` helper so the fake config has `outline_locked` and the fake window exposes the new menu command:

```python
def _fake_window(config_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        bid_writer=SimpleNamespace(config=SimpleNamespace(config_path=config_path, outline_locked=True)),
        open_new_config_editor=lambda: None,
        select_and_switch_config=lambda: None,
        open_config_editor=lambda: None,
        unlock_and_prepare_outline=lambda: None,
        reload_outline=lambda: None,
        refresh_status=lambda: None,
        open_output_dir=lambda: None,
        quit=lambda: None,
    )
```

Change `test_project_menu_starts_with_new_config_entry()` assertion to:

```python
    assert menu.labels[:4] == ["新建配置...", "切换配置...", "编辑当前配置...", "解锁/重新准备大纲..."]
```

Change `test_update_action_states_configures_project_menu_commands_only()` expected configured entries to:

```python
    assert project_menu.configured_entries == [
        ("新建配置...", tk.DISABLED),
        ("切换配置...", tk.DISABLED),
        ("编辑当前配置...", tk.DISABLED),
        ("解锁/重新准备大纲...", tk.DISABLED),
        ("重载大纲", tk.DISABLED),
        ("扫描输出状态", tk.DISABLED),
        ("打开输出目录", tk.DISABLED),
    ]
```

Append these tests:

```python
def test_switch_to_config_prepares_unlocked_outline_before_applying(monkeypatch, tmp_path):
    selected_path = tmp_path / "config_new.yaml"
    current_path = tmp_path / "config.yaml"
    prepared = []
    loaded = []
    synced = []

    class FakeConfig:
        def __init__(self):
            self.config_path = selected_path
            self.outline_locked = False

    class FakeBidWriter:
        def __init__(self, config_path):
            assert Path(config_path) == selected_path
            self.config = FakeConfig()
            self.parser = object()

        def reload_config(self):
            self.config.outline_locked = True

        def load_outline(self):
            loaded.append(True)
            return True

    fake_window = _fake_window(current_path)
    fake_window.status_text = _FakeVar()
    fake_window.update_idletasks = lambda: None
    fake_window._sync_loaded_outline = lambda reset_tree_view=False: synced.append(reset_tree_view)
    monkeypatch.setattr("bid_writer.gui.BidWriter", FakeBidWriter)
    monkeypatch.setattr("bid_writer.gui.GUIAdapter", lambda writer: SimpleNamespace(writer=writer))
    fake_window._prepare_unlocked_outline = lambda writer: prepared.append(writer) or True

    result = MainWindow._switch_to_config_path(fake_window, selected_path)

    assert result is True
    assert len(prepared) == 1
    assert loaded == [True]
    assert synced == [True]
    assert fake_window.bid_writer.config.config_path == selected_path


def test_switch_to_config_cancelled_outline_prepare_keeps_current_config(monkeypatch, tmp_path):
    selected_path = tmp_path / "config_new.yaml"
    current_path = tmp_path / "config.yaml"
    original_writer = SimpleNamespace(config=SimpleNamespace(config_path=current_path))

    class FakeConfig:
        config_path = selected_path
        outline_locked = False

    class FakeBidWriter:
        def __init__(self, _config_path):
            self.config = FakeConfig()

        def load_outline(self):
            raise AssertionError("load_outline should not run when preparation is cancelled")

    fake_window = _fake_window(current_path)
    fake_window.bid_writer = original_writer
    fake_window.status_text = _FakeVar()
    fake_window.update_idletasks = lambda: None
    fake_window._prepare_unlocked_outline = lambda _writer: False
    monkeypatch.setattr("bid_writer.gui.BidWriter", FakeBidWriter)

    result = MainWindow._switch_to_config_path(fake_window, selected_path)

    assert result is False
    assert fake_window.bid_writer is original_writer


def test_unlock_and_prepare_outline_sets_lock_false_then_reopens_dialog(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    calls = []
    fake_window = _fake_window(config_path)
    fake_window.is_generating = False
    fake_window.bid_writer.config.outline_locked = True
    fake_window.status_text = _FakeVar()
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: calls.append((path, force_reload))
    monkeypatch.setattr("bid_writer.gui.messagebox.askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("bid_writer.gui.set_outline_locked", lambda path, locked: calls.append((Path(path), locked)))

    MainWindow.unlock_and_prepare_outline(fake_window)

    assert calls == [(config_path, False), (config_path, True)]
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
uv run pytest tests/test_gui_new_config.py -q
```

Expected: FAIL because the menu entry and outline preparation flow do not exist.

- [ ] **Step 3: Add project menu constants**

Near the menu constants in `bid_writer/gui.py`, add:

```python
PROJECT_MENU_NEW_CONFIG_INDEX = 0
PROJECT_MENU_SWITCH_CONFIG_INDEX = 1
PROJECT_MENU_EDIT_CONFIG_INDEX = 2
PROJECT_MENU_PREPARE_OUTLINE_INDEX = 3
PROJECT_MENU_RELOAD_OUTLINE_INDEX = 5
PROJECT_MENU_REFRESH_STATUS_INDEX = 6
PROJECT_MENU_OPEN_OUTPUT_INDEX = 8
```

- [ ] **Step 4: Add menu entry and action state updates**

Update `_populate_project_menu()`:

```python
    def _populate_project_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="新建配置...", command=self.open_new_config_editor)
        menu.add_command(label="切换配置...", command=self.select_and_switch_config)
        menu.add_command(label="编辑当前配置...", command=self.open_config_editor)
        menu.add_command(label="解锁/重新准备大纲...", command=self.unlock_and_prepare_outline)
        menu.add_separator()
        menu.add_command(label="重载大纲", command=self.reload_outline)
        menu.add_command(label="扫描输出状态", command=self.refresh_status)
        menu.add_separator()
        menu.add_command(label="打开输出目录", command=self.open_output_dir)
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)
```

Update the project menu loop in `update_action_states()`:

```python
            for entry_index in (
                PROJECT_MENU_NEW_CONFIG_INDEX,
                PROJECT_MENU_SWITCH_CONFIG_INDEX,
                PROJECT_MENU_EDIT_CONFIG_INDEX,
                PROJECT_MENU_PREPARE_OUTLINE_INDEX,
                PROJECT_MENU_RELOAD_OUTLINE_INDEX,
                PROJECT_MENU_REFRESH_STATUS_INDEX,
                PROJECT_MENU_OPEN_OUTPUT_INDEX,
            ):
                self.project_menu.entryconfigure(entry_index, state=tool_button_state)
            prepare_label = (
                "继续准备大纲..."
                if not self.bid_writer.config.outline_locked
                else "解锁/重新准备大纲..."
            )
            self.project_menu.entryconfigure(PROJECT_MENU_PREPARE_OUTLINE_INDEX, label=prepare_label)
```

- [ ] **Step 5: Add preparation helpers to `MainWindow`**

Import `set_outline_locked` at the top of `bid_writer/gui.py`:

```python
from .outline_prepare import set_outline_locked
```

Add these methods near `open_new_config_editor()`:

```python
    def _prepare_unlocked_outline(self, bid_writer: BidWriter) -> bool:
        from .outline_prepare_dialog import OutlinePrepareDialog

        dialog = OutlinePrepareDialog(self, bid_writer.config)
        self.wait_window(dialog)
        if not dialog.result.get("confirmed"):
            self.status_text.set("大纲准备已取消")
            return False
        bid_writer.reload_config()
        return True

    def unlock_and_prepare_outline(self):
        """解锁当前大纲并重新进入大纲准备阶段。"""
        current_path = self.bid_writer.config.config_path.resolve()
        if self.bid_writer.config.outline_locked:
            confirmed = messagebox.askyesno(
                "确认解锁大纲",
                "修改大纲可能导致已生成章节状态、文件匹配和事实卡片引用不再对应当前目录。确定要重新准备大纲吗？",
                parent=self,
            )
            if not confirmed:
                return
        try:
            set_outline_locked(current_path, False)
        except Exception as exc:
            messagebox.showerror("解锁失败", str(exc), parent=self)
            return
        self._switch_to_config_path(current_path, force_reload=True)
```

- [ ] **Step 6: Gate config switching on outline preparation**

In `_switch_to_config_path()`, after `next_bid_writer = BidWriter(str(selected_path))` succeeds and before `next_bid_writer.load_outline()`, insert:

```python
        if not next_bid_writer.config.outline_locked:
            if not self._prepare_unlocked_outline(next_bid_writer):
                return False
```

Keep the existing `load_outline()` branch after that insertion.

- [ ] **Step 7: Run GUI new-config tests**

Run:

```bash
uv run pytest tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add bid_writer/gui.py tests/test_gui_new_config.py
git commit -m "feat: gate generation behind outline preparation"
```

## Task 6: Docs, Examples, And End-To-End Verification

**Files:**
- Modify: `config.example.yaml`
- Modify: `.env.example`
- Modify: `docs/config_schema.md`
- Modify: `README.md`
- Modify: `config_统计台账.yaml`
- Modify: `config_child.yaml`
- Modify: `config_公共服务满意度_auto.yaml`
- Modify: `tests/fixtures/current_prompt_config.yaml`
- Modify: `tests/fixtures/fact_card_prompt_config.yaml`

- [ ] **Step 1: Update example YAML configs**

In `config.example.yaml`, add under `project.bidder_name`:

```yaml
  outline_locked: true
  outline_generation:
    role_file: "./roles/标书架构师.md"
```

In active project configs `config_统计台账.yaml`, `config_child.yaml`, and `config_公共服务满意度_auto.yaml`, add the same fields under `project` with `outline_locked: true` because these are existing runnable configs.

In test fixtures `tests/fixtures/current_prompt_config.yaml` and `tests/fixtures/fact_card_prompt_config.yaml`, add:

```yaml
  outline_locked: true
  outline_generation:
    role_file: "./roles/标书架构师.md"
```

- [ ] **Step 2: Update `.env.example`**

Add this block after the main `BID_WRITER_*` generation settings:

```dotenv
# Optional: independent model for bid outline generation.
# Falls back to BID_WRITER_* when these are not set.
# BID_WRITER_OUTLINE_API_BASE_URL=https://api.openai.com/v1
# BID_WRITER_OUTLINE_API_KEY=
# BID_WRITER_OUTLINE_MODEL=gpt-5.4
# BID_WRITER_OUTLINE_TEMPERATURE=0.3
# BID_WRITER_OUTLINE_MAX_TOKENS=6000
# BID_WRITER_OUTLINE_TIMEOUT_SECONDS=120
# BID_WRITER_OUTLINE_MAX_RETRIES=3
# BID_WRITER_OUTLINE_TOP_P=0.95
# BID_WRITER_OUTLINE_SEED=42
```

- [ ] **Step 3: Update config schema docs**

In `docs/config_schema.md`, update the `project` YAML example to include:

```yaml
  outline_locked: true
  outline_generation:
    role_file: "./roles/标书架构师.md"
```

Add a new subsection after `project.inputs` path notes:

```markdown
### 3.1.2 大纲准备与锁定

`project.outline_locked` 表示当前配置是否已经完成大纲确认：

- `false`：新建配置的大纲准备阶段，GUI 会先打开“大纲准备”窗口。
- `true`：大纲已固定，GUI 直接加载章节树并允许扩写。

旧配置缺少该字段时按 `true` 处理，避免历史项目被强制带入新流程。

`project.outline_generation.role_file` 是大纲生成专用角色提示词，默认 `./roles/标书架构师.md`。正文扩写仍使用 `writing.role_file`。
```

In the model environment variables section, add the `BID_WRITER_OUTLINE_*` block from Step 2 and note the fallback order:

```markdown
大纲生成参数读取优先级为 `BID_WRITER_OUTLINE_*`、对应的 `BID_WRITER_*`、代码默认值。
```

- [ ] **Step 4: Update README GUI flow**

In `README.md`, add a short GUI usage note near the existing configuration/startup instructions:

```markdown
### 新建配置后的大纲准备

GUI 中点击“新建配置...”保存并应用后，若 `project.outline_locked: false`，系统会进入“大纲准备”窗口。用户可以读取已有 `outline_file`，也可以根据采购需求和评分标准生成 H4 Markdown 大纲，并在文本框中手动调整。点击“确认大纲并进入扩写”后，系统会写入大纲文件并把配置更新为 `project.outline_locked: true`。
```

- [ ] **Step 5: Run full focused verification**

Run:

```bash
uv run pytest tests/test_config_schema.py tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_outline_generator.py tests/test_outline_prepare.py tests/test_outline_prepare_dialog.py tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Run broader regression tests for touched flows**

Run:

```bash
uv run pytest tests/test_prompt_contract.py tests/test_fact_card_prompt.py tests/test_gui_context_menu.py tests/test_config_editor_tooltips.py -q
```

Expected: PASS.

- [ ] **Step 7: Check git diff for accidental user-file changes**

Run:

```bash
git status --short
git diff -- bid_writer/config.py bid_writer/config_editor.py bid_writer/config_editor_dialog.py bid_writer/outline_generator.py bid_writer/outline_prepare.py bid_writer/outline_prepare_dialog.py bid_writer/gui.py config.example.yaml .env.example docs/config_schema.md README.md
```

Expected: only files from this plan are modified. Untracked `roles/标书架构师.md` files may remain user-owned and should not be added unless the user explicitly asks.

- [ ] **Step 8: Commit Task 6**

Run:

```bash
git add config.example.yaml .env.example docs/config_schema.md README.md config_统计台账.yaml config_child.yaml config_公共服务满意度_auto.yaml tests/fixtures/current_prompt_config.yaml tests/fixtures/fact_card_prompt_config.yaml
git commit -m "docs: document outline preparation config"
```

## Final Verification

- [ ] **Step 1: Run all relevant tests**

Run:

```bash
uv run pytest tests/test_config_schema.py tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_outline_generator.py tests/test_outline_prepare.py tests/test_outline_prepare_dialog.py tests/test_gui_new_config.py tests/test_prompt_contract.py tests/test_fact_card_prompt.py tests/test_gui_context_menu.py tests/test_config_editor_tooltips.py -q
```

Expected: PASS.

- [ ] **Step 2: Confirm no unintended tracked changes remain**

Run:

```bash
git status --short
```

Expected: clean except user-owned untracked role files if they were already present before implementation.

- [ ] **Step 3: Record manual GUI smoke check**

Run the app:

```bash
uv run python run.py
```

Manual expected result:

- “项目” menu shows “新建配置...”, “切换配置...”, “编辑当前配置...”, and “解锁/重新准备大纲...”.
- Applying a config with `project.outline_locked: false` opens “大纲准备”.
- “读取已有大纲” loads text when `outline_file` exists.
- H3-only outline blocks confirmation.
- Valid H4 outline confirms, writes `outline.md`, sets `project.outline_locked: true`, and loads the chapter tree.
