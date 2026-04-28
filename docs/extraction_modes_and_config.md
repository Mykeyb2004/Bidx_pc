# 项目采购需求与评分标准摘录提炼：模式与配置参数说明

## 1. 文档目的

本文只说明“项目采购需求”和“评分标准”这两类源文，在章节生成前如何被摘录/提炼，以及相关配置参数当前的真实作用。

说明：

- 从 2026-04 这轮配置改造开始，YAML 推荐写法已切到 canonical schema：`project / writing / processing / models / runtime`
- 本文后续提到的 `context_pruning.*`，更多是在描述“逻辑参数”和旧 schema 兼容字段
- 新 schema 下，章节提炼主路径统一由 `processing.path` 控制：
  - `full_context`
  - `legacy_rule`
  - `hybrid_extract`
  - `auto`
- 旧 `context_pruning.*` 写法仍兼容，但不再是新项目推荐写法

本文重点回答四个问题：

1. 目前有哪些提炼模式
2. 每种模式分别怎么工作
3. 可以通过哪些配置参数控制
4. 哪些参数当前已经接线生效，哪些只是预留配置

本文不讨论：

- system prompt 的角色设定
- user prompt 的完整拼接合同
- 正文生成后的后处理

相关代码入口：

- `bid_writer/context_pruner.py`
- `bid_writer/config.py`
- `bid_writer/source_unit_parser.py`
- `bid_writer/hybrid_retriever.py`
- `bid_writer/embedding_store.py`
- `bid_writer/llm_verifier.py`

## 2. 总体结构

当前“摘录提炼”在实现上仍属于章节级上下文裁剪的一部分；在 canonical schema 中，主入口位于 `processing.path`。

整体流程如下：

```text
processing.path
  -> build_context(heading)
    -> 构建章节信号（response_labels / chapter_focus_terms / match_keywords）
    -> full_context: 不进入章节级摘录提炼
    -> legacy_rule: 评分标准与采购需求都走规则链路
    -> hybrid_extract: 评分标准与采购需求都走检索摘录链路
    -> auto: 评分项和采购需求走章节级检索；项目背景可按 H2 预生成并注入
    -> 可选 requirement_brief 原文摘录
    -> 输出 ChapterContext
```

最终会产出三类与本文直接相关的结果：

- `scoring_items`
  - 命中的评分标准条目，最终进入 prompt 的 `## 评分关注`
- `requirement_seed`
  - 命中的采购需求块经过程序压缩后的“需求要点”
- `requirement_brief`
  - 命中的采购需求块进一步抽取出的“原文摘录版需求要点”
- `project_background`
  - 在 `auto + processing.project_background.enabled=true` 时，由当前章节所属 H2 的采购需求证据片段生成章级背景摘要

## 3. 当前支持的模式

### 3.1 总开关

`context_pruning.enabled`

- `false`
  - 不做章节级摘录提炼
  - 直接把完整采购需求、完整评分标准塞进 full-context prompt
- `true`
  - 启用章节级提炼
  - 评分标准和采购需求可分别选择自己的模式

### 3.2 评分标准提炼模式

`context_pruning.scoring.mode`

支持两种值：

- `legacy_rule`
- `hybrid_extract`

#### `legacy_rule`

当前行为：

1. 主要解析 Markdown 表格
2. 从表格中识别“子项/评分项/评审因素/项目/子项目”等列
3. 识别“评审标准/评分标准/评审内容/标准”等列
4. 可选识别“权重/分值/满分/分数”等列
5. 通过 `response_labels`、`match_keywords`、`chapter_focus_terms` 做规则打分
6. 选出前 `max_rows` 条进入 `scoring_items`

特点：

- 优点：稳定、低成本、无额外模型调用
- 限制：对纯文字型评分标准不如 `hybrid_extract` 稳

#### `hybrid_extract`

当前行为：

1. 先把评分标准统一解析为 `SourceUnit`
2. `parse_mode=auto` 时，兼容 Markdown 表格和 Markdown 文字评分段
3. 先做 lexical retrieval
4. 若 `vector_enabled=true`，再做向量召回
5. lexical 与 vector 用 rank-based fusion 合并排序
6. 若开启 verifier 链路，再从少量候选中只选择 `unit_id`
7. 最终回填原文，生成 `scoring_items`

