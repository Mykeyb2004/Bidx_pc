# System Gate Rules Single-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `system prompt` 的门禁文案收敛为单一固定文件 `roles/system_gate_rules.md`，保留 `bidder_name` 配置驱动，占位符轻量替换，缺文件直接报错，并把角色文件目录迁到仓库根目录下的 `roles/`。

**Architecture:** 运行时继续通过 `Config` 读取角色正文，但不再由 `AIWriter` 拼装内建门禁文案；改为固定读取 `config` 同级目录下的 `roles/system_gate_rules.md` 原文，并在 `AIWriter` 中只做 `{bidder_name}` 的直接字符串替换。现有 user prompt A+ 结构不变，旧 `writing.hard_constraints` / `allow_markdown_headings` / `allow_english_terms` 仅保留兼容解析与部分后处理用途，不再作为 system gate 文案来源。

**Tech Stack:** Python, PyYAML, pytest, Markdown/YAML 配置文档。

---

## File Map

- **Create:** `roles/system_gate_rules.md`
- **Create:** `roles/通用投标角色.md`
- **Create:** `roles/公共服务满意度_role.md`
- **Create:** `tests/fixtures/roles/example_role.md`
- **Create:** `tests/fixtures/roles/system_gate_rules.md`
- **Modify:** `bid_writer/config.py`
- **Modify:** `bid_writer/ai_writer.py`
- **Modify:** `bid_writer/config_editor.py`
- **Modify:** `bid_writer/config_editor_dialog.py`
- **Modify:** `bid_writer/config_editor_tooltips.py`
- **Modify:** `tests/test_prompt_contract.py`
- **Modify:** `tests/fixtures/current_prompt_config.yaml`
- **Modify:** `config_统计台账.yaml`
- **Modify:** `config_公共服务满意度_auto.yaml`
- **Modify:** `config.example.yaml`
- **Modify:** `docs/config_schema.md`
- **Modify:** `docs/prompt_contract.md`
- **Delete:** `docs/roles/通用投标角色.md`
- **Delete:** `docs/roles/公共服务满意度_role.md`

### Task 1: 锁定失败中的新门禁契约

**Files:**
- Create: `tests/fixtures/roles/example_role.md`
- Create: `tests/fixtures/roles/system_gate_rules.md`
- Modify: `tests/fixtures/current_prompt_config.yaml`
- Modify: `tests/test_prompt_contract.py`

- [ ] **Step 1: 先补齐测试夹具目录和文件**

在 `tests/fixtures/roles/example_role.md` 放入最小角色正文：

```md
你是一位专业的标书撰写专家。
```

在 `tests/fixtures/roles/system_gate_rules.md` 放入固定门禁清单：

```md
- 投标主体统一使用“{bidder_name}”表述；除非用户明确要求，不要替换为其他公司名称、简称或第一人称主体。
- 严禁使用Markdown标题符号（#）。
- 除专有名词或用户明确要求外，禁止输出不必要的英文、英文缩写或中英对照。
- 默认使用正式层级序号组织正文；除非用户明确要求只写单段摘要，否则至少出现一个正式层级序号“一、”。
- 只要正文包含多个板块、多个长段落、表格或并列清单，必须继续使用“（一）”“1.”“（1）”展开，不得输出无序号散文式正文。
```

把 `tests/fixtures/current_prompt_config.yaml` 调整为文件模式，并故意保留旧字段值来证明它们会被忽略：

```yaml
writing:
  role_file: "./roles/example_role.md"
  allow_markdown_headings: true
  allow_english_terms: true
  hard_constraints:
    - "旧字段不应再进入 system prompt"
  extra_rules:
    - "内容要专业、严谨，符合标书撰写规范。"
    - "请根据以上任务卡，结合采购需求、评分标准撰写投标正文。"
```

- [ ] **Step 2: 让测试工作区支持递归复制 `roles/` 子目录**

把 `tests/test_prompt_contract.py` 里的 `_prepare_config_workspace()` 从“只复制根目录文件”改成“目录递归复制 + 文件原样复制”：

```python
def _prepare_config_workspace(tmp_path: Path, config_name: str) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for fixture in FIXTURES_DIR.iterdir():
        destination = workspace / fixture.name
        if fixture.is_dir():
            shutil.copytree(fixture, destination)
        elif fixture.is_file():
            shutil.copy2(fixture, destination)

    config_path = workspace / config_name
    config = Config(str(config_path))
    ...
```

- [ ] **Step 3: 先写失败测试，钉死新的 system gate 行为**

在 `tests/test_prompt_contract.py` 中新增或改写以下断言：

