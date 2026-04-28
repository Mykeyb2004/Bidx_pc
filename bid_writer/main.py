#!/usr/bin/env python3
"""
自动标书撰写系统核心
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .ai_writer import AIWriter
from .chapter_fact_extractor import ChapterFactExtractor, ChapterFactResult
from .chapter_fact_store import ChapterFactStore
from .config import Config
from .fact_card_extractor import FactCardExtractionResult, FactCardExtractor
from .fact_card_store import FactCardStore
from .fact_cards import FactCard, FactCardDraft, FactCardSelection, FactCardSource
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
        self.chapter_fact_store = ChapterFactStore(self.config)
        self.fact_card_store = FactCardStore(self.config)
        self.fact_card_extractor = FactCardExtractor(
            self.config,
            self.file_saver,
        )
        self.chapter_fact_extractor = ChapterFactExtractor(
            self.config,
            self.file_saver,
            self.chapter_fact_store,
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

    def get_output_fact_status(self, heading: HeadingNode) -> str:
        """返回正文 facts 缓存状态。"""
        return self.chapter_fact_extractor.get_output_fact_status(heading)

    def ensure_output_chapter_facts(self, heading: HeadingNode) -> Optional[ChapterFactResult]:
        """生成或复用正文 facts。"""
        return self.chapter_fact_extractor.ensure_output_facts(heading)

    def list_fact_cards(self) -> list[FactCard]:
        """列出当前启用的事实卡片。"""
        return self.fact_card_store.list_cards()

    def list_extracted_fact_cards(self, heading: HeadingNode | str) -> list[FactCard]:
        """列出指定章节已保存的正文提炼事实卡片。"""
        return self.fact_card_store.list_chapter_extracted_cards(self._resolve_heading_path(heading))

    def save_chapter_default_fact_cards(
        self,
        chapter_path: str,
        selections: list[FactCardSelection],
        *,
        should_reference_fact_cards: bool | None = None,
    ) -> list[FactCardSelection]:
        """保存章节默认选中的事实卡片。"""
        return self.fact_card_store.save_chapter_defaults(
            chapter_path,
            selections,
            should_reference_fact_cards=should_reference_fact_cards,
        )

    def list_chapter_default_fact_cards(
        self,
        heading: HeadingNode | str,
    ) -> list[FactCardSelection]:
        """读取章节默认事实卡片方案。"""
        return self.fact_card_store.list_chapter_defaults(self._resolve_heading_path(heading))

    def get_chapter_default_fact_card_state(
        self,
        heading: HeadingNode | str,
    ):
        """读取章节事实卡片引用状态与默认选择。"""
        return self.fact_card_store.get_chapter_default_state(self._resolve_heading_path(heading))

    def save_manual_fact_cards(
        self,
        drafts: Iterable[FactCardDraft | dict],
    ) -> list[FactCard]:
        """保存手工录入/编辑后的事实卡片。"""
        return self.fact_card_store.save_manual_cards(drafts)

    def save_fact_card_library(
        self,
        drafts: Iterable[FactCardDraft | dict],
    ) -> list[FactCard]:
        """保存事实卡片库编辑结果，保留已有卡片来源和 ID。"""
        return self.fact_card_store.save_library_cards(drafts)

    def save_fact_card_library_card(
        self,
        draft: FactCardDraft | dict,
        *,
        source: FactCardSource | None = None,
    ) -> list[FactCard]:
        """保存单张事实卡片编辑结果，可选择更新来源元数据。"""
        return self.fact_card_store.save_library_card(draft, source=source)

    def replace_extracted_fact_cards(
        self,
        heading: HeadingNode | str,
        instruction: str,
        drafts: Iterable[FactCardDraft | dict],
    ) -> list[FactCard]:
        """用最新草稿替换指定章节的提炼事实卡片。"""
        return self.fact_card_store.replace_extracted_cards(
            self._resolve_heading_path(heading),
            instruction,
            drafts,
        )

    def resolve_generation_fact_cards(
        self,
        heading: HeadingNode | str,
        manual_selections: Iterable[FactCardSelection | dict] | None = None,
        *,
        fact_card_mode: bool = False,
    ):
        """解析当前生成应使用的事实卡片。"""
        if not fact_card_mode:
            return []
        return self.fact_card_store.resolve_chapter_prompt_cards(
            self._resolve_heading_path(heading),
            manual_selections,
        )

    def extract_fact_card_drafts_from_output(
        self,
        heading: HeadingNode,
        instruction: str = "",
    ) -> list[FactCardDraft]:
        """从已保存章节正文中提取事实卡片草稿。"""
        return self.fact_card_extractor.extract_from_output(heading, instruction)

    def extract_fact_card_drafts_from_output_with_diagnostics(
        self,
        heading: HeadingNode,
        instruction: str = "",
    ) -> FactCardExtractionResult:
        """从已保存章节正文中提取事实卡片草稿，并返回失败诊断。"""
        return self.fact_card_extractor.extract_from_output_with_diagnostics(heading, instruction)

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

    @staticmethod
    def _resolve_heading_path(heading: HeadingNode | str) -> str:
        if isinstance(heading, HeadingNode):
            return heading.full_path
        return str(heading or "").strip()


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
