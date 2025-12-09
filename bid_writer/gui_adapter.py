"""
GUI适配器
桥接Tkinter GUI和核心业务逻辑
"""

from typing import List, Callable, Optional
from .outline_parser import HeadingNode
from .main import BidWriter


class GUIAdapter:
    """GUI适配器"""

    def __init__(self, bid_writer: BidWriter):
        self.bid_writer = bid_writer

    def get_outline_tree(self) -> List[HeadingNode]:
        """获取大纲树"""
        return self.bid_writer.parser.root_headings

    def get_all_headings(self) -> List[HeadingNode]:
        """获取所有标题节点"""
        return self.bid_writer.parser.get_all_headings()

    def get_generated_titles(self) -> set:
        """获取已生成的标题集合"""
        return self.bid_writer.ui._generated_titles

    def refresh_generated_titles(self) -> None:
        """刷新已生成标题缓存"""
        self.bid_writer.ui._refresh_generated_titles()

    def get_status_icon(self, heading: HeadingNode) -> str:
        """
        获取状态图标
        - 有子节点：显示进度 📁/📂
        - 叶子节点：显示 ✅/🔴
        """
        icon, generated, total = self.bid_writer.ui.get_heading_generation_status(heading)

        if heading.children:
            # 有子节点，使用文件夹图标表示进度
            if icon == "✅":
                return "📁"  # 全部完成
            elif icon == "📝":
                return "📂"  # 部分完成
            else:
                return "📁"  # 未开始
        else:
            # 叶子节点，直接显示状态
            return icon

    def is_heading_generated(self, heading: HeadingNode) -> bool:
        """检查标题是否已生成"""
        if not heading.children:
            # 叶子节点，直接检查
            title_match = self._extract_title(heading.title)
            filename = self._sanitize(title_match)
            return filename in self.get_generated_titles()
        else:
            # 有子节点，检查任一子节点是否生成
            _, generated, _ = self.bid_writer.ui.get_heading_generation_status(heading)
            return generated > 0

    def get_progress(self, heading: HeadingNode) -> tuple:
        """获取进度 (已完成数, 总数)"""
        _, generated, total = self.bid_writer.ui.get_heading_generation_status(heading)
        return generated, total

    def _extract_title(self, title: str) -> str:
        """从标题中提取纯文本（移除编号）"""
        import re
        match = re.match(r'^\d+([.]\d+)*[_\s]+(.+)$', title)
        if match:
            return match.group(2)
        return title

    def _sanitize(self, title: str) -> str:
        """清理标题用于比对"""
        import re
        if not title:
            return ""
        invalid_chars = r'[\\/: *?"<>|\n\r\t]'
        clean = re.sub(invalid_chars, '_', title)
        clean = clean.strip(' .')
        clean = re.sub(r'[_\s]+', '_', clean)
        return clean

    def generate_single(self, heading: HeadingNode,
                       progress_callback: Optional[Callable] = None) -> tuple:
        """
        生成单个标题

        Args:
            heading: 要生成的标题
            progress_callback: 进度回调函数(message: str)

        Returns:
            (success: bool, filepath: str)
        """
        try:
            if progress_callback:
                progress_callback(f"开始生成：{heading.title}")

            # 调用核心业务方法
            success, content, word_count, _ = \
                self.bid_writer.run_expansion(heading, "", 500)

            if success:
                # 保存文件（覆盖模式）
                filepath = self.bid_writer.file_saver.save(
                    heading.title, content, overwrite=True
                )

                # 刷新缓存
                self.refresh_generated_titles()

                if progress_callback:
                    progress_callback(f"✅ 生成成功：{heading.title} ({word_count}字)")

                return True, str(filepath)
            else:
                if progress_callback:
                    progress_callback(f"❌ 生成失败：{heading.title}")
                return False, ""

        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ 错误：{str(e)}")
            return False, ""

    def batch_generate(self, headings: List[HeadingNode],
                      progress_callback: Optional[Callable] = None) -> List[tuple]:
        """
        批量生成多个标题

        Args:
            headings: 要生成的标题列表
            progress_callback: 进度回调函数(message: str)

        Returns:
            [(success: bool, filepath: str), ...]
        """
        results = []
        total = len(headings)

        for i, heading in enumerate(headings, 1):
            if progress_callback:
                progress_callback(f"[{i}/{total}] 正在生成：{heading.title}")

            success, filepath = self.generate_single(heading)
            results.append((success, filepath))

        return results
