#!/usr/bin/env python3
"""Build the desktop application: uv run --group build python scripts/build_nuitka.py."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "bid-writer"
# Explicit allowlist: never bundle local configuration, keys or project inputs.
RESOURCE_FILES = (
    "config.example.yaml",
    ".env.example",
    "软件说明书.md",
    "roles/system_gate_rules.md",
    "roles/通用投标角色.md",
    "roles/标书架构师.md",
    "roles/example_role.md",
    "roles/tender_section_boundaries.yaml",
)


def resolve_mode(mode: str, target_platform: str) -> str:
    if target_platform not in {"darwin", "win32", "linux"}:
        raise ValueError(f"不支持的构建平台：{target_platform}")
    if mode == "auto":
        return "app" if target_platform == "darwin" else "standalone"
    if mode == "app" and target_platform != "darwin":
        raise ValueError("app 模式仅用于 macOS；其他平台请使用 standalone")
    return mode


def build_command(mode: str, output_dir: Path, *, jobs: int, no_cache: bool) -> list[str]:
    command = [
        sys.executable, "-m", "nuitka",
        f"--mode={mode}",
        f"--output-dir={output_dir}",
        f"--output-folder-name={APP_NAME}",
        f"--output-filename={APP_NAME}.exe" if sys.platform == "win32" else f"--output-filename={APP_NAME}",
        "--enable-plugin=tk-inter",
        "--include-package-data=ttkbootstrap",
        "--include-package-data=docx",
        "--include-package-data=pymupdf4llm",
        f"--include-data-dir={ROOT / 'bid_writer' / 'assets'}=bid_writer/assets",
        "--noinclude-data-files=**/.DS_Store",
        "--noinclude-data-files=**/__pycache__/**",
        "--assume-yes-for-downloads",
        f"--jobs={jobs}",
        f"--report={ROOT / 'log' / ('nuitka-' + mode + '-report.xml')}",
    ]
    command.extend(f"--include-data-files={ROOT / name}={name}" for name in RESOURCE_FILES)
    icon = ROOT / "bid_writer" / "assets" / "brand" / "logo_128.png"
    if sys.platform == "darwin" and mode == "app":
        command.extend([
            "--macos-app-name=标书智写",
            "--macos-signed-app-name=cn.bidwriter.desktop",
            f"--macos-app-icon={icon}",
        ])
    elif sys.platform == "win32":
        command.extend(["--windows-console-mode=disable", f"--windows-icon-from-ico={icon}"])
    if no_cache:
        command.extend(["--clean-cache=all", "--disable-cache=all"])
    command.append(str(ROOT / "run.py"))
    return command


def remove_build_path(path: Path, parent: Path) -> None:
    """Delete only a known build child; refuse paths redirected by symlinks."""
    path.resolve().relative_to(parent.resolve())
    if path.is_symlink() or parent.is_symlink() or path.resolve() == parent.resolve():
        raise ValueError(f"拒绝清理不安全的构建路径：{path}")
    if path.exists():
        shutil.rmtree(path)


def clean_python_caches() -> None:
    for name in ("bid_writer", "scripts", "tests"):
        source_dir = ROOT / name
        for cache in source_dir.rglob("__pycache__"):
            remove_build_path(cache, source_dir)
    remove_build_path(ROOT / ".pytest_cache", ROOT)


def check_environment() -> None:
    import importlib.util

    if importlib.util.find_spec("nuitka") is None:
        raise RuntimeError("缺少 Nuitka，请使用 uv run --group build python scripts/build_nuitka.py")
    # The build Python must contain Tk; the plugin collects its Tcl/Tk runtime.
    import tkinter

    tkinter.Tcl()
    for name in (*RESOURCE_FILES, "run.py", "bid_writer/assets/brand/logo_128.png"):
        if not (ROOT / name).is_file():
            raise RuntimeError(f"缺少构建资源：{name}")
    if sys.platform == "darwin":
        subprocess.run(["xcrun", "--find", "clang"], check=True, stdout=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="标书智写 Nuitka 独立应用构建")
    parser.add_argument("--mode", choices=("auto", "app", "standalone"), default="auto")
    parser.add_argument("--clean", action="store_true", help="清理当前目标的旧构建、发布产物及 Python 测试/字节码缓存")
    parser.add_argument("--no-cache", action="store_true", help="彻底重建：隐含 --clean，并清理和禁用本项目的 Nuitka 缓存")
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 1, 8))
    parser.add_argument("--dry-run", action="store_true", help="打印命令和清理范围，不清理、不编译")
    parser.add_argument("--smoke-test", action="store_true", help="构建后从临时工作目录启动成品，离线检查资源、文档导入和 GUI")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs 必须大于 0")
    try:
        mode = resolve_mode(args.mode, sys.platform)
        target = f"{sys.platform}-{platform.machine().lower()}-{mode}"
        work_dir = ROOT / "build" / "nuitka" / target
        release_dir = ROOT / "dist" / "nuitka" / target
        cache_dir = ROOT / "build" / "nuitka-cache"
        command = build_command(mode, work_dir, jobs=args.jobs, no_cache=args.no_cache)
        print(f"目标：{target}\n发布目录：{release_dir}\n构建缓存：{cache_dir}", flush=True)
        print(shlex.join(command), flush=True)
        if args.clean or args.no_cache:
            print(f"清理：{work_dir}、{release_dir}、源码 __pycache__、.pytest_cache", flush=True)
        if args.dry_run:
            return 0
        check_environment()
        if args.clean or args.no_cache:
            remove_build_path(work_dir, ROOT / "build")
            remove_build_path(release_dir, ROOT / "dist")
            clean_python_caches()
        work_dir.mkdir(parents=True, exist_ok=True)
        (ROOT / "log").mkdir(exist_ok=True)
        env = os.environ.copy()
        # Scope --clean-cache=all to this repository, not other projects.
        env["NUITKA_CACHE_DIR"] = str(cache_dir)
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        artifact_name = f"{APP_NAME}.app" if mode == "app" else f"{APP_NAME}.dist"
        source = work_dir / artifact_name
        if not source.is_dir():
            raise RuntimeError(f"未找到构建产物：{source}")
        remove_build_path(release_dir, ROOT / "dist")
        release_dir.mkdir(parents=True)
        artifact = release_dir / artifact_name
        shutil.copytree(source, artifact, symlinks=True)
        print(f"构建完成：{artifact}", flush=True)
        if args.smoke_test:
            import tempfile

            executable = artifact / "Contents" / "MacOS" / APP_NAME if mode == "app" else artifact / (f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME)
            report = ROOT / "log" / f"nuitka-{target}-smoke.json"
            for key in ("PYTHONPATH", "PYTHONHOME", "TCL_LIBRARY", "TK_LIBRARY"):
                env.pop(key, None)
            with tempfile.TemporaryDirectory(prefix="bid-writer-smoke-") as cwd:
                subprocess.run([str(executable), "--smoke-test", str(report)], cwd=cwd, env=env, check=True, timeout=120)
            print(f"成品验证通过：{report}", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
