# 新建配置向导设计

## 背景

当前“新建配置...”复用配置编辑器表单。它已经支持从招标文件导入并抽取“项目采购需求”和“评分标准”，但用户仍需要先理解并填写 `project.root_dir` 等工程化字段。对新项目来说，更自然的起点通常是“我手上有一份招标文件”，系统应根据招标文件位置推导项目目录、资料目录和配置文件路径，再让用户确认。

本设计将新建配置流程改为独立向导。编辑已有配置仍使用现有配置编辑器。

## 目标

- 新建项目时默认从选择招标文件开始。
- 将项目根目录默认设置为招标文件所在目录，并据此推导配置文件路径、资料目录、大纲路径和输出目录。
- 支持保留手动模式：用户可以跳过导入，直接选择或填写采购需求、评分标准文件。
- 自动抽取低置信度时必须预览确认；抽取失败时提供手动文件兜底。
- 原始招标文件智能纳管：项目内来源不复制，项目外来源复制到 `招标文件/`。
- 取消向导时可选择保留已整理资料或清理本次生成内容。
- 保存配置后复用现有配置切换和大纲准备流程。

## 非目标

- 不在本次设计中重写现有“编辑当前配置”窗口。
- 不把大纲准备完整融合到向导内；近期只做半整合，保存后打开现有“大纲准备”窗口。
- 不改变 canonical config schema 的字段含义。
- 不引入 OCR、扫描件识别或多文件批量导入。

## 用户流程

### 1. 招标文件

用户点击“项目 -> 新建配置...”后打开 `NewConfigWizardDialog`。

第一步提供两个入口：

- “选择招标文件...”：主路径，支持当前导入服务已有的 PDF、Word、Excel 类型。
- “跳过导入，手动填写”：进入手动资料文件路径流程。

选择招标文件后，本步只做轻量检查和路径推导，不立即写入项目文件。轻量检查包括：

- 文件是否存在。
- 扩展名是否在支持范围内。
- 项目根目录是否就是用户期望保存本项目资料的位置。

### 2. 项目位置

向导展示系统推导结果，用户必须确认或调整：

- 项目根目录。
- 配置文件保存位置。
- 资料目录，默认 `./项目要求`。
- 输出目录，默认 `./output`。
- 导入报告目录，默认 `./.bid_writer/imports/<import_id>`。
- 原始招标文件是否需要复制，以及复制目标，默认 `./招标文件/<原文件名>`。

推导规则：

- 默认使用招标文件所在目录作为项目根目录。
- 即使招标文件位于 `招标文件`、`资料`、`Downloads` 或 `Desktop` 等目录，也不自动改用上级目录或新建目录。
- 配置文件名仍优先从招标文件名去除“招标文件、采购文件、公告”等后缀得到；无法提取时使用“新项目”。

只有本步确认后，向导才允许创建项目目录、复制原始招标文件和准备导入目录。

### 3. 资料抽取

用户点击“开始抽取”后，系统执行转换与章节抽取。

成功时写入：

- `项目要求/项目采购需求.md`
- `项目要求/评分标准.md`
- `.bid_writer/imports/<import_id>/converted.md`
- `.bid_writer/imports/<import_id>/conversion_map.json`
- `.bid_writer/imports/<import_id>/extraction_report.json`

低置信度时：

- 停留在本步骤。
- 展示采购需求和评分标准的预览、来源页码或来源位置、置信度和警告。
- 用户确认后才写入正式资料文件。

抽取失败时：

- 展示失败原因。
- 提供“手动选择采购需求文件”和“手动选择评分标准文件”。
- 用户也可以返回重新选择招标文件。

手动模式时：

- 不运行转换抽取。
- 用户选择采购需求文件和评分标准文件。
- 路径默认相对项目根目录保存。

### 4. 基础信息

本步骤只展示新项目必须确认的字段：

- 投标主体名称。
- 大纲保存位置或已有大纲文件，默认 `./投标大纲.md`。
- 输出目录。
- 写作角色来源，默认 `./roles/通用投标角色.md`。

高级配置保留在同一个向导内，但默认折叠：

- 写作参数。
- 处理路径。
- 运行与 trace。

高级配置可以复用现有默认模型、校验和 YAML 渲染能力。若完整编辑成本较低，可以提供“打开完整配置编辑器”入口；若实现时发现嵌入旧编辑器复杂，应先实现折叠字段的最小版本。

### 5. 保存应用

最后一步展示保存前检查清单：

- 将保存的配置文件。
- 项目根目录。
- 将复制的原始招标文件。
- 已创建或将创建的资料文件。
- 大纲状态。
- 校验结果。
- 取消时可清理的文件清单。

保存成功后：

- 返回 `saved_path` 和 `apply_path`。
- 主界面复用现有 `_switch_to_config_path()` 切换配置。
- 若新配置 `project.outline_locked: false`，复用现有大纲准备流程打开“大纲准备”窗口。

## 界面结构

`NewConfigWizardDialog` 使用左侧步骤导航、右侧当前步骤内容、底部动作栏：

- 左侧步骤：招标文件、项目位置、资料抽取、基础信息、保存应用。
- 右侧页面：只展示当前步骤需要完成的任务。
- 底部按钮：上一步、取消、下一步；最后一步为“保存并应用”。

