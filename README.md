# 自动标书撰写系统

基于大语言模型的桌面版标书撰写工具。系统会读取 Markdown 大纲，在 GUI 中按章节树选择叶子节点，结合招标需求、评分标准和附加要求生成章节内容，并将结果保存到本地 Markdown 文件中。

当前实现基于 Python + Tkinter，并在运行环境支持时自动启用 `ttkbootstrap` 主题层优化桌面界面观感；若本机 Pillow/Tk 桥接不可用，则自动回退到内建 `ttk` 主题。模型调用使用 OpenAI Python SDK，因此可接入 OpenAI 兼容接口的模型服务。

## 当前功能

- 解析 Markdown 大纲，支持 `#` 到 `######` 的多级标题，自动构建父子树结构
- GUI 中展示大纲树，支持多选叶子节点批量生成
- 支持搜索标题、按“未生成 / 部分完成 / 已完成”筛选章节
- 启动时自动发现 `config*.yaml` / `config*.yml`，并记住上次成功使用的配置文件
- 生成前可填写附加要求、设置最低字数
- 生成时流式显示模型输出
- 批量模式下自动保存，并显示总进度、当前任务、成功/失败统计
- 根据章节完整路径生成稳定文件名后缀，尽量避免同名标题覆盖
- 扫描输出目录后回显每个章节的完成状态
- 主窗口右侧常驻正文工作区，单选章节即可直接查看已生成内容
- 按大纲顺序整合已生成章节，输出一份完整的 Markdown 标书草稿

## 环境要求

- Python `>= 3.10`
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境和依赖
- 运行 GUI 需要本机 Python 具备 Tk 支持
- 环境支持时默认使用 `ttkbootstrap` 的 `litera` 亮色主题；若桥接不可用则自动回退到内建 `clam`
- 可通过环境变量 `BID_WRITER_GUI_THEME` 覆盖 `ttkbootstrap` 的内置主题名

## 安装与运行

### 1. 创建虚拟环境

推荐先在项目根目录创建一个本地虚拟环境：

```bash
uv venv .venv
```

激活方式：

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

说明：

- `uv venv .venv` 会在当前项目下创建 `.venv` 虚拟环境
- 如果你不想手动激活，也可以直接使用 `uv run ...` 运行命令
- `uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 安装依赖，并在需要时使用项目虚拟环境

### 2. 安装依赖

```bash
uv sync
```

### 3. 准备配置文件

可以复制示例配置后再修改：

```bash
cp config.example.yaml config.yaml
cp .env.example .env.local
```

然后把 API 参数写到 `.env.local`：

```bash
BID_WRITER_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_MODEL=gpt-4o-mini
BID_WRITER_TEMPERATURE=0.7
BID_WRITER_MAX_TOKENS=8000
BID_WRITER_API_KEY=your-api-key

# 可选：章节上下文裁剪 / 需求 brief 辅助模型
BID_WRITER_PRUNING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_PRUNING_MODEL=gpt-4o-mini
BID_WRITER_PRUNING_API_KEY=your-api-key

