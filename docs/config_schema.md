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
- `runtime`
  - stream、trace、debug、输出细节与合并行为

模型连接、模型名和采样/超时/token 等运行参数统一放在 `.env.local` 或外部环境变量中，不再写入 YAML。

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

`processing` 推荐保留 4 条业务路径：

- `full_context`
  - 采购需求和评分标准都不做章节级处理，直接把完整原文送入主 prompt
- `legacy_rule`
  - 采购需求和评分标准都走现有规则链路
- `hybrid_extract`
  - 采购需求和评分标准都走检索摘录链路
- `auto`
  - 走章节级智能裁剪链路：评分项与采购需求先检索，再按章节/H2 边界组织上下文

推荐写法：

```yaml
processing:
  path: "auto" # full_context / legacy_rule / hybrid_extract / auto
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
  root_dir: "."
  bidder_name: "示例投标主体名称"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./采购需求.md"
    scoring_criteria_file: "./评分标准.md"
  output_dir: "./output"
```

说明：

- `project.root_dir` 用于声明项目资料根目录
- `project.inputs.*` 与 `project.output_dir` 默认相对 `project.root_dir` 解析
- `project.inputs.knowledge_files` / `project.inputs.knowledge_directory` 仅作为旧配置兼容字段保留；当前章节生成 prompt 不再读取这些字段

### 3.1.1 跨平台路径规范

推荐配置文件使用相对路径，并统一使用 `/` 作为路径分隔符：

```yaml
project:
  root_dir: "."
  inputs:
    outline_file: "./投标大纲.md"
    bid_requirements_file: "./采购需求.md"
    scoring_criteria_file: "./评分标准.md"
  output_dir: "./output"
```

说明：

- `./output`、`项目要求/采购需求.md` 这类写法可在 Windows、macOS、Ubuntu 上由 Python 路径库按当前系统解析
- 不建议在共享配置中写入 `/Users/...`、`/home/...`、`C:/Users/...` 这类绑定本机或操作系统的绝对路径
- 如果必须写 Windows 绝对路径，建议使用 `C:/Users/example/project`，或使用单引号包裹反斜杠路径：`'C:\Users\example\project'`
- 配置编辑器选择项目内文件时，会优先保存为相对路径并使用 `/` 分隔符，便于跨系统迁移

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
  max_tables_per_section: 2
  max_mermaid_flowcharts_per_section: 0
  extra_rules: []
```

说明：

- `writing.role_file` 推荐放在仓库根目录的 `roles/` 下，便于按项目复用角色文件
- `roles/system_gate_rules.md` 是当前固定且唯一的文本来源，用于 system gate 规则
- `writing.target_words.default` 是运行时输入框的基准值，系统会自动推导目标区间并写入 prompt
- `writing.target_words.upper_ratio` 用于控制区间上沿的自动放宽幅度，默认 `1.15`
- `writing.extra_rules` 当前不会单独生成 `## 其他写作要求` 区块，而是直接追加到 `## 结构输出硬要求` 的末尾
- `writing.hard_constraints` 不再生成 system gate prompt 文案；请改 `roles/system_gate_rules.md`
- `writing.allow_markdown_headings`、`writing.allow_english_terms`、`writing.summary_title` 已废弃；配置编辑器规范化保存时会丢弃这些旧字段

### 3.3 `processing`

```yaml
processing:
  path: "auto"
  project_background:
    enabled: true
    scope: "h2_auto" # global / h2_auto
    max_chars: 800
    h2:
      precompute_on_batch: true
      generate_missing_on_single: true
      max_evidence_blocks: 6
      max_evidence_chars: 2400
      include_evidence_in_prompt: false
      min_evidence_blocks: 2
      fallback: "global" # global / raw_evidence / empty
      cache_dir: "./caches/project_background_h2"
  chapter_facts:
    enabled: true
    auto_extract_on_batch: true
    max_facts_per_chapter: 15
  full_context:
    chapter_writing_plan:
      enabled: false
      max_chars: 320
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
    quote_only: true
    return_ids_only: true
    verify_max_candidates: 8
```