特点：

- 优点：支持文字型评分标准；可扩展向量召回和候选校验
- 限制：配置和链路更复杂；若启用 vector/verifier，需要额外连接参数

### 3.3 采购需求提炼模式

`context_pruning.requirements.mode`

支持两种值：

- `legacy_rule`
- `hybrid_extract`

#### `legacy_rule`

当前行为：

1. 按空行把采购需求切块
2. 对看起来像标题块的内容，尝试与下一块合并
3. 对每个块按 `response_labels`、`match_keywords`、`chapter_focus_terms` 做规则打分
4. 过滤明显低价值块
5. 选出少量相关块
6. 对选中块做程序内压缩，生成 `requirement_seed`
7. 若启用 `requirements_brief.enabled=true`，再从这些块抽取 `requirement_brief`

特点：

- 优点：成本低、稳定、无额外模型调用
- 限制：切块粒度和召回能力受规则限制

#### `hybrid_extract`

当前行为：

1. 先把采购需求统一解析为 `SourceUnit`
2. 先做 lexical retrieval
3. 若 `vector_enabled=true`，再做向量召回
4. 若启用 verifier 链路，再从候选中只保留选中的 `unit_id`
5. 对命中原文块生成 `requirement_seed`
6. 若启用 `requirements_brief.enabled=true`，再从命中原文块抽取 `requirement_brief`

特点：

- 优点：召回能力更强，便于保留“原文摘录”约束
- 限制：`requirement_seed` 仍是程序压缩结果，不是逐句原文直贴；若需要更强调原文，应优先看 `requirement_brief`

### 3.4 `auto` 下的 H2 项目背景

当配置满足以下条件时：

```yaml
processing:
  path: auto
  project_background:
    enabled: true
```

章节 prompt 中的 `## 项目背景` 会由 H2 级背景提供：

1. 系统找到当前章节最近的 H2 祖先
2. 使用 H2 标题、完整路径和子树标题构造检索 query
3. 从采购需求中检索相关 `SourceUnit`
4. 若证据片段数达到 `min_evidence_blocks`，调用辅助模型生成 H2 摘要
5. 将摘要、证据 ID、原文片段和配置指纹写入 JSON 缓存
6. 生成具体 H3/H4/H5 章节时，直接读取所属 H2 缓存并注入 `project_background`

这条链路的边界是：

- H2 背景只负责章级项目情境，不替代 `评分关注` 或 `需求要点`
- 默认只把摘要注入 prompt，证据片段进入 trace 供审计
- `full_context` 已经完整注入采购需求和评分标准，不再提炼或注入项目背景；`processing.project_background.*` 在该模式下不生效
- 证据不足或摘要失败时按 `processing.project_background.h2.fallback` 回退

## 4. 当前链路里的三个层次

### 4.1 模式层

决定走哪条主链路：

- `legacy_rule`
- `hybrid_extract`

### 4.2 检索层

只在 `hybrid_extract` 下生效：

- lexical retrieval
- vector retrieval
- 候选融合

### 4.3 校验层

只在 `hybrid_extract` 且开启精排/校验时生效：

- verifier 只返回 `unit_id`
- 程序再按 `unit_id` 回填原文

这意味着当前实现里：

- “提炼”主链路不是全文 LLM 摘要
- LLM 只在可选 verifier 阶段参与
- verifier 不负责生成摘录文本

## 5. 配置参数总览

下面分为“代码默认值”和“`config_公共服务满意度.yaml` 当前示例值”两列。

### 5.1 总控参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 作用 |
|---|---:|---:|---|
| `context_pruning.enabled` | `false` | `true` | 是否启用章节级摘录提炼 |
| `context_pruning.debug_dump` | `false` | `true` | 是否输出 `_context_pruning_debug` 调试文件 |
| `context_pruning.mode` | `legacy_rule` | `legacy_rule` | 总默认模式；若子项未单独配置，则评分/采购需求继承它 |
| `context_pruning.unavailable_policy` | `fallback_legacy` | `fallback_legacy` | 新模式不可用时回退旧模式还是直接报错 |

