"""
GUI适配器
桥接 Tkinter GUI 和核心业务逻辑
"""

import re
from typing import List

from .main import BidWriter
from .outline_parser import HeadingNode


class GUIAdapter:
    """GUI适配器"""

    def __init__(self, bid_writer: BidWriter):
        self.bid_writer = bid_writer
        self._generated_titles: set[str] = set()
        self.refresh_generated_titles()

    def get_outline_tree(self) -> List[HeadingNode]:
        """获取大纲树"""
        return self.bid_writer.parser.root_headings if self.bid_writer.parser else []

    def get_all_headings(self) -> List[HeadingNode]:
        """获取所有标题节点"""
        return self.bid_writer.parser.get_all_headings() if self.bid_writer.parser else []

    def refresh_generated_titles(self) -> None:
        """刷新已生成标题缓存"""
        self._generated_titles.clear()
        output_directory = self.bid_writer.file_saver.output_directory
        if not output_directory.exists():
            return

        for md_file in output_directory.glob("*.md"):
            stem = md_file.stem
            prefix = self.bid_writer.file_saver.prefix
            if prefix and stem.startswith(prefix):
                stem = stem[len(prefix):]
            stem = re.sub(r'_\d+$', '', stem)
            match = re.match(r'^\d+(?:[.]\d+)*[_\s]+(.+)$', stem)
            title_part = match.group(1) if match else stem
            clean_title = self.bid_writer.file_saver.sanitize_filename(title_part)
            if clean_title:
                self._generated_titles.add(clean_title)

    def get_heading_generation_status(self, heading: HeadingNode) -> tuple[str, int, int]:
        """
        检查标题及所有子标题的生成状态

        Returns:
            (状态图标, 已生成数量, 总数量)
        """
        if not self.bid_writer.file_saver.output_directory.exists():
            return "🔴", 0, 0

        if not heading.children:
            filename = self._heading_filename_key(heading)
            is_generated = filename in self._generated_titles
            return ("✅" if is_generated else "🔴"), (1 if is_generated else 0), 1

        leaf_nodes = self._get_leaf_nodes(heading)
        if not leaf_nodes:
            return "🔴", 0, 0

        generated = sum(1 for node in leaf_nodes if self._heading_filename_key(node) in self._generated_titles)
        total = len(leaf_nodes)

        if generated == total:
            return "✅", generated, total
        if generated > 0:
            return "📝", generated, total
        return "🔴", generated, total

    def get_status_icon(self, heading: HeadingNode) -> str:
        """获取树上显示的状态图标"""
        icon, _, _ = self.get_heading_generation_status(heading)
        if heading.children:
            return "📂" if icon == "📝" else "📁"
        return icon

    def is_heading_generated(self, heading: HeadingNode) -> bool:
        """检查标题是否已生成"""
        if not heading.children:
            return self._heading_filename_key(heading) in self._generated_titles
        _, generated, _ = self.get_heading_generation_status(heading)
        return generated > 0

    def get_progress(self, heading: HeadingNode) -> tuple[int, int]:
        """获取进度 (已完成数, 总数)"""
        _, generated, total = self.get_heading_generation_status(heading)
        return generated, total

    def _heading_filename_key(self, heading: HeadingNode) -> str:
        """获取标题对应的文件名比对键"""
        return self.bid_writer.file_saver.sanitize_filename(self._extract_title(heading.title))

    def _extract_title(self, title: str) -> str:
        """从标题中提取纯文本（移除编号）"""
        match = re.match(r'^\d+(?:[.]\d+)*[_\s]+(.+)$', title)
        if match:
            return match.group(1)
        return title

    def _get_leaf_nodes(self, heading: HeadingNode) -> List[HeadingNode]:
        """获取某节点下的所有叶子节点"""
        leaves: List[HeadingNode] = []

        def collect(node: HeadingNode) -> None:
            if not node.children:
                leaves.append(node)
                return
            for child in node.children:
                collect(child)

        for child in heading.children:
            collect(child)
        return leaves
