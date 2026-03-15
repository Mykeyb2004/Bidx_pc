#!/usr/bin/env python3
"""
自动标书撰写系统核心
"""

import argparse
import sys
from typing import Optional

from .ai_writer import AIWriter
from .config import Config
from .file_saver import FileSaver
from .outline_parser import parse_outline


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