# 可选：向量召回 embedding 服务
# 这里写服务根路径，不要直接写到 /embeddings
BID_WRITER_EMBEDDING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_EMBEDDING_API_KEY=your-api-key
```

至少需要配置：

- `BID_WRITER_API_BASE_URL`：写入 `.env.local` 的模型服务地址
- `BID_WRITER_API_KEY`：写入 `.env.local` 的 API Key
- `BID_WRITER_MODEL`：写入 `.env.local` 的模型名称
- `BID_WRITER_PRUNING_API_BASE_URL` / `BID_WRITER_PRUNING_API_KEY`：可选的章节裁剪辅助模型敏感配置，建议仅写入 `.env.local`
- `BID_WRITER_EMBEDDING_API_BASE_URL` / `BID_WRITER_EMBEDDING_API_KEY`：可选的向量召回 embedding 服务敏感配置，建议仅写入 `.env.local`
- `project.inputs.outline_file`：Markdown 大纲文件
- `project.inputs.bid_requirements_file` 或 `project.inputs.bid_requirements`：招标需求
- `project.inputs.scoring_criteria_file` 或 `project.inputs.scoring_criteria`：评分标准
- `project.output_dir`：输出目录

### 4. 启动程序

```bash
uv run python run.py
```

或使用已注册的命令行入口：

```bash
uv run bid-writer
```

指定配置文件：

```bash
uv run python run.py --config config_chatgpt.yaml
```

```bash
uv run bid-writer --config config_chatgpt.yaml
```

## 使用流程

1. 启动程序后，系统会优先尝试加载上次使用的配置文件，否则回退到 `config.yaml` 或当前目录下其它 `config*.yaml`
2. 载入大纲后，在左侧树中展开章节，选择要生成的叶子节点
3. 按需输入附加扩写要求，并设置最低字数
4. 执行生成
5. 批量生成时结果会自动保存到输出目录
6. 单选章节时，主窗口右侧会直接显示已生成正文；生成过程中右侧也会实时显示当前章节内容
7. 需要汇总时，点击“整合标书”，系统会按大纲顺序合并已有章节

## 配置说明

项目当前推荐使用按“信息性质”分层的 canonical schema：

- `project`：项目固有信息、输入资源、输出目录
- `writing`：角色设定、写作规范、提示词约束、字数要求
- `processing`：业务处理路径与章节级提炼参数
- `models`：主模型、辅助模型、embedding 的非敏感参数
- `runtime`：stream、trace、debug、输出细节与合并行为

旧写法仍然兼容，包括：

- 根级 `outline_file` / `bid_requirements` / `scoring_criteria`
- `inputs.*`
- `prompt.*`
- `context_pruning.*`
- `generation_trace.*`
- `api.*`

一个可直接参考的配置示例如下：

```yaml
project:
  root_dir: "/path/to/bid-project"
  bidder_name: "示例投标主体名称"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./项目要求/项目采购需求.md"
    scoring_criteria_file: "./项目要求/评分标准.md"
  output_dir: "./output"

writing:
  role: |
    你是一位专业的标书撰写专家。
  min_words:
    default: 3000
    min: 100
    max: 15000
    step: 100
  output_format: "纯正文"
  first_line_template: ""
  allow_markdown_headings: false
  allow_english_terms: false
  max_tables_per_section: 4
  summary_title: "章节小结"
  hard_constraints:
    - "严禁使用Markdown标题符号（#）。"
    - "禁止输出评论性、意图解释性的内容。"
    - "禁止输出分割线。"
  extra_rules:
    - "内容要专业、严谨，符合标书撰写规范"

processing:
  path: "legacy_rule" # 可改为 full_context，直接把采购需求与评分标准全文送入提示词
  project_background:
    enabled: true
    max_chars: 800
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
    requirement_brief_enabled: false
  hybrid_extract:
    unavailable_policy: "fallback_legacy"
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

models:
  # generation.* / pruning.* / embedding.* 的敏感值仍建议放在 .env.local
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

runtime:
  stream:
    enabled: true
    idle_timeout_seconds: 12
  trace:
    enabled: false
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

### 配置项补充说明

- `models.generation.base_url` 不限于 OpenAI 官方地址，只要接口兼容 OpenAI Chat Completions 即可；同名环境变量优先级更高
- 程序会先读取配置文件同目录下的 `.env`，再读取 `.env.local`；`.env.local` 可覆盖 `.env`，但不会覆盖你外部 shell 已显式设置的环境变量
- 最简单的用法是把整组 API 参数都写进 `.env.local`
- `processing.full_context.chapter_writing_plan.enabled=true` 时，会先为当前章节生成一个简短写作计划，并把它插入“章节任务卡”；该计划默认优先使用 pruning 模型生成
- `project.root_dir` 用于声明项目资料的根目录；`project.inputs.*` 和 `project.output_dir` 默认相对它解析
- `project.inputs.*_file` 支持路径；`project.inputs.bid_requirements`、`project.inputs.scoring_criteria` 也支持直接写长文本
- `writing.role_file` 可把大段角色设定单独存成文件，减少多个项目配置重复粘贴
- `writing.first_line_template` 支持 `{title}` 和 `{full_path}` 占位符
- `processing.path` 是当前项目唯一的章节处理路径入口：
  - `full_context`
  - `legacy_rule`
  - `hybrid_extract`
