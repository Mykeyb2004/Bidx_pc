# 自动标书撰写系统

基于大语言模型的桌面版标书撰写工具。系统会读取 Markdown 大纲，在 GUI 中按章节树选择叶子节点，结合招标需求、评分标准和附加要求生成章节内容，并将结果保存到本地 Markdown 文件中。

当前实现基于 Python + Tkinter，模型调用使用 OpenAI Python SDK，因此可接入 OpenAI 兼容接口的模型服务。

## 当前功能

- 解析 Markdown 大纲，支持 `#` 到 `######` 的多级标题，自动构建父子树结构
- GUI 中展示大纲树，支持多选叶子节点批量生成
- 支持搜索标题、按“未生成 / 部分完成 / 已完成”筛选章节
- 启动时自动发现 `config*.yaml` / `config*.yml`，并记住上次成功使用的配置文件
- 生成前可填写附加要求、设置最低字数
- 生成时流式显示模型输出
- 批量模式下自动保存，并显示总进度、当前任务、成功/跳过/失败统计
- 根据章节完整路径生成稳定文件名后缀，尽量避免同名标题覆盖
- 扫描输出目录后回显每个章节的完成状态
- 支持直接预览已生成文件
- 按大纲顺序整合已生成章节，输出一份完整的 Markdown 标书草稿

## 环境要求

- Python `>= 3.10`
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境和依赖
- 运行 GUI 需要本机 Python 具备 Tk 支持

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
- `inputs.outline_file`：Markdown 大纲文件
- `inputs.bid_requirements_file` 或 `inputs.bid_requirements`：招标需求
- `inputs.scoring_criteria_file` 或 `inputs.scoring_criteria`：评分标准
- `output.directory`：输出目录

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
6. 对已生成章节，可使用“预览所选”直接查看保存后的文件内容
7. 需要汇总时，点击“整合标书”，系统会按大纲顺序合并已有章节

## 配置说明

项目同时兼容两种配置写法：

- 推荐新写法：将输入资源放在 `inputs` 下
- 兼容旧写法：`outline_file`、`bid_requirements`、`scoring_criteria` 也可以直接写在根级

一个可直接参考的配置示例如下：

```yaml
api:
  # API 配置从 .env / .env.local 自动读取

role: |
  你是一位专业的标书撰写专家。

inputs:
  outline_file: "./outline.md"
  bid_requirements_file: "./项目要求/项目采购需求.md"
  scoring_criteria_file: "./项目要求/评分标准.md"
  # 也支持直接写全文：
  # bid_requirements: |
  #   这里直接写招标需求正文
  # scoring_criteria: |
  #   这里直接写评分标准正文

generation:
  default_min_words: 3000
  min_words_min: 100
  min_words_max: 15000
  min_words_step: 100
  stream: true

prompt:
  output_format: "纯正文"
  first_line_template: ""
  allow_markdown_headings: false
  allow_english_terms: false
  bidder_name: "示例投标主体名称"
  max_tables_per_section: 4
  summary_title: "章节小结"
  hard_constraints:
    - "严禁使用Markdown标题符号（#）。"
    - "禁止输出评论性、意图解释性的内容。"
    - "禁止输出分割线。"
  extra_rules:
    - "内容要专业、严谨，符合标书撰写规范"

# prompt 字段说明
# - output_format: 写入任务卡，明确正文组织方式
# - first_line_template: 非空时强制首行模板
# - allow_markdown_headings: false 时自动禁止输出 # 标题
# - allow_english_terms: false 时自动禁止不必要的英文、中英对照
# - max_tables_per_section: 大于 0 时要求章节插入 1 至 N 个 Markdown 表格；为 0 时禁止输出 Markdown 表格
# - summary_title: 为空时不另设总结；非空时指定总结标题名称
# - bidder_name: 写入任务卡和 system 强约束
# - hard_constraints: 注入 system 的最高优先级规则
# - extra_rules: 注入 user prompt 的“其他写作要求”段落

context_pruning:
  enabled: false
  debug_dump: false
  local_outline:
    include_ancestors: true
    include_siblings: true
    max_siblings: 8
  scoring:
    enabled: true
    max_rows: 4
  requirements_brief:
    enabled: false
    fallback: "rule_only"
  api:
    model: "gpt-4o-mini"
    temperature: 0.2
    max_tokens: 1200
    timeout_seconds: 60
    max_retries: 2

generation_trace:
  enabled: false
  mode: "full"
  write_prompt: true
  write_output: true
  write_context: true
  write_summary: true
  redact_sensitive: true

output:
  directory: "./output"
  prefix: ""
  include_title_header: true
  overwrite_existing: true
  normalize_soft_line_breaks_on_merge: false
  filename_max_length: 100
  empty_filename_fallback: "untitled"
```

### 配置项补充说明

- `api.base_url` 不限于 OpenAI 官方地址，只要接口兼容 OpenAI Chat Completions 即可
- 程序会先读取配置文件同目录下的 `.env`，再读取 `.env.local`；`.env.local` 可覆盖 `.env`，但不会覆盖你外部 shell 已显式设置的环境变量
- 最简单的用法是把整组 API 参数都写进 `.env.local`
- `inputs.*_file` 路径会按“相对于配置文件所在目录”解析
- `bid_requirements`、`scoring_criteria` 支持直接写长文本，也兼容“内容字段里只写一个文件路径”的旧配置
- `prompt.first_line_template` 支持 `{title}` 和 `{full_path}` 占位符
- `prompt.first_line_template` 设为空字符串时，模型将直接输出正文而不重复当前章节标题
- `prompt.allow_markdown_headings` 控制是否允许模型输出 Markdown 标题符号 `#`
- `prompt.bidder_name` 用于统一约束投标主体名称
- `prompt.hard_constraints` 用于配置高优先级输出强约束，程序会注入到 system prompt
- `context_pruning.*` 用于配置章节级上下文裁剪；当前主要用于局部大纲、评分路由和需求 brief 的参数约束
- `context_pruning.api.base_url` / `context_pruning.api.api_key` 不建议写入 YAML；请使用 `.env.local` 中的 `BID_WRITER_PRUNING_*` 环境变量提供敏感信息
- `generation_trace.*` 用于记录单次章节扩写的完整 trace；默认输出到 `output/_generation_traces/`

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