### 5.2 评分标准提炼参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 生效范围 | 作用 |
|---|---:|---:|---|---|
| `context_pruning.scoring.enabled` | `true` | `true` | 两种模式 | 是否启用评分标准路由 |
| `context_pruning.scoring.mode` | 继承 `context_pruning.mode` | `legacy_rule` | 两种模式 | 评分标准使用哪种提炼模式 |
| `context_pruning.scoring.parse_mode` | `auto` | `auto` | `hybrid_extract` | `auto`/`table_only`/`text_only` |
| `context_pruning.scoring.max_rows` | `4` | `4` | 两种模式 | 最终进入 `scoring_items` 的条数上限 |

### 5.3 采购需求提炼参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 生效范围 | 作用 |
|---|---:|---:|---|---|
| `context_pruning.requirements.mode` | 继承 `context_pruning.mode` | `legacy_rule` | 两种模式 | 采购需求使用哪种提炼模式 |
| `context_pruning.requirements.max_quotes` | `4` | `4` | `requirement_brief` | 最多保留多少条原文摘录 |
| `context_pruning.requirements.max_quote_chars` | `220` | `220` | `requirement_brief` | 单条原文摘录的最大字符数 |

### 5.4 `requirement_brief` 参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 当前是否接线 | 作用 |
|---|---:|---:|---|---|
| `context_pruning.requirements_brief.enabled` | `false` | `true` | 已接线 | 是否额外生成原文摘录版 `requirement_brief` |
| `context_pruning.requirements_brief.fallback` | `rule_only` | `rule_only` | 未接线 | 配置已暴露，但当前主流程没有读取它决定回退策略 |

### 5.5 `hybrid_extract` 共享检索参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 当前是否接线 | 作用 |
|---|---:|---:|---|---|
| `context_pruning.retrieval.lexical_enabled` | `true` | `true` | 已接线 | 是否启用 lexical retrieval；`hybrid_extract` 当前要求必须为 `true` |
| `context_pruning.retrieval.vector_enabled` | `false` | `false` | 已接线 | 是否启用向量召回 |
| `context_pruning.retrieval.rerank_enabled` | `false` | `false` | 已接线 | 是否进入候选精排/校验链路 |
| `context_pruning.retrieval.top_k_lexical` | `20` | `20` | 已接线 | lexical 候选数 |
| `context_pruning.retrieval.top_k_vector` | `20` | `20` | 已接线 | vector 候选数 |
| `context_pruning.retrieval.top_k_fused` | `30` | `30` | 已接线 | 融合排序后保留多少候选 |
| `context_pruning.retrieval.top_k_final` | `6` | `6` | 已接线 | 最终进入摘录阶段的候选数 |
| `context_pruning.retrieval.min_fused_score` | `0.0` | `0.0` | 已接线 | 最终候选最低分阈值 |

### 5.6 向量召回参数

只有在 `vector_enabled=true` 时才有意义。

| 参数路径 | 代码默认值 | 示例配置当前值 | 当前是否接线 | 作用 |
|---|---:|---:|---|---|
| `BID_WRITER_EMBEDDING_MODEL` | `text-embedding-3-large` | `.env.local` | 已接线 | embedding 模型名 |
| `BID_WRITER_EMBEDDING_BATCH_SIZE` | `64` | `.env.local` | 已接线 | embedding 批大小 |
| 执行入口同级 `embedding_cache` | 执行入口同级 | 固定默认 | 已接线 | 本地缓存目录，不再通过 YAML 配置 |
| `BID_WRITER_EMBEDDING_REBUILD_ON_SOURCE_CHANGE` | `true` | `.env.local` | 已接线 | 源文变化时是否重建向量缓存 |
| `BID_WRITER_EMBEDDING_QUERY_PREFIX` | `""` | `.env.local` | 已接线 | query embedding 的前缀 |
| `BID_WRITER_EMBEDDING_DOCUMENT_PREFIX` | `""` | `.env.local` | 已接线 | document embedding 的前缀 |

对应环境变量：

| 环境变量 | 是否必需 | 作用 |
|---|---|---|
| `BID_WRITER_EMBEDDING_API_BASE_URL` | `vector_enabled=true` 时必需 | embedding 服务根地址 |
| `BID_WRITER_EMBEDDING_API_KEY` | `vector_enabled=true` 时必需 | embedding 服务密钥 |
| `BID_WRITER_EMBEDDING_MODEL` | 可选 | embedding 模型名 |
| `BID_WRITER_EMBEDDING_BATCH_SIZE` | 可选 | embedding 批大小 |

