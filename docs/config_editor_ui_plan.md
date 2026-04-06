# 配置编辑器界面方案

## 1. 目标与边界

本方案面向当前 Tkinter 桌面应用，目标是在现有“切换配置”之外，新增一个可视化配置编辑入口，让用户可以：

- 加载现有 `config*.yaml`
- 以分组表单方式编辑参数
- 实时校验配置是否可运行
- 预览最终 YAML
- 保存覆盖或另存为新配置

边界约束：

- 只编辑项目 YAML，不直接编辑 `.env.local`
- 不在配置界面中直接编辑采购需求、评分标准、大纲正文内容，只维护它们的文件路径
- 保存时以 canonical schema 为主，不继续鼓励旧 schema

## 2. 设计原则

### 2.1 以信息分类，而不是以代码模块分类

界面一级分组直接对应当前 canonical schema：

- `project`
- `writing`
- `processing`
- `models`
- `runtime`

这样用户看到的是“项目资料、写作规则、处理链路、模型参数、运行行为”，而不是实现细节。

### 2.2 `processing.path` 是最重要的业务开关

`processing.path` 决定业务链路，应作为界面中的一级决策点：

- `full_context`
- `legacy_rule`
- `hybrid_extract`

链路切换后，参数面板动态变化，避免让用户同时看到无效参数。

### 2.3 敏感信息与项目文件分离

以下信息不进入 YAML 表单：

- generation 连接信息
- pruning 连接信息
- embedding 连接信息

界面只展示它们在 `.env.local` 中是否已配置，并给出说明。

### 2.4 让用户看见“将要保存成什么”

配置表单不是黑盒。编辑器右侧要始终提供：

- 校验结果
- 当前配置摘要
- YAML 预览

这样用户可以确认结构是否符合预期。

### 2.5 降低参数理解门槛

配置项较多，且不少参数偏技术。编辑器应为主要字段提供悬停提示：

- 鼠标停留在字段标签、输入框或开关上时显示 tip
- tip 优先解释“这是什么”和“什么时候该改”
- 对 `processing`、`models`、`runtime.trace` 这类技术参数尤其重要

## 3. 入口与整体交互

### 3.1 入口设计

在主窗口工具栏中，保留现有 `切换配置`，并新增：

- `编辑配置`

两者职责区分：

- `切换配置`
  - 快速切换当前运行使用的 YAML
- `编辑配置`
  - 打开可视化配置工作台

### 3.2 窗口形态

推荐使用一个较大的 `Toplevel` 工作台，建议初始尺寸约 `1180 x 780`。

原因：

- 与当前 GUI 的弹窗风格一致
- 不打断主窗口结构
- 比传统小对话框更适合承载多分组表单

### 3.3 主布局

推荐三栏布局：

- 左侧：分组导航
- 中间：当前分组表单
- 右侧：校验与 YAML 预览

顶部放文件状态和主操作，底部放保存按钮。

## 4. 信息架构与字段分组

### 4.1 `项目`

目标：编辑项目固有信息和文件路径。

建议字段：

| 字段 | 控件 | 说明 |
| --- | --- | --- |
| `project.root_dir` | 路径选择器 | 项目资料根目录 |
| `project.bidder_name` | 单行输入框 | 投标主体名称 |
| `project.inputs.outline_file` | 文件选择器 | Markdown 大纲路径 |
| `project.inputs.bid_requirements_file` | 文件选择器 | 采购需求文件 |
| `project.inputs.scoring_criteria_file` | 文件选择器 | 评分标准文件 |
| `project.output_dir` | 路径选择器 | 输出目录 |

交互建议：

- 文件字段旁边显示“已找到 / 未找到”
- 提供“相对 `project.root_dir` 保存”提示
- 不在这里直接编辑采购需求或评分标准正文

### 4.2 `写作`

目标：编辑写作风格、字数规则和硬约束。

建议字段：