说明：

- `processing.path` 决定当前项目跑哪条链路
- `processing.project_background.*` 只服务 `processing.path: auto` 链路；`full_context` 会直接注入完整采购需求和评分标准，不再额外提炼或注入项目背景摘要
- `processing.project_background.enabled` 控制 auto 链路是否注入项目背景摘要
- `processing.project_background.scope` 默认是 `global`，兼容旧配置；显式设为 `h2_auto` 时，只有 `processing.path: auto` 会启用 H2 级背景
- `processing.project_background.max_chars` 是 auto 链路中项目背景摘要的目标长度上限
- `processing.project_background.h2.precompute_on_batch` 控制批量生成前是否一次性预生成所有 H2 背景缓存
- `processing.project_background.h2.generate_missing_on_single` 控制单章节生成时若当前 H2 背景缺失，是否补生成一次
- `processing.project_background.h2.max_evidence_blocks` / `max_evidence_chars` 限制 H2 背景生成时使用的采购需求证据片段数量与总长度
- `processing.project_background.h2.include_evidence_in_prompt` 当前默认 `false`；证据会写入 trace，但不默认注入章节 prompt
- `processing.project_background.h2.min_evidence_blocks` 是生成摘要所需的证据片段下限，低于该值会触发回退
- `processing.project_background.h2.fallback` 支持 `global` / `raw_evidence` / `empty`，分别表示回退全局背景、回退原文片段、或不注入项目背景
- `processing.project_background.h2.cache_dir` 默认相对 `project.root_dir` 解析，用于保存 H2 背景 JSON 缓存
- `processing.knowledge.*` 仅作为旧配置兼容字段保留；当前章节生成 prompt 不再注入 `knowledge_context`
- `processing.chapter_facts.*` 控制正文 facts 提炼与缓存刷新边界；`auto_extract_on_batch` 只建议用于批量生成路径
- `processing.full_context.chapter_writing_plan.*` 只在 `full_context` 下生效，用于在章节任务卡中额外插入“章节写作计划”
- 开启后会增加一次辅助 LLM 调用；当前实现会尽量复用正文扩写的 system prompt 与 full-context 参考前缀，以改善 prompt cache 命中率
- auto 模式下的需求检索专业参数不再写入 YAML，也不在配置编辑器展示；如需调整，放入 `.env.local` 或外部环境变量：
  - `BID_WRITER_AUTO_REQUIREMENTS_TOP_K`，默认 `8`
  - `BID_WRITER_AUTO_RETRIEVAL_LEXICAL_ENABLED`，默认 `true`
  - `BID_WRITER_AUTO_RETRIEVAL_VECTOR_ENABLED`，默认 `false`
  - `BID_WRITER_AUTO_RETRIEVAL_TOP_K_LEXICAL`，默认 `20`
  - `BID_WRITER_AUTO_RETRIEVAL_TOP_K_VECTOR`，默认 `20`
  - `BID_WRITER_AUTO_RETRIEVAL_TOP_K_FUSED`，默认 `30`
  - `BID_WRITER_AUTO_RETRIEVAL_TOP_K_FINAL`，默认 `8`
  - `BID_WRITER_AUTO_RETRIEVAL_MIN_FUSED_SCORE`，默认 `0.0`
- 旧配置中的 `processing.auto.requirements_top_k` 与 `processing.hybrid_extract.retrieval.*` 仍作为兼容回退读取；新建或通过配置编辑器保存时不再导出这些字段
- 每条链路自己的参数挂在各自子块下
- `verify_enabled` 统一表达原先 `rerank_enabled` / `llm_verify_enabled` 那条候选校验链路

### 3.4 `fact_cards`

```yaml
fact_cards:
  enabled: true
  cards:
    - id: "fact-card-1"
      name: "企业资质"
      content: "具备建筑工程施工总承包一级资质。"
      category: "资质"
      scope: "global"        # global / local
      enforcement: "strong"  # strong / reference
      active: true
      source:
        type: "manual"  # 或 "chapter_extract"
        chapter_path: ""
        extraction_instruction: ""
      created_at: "2026-04-24T10:00:00+08:00"
      updated_at: "2026-04-24T10:00:00+08:00"
  chapter_defaults:
    "综合服务项目投标方案 > 项目实施方案 > 质量保障措施":
      should_reference: true
      selections:
        - card_id: "fact-card-1"
          selected: false
        - card_id: "fact-card-2"
```

