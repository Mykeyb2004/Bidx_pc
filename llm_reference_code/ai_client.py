"""
AI 调用客户端
封装了 OpenAI SDK 的调用逻辑，支持流式和同步两种模式

使用方法：
    from config import Config
    from ai_client import AIClient
    
    config = Config("config.yaml")
    client = AIClient(config)
    
    # 同步调用
    response = client.chat("你好，请介绍一下人工智能", stream=False)
    print(response)
    
    # 流式调用
    for chunk in client.chat("你好，请介绍一下人工智能", stream=True):
        print(chunk, end='', flush=True)
"""

from typing import Generator, List, Dict, Any
from openai import OpenAI


class AIClient:
    """AI 调用客户端"""
    
    def __init__(self, config=None, base_url: str = None, api_key: str = None, model: str = None):
        """
        初始化 AI 客户端
        
        Args:
            config: Config 对象（如果提供，将从中读取配置）
            base_url: API 基础 URL（如果不提供，从 config 读取）
            api_key: API 密钥（如果不提供，从 config 读取）
            model: 模型名称（如果不提供，从 config 读取）
        """
        if config:
            self.base_url = base_url or config.api_base_url
            self.api_key = api_key or config.api_key
            self.model = model or config.model
            self.temperature = config.temperature
            self.max_tokens = config.max_tokens
            self.system_role = config.role
        else:
            self.base_url = base_url or "https://api.openai.com/v1"
            self.api_key = api_key or ""
            self.model = model or "gpt-4"
            self.temperature = 0.7
            self.max_tokens = 8000
            self.system_role = "你是一位专业的AI助手。"
        
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
    
    def chat(
        self,
        user_message: str,
        system_message: str = None,
        stream: bool = True,
        temperature: float = None,
        max_tokens: int = None
    ) -> Generator[str, None, None] | str:
        """
        发送聊天消息
        
        Args:
            user_message: 用户消息
            system_message: 系统消息（如果为 None，使用默认的 system_role）
            stream: 是否使用流式输出
            temperature: 生成温度（如果为 None，使用默认值）
            max_tokens: 最大 token 数（如果为 None，使用默认值）
            
        Returns:
            流式生成器或完整响应字符串
        """
        messages = [
            {"role": "system", "content": system_message or self.system_role},
            {"role": "user", "content": user_message}
        ]
        
        return self._call_api(
            messages=messages,
            stream=stream,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens
        )
    
    def chat_with_history(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True,
        temperature: float = None,
        max_tokens: int = None
    ) -> Generator[str, None, None] | str:
        """
        带历史记录的聊天
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            stream: 是否使用流式输出
            temperature: 生成温度（如果为 None，使用默认值）
            max_tokens: 最大 token 数（如果为 None，使用默认值）
            
        Returns:
            流式生成器或完整响应字符串
        """
        return self._call_api(
            messages=messages,
            stream=stream,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens
        )
    
    def _call_api(
        self,
        messages: List[Dict[str, str]],
        stream: bool,
        temperature: float,
        max_tokens: int
    ) -> Generator[str, None, None] | str:
        """
        调用 API
        
        Args:
            messages: 消息列表
            stream: 是否使用流式输出
            temperature: 生成温度
            max_tokens: 最大 token 数
            
        Returns:
            流式生成器或完整响应字符串
        """
        if stream:
            return self._stream_call(messages, temperature, max_tokens)
        else:
            return self._sync_call(messages, temperature, max_tokens)
    
    def _stream_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> Generator[str, None, None]:
        """流式调用"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _sync_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> str:
        """同步调用"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        return response.choices[0].message.content or ""


if __name__ == "__main__":
    # 测试代码
    # 方式1：使用配置文件
    # from config import Config
    # config = Config("config.yaml")
    # client = AIClient(config)
    
    # 方式2：直接传参
    client = AIClient(
        base_url="https://api.openai.com/v1",
        api_key="your-api-key",
        model="gpt-4"
    )
    
    # 同步调用
    print("=== 同步调用 ===")
    response = client.chat("你好，请用一句话介绍人工智能", stream=False)
    print(response)
    
    # 流式调用
    print("\n=== 流式调用 ===")
    for chunk in client.chat("请列举3个AI应用场景", stream=True):
        print(chunk, end='', flush=True)
    print()