```python
def test_system_prompt_reads_role_file_and_global_gate_file(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)

    system_prompt = writer.build_system_prompt()

    assert system_prompt.startswith("你是一位专业的标书撰写专家。")
    assert "【最高优先级输出强约束】" in system_prompt
    assert "投标主体统一使用“测试投标主体”表述" in system_prompt
    assert "严禁使用Markdown标题符号（#）。" in system_prompt
    assert "旧字段不应再进入 system prompt" not in system_prompt


def test_system_prompt_fails_fast_when_global_gate_file_missing(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    gate_file = Path(config.config_path).parent / "roles" / "system_gate_rules.md"
    gate_file.unlink()
    writer = _build_writer(monkeypatch, config)

    with pytest.raises(FileNotFoundError, match="system_gate_rules.md"):
        writer.build_system_prompt()


def test_system_prompt_ignores_legacy_gate_switches(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)

    system_prompt = writer.build_system_prompt()

    assert "严禁使用Markdown标题符号（#）。" in system_prompt
    assert "禁止输出不必要的英文、英文缩写或中英对照。" in system_prompt
    assert "旧字段不应再进入 system prompt" not in system_prompt
```

把已有的 `test_system_prompt_keeps_global_gate_rules()` 更新成“仍有 gate shell + 内容来自文件”，不要再暗示规则源来自 `_build_hard_constraints()`。

- [ ] **Step 4: 运行测试，确认它们先失败**

Run:

```bash
uv run pytest tests/test_prompt_contract.py -q
```

Expected:

```text
FAIL tests/test_prompt_contract.py::test_system_prompt_reads_role_file_and_global_gate_file
FAIL tests/test_prompt_contract.py::test_system_prompt_fails_fast_when_global_gate_file_missing
FAIL tests/test_prompt_contract.py::test_system_prompt_ignores_legacy_gate_switches
```


### Task 2: 用固定门禁文件替换散落的 system gate 拼装

**Files:**
- Modify: `bid_writer/config.py`
- Modify: `bid_writer/ai_writer.py`
- Test: `tests/test_prompt_contract.py`

- [ ] **Step 1: 在 `Config` 中增加固定门禁文件读取能力**

在 `bid_writer/config.py` 增加一个只负责“固定路径 + fail fast”的轻量属性，不要引入新配置项：

```python
@property
def system_gate_rules_path(self) -> Path:
    return self.config_path.parent.resolve() / "roles" / "system_gate_rules.md"


@property
def system_gate_rules_template(self) -> str:
    path = self.system_gate_rules_path
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"system gate rules 文件不存在: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"system gate rules 文件为空: {path}")
    return text
```

保留 `prompt_bidder_name` 属性，因为它仍是 `{bidder_name}` 的运行时来源。

- [ ] **Step 2: 删除 `AIWriter` 对内建门禁文案的逐条拼装依赖**

在 `bid_writer/ai_writer.py` 里移除 `_build_hard_constraints()` 的调用，改成“读取模板 + 轻量替换”：

```python
def _render_system_gate_rules(self) -> str:
    gate_rules = self.config.system_gate_rules_template
    if "{bidder_name}" in gate_rules:
        bidder_name = self.config.prompt_bidder_name
        if not bidder_name:
            raise ValueError(
                "roles/system_gate_rules.md 使用了 {bidder_name}，但配置缺少 project.bidder_name。"
            )
        gate_rules = gate_rules.replace("{bidder_name}", bidder_name)
    return gate_rules.strip()


def build_system_prompt(self) -> str:
    sections = []
    role = self.config.role.strip()
    if role:
        sections.append(role)

    gate_rules = self._render_system_gate_rules()
    sections.append(
        "【最高优先级输出强约束】\n"
        "以下规则优先级高于其他风格建议、默认模板和惯常表达；如有冲突，必须以本节规则为准。\n"
        f"{gate_rules}"
    )

    return "\n\n".join(sections).strip()
```

如果 `_build_hard_constraints()` 不再被任何地方使用，直接删掉这个方法，避免后续维护者误以为它仍是权威来源。

- [ ] **Step 3: 同步 prompt contract block 的门禁来源元信息**

更新 `bid_writer/ai_writer.py` 中 `system_constraints` block 的 `source_context`，去掉旧字段来源，改成新的单一来源描述：

```python
"source_context": [
    "Config.role",
    "roles/system_gate_rules.md",
    "project.bidder_name",
],
```

- [ ] **Step 4: 只跑 prompt 契约测试，确认实现生效**

Run:

```bash
uv run pytest tests/test_prompt_contract.py -q
```

