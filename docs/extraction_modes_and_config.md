# 评分标准检索与 H2 项目背景：模式与配置参数说明

## 1. 文档目的

本文说明章节生成前，系统如何处理“评分标准”和“项目采购需求”两类源文，以及相关配置参数当前的真实作用。

从 2026-04 这轮配置改造开始，新项目推荐使用 canonical schema：

- `project`
- `writing`
- `processing`
- `runtime`

旧 `context_pruning.*` 写法仍兼容读取，但不再是新项目推荐写法；配置编辑器规范化保存时会把旧字段迁移或丢弃。

## 2. 当前主链路

主入口由 `processing.path` 控制：

- `full_context`
  - 不做章节级检索裁剪
  - 将完整采购需求和完整评分标准作为固定参考材料注入 prompt
  - 不额外生成 H2 项目背景
- `auto`
  - 对评分标准做章节级检索和可选分类
  - 对采购需求只做 H2 项目背景证据检索
  - 不再为每个叶子章节单独生成采购需求要点区块

兼容路径：

- `legacy_rule`
- `hybrid_extract`

这两个旧路径现在只保留评分标准路由能力；旧的章节级采购需求摘录/压缩逻辑已经移除。

## 3. 评分标准处理

### 3.1 规则模式

`legacy_rule` 会：

1. 解析 Markdown 表格
2. 识别“子项/评分项/评审因素/项目/子项目”等列
3. 识别“评审标准/评分标准/评审内容/标准”等列
4. 根据响应标签、章节关键词、焦点词打分
5. 选出前 `scoring_max_rows` 条进入 prompt 的 `## 评分关注`

优点是稳定、低成本；限制是对纯文字型评分标准不如检索模式稳。

### 3.2 检索模式

`hybrid_extract` / `auto` 的评分链路会：

1. 将评分标准解析为 `SourceUnit`
2. 使用 lexical retrieval 召回候选
3. 如启用向量召回，则合并 vector retrieval 结果
4. 如启用 verifier，则让辅助模型只选择候选 `unit_id`
5. 程序按 ID 回填原文，生成 `scoring_items`

verifier 只负责选片段 ID，不负责生成或改写评分内容。

### 3.3 auto 下的 H2 评分分类缓存

`auto` 模式在 `processing.scoring.enabled=true` 时命中评分项后，会把评分项进一步分为 `scoring_must_respond` 与 `scoring_reference`。该分类结果按当前章节所属 H2 缓存，同一个 H2 下的 H3/H4/H5 章节共享一次辅助模型分类结果。

缓存文件位于 `processing.scoring_classify.cache_dir`，未配置时默认写入项目根目录下的 `./caches/scoring_classify`。新缓存文件名前缀为 `h2_`，缓存 key 包含评分标准全文、H2 完整路径和 H2 子树结构；评分标准或 H2 子树变化会自动生成新缓存。

注意：H2 评分分类缓存只负责“必需响应/参考”的分组。每个叶子章节仍会先执行自己的评分项检索，然后只对本章节命中的评分项套用 H2 分类结果。

当 `processing.scoring.enabled=false` 时，auto 会跳过评分标准解析、检索、分类和 H2 分类缓存写入，最终 prompt 也不会出现 `## 评分关注`。

## 4. H2 项目背景处理

当配置满足：

```yaml
processing:
  path: auto
  project_background:
    enabled: true
```

章节 prompt 中的 `## 项目背景` 会由当前章节所属 H2 的采购需求证据形成：

1. 找到当前章节最近的 H2 祖先
2. 用 H2 标题、完整路径和子树标题构造检索 query
3. 从采购需求中检索相关 `SourceUnit`
4. 默认 `content_mode: excerpts` 时，直接格式化命中的采购需求原文片段
5. 只有 `content_mode: summary` 时，才调用辅助模型基于证据生成摘要
6. 将背景内容、证据 ID、证据片段和配置指纹写入 H2 JSON 缓存
7. 生成 H3/H4/H5 章节时读取所属 H2 缓存并注入 `project_background`

边界：

- H2 项目背景只提供章级项目语境
- 当前叶子章节不再另行拼接采购需求要点区块
- `full_context` 已经完整注入采购需求，并在 `processing.scoring.enabled=true` 时注入评分标准全文，因此不再额外生成项目背景
- 证据不足时按 `processing.project_background.h2.fallback` 回退；完全无命中时不会拿采购需求第一段兜底

## 5. 关键配置

### 5.1 总控

