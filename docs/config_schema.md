# 配置 Schema 说明

## 1. 目标

当前项目推荐使用按“信息性质”分层的 canonical schema，而不是直接沿着实现模块堆字段。

推荐分层如下：

- `project`
  - 项目固有信息、输入资源、输出目录
- `writing`
  - 角色设定、写作规则、提示词约束、篇幅目标
- `processing`
  - 章节处理路径与业务提炼参数
- `models`
  - 主模型、辅助模型、 embedding 的非敏感参数
- `runtime`
  - stream、trace、debug、输出细节与合并行为

## 1.1 维护约定

这份文档是当前配置结构的单一说明入口。后续只要发生以下任一变更，都应同步更新本文档：

- 新增、删除、重命名配置字段
- 调整字段默认值、优先级或路径解析规则
- 调整 `processing.path` 的业务路径语义
- 调整旧 schema 的兼容范围
- 调整示例配置的推荐写法

与本文档需要一起维护的文件通常包括：

- `config.example.yaml`
- 项目级示例配置，如 `config_*.yaml`
- `README.md` 中的配置说明入口
- 涉及配置解析行为的测试夹具与测试用例

## 2. `processing` 的 canonical 设计

`processing` 只保留 3 条业务路径：

- `full_context`
  - 采购需求和评分标准都不做章节级处理，直接把完整原文送入主 prompt
- `legacy_rule`
  - 采购需求和评分标准都走现有规则链路
- `hybrid_extract`
  - 采购需求和评分标准都走检索摘录链路

推荐写法：

```yaml
processing:
  path: "legacy_rule" # full_context / legacy_rule / hybrid_extract
```

在 canonical schema 中，不再推荐把“评分标准”和“采购需求”的主链路拆成两条可自由混搭的项目级参数。

旧 schema 理论上允许 mixed-mode：

- `context_pruning.scoring.mode = legacy_rule`
- `context_pruning.requirements.mode = hybrid_extract`

当前代码仍保留兼容，但这只是兼容层，不再作为推荐写法继续推广。

## 3. 推荐字段布局

### 3.1 `project`

```yaml
project:
  root_dir: "/path/to/bid-project"
  bidder_name: "示例投标主体名称"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./采购需求.md"
    scoring_criteria_file: "./评分标准.md"
    knowledge_files:
      - "./knowledge/公司简介.md"
    knowledge_directory: "./knowledge"
  output_dir: "./output"
```

说明：

- `project.root_dir` 用于声明项目资料根目录
- `project.inputs.*` 与 `project.output_dir` 默认相对 `project.root_dir` 解析
- `project.inputs.knowledge_files` 允许显式声明知识文档，声明顺序优先于目录扫描顺序
- `project.inputs.knowledge_directory` 会按文件名排序扫描目录下的 `.md` 文件，并补齐未显式声明的知识文档

### 3.2 `writing`

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
  extra_rules: []
```

说明：

- `writing.role_file` 推荐放在仓库根目录的 `roles/` 下，便于按项目复用角色文件
- `roles/system_gate_rules.md` 是当前固定且唯一的文本来源，用于 system gate 规则
- `writing.target_words.default` 是运行时输入框的基准值，系统会自动推导目标区间并写入 prompt
- `writing.target_words.upper_ratio` 用于控制区间上沿的自动放宽幅度，默认 `1.15`
- `writing.extra_rules` 当前不会单独生成 `## 其他写作要求` 区块，而是直接追加到 `## 结构输出硬要求` 的末尾
- `writing.hard_constraints`、`writing.allow_markdown_headings`、`writing.allow_english_terms` 不再生成 system gate prompt 文案；旧字段仅用于兼容或局部巡检

### 3.3 `processing`

