# 章节正文扩写实现机制

## 目的

本文面向维护者，说明当前代码库中“扩展投标章节正文”的实际实现机制，包括：

- 从大纲选择章节到发起模型请求的调用链
- prompt 的装配顺序和约束来源
- 章节级上下文裁剪的规则
- 流式生成、后处理、保存与 trace 落盘方式
- 当前实现的边界与维护注意事项

## 总体链路

当前章节扩写链路可概括为：

1. `Config` 加载配置、环境变量和输入资源
2. `OutlineParser` 解析 Markdown 大纲，构建 `HeadingNode` 树
3. GUI 选择叶子章节，收集附加要求、目标篇幅基准值、Mermaid 图示上限，以及可选的事实卡片选择；本章事实只通过 `fact_card_context` 注入
4. `AIWriter.prepare_generation()` 装配 prompt、请求参数和 trace 会话
5. `AIWriter.expand_raw()` 调用 OpenAI 兼容接口生成正文
6. GUI 在生成结束后调用 `AIWriter.finalize_generation()` 做轻量后处理
7. `FileSaver.save()` 将章节正文保存为本地 Markdown 文件

关键入口文件：

- `bid_writer/gui.py`
- `bid_writer/ai_writer.py`
- `bid_writer/fact_card_store.py`
- `bid_writer/fact_card_extractor.py`
- `bid_writer/chapter_fact_extractor.py`
- `bid_writer/chapter_fact_store.py`
- `bid_writer/context_pruner.py`
- `bid_writer/file_saver.py`
- `bid_writer/generation_trace.py`

## 一、大纲解析与章节选择

### 1.1 大纲解析

`OutlineParser.parse()` 会扫描 Markdown 标题行，支持 `#` 到 `######`，并为每个标题构建 `HeadingNode`：

- `level`: 标题层级
- `title`: 标题文本
- `full_path`: 从根到当前节点的完整路径
- `line_number`: 原始行号
- `parent` / `children`: 树关系

实现位置：

- `bid_writer/outline_parser.py`

### 1.2 可扩写章节的判定

当前系统不是按“固定四级标题”写死扩写对象，而是以叶子节点为准。`get_deepest_headings()` 会返回所有没有子节点的标题：

- 如果某一支有更深层级，则扩写最深叶子
- 如果二级标题下没有三级，则该二级也可成为扩写目标
- 如果一级标题本身没有子标题，也可直接扩写

这意味着“章节正文扩写”的最小单位是当前大纲树中的叶子节点。

### 1.3 GUI 侧的选择与批量执行

GUI 中批量生成的主要逻辑位于：

- `BidWriterGUI.batch_generate()`
- `BidWriterGUI._do_batch_generate()`
- `BidWriterGUI._generate_into_workspace()`

行为特点：

- 先获取选中的叶子节点
- 单章模式下，“附加扩写要求”只承载用户手工输入
- 单章节模式下，可在生成参数弹窗中调整事实卡片引用关系；全局卡片排在最前且默认勾选，局部卡片按本章节已保存引用关系回填；强制/参考由卡片本体 `enforcement` 决定
- 单章节生成参数弹窗中的“保存事实卡片引用关系”只保存当前选择并保持窗口打开；“开始扩写”会先保存当前引用关系，再直接进入扩写流程
- 批量模式下，不提供整批共用的临时事实卡片选择；若启用事实卡片功能，会默认加入 active 全局卡片、排除各章节已保存的全局取消项，并读取各章节已保存的局部事实卡片引用关系
- 批量模式逐章执行
- 生成内容在主窗口右侧正文工作区实时显示，完成后自动保存
- 章节树叶子节点右键菜单提供“生成所选”入口，复用与顶部按钮相同的批量生成流程；若已多选并在其中一个章节上右键，会保留当前多选范围

从 2026-04-14 起，扩写过程中的用户可见反馈进一步收紧为：

- 在正文开始返回前，右侧工作区的状态文案会依次显示“准备扩写请求”“分析章节上下文”“整理项目背景”“生成章节写作计划”“请求大模型/等待首批输出”等阶段
- 若模型在正文首批内容返回前失败，右侧工作区会直接替换为失败说明，明确指出“当前章节尚未开始输出正文”以及失败阶段、错误判断和排查建议
- 若模型在流式输出过程中中断，已返回的正文会保留，工作区尾部会追加“生成中断提示”
- 单章生成失败会立即弹出错误框；批量生成失败则在工作区保留最近一次失败详情，并在批量结束后给出集中告警