Expected:

```text
20+ passed
```


### Task 3: 迁移角色资产并更新运行时默认路径

**Files:**
- Create: `roles/system_gate_rules.md`
- Create: `roles/通用投标角色.md`
- Create: `roles/公共服务满意度_role.md`
- Delete: `docs/roles/通用投标角色.md`
- Delete: `docs/roles/公共服务满意度_role.md`
- Modify: `config_统计台账.yaml`
- Modify: `config_公共服务满意度_auto.yaml`
- Modify: `config.example.yaml`
- Modify: `bid_writer/config_editor.py`

- [ ] **Step 1: 在仓库根目录创建新的 `roles/` 资产**

把现有角色正文迁移到新目录，并新增全局门禁文件。`roles/system_gate_rules.md` 建议直接采用当前项目审过的去重版门禁：

```md
- 投标主体统一使用“{bidder_name}”表述；除非用户明确要求，不要替换为其他公司名称、简称或第一人称主体。
- 严禁使用Markdown标题符号（#）。
- 除专有名词或用户明确要求外，禁止输出不必要的英文、英文缩写或中英对照。
- 默认使用正式层级序号组织正文；除非用户明确要求只写单段摘要，否则至少出现一个正式层级序号“一、”。
- 只要正文包含多个板块、多个长段落、表格或并列清单，必须继续使用“（一）”“1.”“（1）”展开，不得输出无序号散文式正文。
- 序号不得脱离小标题单独成行；序号与对应小标题必须在同一标题行，标题行后再另起段书写正文。
- 禁止插入零宽字符、BOM、不可见分隔符。
- 正文中的段内枚举或并列说明不视为章节层级，可使用“第一……、第二……”或“一是……；二是……；三是……”。
- 正文中不得使用“首先、其次、再次、最后”组织内容。
- 严禁输出身份扮演、自我说明、写作意图解释、过程说明或评论性话语，例如“作为××专家”“下面将从以下几方面展开”等。
- 严禁输出空泛套话、AI腔开场和价值表态，如“在当今数字化转型的大背景下”“我们将秉承……理念”等。
- 不得连续堆砌排比句、空洞形容词和夸张表述；表述应尽量落到具体措施、机制或交付物。
- 不得机械重复固定段落模板或句式，避免通篇套用单一“总-分-总”结构。
- 不得为显得专业而堆砌术语；同一概念优先使用稳定、常见的中文表述。
- 禁止输出分割线。
```

- [ ] **Step 2: 更新活跃配置文件到新的角色目录，并移除 system gate 的旧重复来源**

把 `config_统计台账.yaml` 与 `config_公共服务满意度_auto.yaml` 的 `role_file` 改成：

```yaml
writing:
  role_file: ./roles/通用投标角色.md
```

以及：

```yaml
writing:
  role_file: ./roles/公共服务满意度_role.md
```

从 `config_统计台账.yaml` 中删除整段 `writing.hard_constraints`；`allow_markdown_headings` 与 `allow_english_terms` 保留，因为现有后处理巡检仍可能使用它们。

把 `config.example.yaml` 的默认角色路径改成：

```yaml
writing:
  role_file: "./roles/example_role.md"
```

并把示例里的 `hard_constraints` 改成空列表或直接删掉示例项，不再展示“靠 YAML 列表维护 system gate 文案”的写法。

- [ ] **Step 3: 修正配置编辑器里的默认角色路径**

把 `bid_writer/config_editor.py` 中的三个旧默认值统一替换为 `./roles/example_role.md`：

```python
default_file="./roles/example_role.md"
...
writing_payload["role_file"] = model["writing"]["role_file"].strip() or "./roles/example_role.md"
...
role_path = _resolve_path(model["writing"]["role_file"] or "./roles/example_role.md", config_path.parent)
```

- [ ] **Step 4: 用真实配置做一次 system prompt 冒烟检查**

Run:

```bash
uv run python - <<'PY'
from bid_writer.config import Config
from bid_writer.ai_writer import AIWriter

config = Config("config_统计台账.yaml")
writer = AIWriter(config)
system_prompt = writer.build_system_prompt()
print("contains_gate_file_rule=", "严禁使用Markdown标题符号（#）。" in system_prompt, sep="")
print("contains_bidder_name=", "杭州菲尔德咨询" in system_prompt, sep="")
print("contains_legacy_yaml_rule=", "正文中严禁正文中出现类似“作为xx投标专家”之类的内容" in system_prompt, sep="")
PY
```

Expected:

```text
contains_gate_file_rule=True
contains_bidder_name=True
contains_legacy_yaml_rule=True
```