用户可以点击左侧已完成步骤返回修改。跳转到后续步骤前必须满足当前步骤的最低校验。

## 内部模型

新增纯逻辑状态模型，避免把所有流程状态塞进 Tk widget：

```python
@dataclass
class NewConfigWizardState:
    source_path: Path | None
    project_root: Path
    config_path: Path
    import_dir: Path | None
    should_copy_source: bool
    copied_source_path: Path | None
    bid_requirements_path: Path | None
    scoring_criteria_path: Path | None
    outline_path: Path
    output_dir: Path
    bidder_name: str
    created_paths: list[Path]
    manual_inputs: bool
```

`created_paths` 只记录本次向导明确创建或复制的路径，用于取消清理。不得根据目录名做宽泛删除。

## 组件边界

### `bid_writer/new_config_flow.py`

新增纯逻辑模块：

- 推导项目根目录。
- 生成默认配置文件名。
- 判断是否需要复制原始招标文件。
- 生成默认资料路径、大纲路径和输出路径。
- 维护 `created_paths`。
- 构建供 `config_editor.py` 保存的 editor model。
- 执行最终校验。

该模块应覆盖主要单元测试，不依赖 Tk。

### `bid_writer/new_config_wizard.py`

新增 Tk 向导 UI：

- 管理步骤导航和按钮状态。
- 调用 `new_config_flow.py` 更新状态。
- 调用 `TenderImportService` 执行导入。
- 调用 `ConfigEditorDocument.save()` 保存 YAML。
- 返回 `{"saved_path": Path | None, "apply_path": Path | None}`，保持主界面对话框协议一致。

### `bid_writer/tender_import_service.py`

扩展导入服务：

- 支持接收已确认的 `project_root`、`import_dir` 和可选的原始文件复制目标。
- 返回更完整的写入结果，包括创建的文件列表。
- 保持现有转换和章节抽取逻辑可复用。

### `bid_writer/config_editor.py`

继续作为默认模型、canonical YAML 渲染和保存校验的来源。新增向导不应复制 YAML schema 组装逻辑。

### `bid_writer/gui.py`

`open_new_config_editor()` 改为打开 `NewConfigWizardDialog`。取消时保持旧项目活跃，保存并应用时复用现有切换与大纲准备流程。

## 取消与清理

用户取消时，如果没有创建任何文件，直接关闭。

如果已经创建文件，弹出选择：

- 保留已整理资料。
- 清理本次生成内容。
- 返回向导。

清理规则：

- 只删除 `created_paths` 中记录的文件。
- 删除空目录时，只允许删除本次创建且为空的目录。
- 不删除用户原有文件。
- 清理失败时展示失败路径，保留向导窗口供用户处理。

## 校验

每步校验：

- 招标文件：存在且格式支持，手动模式可跳过。
- 项目位置：项目根目录和配置文件父目录可创建或已存在，配置文件名合法。
- 资料抽取：采购需求和评分标准都有有效文件或已确认抽取结果。
- 基础信息：投标主体名称不能为空，大纲路径和输出目录可解析。
- 保存应用：复用 `ConfigEditorDocument.validate()`，并展示所有 error/warning。

## 测试计划

新增或扩展测试：

- `tests/test_new_config_flow.py`
  - 普通目录使用招标文件所在目录。
  - `招标文件/` 等资料目录自身作为项目根目录。
  - `Downloads` / `Desktop` 自身作为项目根目录。
  - 项目外来源需要复制，项目内来源不复制。
  - 默认路径包含 `项目要求/项目采购需求.md`、`项目要求/评分标准.md`、`投标大纲.md`、`output`。
  - 取消清理只删除 `created_paths`。
- `tests/test_new_config_wizard.py`
  - 步骤按钮状态和跳转校验。
  - 保存成功返回 `saved_path` 和 `apply_path`。
  - 取消时有创建文件会进入清理确认。
- `tests/test_config_editor_tender_import.py`
  - 导入服务返回创建文件列表。
  - 低置信度时需要确认。
  - 抽取失败进入手动兜底。
- `tests/test_gui_new_config.py`
  - 主界面新建入口打开新向导。
  - 保存应用后复用配置切换。
  - 取消后旧配置仍保持活跃。

运行命令使用：

```bash
uv run pytest tests/test_new_config_flow.py tests/test_new_config_wizard.py tests/test_config_editor_tender_import.py tests/test_gui_new_config.py -q
```

## 文档维护

实现时需要同步维护：

- `README.md`：更新新建配置使用流程。
- `docs/config_schema.md`：说明向导如何生成 canonical config。
- `config.example.yaml`：如默认值有变化需同步。
- 相关测试夹具。

## 验收标准

- “新建配置...”打开独立向导，而不是完整大表单。
- 用户可从招标文件开始完成配置创建。
- 系统会把项目根目录设置为招标文件所在目录，并允许用户在项目位置步骤手动调整。
- 项目外招标文件可复制到 `招标文件/`。
- 抽取低置信度必须预览确认，失败可手动选择资料文件。
- 保存应用后能切换到新配置，并在需要时进入现有大纲准备窗口。
- 取消时可保留或清理本次生成内容，且不会误删用户原有文件。