```yaml
processing:
  path: "hybrid_extract"
  project_background:
    enabled: true
    max_chars: 800
  knowledge:
    enabled: true
    max_chars: 800
  chapter_facts:
    enabled: true
    auto_extract_on_batch: true
    max_facts_per_chapter: 15
  full_context:
    chapter_writing_plan:
      enabled: false
      max_chars: 320
  context_view:
    include_ancestors: true
    include_siblings: true
    max_siblings: 8
  legacy_rule:
    scoring_max_rows: 4
    requirements_max_quotes: 4
    requirements_max_quote_chars: 220
    requirement_brief_enabled: true
  hybrid_extract:
    unavailable_policy: "fail_fast"
    scoring_parse_mode: "auto"
    scoring_max_rows: 4
    requirements_max_quotes: 4
    requirements_max_quote_chars: 220
    requirement_brief_enabled: true
    retrieval:
      lexical_enabled: true
      vector_enabled: false
      verify_enabled: false
      top_k_lexical: 20
      top_k_vector: 20
      top_k_fused: 30
      top_k_final: 6
      min_fused_score: 0.0
    quote_only: true
    return_ids_only: true
    verify_max_candidates: 8
```

说明：

- `processing.path` 决定当前项目跑哪条链路
- `processing.project_background.*` 当前会在 `auto` 和 `full_context` 下生效
- `processing.knowledge.*` 控制是否注入 `knowledge_context`，phase 1 仅做按条目/段落边界的硬截断
- `processing.chapter_facts.*` 控制正文 facts 提炼与缓存刷新边界；`auto_extract_on_batch` 只建议用于批量生成路径
- `processing.full_context.chapter_writing_plan.*` 只在 `full_context` 下生效，用于在章节任务卡中额外插入“章节写作计划”
- 开启后会增加一次辅助 LLM 调用；当前实现会尽量复用正文扩写的 system prompt 与 full-context 参考前缀，以改善 prompt cache 命中率
- 每条链路自己的参数挂在各自子块下
- `verify_enabled` 统一表达原先 `rerank_enabled` / `llm_verify_enabled` 那条候选校验链路

### 3.4 `models`

```yaml
models:
  generation:
    model: "gpt-4o-mini"
    temperature: 0.7
    max_tokens: 8000
    timeout_seconds: 120
    max_retries: 3
  pruning:
    model: "gpt-4o-mini"
    temperature: 0.2
    max_tokens: 1200
    timeout_seconds: 60
    max_retries: 2
  embedding:
    model: "text-embedding-3-small"
    batch_size: 64
    cache_dir: "./output/_embedding_cache"
    rebuild_on_source_change: true
    query_prefix: ""
    document_prefix: ""
```

说明：

- 敏感值仍建议放 `.env.local`
- 非敏感模型参数留在 YAML

### 3.5 `runtime`

```yaml
runtime:
  stream:
    enabled: true
    idle_timeout_seconds: 12
  trace:
    enabled: true
    directory: "./log/generation_traces"
    mode: "full"
    write_prompt: true
    write_output: true
    write_context: true
    write_summary: true
    redact_sensitive: true
  debug:
    context_pruning_dump: false
  output:
    prefix: ""
    include_title_header: true
    overwrite_existing: true
    filename_max_length: 100
    empty_filename_fallback: "untitled"
  merge:
    normalize_soft_line_breaks: false
```

说明：

- `runtime.trace.directory`、`models.embedding.cache_dir` 这类运行产物路径默认相对配置文件目录解析
- `project.output_dir` 这类项目输出路径默认相对 `project.root_dir` 解析

## 4. 兼容策略

当前代码仍兼容以下旧字段：

- 根级 `outline_file` / `bid_requirements` / `scoring_criteria`
- `inputs.*`
- `role`
- `generation.*`
- `prompt.*`
- `context_pruning.*`
- `generation_trace.*`
- `api.*`

兼容原则：

- 新 schema 优先级高于旧 schema
- 旧字段继续可读，但不再作为推荐写法
- 新项目、示例配置和文档都应优先采用 canonical schema

## 5. 变更检查清单

当你修改配置相关代码时，建议至少检查以下几项：

1. `bid_writer/config.py` 中是否已经接入新字段或兼容逻辑
2. `docs/config_schema.md` 是否反映了真实结构、优先级和路径规则
3. `config.example.yaml` 是否仍是推荐写法
4. 相关 `config_*.yaml` 项目配置是否需要同步迁移
5. `README.md` 的配置入口说明是否仍准确
6. 测试夹具与测试是否覆盖新的读取行为

## 6. 相关文档

- 配置结构的可视化编辑方案见 [配置编辑器界面方案](config_editor_ui_plan.md)
