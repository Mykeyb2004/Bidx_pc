# H2 级项目背景提炼优化方案

## 1. 背景与问题

早期项目背景由 `bid_writer/project_background.py` 中的 `ProjectBackgroundGenerator` 负责：它读取完整采购需求，生成一次全局项目背景摘要，并按源文与 `max_chars` 缓存。当前实现已硬删除这条全局背景链路，auto 模式只保留 H2 级项目背景。

这套机制能减少直接注入完整采购需求的压力，但在 `processing.path: auto` 下存在明显问题：

- `auto` 已经是章节级上下文裁剪链路，核心目标是让当前章节只接收相关的需求、评分和边界信息。
- 早期全局项目背景会进入每个章节 prompt，容易把与当前 H2 无关的项目范围、交付物或质量要求带入章节扩写。
- 如果采购需求很长，旧全局摘要为了覆盖全面会变得抽象，反而弱化当前 H2 下章节扩写所需的项目情境。
- 直接减少旧全局背景长度又有风险：可能丢掉当前 H2 下必须保留的关键业务背景。

因此，本优化目标不是简单压缩项目背景，而是把“项目背景”从全局摘要调整为 `auto` 模式下的 H2 级、证据驱动、可追溯背景材料。当前实现默认使用采购需求原文摘录，只有配置 `content_mode=summary` 时才生成模型摘要。

## 2. 目标

### 2.1 功能目标

- 在 `processing.path: auto` 下，根据当前叶子章节所属的 H2 标题，为该 H2 生成专属项目背景。
- 在批量扩写开始前，一次性遍历大纲中所有 H2，生成并缓存各 H2 的项目背景与证据元数据。
- 扩写具体章节时，不再临时总结全局背景，而是按当前章节所属 H2 读取对应缓存并注入。
- H2 项目背景只围绕该 H2 子树负责的写作范围，避免把全项目背景无差别注入所有章节。
- 背景材料必须基于采购需求原文检索结果生成，默认直接使用原文摘录，不能凭模型自由概括。
- 每个 H2 背景可复用缓存，同一 H2 下多个 H3/H4/H5 章节共享一份 H2 背景。
- 保留当前章节已有的 `评分关注`、`需求要点`、`章节边界参考`，H2 背景不替代章节级需求摘录。

### 2.2 质量目标

- 提高章节扩写针对性：背景信息与当前 H2 的业务主题一致。
- 降低 prompt 噪声：不再把全项目背景重复注入到每个 auto 章节。
- 降低信息丢失风险：摘要之外保留原文证据 ID、片段与 trace。
- 支持人工审计：可从 trace 看到 H2 背景的摘要、命中原文和缓存来源。
- 保持模式语义清晰：`full_context` 继续强调全量参考；`auto` 强调章节级裁剪与提炼。

## 3. 非目标

- 不改变 `full_context` 的全文注入语义。
- 不把评分标准直接混入“项目背景”正文。
- 不移除 `auto` 下已有的章节需求摘录和评分项分类。
- 不在首版引入跨 H2 的复杂知识图谱或多轮摘要树。
- 不用 H2 背景替代事实卡片；事实卡片仍负责投标方事实一致性。

## 4. 现有链路判断

当前代码中与本方案直接相关的事实：

- `Config.processing_path` 已支持 `auto`、`full_context`、`legacy_rule`、`hybrid_extract`。
- `Config.context_pruning_enabled` 在新 schema 下对非 `full_context` 返回 `true`。
- `ChapterContextPruner.build_context()` 在 `processing_path == "auto"` 时进入 `_build_context_auto()`。
- `auto` 目前执行：
  - hybrid 检索评分项；
  - 对评分项做 H2/H4 相关分类；
  - 对采购需求做 hybrid 检索，并直接拼接原文作为 `requirement_seed`；
  - 不生成 `requirement_brief`。
- `AIWriter.build_prompt_result()` 在 `pruned_context is not None` 时会按顺序注入：
  - `task_card`
  - `structure_contract`
  - `scope_reference`
  - `project_background`
  - `scoring_focus`
  - `requirement_brief` 或 `requirement_points`
  - `fact_card_context`

