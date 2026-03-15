"""
文件保存模块
将扩写内容保存为Markdown文件
"""

import hashlib
import re
from pathlib import Path
from typing import Optional, Union

import yaml

from .outline_parser import HeadingNode

class FileSaver:
    """文件保存器"""

    HEADING_ID_SEPARATOR = "__"
    HEADING_ID_PATTERN = re.compile(r'__(?P<heading_id>[0-9a-f]{8,40})(?:_\d+)?$')
    FRONT_MATTER_DELIMITER = "---"
    FRONT_MATTER_MAX_LINES = 50

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

    def _apply_prefix(self, base_filename: str) -> str:
        """为文件名附加配置前缀"""
        return f"{self.prefix}{base_filename}" if self.prefix else base_filename

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

    def build_heading_id(self, heading: Union[HeadingNode, str]) -> str:
        """根据标题完整路径生成稳定 ID"""
        full_path = heading.full_path if isinstance(heading, HeadingNode) else str(heading)
        return hashlib.sha1(full_path.encode('utf-8')).hexdigest()[:12]

    def build_filename_stem(self, title: str, heading_id: Optional[str] = None) -> str:
        """构建最终的文件名 stem（不含扩展名）"""
        safe_title = self.sanitize_filename(title)
        if not heading_id:
            return safe_title

        reserved_length = len(self.HEADING_ID_SEPARATOR) + len(heading_id)
        max_title_length = max(self.max_filename_length - reserved_length, 1)
        if len(safe_title) > max_title_length:
            safe_title = safe_title[:max_title_length].rstrip(' ._') or self.empty_filename_fallback

        return f"{safe_title}{self.HEADING_ID_SEPARATOR}{heading_id}"

    def build_filepath(self, title: str, heading_id: Optional[str] = None) -> Path:
        """根据标题和可选 ID 构建目标文件路径"""
        stem = self._apply_prefix(self.build_filename_stem(title, heading_id))
        return self.output_directory / f"{stem}.md"

    def build_heading_filepath(self, heading: HeadingNode) -> Path:
        """根据标题节点构建标准输出路径"""
        return self.build_filepath(heading.title, self.build_heading_id(heading))

    def get_unique_filepath(self, base_filename: str) -> Path:
        """
        获取唯一的文件路径（避免覆盖已存在的文件）
        
        Args:
            base_filename: 基础文件名（不含扩展名）
            
        Returns:
            唯一的文件路径
        """
        base_filename = self._apply_prefix(base_filename)
        
        filepath = self.output_directory / f"{base_filename}.md"
        
        # 如果文件已存在，添加序号
        counter = 1
        while filepath.exists():
            filepath = self.output_directory / f"{base_filename}_{counter}.md"
            counter += 1

        return filepath

    def parse_heading_id_from_path(self, filepath: Path) -> Optional[str]:
        """从文件名中提取稳定 ID"""
        stem = filepath.stem
        if self.prefix and stem.startswith(self.prefix):
            stem = stem[len(self.prefix):]

        match = self.HEADING_ID_PATTERN.search(stem)
        return match.group("heading_id") if match else None

    def read_metadata(self, filepath: Path) -> dict:
        """读取 Markdown 文件顶部的 YAML front matter"""
        try:
            with filepath.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
                if first_line.strip() != self.FRONT_MATTER_DELIMITER:
                    return {}

                metadata_lines = []
                for _ in range(self.FRONT_MATTER_MAX_LINES):
                    line = handle.readline()
                    if not line:
                        return {}
                    if line.strip() == self.FRONT_MATTER_DELIMITER:
                        break
                    metadata_lines.append(line)
                else:
                    return {}
        except OSError:
            return {}

        try:
            metadata = yaml.safe_load("".join(metadata_lines)) or {}
        except yaml.YAMLError:
            return {}

        return metadata if isinstance(metadata, dict) else {}

    def _build_file_content(
        self,
        title: str,
        content: str,
        include_title: bool,
        metadata: Optional[dict] = None
    ) -> str:
        """构建写入文件的完整内容"""
        sections = []
        if metadata:
            yaml_text = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
            sections.append(self.FRONT_MATTER_DELIMITER)
            sections.append(yaml_text)
            sections.append(self.FRONT_MATTER_DELIMITER)
            sections.append("")

        if include_title:
            sections.append(f"# {title}")
            sections.append("")

        sections.append(content)
        return "\n".join(sections)

    def _resolve_heading_input(
        self,
        heading: Union[HeadingNode, str],
        full_path: Optional[str] = None,
        heading_id: Optional[str] = None
    ) -> tuple[str, Optional[str], Optional[str]]:
        """统一解析标题节点或纯标题文本输入"""
        if isinstance(heading, HeadingNode):
            title = heading.title
            full_path = heading.full_path
            heading_id = heading_id or self.build_heading_id(heading)
        else:
            title = heading
            if full_path and not heading_id:
                heading_id = self.build_heading_id(full_path)

        return title, full_path, heading_id

    def find_filepath_by_heading_id(self, heading_id: str) -> Optional[Path]:
        """根据稳定 ID 查找已保存文件"""
        for filepath in sorted(self.list_saved_files()):
            parsed_id = self.parse_heading_id_from_path(filepath)
            if parsed_id == heading_id:
                return filepath

            metadata = self.read_metadata(filepath)
            if metadata.get("heading_id") == heading_id:
                return filepath

        return None

    def find_legacy_filepaths(self, title: str) -> list[Path]:
        """查找旧命名规则下的文件路径"""
        legacy_stem = self.sanitize_filename(title)
        prefixed_stem = re.escape(self._apply_prefix(legacy_stem))
        pattern = re.compile(rf'^{prefixed_stem}(?:_\d+)?\.md$')
        return sorted(
            filepath for filepath in self.list_saved_files()
            if pattern.match(filepath.name)
        )

    def find_existing_filepath(self, heading: HeadingNode) -> Optional[Path]:
        """查找某个标题当前已存在的输出文件"""
        target_path = self.build_heading_filepath(heading)
        if target_path.exists():
            return target_path

        heading_id = self.build_heading_id(heading)
        by_id = self.find_filepath_by_heading_id(heading_id)
        if by_id:
            return by_id

        legacy_matches = self.find_legacy_filepaths(heading.title)
        return legacy_matches[0] if legacy_matches else None

    def save(
        self,
        heading: Union[HeadingNode, str],
        content: str,
        *,
        full_path: Optional[str] = None,
        heading_id: Optional[str] = None,
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
        title, full_path, heading_id = self._resolve_heading_input(heading, full_path, heading_id)
        filename = self.build_filename_stem(title, heading_id)

        if include_title is None:
            include_title = self.include_title_header
        if overwrite is None:
            overwrite = self.overwrite_existing

        if overwrite:
            filepath = self.build_filepath(title, heading_id)
        else:
            filepath = self.get_unique_filepath(filename)

        # 常规输出文件保持纯正文格式，避免后续合并章节时需要清理元数据。
        full_content = self._build_file_content(title, content, include_title)

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
        heading_id = self.build_heading_id(heading_path)
        metadata = {
            "title": title,
            "full_path": heading_path,
            "heading_id": heading_id,
            "min_words": min_words,
            "actual_words": actual_words,
            "requirements": additional_requirements,
        }

        full_content = self._build_file_content(title, content, True, metadata)

        filename = self.build_filename_stem(title, heading_id)
        filepath = self.get_unique_filepath(filename)
        filepath.write_text(full_content, encoding='utf-8')

        return filepath

    def list_saved_files(self) -> list:
        """列出所有已保存的文件"""
        return list(self.output_directory.glob("*.md"))
