# 自动标书撰写系统

基于 Python + Tkinter 的桌面版标书撰写工具。程序读取 Markdown 大纲、采购需求和评分标准，调用兼容 OpenAI Chat Completions 的模型服务，为选中的章节生成标书正文，并把结果保存为本地 `.md` 文件。

虽然输出载体是 Markdown 文件，正文写作约束面向中文标书场景，默认会强制使用正式层级序号，如 `一、`、`（一）`、`1.`、`（1）`，而不是 Markdown 标题风格。

## 功能概览

- 解析 `#` 到 `######` 的 Markdown 大纲，按树结构展示章节
- 在 GUI 中搜索标题、按“未生成 / 部分完成 / 已完成”筛选并查看进度
- 选择叶子章节批量生成，生成过程支持流式显示和“当前标题完成后停止”
- 主窗口右侧常驻正文工作区，可直接预览已生成内容和当前流式输出
- 按大纲顺序整合已生成章节，输出一份完整的 Markdown 草稿
- 支持 `full_context`、`legacy_rule`、`hybrid_extract`、`auto` 四种处理路径
- 支持项目背景摘要、`full_context` 下章节写作计划、Mermaid 流程图数量控制
- 支持章节生成 trace，便于排查 prompt、上下文裁剪和模型输出
- 启动时自动发现 `config*.yaml` / `config*.yml`，并记住上次成功使用的配置
- 内置可视化配置编辑器，但当前完整支持的编辑路径以 `auto / full_context` 为主

## 环境要求

- Python `>= 3.10`
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖和运行命令
- 运行 GUI 需要本机 Python 具备 Tk 支持
- 若运行环境支持 Pillow/Tk 桥接，会自动启用 `ttkbootstrap` 主题；否则回退到内建 `ttk`

可选 GUI 环境变量：

- `BID_WRITER_GUI_THEME`：覆盖默认 `ttkbootstrap` 主题名，默认 `litera`
- `BID_WRITER_GUI_FONT_DELTA`：手动调大或调小 GUI 字号，例如 `1`

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 准备配置与环境变量

```bash
cp config.example.yaml config.yaml
cp .env.example .env.local
```

至少需要准备主生成模型的连接参数：

```dotenv
BID_WRITER_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_API_KEY=your-api-key
BID_WRITER_MODEL=gpt-4o-mini
```

常见可选参数：

```dotenv
BID_WRITER_TEMPERATURE=0.7
BID_WRITER_MAX_TOKENS=8000

# hybrid_extract / auto 相关辅助模型
BID_WRITER_PRUNING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_PRUNING_API_KEY=your-api-key
BID_WRITER_PRUNING_MODEL=gpt-4o-mini

# 启用向量召回时需要
BID_WRITER_EMBEDDING_API_BASE_URL=https://api.openai.com/v1
BID_WRITER_EMBEDDING_API_KEY=your-api-key
```

### 3. 启动程序

```bash
uv run python run.py
```

或使用入口命令：

```bash
uv run bid-writer
```

指定配置文件：

```bash
uv run python run.py --config config_公共服务满意度_auto.yaml
```

## 使用流程

1. 启动后，程序会按“显式参数 -> 上次成功配置 -> `config.yaml` -> 当前目录下其它 `config*.yaml`”的顺序寻找配置文件。
2. 加载大纲后，在左侧树中搜索、筛选并选择要生成的叶子章节。
3. 输入附加要求，设置目标篇幅基准值；系统会自动推导正文目标区间。
4. 执行“生成所选”，右侧工作区会实时显示当前章节输出。
5. 生成完成后，正文会自动保存到输出目录。
6. 需要汇总时，点击“整合标书”，程序会按大纲顺序合并现有章节。

说明：

- 当前界面文案主要按“四级标题”组织批量生成，但代码层面的实际生成单元是“叶子节点”
- “扫描输出状态”会重新扫描输出目录，刷新树上的完成情况
- “编辑当前配置”已可使用，但对 `legacy_rule / hybrid_extract / mixed` 配置的可视化编辑仍不完整；这类配置若在编辑器中直接保存，当前会按 `auto` 路径标准化导出，因此更适合继续直接维护 YAML

## 配置说明

当前代码优先支持 canonical schema：

- `project`：项目资料、输入文件、输出目录
- `writing`：角色设定、写作规则、篇幅和格式约束
- `processing`：章节处理路径与提炼参数
- `models`：主模型、辅助模型、embedding 的非敏感参数
- `runtime`：流式输出、trace、调试和文件输出行为