因此，H2 背景最适合接在 `auto` 的上下文构建链路中，并通过原有 `project_background` prompt section 注入。

## 5. 推荐方案

### 5.1 总体策略

在 `auto` 模式下新增 H2 级项目背景生成器，并把它设计为“扩写前预生成、扩写时读取注入”的两阶段链路：

```text
批量扩写前
  -> 遍历大纲全部 H2
  -> 为每个 H2 构建 H2 query
  -> 从采购需求中检索相关原文块
  -> 默认格式化为 H2 背景原文摘录；summary 模式才用辅助模型生成 H2 背景摘要
  -> 缓存摘要 + 证据元数据

章节扩写时
  -> 找到当前章节所属 H2
  -> 读取该 H2 的背景缓存
  -> 注入当前章节 prompt 的 `## 项目背景`
```

`full_context` 模式直接注入完整采购需求，并在 `processing.scoring.enabled=true` 时注入评分标准全文，不再调用项目背景生成器。

单章节手动扩写时，如果对应 H2 缓存不存在，可按配置选择“先为该 H2 补生成一次”或“回退到原文片段/空背景”。批量扩写路径应默认先执行全量 H2 背景预生成，避免每个叶子章节扩写时重复触发摘要调用。

### 5.2 核心模块

建议新增模块：

- `bid_writer/h2_project_background.py`

建议新增类：

- `H2ProjectBackgroundGenerator`

主要职责：

- 从已解析大纲中收集全部 H2 节点。
- 在批量扩写前执行 `precompute_all(outline_root)`，为所有 H2 写入缓存。
- 查找当前 heading 所属 H2。
- 构建 H2 级检索 query。
- 调用既有 `SourceUnitParser.parse_requirements()` 切分采购需求。
- 调用既有 `HybridRetriever` 检索 H2 相关原文块。
- 可选调用既有 verifier 只返回 `unit_id`，程序回填原文。
- 默认格式化 H2 背景原文摘录；summary 模式调用辅助 LLM 生成 H2 背景摘要。
- 写入与读取 H2 背景缓存。
- 在章节扩写时执行 `get_for_heading(heading)`，只负责读取对应 H2 缓存，必要时按 fallback 策略补救。
- 返回可追溯结果对象，而不是只返回字符串。

建议数据结构：

```python
@dataclass
class H2ProjectBackgroundResult:
    h2_title: str
    h2_full_path: str
    summary: str
    evidence_unit_ids: list[str]
    evidence_blocks: list[str]
    source_hash: str
    cache_status: str  # hit / miss / disabled / failed / fallback
    fallback_reason: str = ""
```

建议额外提供批处理结果：

```python
@dataclass
class H2ProjectBackgroundPrecomputeReport:
    total_h2: int
    generated: int
    cache_hits: int
    failed: int
    skipped: int
    results: list[H2ProjectBackgroundResult]
```

### 5.3 H2 定位规则

复用 `ChapterContextPruner._find_h2_ancestor()` 的语义，或抽出为共享 helper：

- 当前节点本身是 H2：使用当前节点。
- 当前节点是 H3/H4/H5：向上找到最近的 H2。
- 找不到 H2：回退到当前节点父节点；仍没有则使用当前节点。

H2 背景缓存 key 必须使用 `h2.full_path`，而不是只用 `h2.title`，避免不同章节下同名 H2 混淆。

### 5.4 H2 Query 构建

H2 query 应同时包含结构信号和语义信号：

- H2 标题。
- H2 下直接子标题与叶子标题，最多保留配置数量。
- 当前章节完整路径。
- 当前章节与 H2 能提取出的 `response_labels`。
- 当前章节与 H2 的关键词变体。
- 已命中的评分项标题可作为 query 辅助信号，但不进入背景正文。

推荐 query 形态：

```text
H2 标题：{h2.title}
H2 路径：{h2.full_path}
H2 子树标题：{h2_child_titles}
当前章节路径：{heading.full_path}
响应标签：{response_labels}
重点词：{focus_terms}
```

### 5.5 原文证据检索

首版优先复用现有 `auto` 检索能力：

- `SourceUnitParser.parse_requirements()`：把采购需求解析为 `SourceUnit`。
- `HybridRetriever.retrieve()`：做 lexical 检索，并在配置开启时接入 vector。
- `HybridRetriever.select_final()`：按 `top_k` 和 `min_fused_score` 取最终候选。
- 若 `verify_enabled=true`，继续使用 `LLMVerifier.verify()` 只返回 `unit_id`，由程序回填原文。

建议新增配置：

```yaml
processing:
  project_background:
    enabled: true
    max_chars: 800
    h2:
      precompute_on_batch: true
      generate_missing_on_single: true
      max_evidence_blocks: 6
      max_evidence_chars: 2400
      content_mode: excerpts
      min_evidence_blocks: 2
      fallback: "raw_evidence"   # raw_evidence / empty
      cache_dir: "./caches/project_background_h2"
