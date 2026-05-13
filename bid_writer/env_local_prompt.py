"""
本地模型连接配置提示。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Callable, Literal

from .config import Config
from .gui_state import get_default_base_dir

EnvPromptPurpose = Literal["startup", "outline", "chapter"]

MAIN_MODEL_ENV_TEXT = "\n".join(
    [
        "BID_WRITER_API_BASE_URL=https://api.openai.com/v1",
        "BID_WRITER_API_KEY=你的 API Key",
        "BID_WRITER_MODEL=gpt-5.4",
    ]
)

OUTLINE_MODEL_ENV_TEXT = "\n".join(
    [
        "# 可选：大纲生成需要单独模型服务时再填写",
        "# BID_WRITER_OUTLINE_API_BASE_URL=https://api.openai.com/v1",
        "# BID_WRITER_OUTLINE_API_KEY=你的 API Key",
        "# BID_WRITER_OUTLINE_MODEL=gpt-5.4",
    ]
)


@dataclass(frozen=True)
class EnvLocalPromptResult:
    configured: bool
    opened: bool
    created: bool
    env_path: Path


def get_env_local_path_for_config(config_path: Path) -> Path:
    """返回配置文件同目录下的本地模型环境文件路径。"""
    return config_path.expanduser().resolve().parent / ".env.local"


def build_default_env_local_content(config_dir: Path) -> str:
    """优先复用发布包里的示例环境文件，缺失时写入最小模板。"""
    candidate_paths = [
        config_dir / ".env.example",
        get_default_base_dir() / ".env.example",
        Path(__file__).resolve().parents[1] / ".env.example",
    ]
    for candidate in candidate_paths:
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                pass

    return "\n".join(
        [
            MAIN_MODEL_ENV_TEXT,
            "BID_WRITER_TEMPERATURE=0.7",
            "BID_WRITER_MAX_TOKENS=10000",
            "",
            OUTLINE_MODEL_ENV_TEXT,
            "",
        ]
    )


def ensure_env_local_file(config_path: Path) -> Path:
    """创建配置同目录下的 `.env.local`，不会覆盖已有文件。"""
    env_path = get_env_local_path_for_config(config_path)
    if env_path.exists():
        return env_path

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        build_default_env_local_content(env_path.parent),
        encoding="utf-8",
    )
    return env_path


def open_file_for_edit(path: Path) -> None:
    """用系统默认方式打开文本文件，便于普通用户填写模型配置。"""
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return

    import subprocess

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def is_model_configured(config: Config, purpose: EnvPromptPurpose) -> bool:
    """判断当前用途是否已有可用 API Key。"""
    if purpose == "outline":
        return bool(config.outline_api_key)
    return bool(config.api_key)


def build_required_env_text(purpose: EnvPromptPurpose) -> str:
    """生成面向用户的 `.env.local` 必填/可选配置文本。"""
    if purpose == "outline":
        return f"{MAIN_MODEL_ENV_TEXT}\n\n{OUTLINE_MODEL_ENV_TEXT}"
    return MAIN_MODEL_ENV_TEXT


def build_missing_env_local_prompt(
    *,
    env_path: Path,
    purpose: EnvPromptPurpose,
    file_exists: bool,
) -> str:
    """生成缺少模型连接时展示给用户的提示文案。"""
    action_text = {
        "startup": "使用生成能力",
        "outline": "生成大纲",
        "chapter": "扩写章节",
    }[purpose]
    required_text = build_required_env_text(purpose)

    if file_exists:
        lead = f"当前还没有可用的模型 API Key，{action_text}前需要先配置 .env.local。"
        question = "是否现在打开它进行设置？"
    else:
        lead = f"当前配置目录中还没有 .env.local，{action_text}前需要先配置模型连接。"
        question = "是否现在创建并打开这个文件？"

    return (
        f"{lead}\n\n"
        f"配置文件位置：\n{env_path}\n\n"
        f"请填写以下内容：\n{required_text}\n\n"
        "保存后，请重启软件或重新载入当前配置，再继续生成。\n\n"
        f"{question}"
    )


def prompt_missing_model_config(
    config: Config,
    *,
    parent,
    purpose: EnvPromptPurpose,
    ask_yes_no: Callable[..., bool] = messagebox.askyesno,
    show_error: Callable[..., None] = messagebox.showerror,
    show_warning: Callable[..., None] = messagebox.showwarning,
    open_editor: Callable[[Path], None] = open_file_for_edit,
) -> EnvLocalPromptResult:
    """缺少模型连接时提示用户创建/打开 `.env.local`。"""
    config_path = config.config_path.expanduser().resolve()
    env_path = get_env_local_path_for_config(config_path)
    if is_model_configured(config, purpose):
        return EnvLocalPromptResult(True, False, False, env_path)

    env_exists = env_path.exists()
    prompt = build_missing_env_local_prompt(
        env_path=env_path,
        purpose=purpose,
        file_exists=env_exists,
    )
    if not ask_yes_no("设置模型连接", prompt, parent=parent):
        return EnvLocalPromptResult(False, False, False, env_path)

    created = False
    if not env_exists:
        try:
            env_path = ensure_env_local_file(config_path)
            created = True
        except OSError as exc:
            show_error("创建失败", f"无法创建 .env.local：\n{exc}", parent=parent)
            return EnvLocalPromptResult(False, False, False, env_path)

    try:
        open_editor(env_path)
    except Exception as exc:
        show_warning(
            "打开失败",
            f".env.local 已准备好，但无法自动打开：\n{exc}\n\n请手动打开并填写：\n{env_path}",
            parent=parent,
        )
        return EnvLocalPromptResult(False, False, created, env_path)

    return EnvLocalPromptResult(False, True, created, env_path)