说明：

- `fact_cards.enabled` 控制是否在 GUI 中暴露事实卡片相关入口，以及是否允许单章节/批量生成接入事实卡片模式
- `cards` 是项目级事实卡片库；可在“事实卡片库”窗口编辑名称、分类和内容，保存时保留已有卡片 ID 和来源，避免章节已保存引用关系失效
  - `manual`：用户直接录入或在卡片库窗口新增的卡片
  - `chapter_extract`：从已生成章节正文手动提炼后，经草稿审阅确认保存，也可在卡片库窗口修订名称和内容
- `scope` 只支持 `global` / `local`：全局卡片在事实卡片模式下默认进入每个章节，并可在生成参数窗口中按章节取消；局部卡片只通过章节显式选择或章节已保存引用关系进入 prompt
- `enforcement` 只支持 `strong` / `reference`：强制卡片要求扩写结果保持一致，参考卡片仅作为可引用素材
- `chapter_defaults` 以**章节完整路径**为 key：`should_reference` 保存本章节是否要引用事实卡片；`selections` 保存局部卡片默认选中，以及全局卡片在该章节被用户取消时的 `{card_id: "...", selected: false}`
- 旧版纯列表格式仍可读取；新保存会写入 `{should_reference, selections}` 结构，以区分“本章要引用但暂无命中卡片”和“本章不引用事实卡片”
- 开启事实卡片模式后，本次章节扩写会先检查当前章节已保存的 `should_reference`；若为 `false`，本章不注入任何事实卡片；否则默认纳入 active 全局卡片，排除当前章节已保存引用关系中的全局取消项，并使用显式选择或章节已保存引用关系中的局部卡片；若没有可用卡片，则不注入投标方事实上下文

### 3.5 模型环境变量

```dotenv
BID_WRITER_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_API_KEY=your-api-key
BID_WRITER_MODEL=gpt-5.4
BID_WRITER_TEMPERATURE=0.7
BID_WRITER_MAX_TOKENS=10000
BID_WRITER_TIMEOUT_SECONDS=120
BID_WRITER_MAX_RETRIES=3

BID_WRITER_PRUNING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_PRUNING_API_KEY=your-api-key
BID_WRITER_PRUNING_MODEL=gpt-5.4
BID_WRITER_PRUNING_TEMPERATURE=0.2
BID_WRITER_PRUNING_MAX_TOKENS=1200
BID_WRITER_PRUNING_TIMEOUT_SECONDS=60
BID_WRITER_PRUNING_MAX_RETRIES=2

BID_WRITER_EMBEDDING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_EMBEDDING_API_KEY=your-api-key
BID_WRITER_EMBEDDING_MODEL=text-embedding-3-large
BID_WRITER_EMBEDDING_BATCH_SIZE=64
BID_WRITER_EMBEDDING_REBUILD_ON_SOURCE_CHANGE=true
```

说明：

- `.env.local` 与外部环境变量是模型参数的唯一推荐入口；YAML 中的旧 `models.*` / `api.*` / `context_pruning.api.*` 字段不再参与模型参数读取
- 外部 shell 中已设置的环境变量优先级最高，其次是配置文件同目录下的 `.env.local`，再其次是 `.env`
- `embedding_cache` 默认创建在执行入口文件同级目录，不再通过 YAML 配置

### 3.6 `runtime`

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

- `runtime.trace.directory` 这类配置内运行产物路径默认相对配置文件目录解析
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

兼容原则：

- 新 schema 优先级高于旧 schema
- 旧业务字段继续可读，但不再作为推荐写法
- 旧模型字段如 `models.*`、`api.*`、`context_pruning.api.*` 会被配置编辑器清理，不再参与模型参数读取
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
