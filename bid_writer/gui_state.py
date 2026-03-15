"""
GUI 状态持久化
仅保存界面层状态，不污染业务配置文件。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


STATE_FILENAME = ".bid_writer_gui_state.json"


@dataclass
class GUIState:
    """GUI 持久化状态"""

    last_config_path: Optional[str] = None


def _base_dir(base_dir: Optional[Path] = None) -> Path:
    return (base_dir or Path.cwd()).resolve()


def get_state_file(base_dir: Optional[Path] = None) -> Path:
    """获取 GUI 状态文件路径"""
    return _base_dir(base_dir) / STATE_FILENAME


def _serialize_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def resolve_config_path(config_path: str, base_dir: Optional[Path] = None) -> Path:
    """将配置路径解析为绝对路径"""
    base = _base_dir(base_dir)
    candidate = Path(config_path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def load_gui_state(base_dir: Optional[Path] = None) -> GUIState:
    """读取 GUI 状态"""
    state_file = get_state_file(base_dir)
    if not state_file.exists():
        return GUIState()

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return GUIState()

    if not isinstance(data, dict):
        return GUIState()

    last_config_path = data.get("last_config_path")
    if not isinstance(last_config_path, str) or not last_config_path.strip():
        last_config_path = None

    return GUIState(last_config_path=last_config_path)


def save_gui_state(state: GUIState, base_dir: Optional[Path] = None) -> None:
    """保存 GUI 状态"""
    state_file = get_state_file(base_dir)
    payload = asdict(state)
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def remember_last_config(config_path: str, base_dir: Optional[Path] = None) -> None:
    """记录最后一次成功加载的配置文件"""
    base = _base_dir(base_dir)
    resolved_path = resolve_config_path(config_path, base)
    state = load_gui_state(base)
    state.last_config_path = _serialize_path(resolved_path, base)
    save_gui_state(state, base)


def get_startup_config_candidates(
    explicit_config_path: Optional[str] = None,
    base_dir: Optional[Path] = None
) -> list[str]:
    """获取启动时的候选配置文件列表"""
    base = _base_dir(base_dir)

    if explicit_config_path:
        return [str(resolve_config_path(explicit_config_path, base))]

    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(path_value: Optional[str]) -> None:
        if not path_value:
            return

        resolved = resolve_config_path(path_value, base)
        if resolved in seen:
            return

        seen.add(resolved)
        candidates.append(resolved)

    state = load_gui_state(base)
    add_candidate(state.last_config_path)
    add_candidate("config.yaml")

    for pattern in ("config*.yaml", "config*.yml"):
        for path in sorted(base.glob(pattern), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            if "example" in path.name.lower():
                continue
            add_candidate(str(path))

    return [str(path) for path in candidates]


def resolve_startup_config(
    explicit_config_path: Optional[str] = None,
    base_dir: Optional[Path] = None
) -> str:
    """解析启动时应优先使用的配置文件"""
    for candidate in get_startup_config_candidates(explicit_config_path, base_dir):
        resolved = resolve_config_path(candidate, base_dir)
        if resolved.exists() and resolved.is_file():
            return str(resolved)

    return str(resolve_config_path("config.yaml", base_dir))
