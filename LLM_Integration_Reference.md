# LLM 集成代码参考文档

本文档提取了 BidX_simple 项目中所有与大模型（LLM）调用相关的代码，供其他代码库参考使用。

## 目录

1. [概述](#概述)
2. [依赖配置](#依赖配置)
3. [配置管理模块](#配置管理模块)
4. [AI 调用引擎](#ai-调用引擎)
5. [配置文件示例](#配置文件示例)
6. [使用示例](#使用示例)

---

## 概述

本项目使用 **OpenAI SDK** 来调用兼容 OpenAI API 格式的大模型服务（如 Gemini、ChatGPT 等）。核心设计包括：

- **配置管理**：通过 YAML 文件管理 API 配置、模型参数等
- **AI 调用引擎**：封装了流式和同步两种调用方式
- **提示词构建**：支持动态构建复杂的多上下文提示词
- **错误处理**：支持环境变量覆盖、文件路径解析等

---

## 依赖配置

### pyproject.toml

```toml
[project]
name = "bid-writer"
version = "1.0.0"
description = "自动标书撰写系统 - 基于AI的智能标书内容生成工具"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "rich>=13.0.0",
    "questionary>=2.0.0",
    "pyyaml>=6.0",
    "openai>=1.0.0",  # 核心依赖：OpenAI SDK
]
```

### 安装命令

```bash
# 使用 uv 包管理器
uv sync

# 或使用 pip
pip install openai>=1.0.0 pyyaml>=6.0
```

---

## 配置管理模块

### 文件：`bid_writer/config.py`

```python
"""
配置管理模块
负责加载和管理系统配置
"""

import os
from pathlib import Path
from typing import Optional
import yaml


class Config:
    """系统配置管理器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = {}
        self.load()
    
    def load(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
    
    def reload(self) -> None:
        """重新加载配置"""
        self.load()
    
    @property
    def api_base_url(self) -> str:
        """API基础URL"""
        return self._config.get('api', {}).get('base_url', 'https://api.openai.com/v1')
    
    @property
    def api_key(self) -> str:
        """API密钥"""
        # 优先从环境变量获取
        env_key = os.environ.get('BID_WRITER_API_KEY')
        if env_key:
            return env_key
        return self._config.get('api', {}).get('api_key', '')
    
    @property
    def model(self) -> str:
        """模型名称"""
        return self._config.get('api', {}).get('model', 'gpt-4')
    
    @property
    def temperature(self) -> float:
        """生成温度"""
        return self._config.get('api', {}).get('temperature', 0.7)
    
    @property
    def max_tokens(self) -> int:
        """最大token数"""
        return self._config.get('api', {}).get('max_tokens', 8000)
    
    @property
    def role(self) -> str:
        """角色设定"""
        return self._config.get('role', '你是一位专业的标书撰写专家。')
    
    @property
    def bid_requirements(self) -> str:
        """招标需求"""
        # 优先从文件加载
        file_path = self._config.get('bid_requirements_file')
        if file_path:
            path = Path(file_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        return self._config.get('bid_requirements', '')
    
    @property
    def scoring_criteria(self) -> str:
        """评分标准"""
        # 优先从文件加载
        file_path = self._config.get('scoring_criteria_file')
        if file_path:
            path = Path(file_path)
            if path.exists():
                return path.read_text(encoding='utf-8')
        return self._config.get('scoring_criteria', '')
    
    @property
    def outline_file(self) -> str:
        """大纲文件路径"""
        return self._config.get('outline_file', './outline.md')
    
    @property
    def output_directory(self) -> str:
        """输出目录"""
        return self._config.get('output', {}).get('directory', './output')
    
    @property
    def output_prefix(self) -> str:
        """输出文件名前缀"""
        return self._config.get('output', {}).get('prefix', '')
    
    @property
    def history_enabled(self) -> bool:
        """是否启用历史记录"""
        return self._config.get('history', {}).get('enabled', True)
    
    @property
    def history_file(self) -> str:
        """历史记录文件路径"""
        return self._config.get('history', {}).get('file', './history.json')
    
    @property
    def history_max_records(self) -> int:
        """最大历史记录数"""
        return self._config.get('history', {}).get('max_records', 100)
    
    def get_outline_content(self) -> str:
        """获取大纲内容"""
        outline_path = Path(self.outline_file)
        if not outline_path.exists():
            raise FileNotFoundError(f"大纲文件不存在: {outline_path}")
        return outline_path.read_text(encoding='utf-8')
```

**核心特性：**

1. **环境变量支持**：API Key 优先从环境变量 `BID_WRITER_API_KEY` 读取
2. **文件路径解析**：支持从外部文件加载长文本配置（如招标需求）
3. **默认值处理**：所有配置项都有合理的默认值
4. **热加载**：支持通过 `reload()` 方法重新加载配置

---

## AI 调用引擎

### 文件：`bid_writer/ai_writer.py`

```python
"""
AI扩写引擎
调用Gemini API进行内容扩写
"""

from typing import Generator, Optional
from openai import OpenAI

from .config import Config
from .outline_parser import HeadingNode


class AIWriter:
    """AI扩写引擎"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key
        )
    
    def build_prompt(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500
    ) -> str:
        """
        构建扩写提示词
        
        Args:
            heading: 要扩写的标题节点
            additional_requirements: 用户的附加要求
            min_words: 最低字数要求
            
        Returns:
            完整的提示词
        """
        prompt_parts = []
        
        # 任务说明
        prompt_parts.append(f"""请为以下标书章节进行专业扩写。

## 待扩写章节
标题层级：{heading.full_path}
当前标题：{heading.title}

## 扩写要求
- 字数要求：不少于 {min_words} 字
- 输出格式：Markdown格式
- 第一行应为： #### {heading.title} 
- 请直接输出扩写内容，不要包含标题本身
- 内容要专业、严谨，符合标书撰写规范
- 不要出现不必要的英文，比如某个词语的中英文，不需要！
- 除了第一行有markdown标记外，其他内容不要出现markdown层级标记，但可以用强调文字的markdown标记
- 在每个章节的正文中加入一定数量的markdown表格（少于等于4个），概括、总结、展示正文内容，并增强内容的可读性和专业性。表格标题前不要序号
- 如果要给该章节进行总结，可以给标题命名为"章节小结"的标题，注意序号与前文一直，且保持顺序。
""")
        
        # 添加招标需求上下文
        if self.config.bid_requirements:
            prompt_parts.append(f"""
## 招标需求参考
{self.config.bid_requirements}
""")
        
        # 添加评分标准上下文
        if self.config.scoring_criteria:
            prompt_parts.append(f"""
## 评分标准参考
{self.config.scoring_criteria}
""")
        
        # 添加用户附加要求
        if additional_requirements:
            prompt_parts.append(f"""
## 用户附加要求
{additional_requirements}
""")
        
        return "\n".join(prompt_parts)
    
    def expand(
        self,
        heading: HeadingNode,
        additional_requirements: str = "",
        min_words: int = 500,
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        """
        扩写指定标题
        
        Args:
            heading: 要扩写的标题节点
            additional_requirements: 用户的附加要求
            min_words: 最低字数要求
            stream: 是否使用流式输出
            
        Yields/Returns:
            扩写的内容（流式或一次性返回）
        """
        prompt = self.build_prompt(heading, additional_requirements, min_words)
        
        messages = [
            {"role": "system", "content": self.config.role},
            {"role": "user", "content": prompt}
        ]
        
        if stream:
            return self._stream_expand(messages)
        else:
            return self._sync_expand(messages)
    
    def _stream_expand(self, messages: list) -> Generator[str, None, None]:
        """流式扩写"""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=True
        )
        
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _sync_expand(self, messages: list) -> str:
        """同步扩写"""
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=False
        )
        
        return response.choices[0].message.content or ""
    
    def count_chinese_words(self, text: str) -> int:
        """
        统计中文字数（包括标点和英文单词）
        
        Args:
            text: 要统计的文本
            
        Returns:
            字数
        """
        import re
        
        # 移除Markdown标记
        clean_text = re.sub(r'[#*`\[\]()>-]', '', text)
        
        # 统计中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_text))
        
        # 统计英文单词
        english_words = len(re.findall(r'[a-zA-Z]+', clean_text))
        
        # 统计数字
        numbers = len(re.findall(r'\d+', clean_text))
        
        return chinese_chars + english_words + numbers
```

**核心特性：**

1. **流式输出支持**：`_stream_expand()` 方法支持实时流式返回生成内容
2. **同步输出支持**：`_sync_expand()` 方法一次性返回完整内容
3. **动态提示词构建**：`build_prompt()` 方法支持多上下文组合
4. **OpenAI SDK 兼容**：使用标准的 OpenAI Python SDK，兼容所有 OpenAI API 格式的服务

---

## 配置文件示例

### config.yaml

```yaml
# 自动标书撰写系统配置文件

# API配置
api:
  base_url: "https://api.ssopen.top/v1"  # API 基础 URL
  api_key: "sk-your-api-key-here"        # API 密钥
  model: "gemini-3-pro-preview"          # 模型名称
  temperature: 1                          # 生成温度 (0-2)
  max_tokens: 30000                       # 最大 token 数

# 角色设定
role: |
  你是一名资深的投标专家，擅长撰写专业的标书内容。
  你的输出应该：
  1. 专业、严谨、符合标书规范
  2. 逻辑清晰、层次分明
  3. 内容充实、有理有据

# 招标需求（可以是文件路径或直接内容）
bid_requirements: "/path/to/requirements.md"

# 评分标准（可以是文件路径或直接内容）
scoring_criteria: "/path/to/scoring.md"

# 标书大纲文件路径
outline_file: "./outline.md"

# 输出配置
output:
  directory: "./output"
  prefix: ""

# 历史记录配置
history:
  enabled: true
  file: "./history.json"
  max_records: 100
```

### 环境变量配置（可选）

```bash
# 通过环境变量设置 API Key（优先级高于配置文件）
export BID_WRITER_API_KEY="sk-your-api-key-here"
```

---

## 使用示例

### 基础使用

```python
from bid_writer.config import Config
from bid_writer.ai_writer import AIWriter

# 1. 加载配置
config = Config("config.yaml")

# 2. 初始化 AI 引擎
ai_writer = AIWriter(config)

# 3. 构建提示词（假设有一个 HeadingNode 对象）
prompt = ai_writer.build_prompt(
    heading=heading_node,
    additional_requirements="请重点突出技术优势",
    min_words=1000
)

# 4. 同步调用
content = ai_writer.expand(
    heading=heading_node,
    additional_requirements="请重点突出技术优势",
    min_words=1000,
    stream=False
)
print(content)
```

### 流式输出示例

```python
# 流式调用（实时显示生成内容）
for chunk in ai_writer.expand(
    heading=heading_node,
    additional_requirements="请重点突出技术优势",
    min_words=1000,
    stream=True
):
    print(chunk, end='', flush=True)
```

### 直接使用 OpenAI SDK

```python
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    base_url="https://api.ssopen.top/v1",
    api_key="sk-your-api-key-here"
)

# 构建消息
messages = [
    {"role": "system", "content": "你是一位专业的助手"},
    {"role": "user", "content": "请介绍一下人工智能"}
]

# 同步调用
response = client.chat.completions.create(
    model="gemini-3-pro-preview",
    messages=messages,
    temperature=0.7,
    max_tokens=2000,
    stream=False
)
print(response.choices[0].message.content)

# 流式调用
response = client.chat.completions.create(
    model="gemini-3-pro-preview",
    messages=messages,
    temperature=0.7,
    max_tokens=2000,
    stream=True
)

for chunk in response:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)
```

---

## 核心设计模式

### 1. 配置与业务分离

- **Config 类**：专门负责配置管理
- **AIWriter 类**：专门负责 AI 调用逻辑
- 两者通过依赖注入解耦

### 2. 流式与同步双模式

```python
# 流式：适合实时展示
for chunk in ai_writer.expand(stream=True):
    display(chunk)

# 同步：适合批量处理
content = ai_writer.expand(stream=False)
save_to_file(content)
```

### 3. 多上下文提示词构建

```python
prompt = [
    "任务说明",
    "招标需求上下文",
    "评分标准上下文",
    "用户附加要求"
]
```

### 4. 环境变量优先级

```python
# 优先级：环境变量 > 配置文件 > 默认值
api_key = os.environ.get('BID_WRITER_API_KEY') or config.get('api_key') or ''
```

---

## 兼容的 API 服务

本代码使用 OpenAI SDK，兼容以下服务：

1. **OpenAI 官方 API**
   - base_url: `https://api.openai.com/v1`
   - models: `gpt-4`, `gpt-3.5-turbo` 等

2. **Gemini API（通过代理）**
   - base_url: `https://api.ssopen.top/v1`
   - models: `gemini-2.5-pro`, `gemini-3-pro-preview` 等

3. **其他兼容 OpenAI 格式的服务**
   - Azure OpenAI
   - 本地部署的 LLM（如 Ollama + OpenAI 兼容层）
   - 各类第三方代理服务

---

## 最佳实践

### 1. API Key 安全

```bash
# 推荐：使用环境变量
export BID_WRITER_API_KEY="sk-xxx"

# 不推荐：直接写在配置文件中（仅用于开发环境）
```

### 2. 错误处理

```python
try:
    content = ai_writer.expand(heading, stream=False)
except Exception as e:
    print(f"AI 调用失败: {e}")
    # 记录日志、重试或降级处理
```

### 3. Token 控制

```python
# 根据模型限制设置合理的 max_tokens
config = {
    "max_tokens": 30000,  # Gemini 支持更长上下文
    "temperature": 0.7,   # 平衡创造性和稳定性
}
```

### 4. 流式输出优化

```python
# 使用缓冲区避免频繁刷新
buffer = []
for chunk in ai_writer.expand(stream=True):
    buffer.append(chunk)
    if len(buffer) >= 10:  # 每 10 个 chunk 刷新一次
        print(''.join(buffer), end='', flush=True)
        buffer.clear()
```

---

## 总结

本文档提取的代码提供了一个**完整、可复用的 LLM 集成方案**，核心优势：

✅ **简洁易用**：只需配置 YAML 文件即可开始使用  
✅ **高度灵活**：支持流式/同步、多上下文、环境变量等  
✅ **兼容性强**：基于 OpenAI SDK，兼容多种 API 服务  
✅ **生产就绪**：包含配置管理、错误处理、字数统计等实用功能  

可直接复制 `config.py` 和 `ai_writer.py` 到其他项目中使用！
