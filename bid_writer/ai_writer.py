"""
AI扩写引擎
调用Gemini API进行内容扩写
"""

from typing import Generator
from openai import OpenAI

from .config import Config
from .outline_parser import HeadingNode


class AIWriter:
    """AI扩写引擎"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries
        )

    def _format_first_line(self, heading: HeadingNode) -> str:
        """渲染提示词中的首行模板"""
        template = self.config.prompt_first_line_template
        try:
            return template.format(title=heading.title, full_path=heading.full_path)
        except (KeyError, ValueError):
            return template.replace("{title}", heading.title)

    def _build_request_options(self, messages: list, stream: bool) -> dict:
        """构建模型请求参数"""
        options = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream
        }
        if self.config.api_top_p is not None:
            options["top_p"] = self.config.api_top_p
        if self.config.api_seed is not None:
            options["seed"] = self.config.api_seed
        return options

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

        first_line = self._format_first_line(heading)
        english_rule = (
            "- 可保留必要的专业英文术语，但不要堆砌中英对照。"
            if self.config.prompt_allow_english_terms
            else "- 不要出现不必要的英文，比如某个词语的中英文，不需要！"
        )
        format_rule = f"- 输出格式：{self.config.prompt_output_format}"
        markdown_specific_rules = []
        if "markdown" in self.config.prompt_output_format.lower():
            markdown_specific_rules.append(
                "- 除了第一行有markdown标记外，其他内容不要出现markdown层级标记，但可以用强调文字的markdown标记"
            )
            if self.config.prompt_max_tables_per_section > 0:
                markdown_specific_rules.append(
                    f"- 在每个章节的正文中加入一定数量的markdown表格（少于等于{self.config.prompt_max_tables_per_section}个），概括、总结、展示正文内容，并增强内容的可读性和专业性。表格标题前不要序号"
                )
        summary_rule = ""
        if self.config.prompt_summary_title:
            summary_rule = (
                f"- 如果要给该章节进行总结，可以给标题命名为“{self.config.prompt_summary_title}”的标题，注意序号与前文一致，且保持顺序。"
            )
        extra_rules = "\n".join(f"- {rule}" for rule in self.config.prompt_extra_rules)

        prompt_parts.append(f"""请为以下标书章节进行专业扩写。

## 待扩写章节
标题层级：{heading.full_path}
当前标题：{heading.title}

## 扩写要求
- 字数要求：不少于 {min_words} 字
- 第一行应为： {first_line}
- 请直接输出扩写内容，不要包含标题本身
- 内容要专业、严谨，符合标书撰写规范
{format_rule}
{english_rule}
{chr(10).join(markdown_specific_rules)}
{summary_rule}
{extra_rules}
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
        response = self.client.chat.completions.create(**self._build_request_options(messages, stream=True))

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _sync_expand(self, messages: list) -> str:
        """同步扩写"""
        response = self.client.chat.completions.create(**self._build_request_options(messages, stream=False))

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