### 1.4 事实卡片一致性

章节间一致性现在由事实卡片机制负责：

- 全局事实卡片自动参与启用事实卡片模式的扩写
- 局部事实卡片可按章节保存默认选择，也可在单章生成前手动调整
- 强制事实卡片会在 prompt 中作为必须遵守的硬约束
- 参考事实卡片只作为可引用信息，不强制覆盖章节边界
- 旧的章节关系与摘要缓存功能已下线，生成主链路不再读取 `.bid_writer/chapter_dependencies.json` 或 `.bid_writer/chapter_summaries.json`

## 二、配置如何影响章节扩写

### 2.1 配置来源

`Config` 同时支持：

- `.env` / `.env.local`
- YAML 中的 `inputs.*`
- YAML 根级兼容字段，如 `outline_file`、`bid_requirements`、`scoring_criteria`

兼容逻辑依赖：

- `_get_first_defined(...)`
- `_get_text_or_file(...)`
- `_extract_inline_file_path(...)`

也就是说，维护时不能假设所有项目都只使用一种配置形态。

### 2.2 与扩写直接相关的配置

章节扩写主要受以下配置影响：

- `writing.target_words.default`
- `generation.stream`
- `generation.stream_idle_timeout_seconds`
- `prompt.output_format`
- `prompt.first_line_template`
- `prompt.allow_markdown_headings`
- `prompt.allow_english_terms`
- `prompt.bidder_name`
- `prompt.max_tables_per_section`
- `prompt.max_mermaid_flowcharts_per_section`
- `prompt.summary_title`
- `prompt.hard_constraints`
- `prompt.extra_rules`
- `context_pruning.*`
- `generation_trace.*`
- `output.*`

### 2.3 当前仓库内的活跃样例配置

`config_公共服务满意度.yaml` 当前体现的运行策略是：

- 开启流式生成
- 开启上下文裁剪
- 开启评分路由
- 开启 `requirement_brief`
- 开启 trace 全量落盘
- 禁止 Markdown 标题
- 禁止不必要英文
- 强制正式层级序号

因此，分析当前行为时应优先以该配置而不是 README 中的保守默认值为参考。

## 三、Prompt 装配机制

## 3.1 system prompt 与 user prompt 分离

章节扩写使用两类 prompt：

- `system prompt`: 全局角色和最高优先级强约束
- `user prompt`: 当前章节任务、结构规则、上下文和人工附加要求

system prompt 由 `AIWriter.build_system_prompt()` 构建，来源包括：

- `Config.role`
- `prompt_bidder_name`
- `prompt_allow_markdown_headings`
- `prompt_allow_english_terms`
- `prompt_hard_constraints`

其中强约束会被放入“最高优先级输出强约束”区块，优先级高于普通风格建议。

### 3.2 user prompt 装配顺序

`AIWriter.build_prompt_result()` 是章节 prompt 的核心装配函数。pruned 分支的默认顺序为：

1. `task_card`
2. `structure_contract`
3. `first_line_rule`，仅在配置了首行模板时出现
4. `scope_reference`
5. `project_background`，若存在
6. 若有裁剪上下文：
   - `scoring_focus`
   - `requirement_brief` 或 `requirement_points`
7. 若存在可用事实卡片，则为 `fact_card_context`
8. 若没有裁剪上下文：
   - `bid_requirements`
   - `scoring_criteria`
9. `additional_requirements`

在 `full_context` 分支中，会为了提高跨章节遍历时的 prompt cache 命中率，改成“稳定前缀在前、章节动态段落在后”：

1. `structure_contract`
2. `project_background`，若存在
3. `bid_requirements`
4. `scoring_criteria`
5. `task_card`
6. `first_line_rule`，若存在
7. `scope_reference`
8. 若存在可用事实卡片，则为 `fact_card_context`
9. `additional_requirements`

这里不会把 `scope_reference` 放进共享前缀，因为它包含当前标题、上级标题和同级标题，属于章节动态信息；若放在最前面，反而会降低跨 h3/h4 调用的前缀复用率。

这套差异化顺序也是 `docs/prompt_contract.md` 中维护的契约。

### 3.3 任务卡内容

`_build_task_card()` 会写入：

- 写作场景
- 当前章节路径
- 本章重点
- 可选的章节写作计划
- 篇幅目标区间
- 输出方式
- 结构要求
- 表格控制
- 可选的流程图控制
- 写作依据

其中：

