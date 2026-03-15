#!/usr/bin/env python3
"""
自动标书撰写系统核心
"""

import argparse
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