```

说明：

- `processing.project_background.scope` 已废弃；auto 下固定使用 H2 背景，旧值 `global` 会被运行时拒绝。
- `precompute_on_batch` 表示批量扩写前先一次性生成所有 H2 背景缓存，建议默认开启。
- `generate_missing_on_single` 表示单章节扩写时若 H2 缓存缺失，是否先补生成当前 H2 背景；建议默认开启。
- `include_evidence_in_prompt` 已废弃；默认 `content_mode=excerpts` 时项目背景本身就是原文摘录，evidence 同时进入 trace。
- 当 H2 摘要质量不稳定时，可临时开启 evidence 注入做人工对比。

### 5.6 摘要生成规则

H2 背景摘要由辅助模型生成，必须使用低温度和严格提示词。输入只包含：

- H2 标题与路径。
- H2 子树标题。
- 当前采购需求命中的证据片段。
- 输出长度上限。

推荐 prompt 要求：

```text
请仅基于给定采购需求原文片段，提炼当前 H2 章节的项目背景。

必须覆盖：
1. 与本 H2 相关的项目目标或问题来源
2. 与本 H2 相关的任务范围
3. 与本 H2 相关的主要交付物或成果
4. 与本 H2 相关的质量、合规、时限或验收要求
5. 本 H2 下章节扩写时不可遗漏的关键信息