- “本章重点”并不是简单使用标题原文，而是优先来自裁剪后的焦点词
- 当 `processing.path = full_context` 且开启 `processing.full_context.chapter_writing_plan.enabled` 时，会先调用章节写作计划生成器生成简短的“章节写作计划”，再把它插入任务卡
- 该生成器会优先复用正文扩写所使用的 `system prompt` 与 full-context 稳定前缀；章节边界信息会作为后缀单独追加，以兼顾 cache 命中率和章节边界表达
- 当 `max_mermaid_flowcharts_per_section` 的配置值或运行时 override 值大于 `0` 时，任务卡会额外插入“流程图控制”一行；值为 `0` 时不会提及 Mermaid
- 该提示不再把图类型固定为 `flowchart TD`，模型可以按内容需要选择合适的 Mermaid 图类型

### 3.4 结构硬约束

`_build_structure_contract_section()` 会显式要求：

- 正文不要写成无序号散文
- 至少出现一个正式层级序号 `一、`
- 若存在多个板块、多个自然段、表格、清单、流程、机制或并列措施，必须继续下钻到 `（一）`、`1.`、`（1）`
- 序号后若带标题，该行只写“序号 + 标题”，正文另起

这部分与 system prompt 中的强约束一起构成双层约束：一层在 system，一层在 user。

### 3.5 首行规则与额外规则

- `prompt.first_line_template` 非空时，模型被要求固定首行输出
- `prompt.extra_rules` 不再单独成段，而是追加到 `## 结构输出硬要求` 的末尾

这两项都属于 user prompt 的结构补充，不属于 system 级约束。

### 3.6 事实卡片如何进入 prompt

- 全局卡片：`active=true` 且 `scope=global` 时，在生成参数窗口中默认勾选并排在列表最前面；用户可按章节取消，取消状态会保存到该章节事实卡片引用关系的 `selections`
- 局部卡片：`scope=local` 时，只在单章节手动选择或章节已保存引用关系命中时进入 prompt
- 章节引用状态：保存事实卡片引用关系时会同时保存 `should_reference`，用于区分“本章要引用但暂无可用卡片”和“本章不引用事实卡片”
- 强制/参考：由卡片本体 `enforcement` 决定，生成参数弹窗不再为每个章节单独设置用途
- 批量模式：先读取各章节已保存的 `should_reference`；若本章明确为 `false` 则不注入事实卡片，否则默认加入全局卡片、排除各章节已保存的全局取消项，并读取各章节已保存的局部事实卡片引用关系
- 事实卡片是投标方事实的唯一 prompt 注入口；若事实卡片模式开启但本章没有任何可用卡片，则不注入投标方事实上下文
- 事实卡片提炼和 prompt 渲染都会去除“本章节”“本文”“上述内容”等来源章节元话语，避免旧卡片或模型输出把章节总结句式带入正文
- 若同一次扩写中存在 `strong/strong` 冲突，生成会在调用模型前阻断

维护影响：

- facts 是否成功进入 prompt，优先查看 trace 中的 `prompt_sections.fact_card_context`
- 若 trace 中没有 `prompt_sections.fact_card_context`，表示本次没有向模型注入投标方事实
- 若要排查事实卡片来源，优先查看配置 YAML 中的 `fact_cards.cards` 与 `fact_cards.chapter_defaults`

### 3.6.1 章节事实提炼交互

“提炼当前章节事实卡片”入口现在使用专用工作台，而不是单行输入框：

- 打开后先展示“提炼要求”多行输入框，默认要求以类似网页 placeholder 的浅色提示展示；用户不填写时使用默认要求，填写后以用户内容为准
- 若该章节已有 `chapter_extract` 事实卡片，入口文案会显示为“查看/更新事实卡片”，弹窗会默认加载上次卡片草稿和上次提炼要求
- 对已有提炼结果，弹窗会根据章节正文文件更新时间提示“可直接复用”或“建议重新提炼”；用户编辑后只有点击“保存卡片”才会替换原结果
- 用户点击“提炼草稿”后，后台线程会读取当前章节已保存正文并调用事实卡片提炼器，避免阻塞弹窗交互
- 每次从一个章节只保留当前 1 张核心事实卡片草稿；草稿会进入下半区编辑器，用户可继续修改卡片名称、分类、内容，内容输入框会随窗口高度自动伸缩，删除前需二次确认；该工作台不提供“新增卡片”
- 手工新增事实卡片位于主窗口“章节”菜单中的独立“新增事实卡片...”弹窗，内容输入框同样随窗口高度自动伸缩，保存后加入事实卡片库
- 事实卡片工作台、草稿确认、新增和卡片库窗口都会按当前屏幕约束初始尺寸，低分辨率屏幕下避免固定大窗口超出显示区域
- 若对结果不满意，可修改上方提炼要求后点击“重新提炼”，系统会用最新要求重新生成草稿
- 若未生成可保存草稿，弹窗会展示更具体的诊断信息，包括正文文件/章节正文缺失、模型接口异常、模型空响应、非合法 JSON、空数组或字段缺失等原因，并尽量附带原始返回截断内容
- 只有在当前提炼要求已经实际执行过一次提炼后，才允许保存；保存时会替换该章节旧的 `chapter_extract` 卡片

