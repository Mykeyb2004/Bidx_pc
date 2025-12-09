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