- canonical schema 不再推荐把“评分标准”和“采购需求”拆成两条可自由混搭的主链路；旧 mixed-mode 仅保留兼容
- `models.pruning.*` / `models.embedding.*` 只放非敏感参数；密钥和真实服务地址仍建议放 `.env.local`
- `runtime.trace.*` 用于记录单次章节扩写的完整 trace；默认输出到仓库下的 `log/generation_traces`
- 旧 `prompt.*` / `context_pruning.*` / `generation_trace.*` / `api.*` 写法仍兼容，但新项目建议只写 canonical schema
- 详细 schema 说明与迁移原则见 [docs/config_schema.md](./docs/config_schema.md)
- 配置字段或默认行为有变更时，请同步更新 [docs/config_schema.md](./docs/config_schema.md) 与 [config.example.yaml](./config.example.yaml)

### Prompt Contract 维护说明

- 当前 prompt contract 仍然由代码定义，核心装配路径在 `bid_writer/ai_writer.py`，维护者视角的 contract 说明见 `docs/prompt_contract.md`
- 现有 YAML 写法继续兼容，包含根级 `outline_file` / `bid_requirements` / `scoring_criteria` 以及 `inputs.*` 形式
- Phase 1 新增的是可观测性和摘要层，不要求你为现有配置补写新的 prompt contract 字段
- 回归命令：

```bash
uv run pytest tests/test_prompt_contract.py -q
```

- 这组测试会同时检查：
  - existing YAML 配置在没有新字段时仍能成功构建 prompt
  - `prompt_contract` 摘要层和原有 `prompt_sections` 细节层同时存在
- `generation_trace.redact_sensitive: true` 时，trace 只保留 `api_base_url` 的 host，不写入完整地址与任何密钥
- `output.normalize_soft_line_breaks_on_merge` 控制“整合标书”时是否把普通正文中的软回车合并回单段，默认关闭
- `output.overwrite_existing: true` 时，同一标题默认覆盖已有标准输出文件
- `output.prefix` 可为所有输出文件统一增加前缀

## 大纲格式

大纲使用标准 Markdown 标题语法，例如：

```markdown
# 第一章 项目概述
## 1.1 项目背景
### 1.1.1 政策依据
### 1.1.2 项目目标
## 1.2 实施范围
```

系统实际生成的是“叶子节点”：

- 某标题没有子标题时，该标题就是可生成章节
- 不要求必须固定是三级或四级标题
- 如果某一级标题下面还有子标题，则通常由更深层的叶子标题负责生成

## 输出规则

- 输出目录默认是 `./output`
- 每个章节保存为一个 `.md` 文件
- 文件名会做非法字符清理，并附加基于章节完整路径生成的稳定 ID
- “整合标书”会按大纲顺序拼接已生成章节，跳过缺失章节，输出新的 Markdown 文件

## 项目结构

```text
.
├── bid_writer/
│   ├── __init__.py
│   ├── ai_writer.py        # 模型请求、提示词构建、流式生成
│   ├── config.py           # 配置读取与兼容逻辑
│   ├── file_saver.py       # 文件命名、保存、已生成文件查找
│   ├── gui.py              # Tkinter 主界面
│   ├── gui_adapter.py      # GUI 与业务状态桥接
│   ├── gui_state.py        # GUI 状态持久化（记住上次配置）
│   ├── main.py             # 核心服务与整合逻辑
│   └── outline_parser.py   # Markdown 大纲解析
├── config.example.yaml
├── config.yaml
├── outline.md
├── run.py
├── pyproject.toml
└── README.md
```

## 开发说明

- 依赖管理使用 `uv`
- 建议所有运行和测试命令都使用 `uv run ...`
- 更新依赖锁文件：

```bash
uv lock
uv sync
```

## 已知注意事项

- 本项目当前没有自动化测试套件
- GUI 基于 Tkinter，若运行环境缺少 Tk，程序可能无法启动
- 模型生成质量高度依赖大纲质量、招标需求完整度和评分标准细化程度