限制：
- 不得引入原文没有的信息。
- 不要写成评分响应清单。
- 不要覆盖其他 H2 的职责范围。
- 如果证据片段不足以支持某项内容，省略该项，不要编造。
- 直接输出摘要正文，不要输出引导语。
```

建议输出为短段落加少量条目，不使用 Markdown 标题。实际注入 prompt 时仍由 `AIWriter._build_project_background_section()` 包装成：

```text
## 项目背景
{summary}
```

### 5.7 Prompt 注入位置

`auto` 分支中保持现有位置：

```text
## 章节边界参考
## 项目背景
## 评分关注
## 需求要点
```

理由：

- 章节边界先限定写作范围。
- H2 背景提供章级项目情境。
- 评分关注和需求要点提供当前叶子章节的硬响应内容。
- H2 背景不应放在评分和需求之后，否则容易被模型当作补充材料而非章级语境。

### 5.8 回退策略

H2 背景生成失败时不能阻断章节正文生成。

推荐回退顺序：

1. 批量扩写前预生成失败时，记录该 H2 失败原因，但不中断整个批量任务，除非后续配置增加 `fail_fast`。
2. 章节扩写时优先读取当前 H2 的有效缓存。
3. 如果缓存中已有同源文 hash 的旧摘要，使用缓存并标记 `cache_status=stale_fallback`。
4. 若单章节扩写且 `generate_missing_on_single=true`，先为当前 H2 补生成一次。
5. 若配置 `fallback=raw_evidence`，把命中的 1-3 个采购需求片段作为短背景依据注入。
6. 若配置 `fallback=empty`，不注入项目背景。

默认建议 `fallback=raw_evidence`，避免恢复无差别全局摘要。

## 6. 防止丢失重要信息的机制

### 6.1 摘要不替代原文摘录

H2 背景只提供章级语境；当前叶子章节的 `需求要点` 仍由 `auto` 的 requirement retrieval 生成。即：

- H2 背景负责“为什么写、围绕什么写”。
- `需求要点` 负责“本章节必须写哪些采购需求”。
- `评分关注` 负责“本章节如何响应评分标准”。

### 6.2 保留证据元数据

每份 H2 背景缓存必须保存：

- H2 标题与完整路径。
- 采购需求源文 hash。
- H2 子树结构 hash。
- evidence unit ids。
- evidence 原文片段。
- summary。
- 生成模型、生成时间、max_chars。

这样即使摘要较短，也能回看它基于哪些原文生成。

### 6.3 使用证据数量下限

如果命中的采购需求原文块少于 `min_evidence_blocks`，不直接生成摘要，应触发回退。

原因：

- 命中太少时，LLM 容易凭章节标题补全背景。
- 对标书场景而言，缺证据比摘要短更危险。

### 6.4 使用原文回填

verifier 只能返回 `unit_id`，程序再回填原文，不允许 verifier 直接改写证据。这与现有 `hybrid_extract` 的设计保持一致。

### 6.5 限制摘要职责边界

摘要 prompt 必须明确：

- 只写当前 H2 负责范围。
- 不覆盖同级 H2。
- 不把评分标准写成背景。
- 不输出“必须覆盖、硬约束”等元语言。

### 6.6 Trace 对比

trace 中必须能同时看到：

- H2 背景材料字符数。
- evidence 数量。
- evidence 原文片段。
- 本章节 `需求要点` 字符数。
- 本章节 `评分关注` 数量。

这样可以人工判断“背景变短后，章节硬信息是否仍在需求/评分区块中保留”。

## 7. 配置与兼容性

### 7.1 配置读取

建议新增或扩展 `Config` 属性：

- `project_background_scope`
- `h2_project_background_enabled`
- `h2_project_background_cache_dir`
- `h2_project_background_precompute_on_batch`
- `h2_project_background_generate_missing_on_single`
- `h2_project_background_max_evidence_blocks`
- `h2_project_background_max_evidence_chars`
- `h2_project_background_content_mode`
- `h2_project_background_min_evidence_blocks`
- `h2_project_background_fallback`

兼容策略：

- 旧配置只有 `processing.project_background.enabled/max_chars` 时，默认保持现有 global 行为，避免突然改变用户结果。
- 新建配置编辑器可默认使用 `scope: h2_auto`，因为当前 GUI 已把 `auto` 作为主要智能模式入口。
- `full_context` 下即使配置了 `scope: h2_auto`，也建议仍走 global 或全文背景，避免破坏 full-context 语义。

### 7.2 文档同步

实现时需要同步维护：

- `docs/config_schema.md`
- `docs/prompt_contract.md`
- `docs/generation_trace.md`
- `docs/extraction_modes_and_config.md`
- `config.example.yaml`
- `config_公共服务满意度_auto.yaml`
- 相关测试夹具

这是仓库现有约定，配置结构相关变更不能只改代码。

## 8. Cache 设计

### 8.1 Cache Key

建议 cache key 输入：

```text
bid_requirements_hash
h2_full_path
h2_subtree_hash
max_chars
max_evidence_blocks
max_evidence_chars
retrieval_config_fingerprint
prompt_version
model
```

其中 `prompt_version` 用于未来调整摘要提示词后自动失效旧缓存。

### 8.2 Cache 文件

建议使用 JSON：

```json
{
  "version": 1,
  "h2_title": "总体服务方案",
  "h2_full_path": "投标文件 > 总体服务方案",
  "source_hash": "...",
  "subtree_hash": "...",
  "summary": "...",
  "evidence_unit_ids": ["req_001", "req_008"],
  "evidence_blocks": ["..."],
  "model": "gpt-5.4",
  "created_at": "2026-04-28T10:00:00+08:00",
  "retrieval": {
    "top_k": 6,
    "min_fused_score": 0.0,
    "vector_enabled": false,
    "verify_enabled": false
  }
}
```

JSON 比纯文本更适合 trace 与人工排查。

### 8.3 预生成时机

批量生成入口应在真正开始逐章节扩写前执行：

```text
MainWindow.batch_generate()
  -> BidWriter.precompute_h2_project_backgrounds()
  -> 逐章节调用 generate_section()
