# 自动标书撰写系统

基于AI的智能标书内容生成工具，支持解析 Markdown 大纲、在 GUI 中选择标题、AI 扩写和文件保存。

## 功能特点

- 📄 **大纲解析**：支持解析 Markdown 格式的标书大纲（1-4级标题）
- 🖥️ **图形界面**：在 Tkinter GUI 中浏览大纲、选择四级标题并批量生成
- 🤖 **AI扩写**：调用Gemini模型进行专业内容生成
- 📝 **结果预览**：生成后预览内容，支持修改确认
- 💾 **自动保存**：以小标题为文件名保存到指定目录

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置系统

编辑 `config.yaml` 文件，配置以下内容：

- **API配置**：API地址、密钥、模型名称
- **角色设定**：AI撰写风格和专业背景
- **招标需求**：项目的招标需求文档
- **评分标准**：项目的评分标准
- **大纲文件**：标书大纲的文件路径

### 3. 准备大纲

创建或编辑标书大纲文件（默认为 `outline.md`），使用Markdown标题格式：

```markdown
# 第一章 项目概述
## 1.1 项目背景
### 1.1.1 政策背景
### 1.1.2 项目意义
```

### 4. 运行系统

```bash
uv run python run.py
```

或使用安装的命令：

```bash
uv run bid-writer
```

## 使用流程

1. 启动系统后，GUI 会自动加载大纲
2. 在树形结构中展开章节并选择四级标题
3. 输入附加扩写要求和最低字数
4. 等待 AI 生成内容
5. 预览生成结果，选择保存/修改/跳过
6. 内容自动保存到输出目录

## 配置说明

### config.yaml 示例

```yaml
# API配置
api:
  base_url: "https://api.ssopen.top/v1"
  api_key: "your-api-key"
  model: "gemini-2.5-pro"
  temperature: 0.7
  max_tokens: 8000

# 角色设定
role: |
  你是一位资深的标书撰写专家...

inputs:
  outline_file: "./outline.md"

# 输出配置
output:
  directory: "./output"
```

## 项目结构

```
.
├── bid_writer/
│   ├── __init__.py       # 包初始化
│   ├── config.py         # 配置管理
│   ├── outline_parser.py # 大纲解析
│   ├── ai_writer.py      # AI扩写引擎
│   ├── file_saver.py     # 文件保存
│   ├── gui.py            # GUI界面
│   ├── gui_adapter.py    # GUI适配层
│   └── main.py           # GUI共享核心
├── config.yaml           # 配置文件
├── outline.md            # 标书大纲
├── run.py                # 运行脚本
└── README.md             # 说明文档
```

## 许可证

MIT License