| 字段 | 控件 |
| --- | --- |
| `writing.role_file` / `writing.role` | 单选切换 + 文件选择器 / 多行文本 |
| `writing.min_words.default` | 数字输入 |
| `writing.min_words.min` | 数字输入 |
| `writing.min_words.max` | 数字输入 |
| `writing.min_words.step` | 数字输入 |
| `writing.output_format` | 下拉框 |
| `writing.first_line_template` | 单行输入框 |
| `writing.allow_markdown_headings` | 开关 |
| `writing.allow_english_terms` | 开关 |
| `writing.max_tables_per_section` | 数字输入 |
| `writing.summary_title` | 单行输入框 |
| `writing.hard_constraints` | 列表编辑器 |
| `writing.extra_rules` | 列表编辑器 |

交互建议：

- `role` 使用“文件 / 内嵌文本”二选一
- `hard_constraints` 和 `extra_rules` 提供“新增一条 / 删除 / 上移 / 下移”
- 长文本区域支持只读预览和展开编辑

### 4.3 `处理路径`

目标：让用户先选业务链路，再配置链路参数。

界面结构建议：

1. 链路选择卡片
2. 公共上下文视图参数
3. 当前链路参数
4. 高级参数折叠区

### 路径选择

- `full_context`
  - 不做章节级处理
- `legacy_rule`
  - 使用当前规则链路
- `hybrid_extract`
  - 使用检索摘录链路

### 公共参数

仅在 `legacy_rule` / `hybrid_extract` 下显示：

- `processing.context_view.include_ancestors`
- `processing.context_view.include_siblings`
- `processing.context_view.max_siblings`

### `legacy_rule` 参数

- `scoring_max_rows`
- `requirements_max_quotes`
- `requirements_max_quote_chars`
- `requirement_brief_enabled`

### `hybrid_extract` 参数

基础参数：

- `unavailable_policy`
- `scoring_parse_mode`
- `scoring_max_rows`
- `requirements_max_quotes`
- `requirements_max_quote_chars`
- `requirement_brief_enabled`

高级参数：

- `retrieval.lexical_enabled`
- `retrieval.vector_enabled`
- `retrieval.verify_enabled`
- `retrieval.top_k_lexical`
- `retrieval.top_k_vector`
- `retrieval.top_k_fused`
- `retrieval.top_k_final`
- `retrieval.min_fused_score`
- `quote_only`
- `return_ids_only`
- `verify_max_candidates`

交互建议：

- `full_context` 下隐藏链路参数，显示说明卡片
- `hybrid_extract` 参数默认只展示基础项，高级项折叠
- 当 `vector_enabled=true` 但 embedding 未配置时，右侧立即报错
- 当 `verify_enabled=true` 但 pruning 未配置时，右侧立即报错

### 4.4 `模型`

目标：只编辑非敏感模型参数。

建议拆成三个子卡片：

- 主生成模型 `models.generation`
- 辅助模型 `models.pruning`
- 向量模型 `models.embedding`

可编辑字段：

- `model`
- `temperature`
- `max_tokens`
- `timeout_seconds`
- `max_retries`
- `top_p`
- `seed`
- `batch_size`
- `cache_dir`
- `rebuild_on_source_change`
- `query_prefix`
- `document_prefix`

只读状态区：

- 主模型连接状态：来自 `.env.local`
- pruning 连接状态：来自 `.env.local`
- embedding 连接状态：来自 `.env.local`

说明文案建议：

- “本界面不保存 API Key、Base URL 等敏感或环境级配置”
- “如需修改连接信息，请更新 `.env.local`”

### 4.5 `运行`

目标：编辑运行时行为、调试输出和文件输出策略。

建议字段：

| 分组 | 字段 |
| --- | --- |
| `stream` | `enabled`、`idle_timeout_seconds` |
| `trace` | `enabled`、`directory`、`mode`、`write_prompt`、`write_output`、`write_context`、`write_summary`、`redact_sensitive` |
| `debug` | `context_pruning_dump` |
| `output` | `prefix`、`include_title_header`、`overwrite_existing`、`filename_max_length`、`empty_filename_fallback` |
| `merge` | `normalize_soft_line_breaks` |

交互建议：

- `trace` 和 `debug` 放进单独“调试与追踪”卡片
- `runtime.trace.directory` 标注为“相对配置文件目录”

### 4.6 `预览与保存`

这个页面不一定单独成页，也可以放到右侧固定区域。

建议包含：