### Task 4: 同步文档与编辑器提示，避免旧配置口径继续误导

**Files:**
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `bid_writer/config_editor_dialog.py`
- Modify: `bid_writer/config_editor_tooltips.py`

- [ ] **Step 1: 更新配置文档，明确固定门禁文件是唯一文本来源**

把 `docs/config_schema.md` 中 `writing` 示例更新成：

```yaml
writing:
  role_file: "./roles/example_role.md"
  target_words:
    default: 1500
    min: 100
    max: 12000
    step: 100
    upper_ratio: 1.15
  output_format: "纯正文"
  first_line_template: ""
  allow_markdown_headings: false
  allow_english_terms: false
  max_tables_per_section: 2
  max_mermaid_flowcharts_per_section: 0
  summary_title: ""
  hard_constraints: []
  extra_rules: []
```

并补充说明文字：

```md
- `writing.role_file` 推荐放在仓库根目录下的 `roles/`
- `roles/system_gate_rules.md` 是 system prompt 门禁文案的固定唯一文本来源
- `writing.hard_constraints`、`writing.allow_markdown_headings`、`writing.allow_english_terms` 不再生成 system gate 文案
```

- [ ] **Step 2: 更新 prompt 合同文档，删掉 `_build_hard_constraints()` 的旧叙述**

把 `docs/prompt_contract.md` 的 System Prompt 章节改成下面这个口径：

```md
`system prompt` 由两块组成：

1. `Config.role`
2. 固定门禁文件 `roles/system_gate_rules.md`

门禁文件按原文读取；如果包含 `{bidder_name}`，运行时使用 `project.bidder_name` 直接替换。
缺少门禁文件、门禁文件为空、或缺少占位符所需配置时，直接报错。
```

并把旧的以下说法删除或改写：

```md
- `_build_hard_constraints()` 会按顺序拼出以下约束
- `prompt_allow_markdown_headings` 会自动生成禁止 `#` 标题
- `prompt_allow_english_terms` 会自动生成禁止不必要英文
- `prompt_hard_constraints` 会直接追加到 system prompt
```

- [ ] **Step 3: 给配置编辑器加最小化的去误导文案**

不要重做 UI 结构，只改文本提示。把 `bid_writer/config_editor_dialog.py` 中旧的“高优先级约束”区块改成兼容说明：

```python
hard_constraints = ttk.LabelFrame(content, text="兼容旧字段（暂不参与 system 门禁）", padding=12)
...
self._add_text_block(
    hard_constraints,
    "hard_constraints",
    "writing.hard_constraints_text",
    help_text="兼容旧配置保留；system 门禁请改 ./roles/system_gate_rules.md。",
    height=8,
)
```

同时把 `bid_writer/config_editor_tooltips.py` 中相关说明改成：

```python
"writing.allow_markdown_headings": "该开关仍用于部分输出巡检，不再生成 system prompt 门禁文案。",
"writing.allow_english_terms": "该开关仍用于部分输出巡检，不再生成 system prompt 门禁文案。",
"writing.hard_constraints_text": "兼容旧字段保留，不再作为 system prompt 门禁来源。请改 ./roles/system_gate_rules.md。",
```

- [ ] **Step 4: 运行回归测试和 prompt 渲染检查**

Run:

```bash
uv run pytest tests/test_prompt_contract.py -q
uv run python - <<'PY'
from bid_writer.config import Config
from bid_writer.ai_writer import AIWriter
from bid_writer.outline_parser import parse_outline

config = Config("config_统计台账.yaml")
writer = AIWriter(config)
parser = parse_outline(config.get_outline_content())
heading = parser.get_deepest_headings()[0]
result = writer.build_prompt_result(heading, target_words=config.generation_default_target_words)
print("contains_system_gate=", "请严格遵守 system 中全部硬门禁" in result.prompt, sep="")
print("contains_structure_output_hard_req=", "## 结构输出硬要求" in result.prompt, sep="")
PY
```

Expected:

```text
20+ passed
contains_system_gate=True
contains_structure_output_hard_req=False
```


## Self-Review Checklist

- [ ] 计划中的实现文件与 spec 一致：固定门禁文件、`roles/` 迁移、`bidder_name` 占位符、fail fast 都有对应任务
- [ ] 没有留下 “TODO / TBD / 以后补” 一类占位说法
- [ ] 所有测试命令都使用 `uv run`
- [ ] 没有把 user prompt A+ 拆分一起改坏
- [ ] 没有引入 `writing.system_gate_rules_file` 等新的配置字段
