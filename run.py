#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 启动脚本
"""

import argparse


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="自动标书撰写系统"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径（留空则启动后在界面中选择）"
    )
    args = parser.parse_args()

    from bid_writer.gui import run_gui
    run_gui(args.config)


if __name__ == "__main__":
    main()