- 当前配置摘要
- 校验结果
- YAML 预览
- 另存为路径
- 保存行为说明

## 5. 保存策略

### 5.1 内部数据模型

编辑器内部统一转换成 canonical view model。

加载来源可以是：

- 当前 canonical schema
- 旧 schema

但表单层不直接暴露旧字段。

### 5.2 保存行为

建议支持 3 个动作：

- `保存`
  - 覆盖当前文件
- `另存为`
  - 保存为新的 `config*.yaml`
- `导出 YAML`
  - 仅导出文本，不切换当前运行配置

建议行为：

- 保存时按固定顺序输出 canonical schema
- 若原文件是旧 schema，保存时自动标准化
- 首次覆盖保存前可自动生成一个 `.bak` 备份

### 5.3 关于注释和顺序

这是必须提前告知用户的行为边界：

- 首版不保证保留原有 YAML 注释
- 首版不保证保留原字段顺序
- 保存后文件会变成统一的 canonical 排序

这与当前“配置结构归一化”的目标是一致的，但需要在界面中显式提示。

## 6. 校验策略

右侧校验面板建议分 3 级：

- 错误
  - 保存后当前配置无法运行
- 警告
  - 可以保存，但行为可能不符合预期
- 信息
  - 说明配置已被标准化，或某些参数当前不生效

建议校验项：

- `project.root_dir` 是否存在
- 输入文件是否存在
- 数值范围是否合法
- `min <= default <= max`
- `processing.path` 与链路参数是否匹配
- `hybrid_extract + vector_enabled` 时 embedding 是否已配置
- `hybrid_extract + verify_enabled` 时 pruning 是否已配置
- `return_ids_only` 在 verify 场景下是否为 `true`
- `trace.directory`、`embedding.cache_dir` 路径是否可写

## 7. 推荐交互细节

为了降低复杂度，建议加入这些细节：

- 未保存变更提示
- 恢复本页默认值
- 恢复到文件当前值
- 字段旁即时说明文案
- “基础 / 高级”折叠
- 切换 `processing.path` 前提示将隐藏不相关参数，但不会立刻丢值

## 8. 线框图

### 8.1 主工作台

```text
+------------------------------------------------------------------------------------------------------------------+
| 配置编辑器                                          当前文件: config_公共服务满意度.yaml                         |
| 状态: 已加载 / 未保存变更                                                         [校验] [预览 YAML] [关闭]    |
+------------------+----------------------------------------------------------------+---------------------------+
| 配置分组         | 当前分组表单                                                   | 校验 / 摘要 / 预览        |
|------------------|----------------------------------------------------------------|---------------------------|
| 项目             | 项目根目录   [ /path/to/project                         ][浏览] | 错误 0                    |
| 写作             | 投标主体名称 [ 杭州菲尔德咨询                             ]      | 警告 2                    |
| 处理路径         | 大纲文件     [ ./投标大纲.md                              ][浏览] |                           |
| 模型             | 采购需求文件 [ ./采购需求.md                              ][浏览] | 当前摘要                  |
| 运行             | 评分标准文件 [ ./评分标准.md                              ][浏览] | - processing=legacy_rule  |
|                 | 输出目录     [ ./output                                   ][浏览] | - trace=enabled           |
|                 |                                                                | - debug_dump=true         |
|                 |                                                                |                           |
|                 |                                                                | YAML 预览                 |
|                 |                                                                | project:                  |
|                 |                                                                |   bidder_name: ...        |
+------------------+----------------------------------------------------------------+---------------------------+
| [恢复加载值] [恢复默认值]                                                         [另存为] [保存]              |
+------------------------------------------------------------------------------------------------------------------+
```

### 8.2 `处理路径` 页面