最小示例：

```yaml
project:
  root_dir: "/path/to/bid-project"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./采购需求.md"
    scoring_criteria_file: "./评分标准.md"
  output_dir: "./output"

writing:
  role: |
    你是一位专业的标书撰写专家。
  target_words:
    default: 1500

processing:
  path: "full_context"

models:
  generation:
    model: "gpt-4o-mini"

runtime:
  stream:
    enabled: true
```

处理路径说明：

- `full_context`：把采购需求和评分标准全文直接送入 prompt
- `legacy_rule`：使用规则链路提炼评分标准和采购需求
- `hybrid_extract`：使用检索摘录链路，可叠加 lexical / vector / verify
- `auto`：当前代码支持的组合路径，偏向 GUI 配置编辑器使用；运行时需要 pruning 连接配置

配置读取与优先级：

- 程序会先读取配置文件同目录下的 `.env`，再读取 `.env.local`
- `.env.local` 会覆盖 `.env`
- 已在外部 shell 中显式设置的环境变量优先级最高，不会被 `.env` 文件覆盖
- `project.inputs.*` 和 `project.output_dir` 默认相对 `project.root_dir` 解析
- `runtime.trace.directory`、`models.embedding.cache_dir` 等运行产物路径默认相对配置文件目录解析

兼容性说明：

- 旧字段仍兼容，包括根级 `outline_file` / `bid_requirements` / `scoring_criteria`、`prompt.*`、`context_pruning.*`、`generation_trace.*`、`api.*`
- 新项目建议优先参考 [config.example.yaml](./config.example.yaml) 和 [docs/config_schema.md](./docs/config_schema.md)

## 输出与调试产物

- 默认输出目录为 `project.output_dir`，通常是 `./output`
- 单章节输出文件名会清理非法字符，并附加基于章节完整路径生成的稳定 ID，例如 `质量保障措施__1a2b3c4d5e6f.md`
- `runtime.output.overwrite_existing=true` 时会覆盖标准输出文件；否则会自动追加编号后缀
- “整合标书”会按大纲顺序拼接已生成章节，跳过缺失章节，并生成新的 Markdown 文件
- 若启用 `runtime.trace.enabled=true`，默认会在 `log/generation_traces` 下落盘 trace
- GUI 会在工作区根目录保存 `.bid_writer_gui_state.json`，仅用于记住上次使用的配置文件

相关文档：

- [docs/config_schema.md](./docs/config_schema.md)：配置结构与兼容策略
- [docs/prompt_contract.md](./docs/prompt_contract.md)：prompt 装配说明
- [docs/extraction_modes_and_config.md](./docs/extraction_modes_and_config.md)：章节提炼模式说明
- [docs/generation_trace.md](./docs/generation_trace.md)：trace 目录结构与查看方式

## 测试与开发

项目已经包含 `pytest` 测试，不再是“无自动化测试”状态。常用命令：

```bash
uv run pytest -q
```

配置 / prompt 相关回归：

```bash
uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -q
```

GUI / 配置编辑器相关回归：

```bash
uv run pytest tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_gui_scaling.py -q
```

开发约定：

- 运行和测试命令统一优先使用 `uv run ...`
- 测试夹具在 [`tests/`](./tests/)
- 功能说明与分析文档在 [`docs/`](./docs/)
- 配置结构变更时，需要同步维护 `README.md`、[`docs/config_schema.md`](./docs/config_schema.md)、[`config.example.yaml`](./config.example.yaml)、相关 `config_*.yaml` 和测试夹具
- 调试日志放在 `log/` 目录

## 项目结构

```text
.
├── bid_writer/
│   ├── ai_writer.py              # prompt 构建、模型调用、正文后处理
│   ├── config.py                 # 配置解析、兼容层、环境变量读取
│   ├── context_pruner.py         # 章节级上下文提炼与检索路由
│   ├── file_saver.py             # 输出文件命名、保存、状态回查
│   ├── generation_trace.py       # trace 落盘
│   ├── gui.py                    # Tkinter 主界面
│   ├── config_editor*.py         # 配置编辑器模型、对话框与提示
│   ├── gui_adapter.py            # GUI 与核心状态桥接
│   ├── gui_state.py              # GUI 状态持久化
│   └── main.py                   # 应用入口与整合标书逻辑
├── docs/
├── tests/
├── config.example.yaml
├── run.py
├── pyproject.toml
└── README.md
```
