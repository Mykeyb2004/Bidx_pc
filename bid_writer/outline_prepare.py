"""
大纲准备阶段的文件读写与锁定辅助函数。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .outline_generator import validate_outline_text


class OutlinePrepareError(RuntimeError):
    """大纲准备无法继续。"""


def outline_path(config: Config) -> Path:
    return Path(config.outline_file).expanduser().resolve()


def load_existing_outline(config: Config) -> str:
    path = outline_path(config)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def set_outline_locked(config_path: str | Path, locked: bool) -> None:
    path = Path(config_path).expanduser().resolve()
    payload: dict[str, Any]
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        payload = {}
    project = payload.setdefault("project", {})
    if not isinstance(project, dict):
        raise OutlinePrepareError("配置文件中的 project 字段不是对象，无法写入 outline_locked。")
    project["outline_locked"] = bool(locked)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip() + "\n",
        encoding="utf-8",
    )


def confirm_outline_and_lock(config: Config, outline_text: str) -> Path:
    messages = validate_outline_text(outline_text)
    errors = [message.text for message in messages if message.level == "error"]
    if errors:
        raise OutlinePrepareError("\n".join(errors))

    path = outline_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = outline_text.strip() + "\n"
    path.write_text(normalized, encoding="utf-8")
    set_outline_locked(config.config_path, True)
    return path
