#!/usr/bin/env python3
"""
自动标书撰写系统核心
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .ai_writer import AIWriter
from .config import Config
from .file_saver import FileSaver
from .outline_parser import HeadingNode, parse_outline


@dataclass(frozen=True)
class MergedBidResult:
    """整合标书输出结果"""

    filepath: Path
    merged_sections: int
    missing_sections: int
    total_sections: int


class BidWriter:
    """GUI 共享的核心状态与服务"""

    _MARKDOWN_HEADING_RE = re.compile(r'^\s*#{1,6}\s+')
    _UNORDERED_LIST_RE = re.compile(r'^\s*[-*+]\s+')
    _ORDERED_LIST_RE = re.compile(r'^\s*(?:\d+[.)]|[（(]\d+[)）]|[一二三四五六七八九十百千]+、)\s*')
    _HORIZONTAL_RULE_RE = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = Config(config_path)
        self.parser = None
        self.last_error_message = ""
        self._rebuild_services()

    def _rebuild_services(self) -> None:
        """根据当前配置重建运行时服务"""
        self.ai_writer = AIWriter(self.config)
        self.file_saver = FileSaver(
            self.config.output_directory,
            self.config.output_prefix,
            max_filename_length=self.config.output_filename_max_length,
            empty_filename_fallback=self.config.output_empty_filename_fallback,
            include_title_header=self.config.output_include_title_header,
            overwrite_existing=self.config.output_overwrite_existing
        )

    def load_outline(self) -> bool:
        """加载并解析大纲"""
        try:
            content = self.config.get_outline_content()
            self.parser = parse_outline(content)
            self.last_error_message = ""
            return True
        except Exception as e:
            self.parser = None
            self.last_error_message = str(e)
            return False

    def reload_config(self) -> None:
        """重新加载配置"""
        self.config.reload()
        self._rebuild_services()
        self.last_error_message = ""

    @staticmethod
    def _get_heading_chain(heading: HeadingNode) -> list[HeadingNode]:
        """获取从根节点到当前标题的完整链路。"""
        chain: list[HeadingNode] = []
        current: Optional[HeadingNode] = heading
        while current is not None:
            chain.insert(0, current)
            current = current.parent
        return chain

    @staticmethod
    def _needs_spacing_between(left: str, right: str) -> bool:
        """处理中英文混排时的最小空格补齐。"""
        if not left or not right:
            return False
        return left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum()

    @classmethod
    def _is_structured_markdown_line(cls, line: str, in_code_block: bool) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith("```"):
            return True
        if in_code_block:
            return True
        if cls._MARKDOWN_HEADING_RE.match(line):
            return True
        if stripped.startswith(">"):
            return True
        if stripped.startswith("|") or (stripped.endswith("|") and stripped.count("|") >= 2):
            return True
        if cls._UNORDERED_LIST_RE.match(line) or cls._ORDERED_LIST_RE.match(line):
            return True
        return bool(cls._HORIZONTAL_RULE_RE.match(line))

    @classmethod
    def _normalize_soft_line_breaks_for_merge(cls, content: str) -> str:
        """整合标书时，移除行尾空格并将 LF 统一替换为 CRLF。"""
        if not content:
            return content
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        normalized = "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))
        return normalized.replace("\n", "\r\n")

    def merge_generated_sections(self, output_title: str = "整合标书") -> MergedBidResult:
        """按大纲顺序整合所有已生成章节正文。"""
        if self.parser is None:
            raise RuntimeError("请先加载大纲后再整合标书")

        leaf_headings = self.parser.get_deepest_headings()
        if not leaf_headings:
            raise ValueError("当前大纲中没有可整合的叶子章节")

        merged_parts: list[str] = []
        previous_chain: list[HeadingNode] = []
        merged_sections = 0
        missing_sections = 0

        for heading in leaf_headings:
            filepath = self.file_saver.find_existing_filepath(heading)
            if not filepath or not filepath.exists():
                missing_sections += 1
                continue

            section_body = self.file_saver.load_section_body(filepath, heading.title)
            if not section_body.strip():
                missing_sections += 1
                continue
            heading_chain = self._get_heading_chain(heading)
            shared_depth = 0
            for previous_heading, current_heading in zip(previous_chain, heading_chain):
                if previous_heading.full_path != current_heading.full_path:
                    break
                shared_depth += 1

            for chain_heading in heading_chain[shared_depth:]:
                heading_level = min(max(chain_heading.level, 1), 6)
                merged_parts.append(f"{'#' * heading_level} {chain_heading.title}")
                merged_parts.append("")

            merged_parts.append(section_body.strip())
            merged_parts.append("")
            previous_chain = heading_chain
            merged_sections += 1

        if merged_sections == 0:
            raise ValueError("输出目录中未找到可整合的已生成章节")

        merged_content = "\n".join(merged_parts).rstrip() + "\n"
        if self.config.output_normalize_soft_line_breaks_on_merge:
            merged_content = self._normalize_soft_line_breaks_for_merge(merged_content)
        filepath = self.file_saver.save(
            output_title,
            merged_content,
            include_title=False,
            overwrite=True
        )
        self.last_error_message = ""
        return MergedBidResult(
            filepath=filepath,
            merged_sections=merged_sections,
            missing_sections=missing_sections,
            total_sections=len(leaf_headings)
        )


def main(config_path: Optional[str] = None):
    """GUI 启动入口"""
    if config_path is None:
        parser = argparse.ArgumentParser(
            description="自动标书撰写系统"
        )
        parser.add_argument(
            "-c", "--config",
            default=None,
            help="配置文件路径（留空则自动使用上次配置或 config.yaml）"
        )
        parser.add_argument(
            "--version",
            action="version",
            version="自动标书撰写系统 v1.0.0"
        )
        args = parser.parse_args()
        config_path = args.config

    try:
        from .gui import run_gui
        run_gui(config_path)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n程序已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