| 参数路径 | 默认值 | 作用 |
|---|---:|---|
| `processing.path` | `auto` | 选择 `auto` 或 `full_context` 主链路 |
| `runtime.debug.context_pruning_dump` | `false` | 是否输出上下文裁剪调试 sidecar |

### 5.2 H2 项目背景

| 参数路径 | 默认值 | 作用 |
|---|---:|---|
| `processing.project_background.enabled` | `true` | auto 链路是否注入 H2 项目背景 |
| `processing.project_background.max_chars` | `800` | summary 模式下摘要目标长度上限 |
| `processing.project_background.h2.generate_missing_on_single` | `true` | 单章生成时 H2 背景缺失是否补生成 |
| `processing.project_background.h2.max_evidence_blocks` | `6` | H2 背景最多使用多少个采购需求证据片段 |
| `processing.project_background.h2.max_evidence_chars` | `2400` | H2 背景证据片段总字符上限 |
| `processing.project_background.h2.content_mode` | `excerpts` | `excerpts` 直接用原文摘录；`summary` 调辅助模型生成摘要 |
| `processing.project_background.h2.min_evidence_blocks` | `1` | 生成 H2 背景所需最少证据数 |
| `processing.project_background.h2.fallback` | `raw_evidence` | 支持 `raw_evidence` / `empty` |
| `processing.project_background.h2.cache_dir` | `./caches/project_background_h2` | H2 背景缓存目录 |

### 5.3 评分检索

| 参数路径 | 默认值 | 作用 |
|---|---:|---|
| `processing.scoring.enabled` | `true` | 是否启用评分标准处理链路；关闭后 auto 跳过评分检索/分类，full_context 不注入评分标准全文 |
| `processing.hybrid_extract.scoring_parse_mode` | `auto` | 评分标准解析方式：`auto` / `table_only` / `text_only` |
| `processing.hybrid_extract.scoring_max_rows` | `4` | 最终进入 `## 评分关注` 的评分项数量 |
| `processing.hybrid_extract.retrieval.lexical_enabled` | `true` | 是否启用 lexical retrieval |
| `processing.hybrid_extract.retrieval.vector_enabled` | `false` | 是否启用向量召回 |
| `processing.hybrid_extract.retrieval.top_k_lexical` | `20` | lexical 候选数 |
| `processing.hybrid_extract.retrieval.top_k_vector` | `20` | vector 候选数 |
| `processing.hybrid_extract.retrieval.top_k_fused` | `30` | 融合后候选数 |
| `processing.hybrid_extract.retrieval.top_k_final` | `8` | 最终保留候选数 |
| `processing.hybrid_extract.retrieval.min_fused_score` | `0.0` | 最低融合分 |
| `processing.hybrid_extract.verify_max_candidates` | `8` | 送入 verifier 的候选数上限 |
| `processing.scoring_classify.cache_dir` | `./caches/scoring_classify` | auto 下 H2 评分分类缓存目录 |

`auto` 模式下，评分检索的专业参数优先从环境变量读取，适合放在 `.env.local` 中：

- `BID_WRITER_AUTO_RETRIEVAL_LEXICAL_ENABLED`
- `BID_WRITER_AUTO_RETRIEVAL_VECTOR_ENABLED`
- `BID_WRITER_AUTO_RETRIEVAL_TOP_K_LEXICAL`
- `BID_WRITER_AUTO_RETRIEVAL_TOP_K_VECTOR`
- `BID_WRITER_AUTO_RETRIEVAL_TOP_K_FUSED`
- `BID_WRITER_AUTO_RETRIEVAL_TOP_K_FINAL`
- `BID_WRITER_AUTO_RETRIEVAL_MIN_FUSED_SCORE`

## 6. 运行时校验

`auto` 模式要求：

- 已配置 `BID_WRITER_PRUNING_API_BASE_URL`
- 已配置 `BID_WRITER_PRUNING_API_KEY`
- lexical retrieval 保持开启

启用向量召回时，还必须配置：

- `BID_WRITER_EMBEDDING_API_BASE_URL`
- `BID_WRITER_EMBEDDING_API_KEY`

`hybrid_extract` 兼容路径要求 lexical retrieval 开启；如果开启 verifier，则要求 `return_ids_only=true`，以保证程序回填原文。

## 7. 推荐理解方式

当前系统可以简化理解为：

> `auto` 负责“评分关注 + H2 项目背景”；`full_context` 负责“全文参考材料”。采购需求不再在叶子章节层面单独做一份要点区块。