## 四、章节级上下文裁剪

## 4.1 裁剪是否启用

`AIWriter.build_prompt_result()` 会先检查 `context_pruning_enabled`。如果开启，则调用：

- `ChapterContextPruner.build_context(heading)`

如果裁剪失败，代码会静默回退到 full-context 模式，不会阻断整次生成。

### 4.2 裁剪产物结构

裁剪结果封装在 `ChapterContext` 中，主要字段包括：

- `local_outline`
- `response_labels`
- `chapter_focus_terms`
- `match_keywords`
- `scoring_items`
- `scoring_candidates`
- `requirement_seed`
- `requirement_blocks`
- `requirement_brief`

### 4.3 局部大纲

`_build_local_outline()` 会根据配置保留：

- 当前节点的祖先链
- 当前节点的同级标题

同级标题数量可通过 `context_pruning.local_outline.max_siblings` 限制。这样做的目标不是给模型完整大纲，而是帮助模型理解“本章边界”和“哪些内容属于兄弟章节而不应提前展开”。

### 4.4 响应标签与关键词

`_extract_response_labels()` 会从标题链中提取形如：

- `响应: xxx`
- `对应评分标准: xxx`

的标签。

之后 `_build_match_keywords()` 会综合：

- 响应标签
- 当前章节标题
- 祖先标题

生成一组匹配关键词，用于评分项路由和需求块筛选。

### 4.5 评分项路由

评分项路由依赖 `scoring_criteria` 中的 Markdown 表格：

1. `_parse_markdown_tables()` 解析表格
2. `_parse_scoring_rows()` 找到“子项/评分项/评审因素”和“评审标准”等列
3. `_score_criterion()` 根据响应标签、关键词和最长公共子串计算分数
4. `_score_focus_terms()` 用章节自身焦点词加权
5. `_route_scoring_items()` 取 Top N 项作为 `scoring_items`

维护注意：

- 如果评分标准不是 Markdown 表格，当前路由能力会明显下降
- 表头命名虽然有别名兼容，但仍依赖表格结构可被解析

### 4.6 采购需求块筛选

需求裁剪流程如下：

1. `_split_requirement_blocks()` 按空行切块
2. `_merge_heading_blocks()` 尝试把纯标题块和其后的正文块合并
3. `_build_requirement_seed()` 对每个需求块按关键词、响应标签、焦点词打分
4. 高分块进入 `selected`
5. `_summarize_requirement_blocks()` 将选中的原文块压缩成要点摘要

这里有两个产物：

- `requirement_seed`: 归纳后的要点列表
- `requirement_blocks`: 命中的原始块及其得分、是否被选中

### 4.7 requirement_brief 的真实实现

当前 `requirement_brief` 不是辅助模型生成的摘要，而是从已选中的需求块里抽取原文摘录：

- `_extract_requirement_excerpt()`
- `_build_requirement_brief()`

它会：

- 过滤低价值块
- 尝试保留原文语义
- 最多摘取 4 条
- 避免重复

因此当前的 `requirements_brief` 更接近“原文摘录”而不是“智能总结”。

但在最终发给模型的 `user prompt` 中，这部分仍以“需求要点”标题呈现，以保持和任务卡里的“根据下方评分关注和需求要点组织内容”一致，避免前后指代漂移。

### 4.8 调试输出

当 `context_pruning.debug_dump` 开启时，`dump_debug()` 会在输出目录下写入 `_context_pruning_debug` 调试文件，便于维护者检查：

- 命中的评分项
- 需求 seed
- 需求原文摘录
- 局部大纲
- prompt 长度

## 五、模型请求与流式生成

## 5.1 请求准备

`AIWriter.prepare_generation()` 会完成三件事：

1. 调用 `build_prompt_result()` 组装 prompt
2. 调用 `build_system_prompt()` 组装 system prompt
3. 调用 `_build_request_options()` 生成模型请求参数