说明：

- embedding 客户端会自动把误写成 `.../embeddings` 的 base URL 归一化到服务根路径
- 向量缓存 key 当前包含：`embedding_model`、`embedding_document_prefix`、文档内容本身

### 5.7 候选校验参数

当前项目里没有单独的“重排模型”和“校验模型”两套实现，`rerank_enabled` 和 `llm_verify_enabled` 最终共用同一个 `LLMVerifier`。

| 参数路径 | 代码默认值 | 示例配置当前值 | 当前是否接线 | 作用 |
|---|---:|---:|---|---|
| `context_pruning.extraction.quote_only` | `true` | `true` | 未接线 | 当前只作为语义约束保留，主流程没有读取它做分支控制 |
| `context_pruning.extraction.return_ids_only` | `true` | `true` | 已接线 | 启用 verifier 时必须为 `true`，否则运行时校验报错 |
| `context_pruning.extraction.llm_verify_enabled` | `false` | `false` | 已接线 | 是否显式开启 verifier |
| `context_pruning.extraction.llm_verify_max_candidates` | `8` | `8` | 已接线 | 最多送入 verifier 的候选数 |

### 5.8 verifier 辅助模型参数

| 参数路径 | 代码默认值 | 示例配置当前值 | 当前是否接线 | 作用 |
|---|---:|---:|---|---|
| `BID_WRITER_PRUNING_MODEL` | `gpt-5.4` | `.env.local` | 已接线 | verifier 模型名 |
| `BID_WRITER_PRUNING_TEMPERATURE` | `0.2` | `.env.local` | 未按配置接线 | `LLMVerifier` 当前实际写死 `temperature=0` |
| `BID_WRITER_PRUNING_MAX_TOKENS` | `1200` | `.env.local` | 未接线 | 当前调用 verifier 时未传 `max_tokens` |
| `BID_WRITER_PRUNING_TIMEOUT_SECONDS` | `60` | `.env.local` | 已接线 | OpenAI 客户端超时 |
| `BID_WRITER_PRUNING_MAX_RETRIES` | `2` | `.env.local` | 已接线 | OpenAI 客户端重试次数 |
| `BID_WRITER_PRUNING_TOP_P` | `None` | `.env.local` | 未接线 | 当前 verifier 调用未传 `top_p` |
| `BID_WRITER_PRUNING_SEED` | `None` | `.env.local` | 未接线 | 当前 verifier 调用未传 `seed` |

对应环境变量：

| 环境变量 | 是否必需 | 说明 |
|---|---|---|
| `BID_WRITER_PRUNING_API_BASE_URL` | verifier 开启时必需 | verifier 服务地址 |
| `BID_WRITER_PRUNING_API_KEY` | verifier 开启时必需 | verifier 密钥 |
| `BID_WRITER_PRUNING_MODEL` | 可选 | 辅助模型名称 |
| `BID_WRITER_PRUNING_TEMPERATURE` | 可选 | 当前 Config 可读，但 verifier 调用未使用 |
| `BID_WRITER_PRUNING_MAX_TOKENS` | 可选 | 当前 Config 可读，但 verifier 调用未使用 |
| `BID_WRITER_PRUNING_TIMEOUT_SECONDS` | 可选 | 已接线 |
| `BID_WRITER_PRUNING_MAX_RETRIES` | 可选 | 已接线 |
| `BID_WRITER_PRUNING_TOP_P` | 可选 | 当前 Config 可读，但 verifier 调用未使用 |
| `BID_WRITER_PRUNING_SEED` | 可选 | 当前 Config 可读，但 verifier 调用未使用 |

## 6. 当前真实生效的模式组合

### 6.1 最常见组合

#### 组合 A：纯规则模式

```yaml
context_pruning:
  enabled: true
  mode: legacy_rule
  scoring:
    mode: legacy_rule
  requirements:
    mode: legacy_rule
```

特点：

- 不用 embedding
- 不用 verifier
- 成本最低
- 适合作为稳定基线

