# 标书撰写系统 RESTful API 设计方案

## 技术选型

- **Web框架**: FastAPI（轻量级异步框架，与当前代码风格匹配）
- **认证**: 暂不需要
- **流式输出**: SSE (Server-Sent Events) - 用于AI内容实时显示

## 一、数据流总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API 入口 (main.py)                              │
│                        BidWriter 类作为核心编排器                              │
└─────────────────────────────────────────────────────────────────────────────┘
           │                    │                    │                    │
           ▼                    ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   /config/*      │ │   /outline/*     │ │   /expand/*      │ │   /history/*     │
│   配置管理模块    │ │   大纲解析模块   │ │   AI生成模块     │ │   历史记录模块   │
└──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘
           │                    │                    │                    │
           │                    ▼                    │                    ▼
           │           ┌──────────────────┐          │           ┌──────────────────┐
           │           │   file_saver.py  │◄─────────┘           │   history.json   │
           │           │   文件保存模块    │                      │   持久化存储      │
           │           └──────────────────┘                      └──────────────────┘
           │                    │
           └────────────────────┴────────────────────────► 输出目录 ./output/*.md
```

---

## 二、建议的 RESTful API 端点

### 1. 配置管理端点 `/api/config`

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| GET | `/api/config` | 获取当前配置 | 无 | 全部配置项（敏感信息除外） |
| PUT | `/api/config` | 更新配置 | JSON配置对象 | 更新后的配置 |
| GET | `/api/config/requirements` | 获取招标需求内容 | 无 | `bid_requirements` 文本 |
| PUT | `/api/config/requirements` | 更新招标需求 | Markdown文本 | 成功状态 |
| GET | `/api/config/scoring` | 获取评分标准内容 | 无 | `scoring_criteria` 文本 |
| PUT | `/api/config/scoring` | 更新评分标准 | Markdown文本 | 成功状态 |
| POST | `/api/config/reload` | 重新加载配置 | 无 | 重新加载后的配置 |

**数据来源**: `config.py` 中的 `Config` 类

- 配置文件: `config.yaml`
- 招标需求文件: `bid_requirements_file`
- 评分标准文件: `scoring_criteria_file`

---

### 2. 大纲管理端点 `/api/outline`

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| GET | `/api/outline` | 获取完整大纲结构 | 无 | 树形结构的标题列表 |
| GET | `/api/outline/content` | 获取大纲原始内容 | 无 | Markdown文本 |
| PUT | `/api/outline/content` | 更新大纲内容 | Markdown文本 | 解析后的大纲结构 |
| GET | `/api/outline/headings` | 获取所有标题节点 | `?level=N` (可选) | HeadingNode数组 |
| GET | `/api/outline/leaves` | 获取叶子节点（可扩写） | 无 | 只有子节点的标题列表 |
| GET | `/api/outline/{title}` | 根据标题查找节点 | 路径参数: title | HeadingNode详情 |
| GET | `/api/outline/{title}/context` | 获取标题上下文路径 | 路径参数: title | 完整路径字符串 |

**数据来源**: `outline_parser.py` 中的 `OutlineParser` 类

- 输入: Markdown大纲文本（来自 `Config.get_outline_content()`）

**HeadingNode 数据结构**:

```json
{
  "level": 1,
  "title": "第一章 项目概述",
  "full_path": "第一章 项目概述",
  "line_number": 1,
  "children": []
}
```

---

### 3. 内容扩写端点 `/api/expand` (核心功能)

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| POST | `/api/expand` | 扩写单个标题 | 见下方 | 流式/完整内容 |
| POST | `/api/expand/stream` | 流式扩写 | 见下方 | SSE流式响应 |
| POST | `/api/expand/batch` | 批量扩写 | 标题数组+参数 | 任务ID + 状态 |
| GET | `/api/expand/{taskId}` | 查询扩写任务状态 | 路径参数: taskId | 任务状态+结果 |
| POST | `/api/expand/{taskId}/cancel` | 取消扩写任务 | 路径参数: taskId | 取消状态 |

**POST `/api/expand` 请求体**:

```json
{
  "heading": {
    "title": "1.1.1 项目背景",
    "path": "第一章 项目概述 > 1.1 项目背景 > 1.1.1 项目背景"
  },
  "additional_requirements": "请重点突出技术创新",
  "min_words": 500,
  "stream": true
}
```

**POST `/api/expand/stream` 响应 (SSE)**:

```
data: {"chunk": "第一段内容..."}
data: {"chunk": "第二段内容..."}
data: {"chunk": "[DONE]"}
```

**POST `/api/expand/batch` 请求体**:

```json
{
  "items": [
    {
      "heading": {"title": "...", "path": "..."},
      "additional_requirements": "要求1",
      "min_words": 500
    },
    {
      "heading": {"title": "...", "path": "..."},
      "additional_requirements": "要求2",
      "min_words": 800
    }
  ],
  "parallel": false
}
```

**数据来源**: `ai_writer.py` 中的 `AIWriter` 类

- 构建提示词: `build_prompt(heading, additional_requirements, min_words)`
- 调用AI: `expand(heading, additional_requirements, min_words, stream)`
- 依赖配置: `Config.role`, `Config.bid_requirements`, `Config.scoring_criteria`

---

### 4. 文件管理端点 `/api/files`

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| GET | `/api/files` | 列出输出目录文件 | `?directory=/path` (可选) | 文件列表 |
| GET | `/api/files/{filename}` | 读取文件内容 | 路径参数: filename | Markdown内容 |
| POST | `/api/files` | 保存内容到文件 | 见下方 | 文件路径 |
| PUT | `/api/files/{filename}` | 更新文件内容 | Markdown文本 | 更新后的文件路径 |
| DELETE | `/api/files/{filename}` | 删除文件 | 路径参数: filename | 删除状态 |
| GET | `/api/files/{filename}/metadata` | 获取文件元数据 | 路径参数: filename | 创建时间、字数等 |
| POST | `/api/files/preview` | 预览保存效果 | Markdown文本 | 渲染后的HTML |

**POST `/api/files` 请求体**:

```json
{
  "title": "1.1.1 项目背景分析",
  "content": "# 项目背景分析\n\n详细内容...",
  "directory": "./output",
  "overwrite": false
}
```

**GET `/api/files` 响应**:

```json
{
  "directory": "./output",
  "files": [
    {
      "name": "1.1.1_项目背景分析.md",
      "size": 1024,
      "created_at": "2025-01-15T10:30:00Z",
      "word_count": 520
    }
  ]
}
```

**数据来源**: `file_saver.py` 中的 `FileSaver` 类

- `sanitize_filename(title)` - 文件名清理
- `get_unique_filepath(base_filename)` - 防止冲突
- `save(title, content, include_title, overwrite)` - 保存文件

---

### 5. 历史记录端点 `/api/history`

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| GET | `/api/history` | 获取历史记录列表 | `?limit=20&offset=0` | HistoryRecord数组 |
| GET | `/api/history/{id}` | 获取单条记录 | 路径参数: id | HistoryRecord详情 |
| GET | `/api/history/statistics` | 获取统计信息 | 无 | 统计数据 |
| GET | `/api/history/search` | 搜索历史记录 | `?title=关键词` | 匹配的记录 |
| PUT | `/api/history/{id}/status` | 更新记录状态 | `?status=success` | 更新后的记录 |
| DELETE | `/api/history/{id}` | 删除单条记录 | 路径参数: id | 删除状态 |
| DELETE | `/api/history` | 清空所有历史 | 无 | 清空状态 |

**GET `/api/history` 响应**:

```json
{
  "total": 50,
  "limit": 20,
  "offset": 0,
  "records": [
    {
      "id": "20250115103000123456",
      "timestamp": "2025-01-15T10:30:00Z",
      "heading_title": "1.1.1 项目背景分析",
      "heading_path": "第一章 项目概述 > 1.1 项目背景 > 1.1.1 项目背景",
      "additional_requirements": "请重点突出技术创新",
      "min_words": 500,
      "actual_words": 680,
      "output_file": "./output/1.1.1_项目背景分析.md",
      "status": "success"
    }
  ]
}
```

**GET `/api/history/statistics` 响应**:

```json
{
  "total": 50,
  "success": 45,
  "failed": 3,
  "modified": 2,
  "total_words": 125000,
  "success_rate": 0.9
}
```

**数据来源**: `history.py` 中的 `HistoryManager` 类

- 持久化: `history.json` 文件
- 核心方法: `load()`, `save()`, `add_record()`, `get_statistics()`

---

### 6. 工具端点 `/api/utils`

| 方法 | 端点 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| GET | `/api/utils/word-count` | 统计中文字数 | `?text=内容` | 字数统计 |
| POST | `/api/utils/sanitize-filename` | 清理文件名 | `{"title": "标题"}` | 合法文件名 |
| GET | `/api/utils/directories` | 获取可用输出目录 | 无 | 目录列表 |
| POST | `/api/utils/check-filename` | 检查文件名是否可用 | `{"filename": "xxx"}` | 是否可用+建议 |

---

## 三、关键数据结构映射

### HeadingNode → JSON

```python
@dataclass
class HeadingNode:
    level: int          # 标题级别 1-6
    title: str          # 标题文本
    full_path: str      # 完整路径 "1.1 > 1.1.1 > 标题"
    line_number: int    # 行号
    children: List["HeadingNode"]  # 子节点
```

### HistoryRecord → JSON

```python
@dataclass
class HistoryRecord:
    id: str                      # 时间戳ID
    timestamp: str               # ISO时间
    heading_title: str           # 标题
    heading_path: str            # 完整路径
    additional_requirements: str # 附加要求
    min_words: int               # 最低字数
    actual_words: int            # 实际字数
    output_file: str             # 输出文件路径
    status: str                  # success/failed/modified
```

### ExpansionParams → JSON

```json
{
  "heading": {
    "title": "1.1.1 项目背景",
    "path": "第一章 > 1.1 > 1.1.1"
  },
  "additional_requirements": "要求",
  "min_words": 500
}
```

---

## 四、文件 I/O 操作映射

| 操作 | 原模块 | 新API端点 | HTTP方法 |
|------|--------|----------|----------|
| 读取配置 | `Config.load()` | `/api/config` | GET |
| 读取大纲 | `Config.get_outline_content()` | `/api/outline/content` | GET |
| 解析大纲 | `OutlineParser.parse()` | `/api/outline` | GET |
| AI扩写 | `AIWriter.expand()` | `/api/expand` | POST |
| 保存文件 | `FileSaver.save()` | `/api/files` | POST |
| 读取历史 | `HistoryManager.load()` | `/api/history` | GET |
| 写入历史 | `HistoryManager.add_record()` | 自动触发 | POST (expand时) |

---

## 五、建议的开发优先级

1. **P0 - 核心功能**

   - `POST /api/expand` - 扩写API（最核心）
   - `GET /api/outline` - 大纲结构API

2. **P1 - 基础支撑**

   - `GET/PUT /api/config` - 配置管理
   - `GET/POST /api/files` - 文件管理
   - `GET /api/history` - 历史记录

3. **P2 - 增强功能**

   - 流式扩写 `POST /api/expand/stream`
   - 批量扩写 `POST /api/expand/batch`
   - 统计信息 `GET /api/history/statistics`

4. **P3 - 工具功能**

   - 字数统计
   - 文件名清理
   - 搜索功能

---

# 六、FastAPI 实现建议

## 1. 新增文件结构

```
bid_writer/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── config.py        # /api/config 端点
│   │   ├── outline.py       # /api/outline 端点
│   │   ├── expand.py        # /api/expand 端点
│   │   ├── files.py         # /api/files 端点
│   │   └── history.py       # /api/history 端点
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py       # Pydantic 数据模型
│   │   └── exceptions.py    # 自定义异常
│   └── deps.py              # 依赖注入（获取配置、历史等）
```

## 2. 需要添加的依赖

```yaml
# pyproject.toml 或 requirements.txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sse-starlette>=2.0.0
```

## 3. 核心 Pydantic Models (schemas.py)

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# 配置相关
class ConfigResponse(BaseModel):
    api_base_url: str
    model: str
    temperature: float
    max_tokens: int
    output_directory: str
    history_enabled: bool

class RequirementsUpdate(BaseModel):
    content: str

# 大纲相关
class HeadingNodeModel(BaseModel):
    level: int
    title: str
    full_path: str
    line_number: int
    children: List["HeadingNodeModel"] = []

class OutlineResponse(BaseModel):
    headings: List[HeadingNodeModel]
    total_count: int
    leaf_count: int

# 扩写相关
class ExpandRequest(BaseModel):
    heading: dict  # {"title": "...", "path": "..."}
    additional_requirements: str = ""
    min_words: int = 500
    stream: bool = True

class ExpandResponse(BaseModel):
    title: str
    content: str
    word_count: int
    output_file: Optional[str] = None

# 文件相关
class FileSaveRequest(BaseModel):
    title: str
    content: str
    directory: str = "./output"
    overwrite: bool = False

class FileInfo(BaseModel):
    name: str
    size: int
    created_at: datetime
    word_count: int

# 历史相关
class HistoryRecordModel(BaseModel):
    id: str
    timestamp: datetime
    heading_title: str
    heading_path: str
    additional_requirements: str
    min_words: int
    actual_words: int
    output_file: str
    status: str

class HistoryListResponse(BaseModel):
    total: int
    records: List[HistoryRecordModel]

class StatisticsResponse(BaseModel):
    total: int
    success: int
    failed: int
    modified: int
    total_words: int
    success_rate: float
```

## 4. 依赖注入 (deps.py)

```python
from typing import Annotated
from fastapi import Depends
from ..config import Config
from ..history import HistoryManager
from ..file_saver import FileSaver

# 全局实例（简化方案，生产环境可用 lifespan）
_config: Optional[Config] = None
_history: Optional[HistoryManager] = None
_file_saver: Optional[FileSaver] = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config

def get_history() -> HistoryManager:
    global _history
    if _history is None:
        _history = HistoryManager()
    return _history

def get_file_saver() -> FileSaver:
    global _file_saver
    if _file_saver is None:
        config = get_config()
        _file_saver = FileSaver(config.output_directory)
    return _file_saver

ConfigDep = Annotated[Config, Depends(get_config)]
HistoryDep = Annotated[HistoryManager, Depends(get_history)]
FileSaverDep = Annotated[FileSaver, Depends(get_file_saver)]
```

## 5. 流式扩写实现示例 (routes/expand.py)

```python
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from ..ai_writer import AIWriter
from ..deps import ConfigDep, get_ai_writer

router = APIRouter()

@router.post("/stream")
async def expand_stream(
    request: ExpandRequest,
    config: ConfigDep,
    ai_writer: Annotated[AIWriter, Depends(get_ai_writer)]
):
    """流式扩写 - SSE响应"""

    async def generate():
        try:
            # 构建提示词
            heading = create_heading_node(request.heading)
            messages = ai_writer.build_prompt(
                heading,
                request.additional_requirements,
                request.min_words
            )

            # 流式生成
            async for chunk in ai_writer._stream_expand(messages):
                yield {"data": chunk}
            yield {"data": "[DONE]"}
        except Exception as e:
            yield {"data": f"error: {str(e)}"}

    return EventSourceResponse(generate())

@router.post("")
async def expand(
    request: ExpandRequest,
    config: ConfigDep,
    ai_writer: Annotated[AIWriter, Depends(get_ai_writer)]
) -> ExpandResponse:
    """同步扩写 - 完整内容返回"""
    # 实现逻辑...
```

## 6. 启动命令

```bash
# 开发模式
uv run uvicorn bid_writer.api.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uv run uvicorn bid_writer.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 7. API 文档

启动后访问: `http://localhost:8000/docs` - 自动生成的 Swagger UI
