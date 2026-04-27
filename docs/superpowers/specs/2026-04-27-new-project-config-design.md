# 新建项目配置文件设计

## 目标

为桌面 GUI 增加“新建配置...”入口，让用户可以从默认模板创建新的项目配置文件，而不需要手写 YAML。

该功能面向新项目初始化：用户填写项目运行所需的关键参数，系统为其他参数填入推荐默认值，最后保存为新的 `config_*.yaml`。保存成功后，用户可以立即切换到新配置并加载大纲。

## 范围

本次只创建和保存项目配置 YAML，不自动创建项目资料目录、资料文件、角色文件或 `.env.local`。

包含：

- 主界面新增“新建配置...”入口
- 复用现有 `ConfigEditorDialog`，增加新建模式
- 提供默认配置模型
- 对必填字段做校验提示
- 保存时默认走“另存为”流程
- 保存成功后可切换到新配置
- 补充配置编辑器相关测试

不包含：

- 项目目录脚手架
- 空白 `outline.md`、采购需求、评分标准文件生成
- API Key 或 Base URL 写入
- 独立的 CLI 初始化命令
- 完整多步骤向导 UI

## 用户体验

主界面在现有配置菜单中增加“新建配置...”。

点击后打开配置编辑器的新建模式：

- 窗口标题显示“新建配置”
- 顶部文件状态显示“未保存的新配置”
- 表单使用现有项目、写作、处理路径、模型、运行分组
- 必填项目字段为空或使用推荐相对路径，等待用户确认
- 右侧继续展示校验结果、配置摘要和 YAML 预览

保存时：

- 新建模式默认弹出“另存为”
- 推荐文件名为 `config_新项目.yaml`
- 如果用户选择已有文件，沿用现有覆盖确认或备份策略
- 保存成功后提示是否立即切换到新配置

切换后：

- 调用现有配置切换流程
- 记录为最近使用配置
- 尝试加载大纲
- 如果大纲或资料路径不存在，按现有错误反馈展示

## 必填字段

新建配置要求用户明确填写或确认以下字段：

- `project.root_dir`
- `project.bidder_name`
- `project.inputs.outline_file`
- `project.inputs.bid_requirements_file`
- `project.inputs.scoring_criteria_file`

校验规则沿用现有配置编辑器：

- `project.root_dir` 必须存在
- 大纲、采购需求、评分标准文件必须存在
- 投标主体名称不能为空

投标主体名称当前编辑器原本可以为空；新建模式下应提升为错误，避免生成无主体信息的新项目配置。

## 默认配置

新增一个配置编辑器级别的默认文档创建函数：

```python
create_new_config_editor_document(config_path: str | Path | None = None) -> ConfigEditorDocument
```

默认模型应与 canonical schema 保持一致，并尽量贴近 `config.example.yaml`。

推荐默认值：

- `project.root_dir: "."`
- `project.bidder_name: ""`
- `project.inputs.outline_file: "./outline.md"`
- `project.inputs.bid_requirements_file: "./项目要求/项目采购需求.md"`
- `project.inputs.scoring_criteria_file: "./项目要求/评分标准.md"`
- `project.output_dir: "./output"`
- `writing.role_file: "./roles/example_role.md"`
- `writing.target_words.default: 3000`
- `writing.target_words.min: 100`
- `writing.target_words.max: 15000`
- `writing.target_words.step: 100`
- `writing.target_words.upper_ratio: 1.15`
- `writing.output_format: "纯正文"`
- `writing.allow_markdown_headings: false`
- `writing.allow_english_terms: false`
- `writing.max_tables_per_section: 2`
- `writing.max_mermaid_flowcharts_per_section: 0`
- `processing.path: "auto"`
- `runtime.stream.enabled: true`
- `runtime.trace.enabled: false`
- `runtime.output.overwrite_existing: true`

模型参数沿用当前 `config.example.yaml`：

- generation model: `gpt-4o-mini`
- pruning model: `gpt-4o-mini`
- embedding model: `text-embedding-3-small`

`fact_cards` 默认写为：

```yaml
fact_cards:
  enabled: true
  cards: []
  chapter_defaults: {}
```

## 架构

### `bid_writer/config_editor.py`

新增默认模型构造能力，并通过现有 `build_canonical_config()` 和 `ConfigEditorDocument.render_yaml()` 输出 YAML。

建议新增：

- `build_default_editor_model()`
- `create_new_config_editor_document(config_path: str | Path | None = None)`

新建文档的 `raw_config` 应来自默认模型渲染后的 canonical config，避免默认模型和 YAML 预览不一致。

新建模式需要校验投标主体名称。可以通过给 `validate_editor_model()` 增加参数控制：

```python
validate_editor_model(..., require_project_identity: bool = False)
```

普通编辑模式保持现有兼容；新建模式开启该要求。

### `bid_writer/config_editor_dialog.py`

`ConfigEditorDialog` 增加新建模式参数：

```python
ConfigEditorDialog(parent, config_path=None, new_config=True)
```

行为差异：

- 使用默认文档创建函数，而不是读取已有文件
- 标题改为“新建配置”
- 当前文件显示为“未保存的新配置”
- 保存按钮在未保存前调用另存为
- 校验时启用新建模式必填规则

保存成功后仍通过 `result` 返回：

- `saved_path`
- `apply_path`

现有打开编辑器的逻辑不应受影响。

### `bid_writer/gui.py`

主界面新增入口：

- 菜单项：`新建配置...`
- 回调：`open_new_config_editor()`

回调打开新建模式配置编辑器。用户保存并选择应用时，复用 `_switch_to_config_path()` 完成切换。

## 错误处理

- 用户取消保存：关闭对话框或返回编辑器，不产生文件
- 保存路径父目录不存在：保存逻辑创建父目录
- 目标文件已存在：沿用当前备份或覆盖确认策略
- 必填字段缺失：展示错误并阻止保存
- 保存成功但切换失败：保留已保存配置，并展示切换失败原因

## 测试

新增或扩展 `tests/test_config_editor.py`：

- 默认新建文档能渲染 canonical YAML
- 默认 YAML 包含 `fact_cards` 空结构
- 默认值与 `config.example.yaml` 的关键字段一致
- 新建模式下 `bidder_name` 为空会报错
- 填入有效路径后校验通过关键项目字段

可扩展 `tests/test_config_editor_dialog.py`：

- 新建模式初始化不读取磁盘配置
- 新建模式标题或状态变量显示未保存状态

运行命令：

```bash
uv run pytest tests/test_config_editor.py tests/test_config_editor_dialog.py -q
```

## 文档维护

本功能涉及配置创建体验，不改变 schema 字段含义。若实现时调整默认值，需要同步维护：

- `docs/config_schema.md`
- `config.example.yaml`
- `README.md` 中配置启动与 GUI 使用说明
- 相关测试夹具

## 验收标准

- GUI 有“新建配置...”入口
- 可以从默认模板打开配置编辑器
- 保存后生成新的 YAML 文件
- YAML 使用 canonical schema
- 必填项缺失会给出清晰错误
- 保存成功后可以立即切换到新配置
- 现有“编辑当前配置...”和“切换配置”行为不回归
- 相关测试通过