```

或在非 GUI 批量入口中执行同等步骤。预生成完成后，应在 GUI 状态区展示简短结果，例如：

```text
H2 项目背景：共 8 个，命中缓存 3 个，新生成 5 个，失败 0 个
```

单章节扩写入口不强制预生成全部 H2。若当前 H2 缓存不存在，按 `generate_missing_on_single` 和 `fallback` 处理。

## 9. 界面与后台任务设计

H2 背景提炼需要调用大模型，是明显耗时操作。界面上不应把它伪装成普通同步步骤，也不应让 Tk 主线程阻塞等待。推荐把它设计为“项目上下文准备任务”：可观察、可停止、可重试、可审计，并与正文扩写进度分阶段展示。

### 9.1 批量生成前的准备阶段

当用户点击 `生成所选`，且当前配置满足以下条件时：

- `processing.path = auto`
- `processing.project_background.enabled = true`
- `processing.project_background.scope = h2_auto`
- `processing.project_background.h2.precompute_on_batch = true`

批量生成流程应先进入 H2 背景准备阶段：

```text
阶段一：准备 H2 项目背景
  -> 检查全部 H2 缓存状态
  -> 生成缺失或过期 H2 背景
  -> 写入缓存与任务报告

阶段二：生成章节正文
  -> 按所选叶子章节逐章扩写
  -> 扩写时读取所属 H2 背景缓存