GUI 主链路会把“生成参数设置”弹窗中的 Mermaid 图示上限作为运行时 override 传给 `prepare_generation()`；首次打开时该值默认是 `0`，之后会优先回填用户上次点击“开始扩写”时确认的 Mermaid 图示上限，并直接覆盖配置文件中的同名参数。目标篇幅基准值也会按同样方式记住最近一次确认值。

最终消息格式是标准 Chat Completions 结构：

- `{"role": "system", "content": system_prompt}`
- `{"role": "user", "content": user_prompt}`

### 5.2 trace 会话创建

如果开启 `generation_trace`，`prepare_generation()` 还会创建 `GenerationTraceSession`，在真正发请求前就落盘初始产物：

- `manifest.json`
- `01_heading.json`
- `02_context_assembly.json`
- `03_prompt_system.md`
- `04_prompt_user.md`
- `05_request_options.json`

### 5.3 实际模型调用

正文生成通过 OpenAI Python SDK 发起：

- 流式：`self.client.chat.completions.create(**request_options)`
- 同步：同样使用 `chat.completions.create(...)`

虽然文件头注释仍写“Gemini API”，但实际实现已经切换为 OpenAI 兼容接口。

### 5.4 流式读取机制

流式实现位于 `_stream_expand_raw()`，关键点：

- 单独启动 reader 线程遍历响应流
- 每收到 token 就放入队列并 `yield`
- 主循环按超时机制等待新 token
- 若最后一个 token 后静默超过 `generation.stream_idle_timeout_seconds`，则主动关闭响应

这套机制的目标是避免模型侧流结束不规范导致 GUI 一直卡在“生成中”。

## 六、GUI 侧的生成与预览

### 6.1 当前 GUI 实际调用路径

GUI 的真实路径不是直接调用 `AIWriter.expand()`，而是：

1. `prepare_generation()`
2. `expand_raw()`
3. 生成完成后再 `finalize_generation()`

这意味着：

- 主窗口右侧正文工作区中实时显示的是原始模型输出
- 后处理发生在流式输出结束后，随后直接覆盖右侧工作区内容
- `AIWriter.expand()` 中自带的“流式后替换 sentinel”机制，当前 GUI 主路径并没有使用到
- GUI 主窗口顶部提供大纲搜索、状态筛选和选择工具；主体采用“左大纲树、右正文工作区”的并列布局，两栏宽度可拖动调整

### 6.2 主窗口正文展示与自动保存

单章生成完成后：

- 先做后处理
- 再直接自动保存到输出目录
- 若用户单选某个章节，右侧工作区会直接回显该章节当前已保存的正文内容
- 正文工作区标题栏会同步显示当前节点已生成正文的字符数；未选中节点时显示 `-`，已选中但尚未生成时显示 `0`

当前 GUI 主路径不再弹出独立预览窗口，也不再提供“修改后重新生成”的单章弹窗交互。

## 七、后处理机制

当前后处理刻意保持轻量，不再做二次大模型格式修复。

### 7.1 投标主体统一

`_normalize_bidder_references()` 会把以下主体自称替换成配置中的 `prompt.bidder_name`：

- `我方`
- `我司`
- `本公司`
- `本单位`

替换时会跳过已知专业术语中的嵌套片段，避免把 `基本单位`、`样本单位`、`标本单位`、`成本单位` 这类固定词组误替换成投标主体名称。

### 7.2 输出问题检测

`_collect_output_issues()` 当前会检测：

- `numbering_transitions`
  - 出现“首先、其次、再次、最后”等段首转承
- `missing_formal_hierarchy`
  - 文本已明显多段分层，但没有正式层级序号
- `markdown_headings`
  - 在禁止 Markdown 标题时仍输出 `#`
- `forbidden_summary`
  - 在 `summary_title` 为空时仍出现“小结/总结”

注意：

- 这些问题当前只会记录在 `postprocess` 和 trace 中
- 不会自动重写正文
- `format_repair_applied` 当前固定为 `False`

## 八、保存机制

## 8.1 文件命名

`FileSaver` 为避免同名章节互相覆盖，会基于 `HeadingNode.full_path` 生成稳定 ID：

- `heading_id = sha1(full_path)[:12]`

最终文件名格式类似：

- `章节标题__abcdef123456.md`

### 8.2 保存内容格式

常规 `save()` 默认会：

- 可选写入 `# 标题`
- 再写入正文内容

