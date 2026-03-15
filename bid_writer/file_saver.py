"""
文件保存模块
将扩写内容保存为Markdown文件
"""

import re
from pathlib import Path
from typing import Optional


class FileSaver:
    """文件保存器"""

    def __init__(
        self,
        output_directory: str = "./output",
        prefix: str = "",
        max_filename_length: int = 100,
        empty_filename_fallback: str = "untitled",
        include_title_header: bool = True,
        overwrite_existing: bool = False
    ):
        self.output_directory = Path(output_directory)
        self.prefix = prefix
        self.max_filename_length = max_filename_length
        self.empty_filename_fallback = empty_filename_fallback
        self.include_title_header = include_title_header
        self.overwrite_existing = overwrite_existing
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保输出目录存在"""
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, title: str) -> str:
        """
        清理标题，生成合法的文件名
        
        Args:
            title: 原始标题
            
        Returns:
            清理后的文件名（不含扩展名）
        """
        # 移除或替换不合法的文件名字符
        # Windows不允许: \ / : * ? " < > |
        # 同时移除其他可能导致问题的字符
        invalid_chars = r'[\\/:*?"<>|\n\r\t]'
        filename = re.sub(invalid_chars, '_', title)
        
        # 移除首尾空格和点
        filename = filename.strip(' .')
        
        # 替换连续的下划线和空格
        filename = re.sub(r'[_\s]+', '_', filename)

        # 限制文件名长度（保留一些余量给扩展名和路径）
        if len(filename) > self.max_filename_length:
            filename = filename[:self.max_filename_length]

        # 如果标题为空，使用默认名称
        if not filename:
            filename = self.empty_filename_fallback

        return filename

    def get_unique_filepath(self, base_filename: str) -> Path:
        """
        获取唯一的文件路径（避免覆盖已存在的文件）
        
        Args:
            base_filename: 基础文件名（不含扩展名）
            
        Returns:
            唯一的文件路径
        """
        if self.prefix:
            base_filename = f"{self.prefix}{base_filename}"
        
        filepath = self.output_directory / f"{base_filename}.md"
        
        # 如果文件已存在，添加序号
        counter = 1
        while filepath.exists():
            filepath = self.output_directory / f"{base_filename}_{counter}.md"
            counter += 1

        return filepath

    def save(
        self,
        title: str,
        content: str,
        include_title: Optional[bool] = None,
        overwrite: Optional[bool] = None
    ) -> Path:
        """
        保存扩写内容到文件
        
        Args:
            title: 标题（用于生成文件名和可选的内容标题）
            content: 扩写的内容
            include_title: 是否在文件开头包含标题
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            保存的文件路径
        """
        filename = self.sanitize_filename(title)

        if include_title is None:
            include_title = self.include_title_header
        if overwrite is None:
            overwrite = self.overwrite_existing

        if overwrite:
            filepath = self.output_directory / f"{self.prefix}{filename}.md"
        else:
            filepath = self.get_unique_filepath(filename)

        # 构建文件内容
        if include_title:
            full_content = f"# {title}\n\n{content}"
        else:
            full_content = content

        # 写入文件
        filepath.write_text(full_content, encoding='utf-8')

        return filepath

    def save_with_metadata(
        self,
        title: str,
        content: str,
        heading_path: str,
        min_words: int,
        actual_words: int,
        additional_requirements: str = ""
    ) -> Path:
        """
        保存扩写内容，并在文件开头添加元数据
        
        Args:
            title: 标题
            content: 扩写内容
            heading_path: 标题完整路径
            min_words: 要求的最低字数
            actual_words: 实际字数
            additional_requirements: 附加要求
            
        Returns:
            保存的文件路径
        """
        # 构建YAML front matter
        metadata = f"""---
title: "{title}"
path: "{heading_path}"
min_words: {min_words}
actual_words: {actual_words}
requirements: "{additional_requirements}"
---

"""

        full_content = f"{metadata}# {title}\n\n{content}"

        filename = self.sanitize_filename(title)
        filepath = self.get_unique_filepath(filename)
        filepath.write_text(full_content, encoding='utf-8')

        return filepath

    def list_saved_files(self) -> list:
        """列出所有已保存的文件"""
        return list(self.output_directory.glob("*.md"))
