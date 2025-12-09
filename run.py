#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行脚本 - 支持GUI和终端模式
"""

import sys
import argparse


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="自动标书撰写系统"
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="使用GUI界面"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径"
    )

    args = parser.parse_args()

    if args.gui:
        # GUI模式
        from bid_writer.gui import run_gui
        run_gui(args.config)
    else:
        # 终端模式（默认）
        from bid_writer.main import main as term_main
        term_main(args.config)


if __name__ == "__main__":
    main()
