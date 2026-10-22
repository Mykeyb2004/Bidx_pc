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
    parser.add_argument(
        "--smoke-test", metavar="REPORT_JSON",
        help="验证打包资源、文档依赖和 GUI，将结果写入 JSON 后退出（不调用模型）",
    )
    args = parser.parse_args()

    if args.smoke_test:
        from bid_writer.packaging_smoke import run_smoke_test
        raise SystemExit(run_smoke_test(args.smoke_test))

    from bid_writer.gui import run_gui
    with suppress_native_macos_stderr_noise():
        run_gui(args.config)


if __name__ == "__main__":
    main()