```

主窗口状态栏和任务文本应清晰展示当前阶段，例如：

```text
当前任务: 准备 H2 项目背景 3/8：总体服务方案
状态: 正在调用辅助模型...
进度: 3 / 8
```

准备完成后，再切换为原有章节生成状态：

```text
当前任务: 生成章节正文 1/24：质量保障措施
状态: 正在生成章节正文...
进度: 1 / 24
```

这样用户能明确知道“第一章还没开始生成”并不是卡住，而是在进行项目背景准备。

### 9.2 H2 项目背景管理窗口

建议新增独立窗口：`H2 项目背景`。

入口位置：

- 主工具栏：`H2背景`
- 或菜单：`工具 -> H2 项目背景...`

窗口用途：

- 用户可在正式扩写前主动生成或刷新 H2 背景缓存。
- 用户可查看每个 H2 背景的摘要与证据片段。
- 用户可对失败项单独重试。

窗口布局建议：

```text
┌──────────────────────────────────────────────────────────────┐
│ H2 项目背景                                                   │
│ 共 8 个 H2，已缓存 5，需更新 2，失败 1                        │
├──────────────────────────────────────────────────────────────┤
│ H2 标题              状态      证据  字数  更新时间     操作 │
│ 项目理解与工作基础   有效      5     620   10:12       预览 │
│ 总体服务方案         需更新    6     580   09:40       生成 │
│ 质量保障措施         失败      2     -     -           重试 │
├──────────────────────────────────────────────────────────────┤
│ 摘要预览 / 证据片段 / 错误详情                               │
├──────────────────────────────────────────────────────────────┤
│ [生成缺失] [刷新过期] [全部重新生成] [停止] [关闭]            │
└──────────────────────────────────────────────────────────────┘
```

表格列建议：

- `H2 标题`
- `状态`
- `证据片段数`
- `摘要字数`
- `更新时间`
- `操作`

详情区域建议显示：

- H2 完整路径。
- H2 背景材料。
- 命中的采购需求原文片段。
- 生成模型、缓存状态、失败原因。
- `source_hash` / `subtree_hash` 可折叠显示，供排查使用。

### 9.3 任务状态

每个 H2 背景缓存建议使用以下 UI 状态：

| 状态 | 含义 |
|---|---|
| 未生成 | 没有缓存文件 |
| 有效 | 缓存存在，且源文、大纲子树、配置和 prompt version 均匹配 |
| 需更新 | 缓存存在，但采购需求、大纲子树、配置或 prompt version 已变化 |
| 生成中 | 当前正在调用辅助模型生成 |
| 失败 | 本 H2 生成失败，保留错误信息 |
| 已跳过 | 用户停止任务后，该 H2 尚未处理 |

主大纲树中也可以在 H2 行的状态列显示轻量状态：

- `背景有效`
- `背景待生成`
- `背景需更新`
- `背景失败`

叶子章节仍保留正文生成状态，避免把“背景缓存状态”和“正文生成状态”混在一起。

### 9.4 后台线程与队列

H2 背景生成必须在后台线程执行，不能阻塞 Tk 主线程。

推荐沿用现有 `GenerationSession` 的模式：

- 后台线程逐个 H2 调用检索与辅助模型。
- `queue.Queue` 发送状态事件到主线程。
- 主线程通过 `after()` 轮询队列并更新表格、状态栏和进度条。
- 每完成一个 H2 立即写缓存。
- 任务结束后输出 `H2ProjectBackgroundPrecomputeReport`。

事件类型建议：

```text
started(total_h2)
item_started(h2_full_path)
item_cache_hit(h2_full_path)
item_completed(h2_full_path, summary_chars, evidence_count)
item_failed(h2_full_path, error)
item_skipped(h2_full_path)
finished(report)
```

每个 H2 完成后立即落盘，避免任务中途失败、窗口关闭或用户停止时丢失已完成结果。

### 9.5 停止与取消

`停止` 不应强行中断正在进行的大模型 HTTP 请求。更稳妥的语义是：

- 用户点击 `停止` 后，设置 `stop_requested=true`。
- 当前正在处理的 H2 等本次调用返回后正常收尾。
- 后续未开始的 H2 标记为 `已跳过`。
- 已完成的 H2 缓存保留可用。

界面文案建议：

```text
已请求停止，将在当前 H2 完成后停止后续背景生成。
```

### 9.6 批量生成前的确认策略

如果缺失或过期 H2 数量较少，可以自动进入准备阶段。

如果缺失或过期数量较多，例如超过 5 个，建议在批量生成前弹出确认：

```text
需要先准备 8 个 H2 项目背景，可能耗时数分钟。
```

按钮：

- `开始准备`
- `跳过并回退`
- `取消生成`

`跳过并回退` 应按配置的 `fallback` 执行。默认 `fallback=raw_evidence` 时，正文扩写使用命中的采购需求原文片段作为短背景；`empty` 则不注入项目背景。

### 9.7 失败处理

H2 背景准备失败不建议默认中断整个批量扩写。准备阶段结束后，如果存在失败项，弹出汇总确认：

```text
H2 项目背景准备完成：成功 7，失败 1。
失败的 H2 将使用全局背景回退。
```

按钮：

- `继续生成`
- `重试失败项`
- `取消`

如果 `fallback=empty`，文案改为：

```text
失败的 H2 将不注入项目背景。
```

如果未来增加 `fallback=fail_fast`，则失败时直接阻断正文扩写。

### 9.8 单章节生成体验

单章节生成不应默认预生成所有 H2。只检查当前章节所属 H2：

- 缓存有效：直接扩写。
- 缓存缺失或过期，且 `generate_missing_on_single=true`：提示是否先生成当前 H2 背景。
- 用户选择回退：按 `fallback` 继续。
- 用户取消：停止本次章节生成。

提示文案：

```text
当前章节所属 H2 背景尚未准备，是否先生成？
```

按钮：

- `生成并继续`
- `使用回退继续`
- `取消`

### 9.9 进度与结果反馈

H2 准备阶段结束后，状态栏显示：

```text
H2 项目背景：共 8 个，命中缓存 3 个，新生成 4 个，失败 1 个
```

如果来自管理窗口，则表格状态实时更新；如果来自批量生成自动预检，则可只显示紧凑进度，并在失败时提供“查看详情”入口打开管理窗口。

## 10. Trace 与 Prompt Contract

### 10.1 Prompt section

仍使用现有 section 名：

- `project_background`

trace 中的 `source_context` 记录为：

```text
H2ProjectBackgroundGenerator.get_for_heading
```

### 10.2 Context payload

`GenerationTraceSession._build_context_payload()` 中，当存在 H2 背景结果时，建议新增：

```json
"project_background": {
  "scope": "h2",
  "h2_title": "...",
  "h2_full_path": "...",
  "summary_chars": 512,
  "evidence_unit_ids": ["..."],
  "evidence_blocks": ["..."],
  "cache_status": "hit",
  "precomputed": true
}
```

如果保持 `PromptBuildResult` 当前字段不变，也可以先把该信息挂到 `full_context_stats` / `pruned_context` 之外的新增 trace 字段中。更干净的方式是给 `PromptBuildResult` 增加 `project_background_trace`。

### 10.3 Summary

`07_summary.md` 建议新增：

- `project_background_scope`
- `project_background_h2`
- `project_background_chars`
- `project_background_evidence_blocks`
- `project_background_cache_status`

## 11. 实施步骤

### 阶段一：模型与缓存

- 新增 `H2ProjectBackgroundResult`。
- 新增 `H2ProjectBackgroundPrecomputeReport`。
- 新增 `H2ProjectBackgroundGenerator`。
- 实现 H2 定位、H2 子树标题收集、source hash、subtree hash。
- 实现 JSON cache 读写。
- 实现全量 H2 收集与 `precompute_all()`。

### 阶段二：检索与背景材料生成

- 复用 `SourceUnitParser` 与 `HybridRetriever` 检索采购需求。
- 接入可选 verifier，保持 `unit_id` 回填。
- 实现 H2 背景原文摘录格式化，保留 summary 模式的摘要 prompt。
- 增加失败回退逻辑。

### 阶段三：Prompt 接入

- `AIWriter` 初始化时根据配置创建 global 或 H2 背景生成器。
- 批量扩写开始前，通过 `BidWriter.precompute_h2_project_backgrounds()` 一次性生成所有 H2 背景缓存。
- `auto` / pruned 分支中为当前 heading 读取对应 H2 背景缓存。
- `full_context` 分支保持 global 背景。
- 同步 `_build_prompt_contract_blocks()` 的 source context。

### 阶段四：UI 与后台任务

- 新增 H2 项目背景管理窗口。
- 实现后台预生成任务线程与队列事件。
- 批量生成前接入 H2 背景预检与准备阶段。
- 单章节生成接入当前 H2 缓存检查与补生成确认。
- 在 H2 行状态列展示轻量背景状态。
- 实现停止、失败汇总、重试失败项、跳过并回退。

### 阶段五：Trace 与文档

- 扩展 trace payload 与 summary。
- 更新 prompt contract 文档。
- 更新 config schema、example config、公共服务满意度配置。
- 更新配置编辑器提示文案。

### 阶段六：测试与验证

- 补充配置解析测试。
- 补充 H2 定位和缓存 key 测试。
- 补充批量扩写前预生成所有 H2 背景的测试。
- 补充 H2 背景检索证据测试。
- 补充 prompt 注入测试。
- 补充 trace payload 测试。
- 补充 UI 后台任务状态、停止、失败重试、批量生成预检测试。
- 用公共服务满意度项目抽 2-3 个 H2 做人工对比。

## 12. 测试建议

### 12.1 单元测试

- `test_h2_project_background_finds_h2_ancestor`
- `test_h2_project_background_cache_key_changes_when_subtree_changes`
- `test_precompute_h2_project_backgrounds_generates_all_h2_caches`
- `test_auto_generation_reads_precomputed_h2_background`
- `test_h2_project_background_uses_requirement_evidence_only`
- `test_h2_project_background_falls_back_when_evidence_is_insufficient`
- `test_auto_prompt_uses_h2_project_background`
- `test_full_context_prompt_keeps_global_project_background`
- `test_trace_records_h2_project_background_evidence`

### 12.2 UI 与任务流测试

- `test_h2_background_dialog_lists_all_h2_statuses`
- `test_h2_background_precompute_task_reports_progress_events`
- `test_h2_background_precompute_stop_marks_remaining_as_skipped`
- `test_batch_generate_runs_h2_precompute_before_chapter_generation`
- `test_batch_generate_can_continue_with_fallback_after_h2_failures`
- `test_single_generation_prompts_for_missing_h2_background`

### 12.3 回归测试

运行：

```bash
uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -q
uv run pytest tests/test_chapter_fact_store.py tests/test_fact_card_prompt.py -q
uv run python -m compileall bid_writer run.py tests
```

如新增独立测试文件：

```bash
uv run pytest tests/test_h2_project_background.py -q
```

### 12.4 人工验证样例

对同一项目选择至少两个 H2：

- 一个偏“项目理解 / 工作基础”。
- 一个偏“实施方案 / 服务方案”。
- 一个偏“质量保障 / 保密 / 进度”。

对比内容：

- H2 背景是否只覆盖本 H2。
- 是否漏掉 H2 下章节扩写所需关键项目事实。
- 当前章节 `需求要点` 是否仍包含具体硬要求。
- 生成正文是否减少跨章节重复。
- prompt 总长度是否下降或更稳定。

## 13. 风险与缓解

| 风险 | 表现 | 缓解 |
|---|---|---|
| H2 检索召回不足 | 背景材料缺关键事实 | 设置 evidence 下限，完全未命中时不注入项目背景 |
| 摘要幻觉 | 出现采购需求没有的信息 | prompt 限制只基于证据；trace 保留 evidence；温度设为 0 |
| 同名 H2 缓存冲突 | 不同章节复用错误背景 | cache key 使用 `h2.full_path` 和 subtree hash |
| prompt 变长 | 原文摘录过长影响正文生成 | 用 `max_evidence_blocks` / `max_evidence_chars` 控制摘录数量和总字符数 |
| 配置语义混乱 | 用户不清楚 global 与 h2_auto 区别 | 更新 schema、配置编辑器 tooltip 和 prompt contract |
| full_context 行为变化 | 旧项目输出风格突变 | full_context 保持 global，不默认改为 H2 |
| 界面假死 | H2 背景生成时无法操作窗口 | 后台线程执行模型调用，主线程只消费队列事件 |
| 用户误以为正文生成卡住 | 批量生成前长时间停留 | 明确显示“准备 H2 项目背景”阶段与 H2 进度 |
| 中途停止导致成果丢失 | 已生成 H2 没有保存 | 每个 H2 完成后立即写缓存 |
| 单个 H2 失败阻断全部任务 | 批量任务可用性差 | 失败汇总后允许重试失败项或按 fallback 继续 |

## 14. 推荐默认值

```yaml
processing:
  path: "auto"
  project_background:
    enabled: true
    max_chars: 800
    h2:
      precompute_on_batch: true
      generate_missing_on_single: true
      max_evidence_blocks: 6
      max_evidence_chars: 2400
      content_mode: excerpts
      min_evidence_blocks: 2
      fallback: "raw_evidence"
      cache_dir: "./caches/project_background_h2"