因此“模型输出的正文”和“落盘后的 Markdown 文件”不是完全等价的：

- 模型侧被要求“不重复标题”
- 文件侧可能依然包一层 Markdown 标题，便于人工阅读

### 8.3 已生成文件识别

系统识别章节是否已生成时，优先看：

- 文件名中的稳定 ID
- 旧格式文件名
- 旧文件中的 front matter 元数据

这样兼容了旧版本输出。

## 九、trace 与可观测性

### 9.1 trace 记录了什么

`GenerationTraceSession` 记录：

- 当前标题信息
- 请求参数
- system prompt
- user prompt
- prompt contract 摘要层
- raw `prompt_sections`
- pruned context 或 full context 统计
- `fact_card_mode` 与 `fact_card_selection`；章节级是否引用事实卡片由配置中的 `fact_cards.chapter_defaults.*.should_reference` 保存
- 最终输出
- 后处理 issue

### 9.2 Prompt Contract 摘要层

当前 trace 里除了原始 `prompt_sections`，还增加了维护者摘要视图 `prompt_contract_blocks`，固定包含八个 block：

1. `system_constraints`
2. `chapter_task`
3. `structure_rules`
4. `chapter_scope`
5. `project_background`
6. `fact_card_context`
7. `requirement_context`
8. `scoring_context`

这层不是替代原始 prompt sections，而是为了让维护者更快看懂“一次章节扩写到底喂给了模型什么”。

### 9.3 维护者排查顺序

当前推荐排查顺序仍然是：

1. 先看 `07_summary.md`
2. 再看 `04_prompt_user.md`
3. 再看 `02_context_assembly.json`
4. 最后看 `06_generation_output.md`

## 十、当前实现的边界

### 10.1 裁剪是规则驱动，不是智能规划

`context_pruner.py` 的基础裁剪仍然主要由规则和检索驱动；只有启用候选校验等辅助链路时，才会使用 `.env.local` 中的 `BID_WRITER_PRUNING_*`。因此当前裁剪效果高度依赖：

- 标题命名质量
- 评分标准结构
- 需求文档分段质量

### 10.2 评分路由依赖 Markdown 表格

如果评分标准改成纯段落文本，`_parse_scoring_rows()` 很可能拿不到有效评分项，`scoring_focus` 将退化或为空。

### 10.3 后处理只做检测，不做纠正

当前系统能发现：

- 层级不规范
- Markdown 标题违规
- 总结违规

但不会自动修正。若需要“自动格式修复”，需要重新引入或新增一层修复机制。

### 10.4 GUI 主路径绕过了 `AIWriter.expand()` 的整合封装

这不是 bug，但属于重要实现事实。以后如果修改 `AIWriter.expand()` 的行为，未必会影响 GUI 主链路；真正影响 GUI 的是：

- `prepare_generation()`
- `expand_raw()`
- `finalize_generation()`

## 十一、维护建议

### 11.1 改 prompt 时优先检查三处

- `AIWriter.build_system_prompt()`
- `AIWriter.build_prompt_result()`
- `docs/prompt_contract.md`

如果只改代码、不更新契约文档，后续维护会失真。

### 11.2 改裁剪逻辑时优先检查四处

- `ChapterContext` 字段定义
- `build_context()` 的返回结构
- `GenerationTraceSession._build_context_payload()`
- `_context_pruning_debug` 调试输出格式

否则 trace 和调试文档可能与运行时不一致。

### 11.3 改保存逻辑时注意兼容旧文件

`FileSaver.find_existing_filepath()` 目前兼容：

- 新文件名中的稳定 ID
- 老文件名规则
- front matter 元数据

修改命名规则时，不要直接破坏这三层兼容。

### 11.4 改 GUI 生成流程时注意线程边界

当前设计是：

- 模型调用在后台线程
- UI 更新在主线程
- 通过队列通信

任何直接在后台线程触碰 Tk 控件的改动，都容易引入线程安全问题。

## 十二、核心结论

当前“扩展投标章节正文”的实现，不是一个单点函数，而是一条明确分层的流水线：

- 大纲树决定章节边界
- 配置决定约束与生成策略
- `AIWriter` 负责 prompt 装配和模型调用
- `ChapterContextPruner` 负责章节级上下文压缩
- GUI 负责交互、正文展示与批量调度
- `FileSaver` 负责稳定落盘
- `GenerationTraceSession` 负责全过程可观测性

从维护角度看，最重要的不是单独看模型调用，而是把这几层一起理解，否则很容易误判“为什么某一章会生成成这样”。
