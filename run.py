#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 启动脚本
"""

import argparse

from bid_writer.macos_stderr_filter import suppress_native_macos_stderr_noise


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="标书智写"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径（留空则自动使用上次配置或 config.yaml）"
    )
    args = parser.parse_args()

    from bid_writer.gui import run_gui
    with suppress_native_macos_stderr_noise():
        run_gui(args.config)


if __name__ == "__main__":
    main()