#### 组合 B：检索摘录模式，不开向量、不校验

```yaml
context_pruning:
  enabled: true
  mode: hybrid_extract
  scoring:
    mode: hybrid_extract
  requirements:
    mode: hybrid_extract
  retrieval:
    lexical_enabled: true
    vector_enabled: false
    rerank_enabled: false
  extraction:
    llm_verify_enabled: false
```

特点：

- 仍然没有额外模型调用
- 已经能支持文字评分标准
- 召回强于 `legacy_rule`

#### 组合 C：检索摘录 + 向量召回

```yaml
context_pruning:
  enabled: true
  mode: hybrid_extract
  retrieval:
    lexical_enabled: true
    vector_enabled: true
```

额外要求：

- `.env.local` 中必须配置 `BID_WRITER_EMBEDDING_*`

#### 组合 D：检索摘录 + 候选校验

```yaml
context_pruning:
  enabled: true
  mode: hybrid_extract
  retrieval:
    rerank_enabled: true
  extraction:
    return_ids_only: true
    llm_verify_enabled: true
```

额外要求：

- `.env.local` 中必须配置 `BID_WRITER_PRUNING_*`
- 当前 verifier 只返回 `selected_ids`

## 7. 运行时校验规则

当请求 `hybrid_extract` 时，当前代码会做以下校验：

1. `lexical_enabled` 必须为 `true`
2. 若 `vector_enabled=true`，必须配置 `BID_WRITER_EMBEDDING_API_BASE_URL` 和 `BID_WRITER_EMBEDDING_API_KEY`
3. 若进入 rerank/verify 链路，必须配置 `BID_WRITER_PRUNING_*`
4. 若进入 rerank/verify 链路，`return_ids_only` 必须为 `true`

若校验失败：

- `unavailable_policy=fallback_legacy`
  - 自动回退到 `legacy_rule`
- `unavailable_policy=fail_fast`
  - 直接抛错

## 8. 当前需要特别注意的实现事实

### 8.1 `rerank_enabled` 不是独立 reranker

当前代码里：

- `rerank_enabled=true`
- `llm_verify_enabled=true`

这两个开关最终都走同一个 `LLMVerifier`。

也就是说，当前没有“两套不同精排器”。

### 8.2 `requirement_seed` 不是原文直贴

`requirement_seed` 来自命中块后的程序压缩结果，属于“短要点”。

如果你要更强调“原文摘录”，应关注：

- `requirements_brief.enabled`
- `requirement_brief`

### 8.3 有些参数已经暴露，但还没真正接线

当前未真正接线或未完整接线的参数主要有：

- `context_pruning.requirements_brief.fallback`
- `context_pruning.extraction.quote_only`
- `BID_WRITER_PRUNING_TEMPERATURE`
- `BID_WRITER_PRUNING_MAX_TOKENS`
- `BID_WRITER_PRUNING_TOP_P`
- `BID_WRITER_PRUNING_SEED`

这些参数“可配置”不等于“当前实现已经消费它们”。

## 9. 当前示例配置的实际状态

`config_公共服务满意度.yaml` 当前状态是：

- `context_pruning.enabled = true`
- 评分标准模式：`legacy_rule`
- 采购需求模式：`legacy_rule`
- `requirements_brief.enabled = true`
- `vector_enabled = false`
- `rerank_enabled = false`
- `llm_verify_enabled = false`
- embedding 模型默认来自 `.env.local` / `BID_WRITER_EMBEDDING_MODEL`，未设置时为 `text-embedding-3-large`
- verifier 模型默认来自 `.env.local` / `BID_WRITER_PRUNING_MODEL`，未设置时为 `gpt-5.4`

这意味着当前示例配置虽然已经把新链路参数都摆出来了，但实际运行仍以“规则模式 + 原文摘录 requirement_brief”为主。

## 10. 推荐理解方式

如果只从“摘录提炼”角度理解当前系统，可以把它分成一句话：

> 当前系统支持两套主模式：`legacy_rule` 和 `hybrid_extract`；默认示例仍跑 `legacy_rule`，`hybrid_extract` 可以逐步叠加 lexical、vector、verifier，但 verifier 只负责选片段 ID，不负责改写原文。