```text
+------------------------------------------------------------------------------------------------------------------+
| 处理路径                                                                                                         |
| 业务链路:   ( ) full_context      (x) legacy_rule      ( ) hybrid_extract                                        |
| 说明: legacy_rule 会对采购需求和评分标准做章节级规则提炼。                                                       |
+------------------------------------------------------------------------------------------------------------------+
| 公共上下文视图                                                                                                   |
| [x] 包含祖先标题        [x] 包含同级标题        同级标题上限 [ 8 ]                                                |
+------------------------------------------------------------------------------------------------------------------+
| legacy_rule 参数                                                                                                 |
| 评分最多保留 [ 4 ] 行      需求最多摘录 [ 4 ] 条      单条最大字符 [ 220 ]                                        |
| [x] 启用 requirement brief                                                                                       |
+------------------------------------------------------------------------------------------------------------------+
| 高级说明                                                                                                         |
| - 切到 full_context 后，本页参数不再生效                                                                         |
| - 切到 hybrid_extract 后，将显示 retrieval / verify 高级参数                                                     |
+------------------------------------------------------------------------------------------------------------------+
```

### 8.3 `模型` 页面中的环境状态卡片

```text
+--------------------------------------------------------------------------------------------------------------+
| 模型参数                                                                                                     |
| 主模型 model [ gpt-5.4-mini ]  temperature [ 0.7 ]  max_tokens [ 8000 ]                                     |
| 辅助模型 model [ gpt-5.4-mini ]  temperature [ 0.2 ]  max_tokens [ 1200 ]                                   |
| 向量模型 model [ text-embedding-3-small ]  batch_size [ 64 ]                                                 |
+--------------------------------------------------------------------------------------------------------------+
| 环境状态                                                                                                     |
| 主模型连接       已检测到 `.env.local` 配置                                                                   |
| 辅助模型连接     未检测到 `.env.local` 配置                                                                   |
| embedding 连接   已检测到 `.env.local` 配置                                                                   |
| 说明：API Key / Base URL 不在此处编辑，避免把环境级配置写入项目 YAML。                                        |
+--------------------------------------------------------------------------------------------------------------+
```

## 9. 分阶段实现建议

### Phase 1

- 新增 `编辑配置` 入口
- 完成 editor shell 和 canonical view model
- 完成 `项目 / 写作 / 处理路径 / 运行` 基础表单

### Phase 2

- 完成 `模型` 页面
- 接入右侧校验面板
- 接入 YAML 预览和 `另存为`

### Phase 3

- 补齐 legacy 配置加载和标准化保存
- 加入 `.bak` 备份
- 补齐 GUI 测试和配置保存测试

## 10. 当前推荐结论

如果按“投入产出比”排序，最推荐的首版是：

1. 新增一个大号 `Toplevel` 配置编辑器，而不是继续堆小弹窗
2. 用 canonical schema 做唯一编辑模型
3. 把 `processing.path` 做成主开关
4. secrets 只显示状态，不进入 YAML
5. 右侧固定提供校验和 YAML 预览

这样既贴合当前 Tkinter 应用形态，也能把现在已经整理好的配置结构真正变成可操作的用户界面。

## 11. 当前实现状态

截至 `2026-04-03`，首版配置编辑器已经落地：

- 主窗口工具栏已新增 `编辑配置`
- 文件菜单已新增 `编辑当前配置...`
- 已实现大号 `Toplevel` 配置编辑器
- 已支持按 `project / writing / processing / models / runtime` 分组编辑
- 已支持主要字段的悬停 tip，帮助用户理解参数含义和修改时机
- 已支持右侧连接状态、校验结果、摘要和 YAML 预览
- 已支持 `保存` 与 `另存为`
- 已支持保存后对当前配置自动重载，或在另存为后选择切换
- 已支持 legacy 配置加载、canonical schema 标准化导出和部分兼容字段保留
- 已与主窗口共享 GUI 主题，并会随屏幕 DPI / 分辨率自动调大默认字号
- `processing.path` 当前已提供 `auto / full_context` 两个可视化入口；`full_context` 会恢复全文直送链路所需的配置项展示
- `full_context` 下已支持“章节写作计划”开关和长度上限配置

首版与理想方案的差异：

- `hard_constraints` / `extra_rules` 当前采用“每行一条”的文本编辑方式，尚未做成带增删排序按钮的列表控件
- `hybrid_extract` 高级参数当前直接展开在同页中，尚未单独做折叠交互
- `legacy_rule / hybrid_extract` 仍未恢复为完整可视化编辑路径，当前更适合继续手工维护 YAML
- YAML 注释和原字段顺序仍不会被保留，保存后会转为标准化结构