```

如果用户选择 `full_context`：

```yaml
processing:
  path: "full_context"
  project_background:
    enabled: true
    scope: "global"
    max_chars: 800
```

## 15. 最终结论

建议采用“`auto` 模式批量预生成 H2 级背景，扩写时按所属 H2 读取注入；`full_context` 模式继续使用全局背景”的双路径策略。

这个方案符合当前代码架构：`auto` 已经承担章节级检索、分类和原文摘录，H2 背景预生成是对该链路的自然增强；`full_context` 保持全文参考语义，不引入额外行为变化。

为了确保提炼准确、不丢失重要信息，首版必须坚持三条原则：

1. 先检索证据，再生成摘要。
2. 摘要只提供 H2 章级语境，不替代当前章节需求摘录和评分关注。
3. 批量扩写前一次性生成全部 H2 背景缓存，正文扩写阶段只读取对应 H2 背景并注入。
4. 每次摘要都保留 evidence、cache、trace，便于人工审计与回归对比。

## 16. 参考依据

- Patrick Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks: https://arxiv.org/abs/2005.11401
- Nelson F. Liu et al., Lost in the Middle: How Language Models Use Long Contexts: https://arxiv.org/abs/2307.03172
- Query-focused abstractive summarization research direction: https://arxiv.org/abs/1801.07704
- Anthropic long-context prompting guidance: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips
