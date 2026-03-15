# LLM 集成参考代码

这是从 BidX_simple 项目中提取的大模型调用代码，可以直接复制到其他项目中使用。

## 📁 文件说明

- `config.py` - 配置管理模块
- `ai_client.py` - AI 调用客户端（简化版）
- `example_config.yaml` - 配置文件示例
- `example_usage.py` - 使用示例代码

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install openai>=1.0.0 pyyaml>=6.0
```

或使用 uv:

```bash
uv add openai pyyaml
```

### 2. 配置文件

复制 `example_config.yaml` 为 `config.yaml`，并修改其中的 API 配置：

```yaml
api:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-your-api-key-here"
  model: "gpt-4"
  temperature: 0.7
  max_tokens: 8000
```

### 3. 使用示例

```python
from config import Config
from ai_client import AIClient

# 加载配置
config = Config("config.yaml")

# 初始化客户端
client = AIClient(config)

# 同步调用
response = client.chat("你好，请介绍一下人工智能", stream=False)
print(response)

# 流式调用
for chunk in client.chat("请列举3个AI应用场景", stream=True):
    print(chunk, end='', flush=True)
```

## 📖 详细文档

### Config 类

配置管理器，负责加载和管理 YAML 配置文件。

**主要属性：**
- `api_base_url` - API 基础 URL
- `api_key` - API 密钥（支持环境变量）
- `model` - 模型名称
- `temperature` - 生成温度
- `max_tokens` - 最大 token 数
- `role` - 系统角色设定

**主要方法：**
- `load()` - 加载配置文件
- `reload()` - 重新加载配置
- `get_text_from_file_or_config()` - 从文件或配置中获取文本

### AIClient 类

AI 调用客户端，封装了 OpenAI SDK 的调用逻辑。

**主要方法：**

#### `chat(user_message, system_message=None, stream=True, ...)`

发送单条消息。

```python
# 同步
response = client.chat("你好", stream=False)

# 流式
for chunk in client.chat("你好", stream=True):
    print(chunk, end='')
```

#### `chat_with_history(messages, stream=True, ...)`

带历史记录的多轮对话。

```python
messages = [
    {"role": "system", "content": "你是一位专业助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
    {"role": "user", "content": "请介绍一下AI"}
]

response = client.chat_with_history(messages, stream=False)
```

## 🔧 高级用法

### 1. 使用环境变量

```bash
export BID_WRITER_API_KEY="sk-your-api-key"
```

配置文件中的 `api_key` 将被环境变量覆盖。

### 2. 不使用配置文件

```python
client = AIClient(
    base_url="https://api.openai.com/v1",
    api_key="sk-your-api-key",
    model="gpt-4"
)
```

### 3. 自定义参数

```python
response = client.chat(
    user_message="你好",
    system_message="你是一位幽默的助手",
    temperature=1.2,
    max_tokens=2000,
    stream=False
)
```

### 4. 从文件加载上下文

在 `config.yaml` 中：

```yaml
context_file: "/path/to/context.txt"
```

在代码中：

```python
context = config.get_text_from_file_or_config('context')
response = client.chat(f"{context}\n\n{user_question}", stream=False)
```

## 🌐 兼容的 API 服务

本代码使用 OpenAI SDK，兼容以下服务：

- ✅ OpenAI 官方 API
- ✅ Azure OpenAI
- ✅ Gemini API（通过代理）
- ✅ 本地部署的 LLM（如 Ollama + OpenAI 兼容层）
- ✅ 各类第三方代理服务

只需修改 `base_url` 和 `model` 即可切换不同的服务。

## 📝 最佳实践

### 1. API Key 安全

```bash
# ✅ 推荐：使用环境变量
export BID_WRITER_API_KEY="sk-xxx"

# ❌ 不推荐：直接写在配置文件中（仅用于开发环境）
```

### 2. 错误处理

```python
try:
    response = client.chat("你好", stream=False)
except Exception as e:
    print(f"API 调用失败: {e}")
    # 记录日志、重试或降级处理
```

### 3. 流式输出优化

```python
# 使用缓冲区避免频繁刷新
buffer = []
for chunk in client.chat("你好", stream=True):
    buffer.append(chunk)
    if len(buffer) >= 10:  # 每 10 个 chunk 刷新一次
        print(''.join(buffer), end='', flush=True)
        buffer.clear()

# 输出剩余内容
if buffer:
    print(''.join(buffer), end='', flush=True)
```

### 4. Token 控制

```python
# 根据模型限制设置合理的 max_tokens
config = {
    "max_tokens": 8000,    # GPT-4
    # "max_tokens": 30000, # Gemini
}
```

## 🔗 相关资源

- [OpenAI API 文档](https://platform.openai.com/docs/api-reference)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [完整文档](../LLM_Integration_Reference.md)

## 📄 许可证

MIT License
