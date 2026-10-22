"""
GUI 状态持久化
仅保存界面层状态，不污染业务配置文件。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


STATE_FILENAME = ".bid_writer_gui_state.json"


@dataclass
class GUIState:
    """GUI 持久化状态"""

    last_config_path: Optional[str] = None
    last_generation_target_words: Optional[int] = None
    last_max_mermaid_flowcharts_per_section: Optional[int] = None


def _base_dir(base_dir: Optional[Path] = None) -> Path:
    if base_dir is not None:
        return base_dir.resolve()
    return get_default_base_dir()


def get_default_base_dir() -> Path:
    """返回 GUI 启动时默认读写配置和状态文件的目录。"""
    if is_compiled():
        return get_shared_config_dir()
    return Path.cwd().resolve()


def is_compiled() -> bool:
    """Nuitka 为编译后的模块提供 __compiled__，源码运行时不存在。"""
    return "__compiled__" in globals()


def get_application_root_dir() -> Path:
    """返回共享环境配置、状态和日志的可写目录。"""
    if is_compiled():
        if sys.platform == "darwin":
            return Path.home() / ".bid-writer"
        if sys.platform == "win32":
            # Windows 使用可移动的独立目录，配置保留在程序旁边。
            return Path(__compiled__.containing_dir).resolve()
        data_home = os.environ.get("XDG_DATA_HOME")
        return (Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share") / "bid-writer"
    return get_resource_root_dir()


def get_shared_config_dir() -> Path:
    """共享模型连接及默认配置的目录。"""
    root = get_application_root_dir()
    return root / "config" if is_compiled() and sys.platform == "darwin" else root


def get_log_dir() -> Path:
    """未指定项目日志位置时的默认日志目录。"""
    name = "logs" if is_compiled() and sys.platform == "darwin" else "log"
    return get_application_root_dir() / name


def get_cache_root_dir() -> Path:
    """编译成品的跨项目缓存根目录。"""
    root = get_application_root_dir()
    return root / "cache" if is_compiled() and sys.platform == "darwin" else root


def get_resource_root_dir() -> Path:
    """内置只读资源目录；Nuitka 将资源放在编译模块的相对位置。"""
    return Path(__file__).resolve().parents[1]


def get_state_file(base_dir: Optional[Path] = None) -> Path:
    """获取 GUI 状态文件路径"""
    base = _base_dir(base_dir)
    if is_compiled() and sys.platform == "darwin" and base == get_default_base_dir():
        return get_application_root_dir() / "state" / STATE_FILENAME
    return base / STATE_FILENAME


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

    def parse_optional_int(key: str) -> Optional[int]:
        value = data.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    return GUIState(
        last_config_path=last_config_path,
        last_generation_target_words=parse_optional_int("last_generation_target_words"),
        last_max_mermaid_flowcharts_per_section=parse_optional_int(
            "last_max_mermaid_flowcharts_per_section"
        ),
    )


def save_gui_state(state: GUIState, base_dir: Optional[Path] = None) -> None:
    """保存 GUI 状态"""
    state_file = get_state_file(base_dir)
    payload = asdict(state)
    state_file.parent.mkdir(parents=True, exist_ok=True)
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


def remember_generation_dialog_settings(
    target_words: int,
    max_mermaid_flowcharts_per_section: int,
    base_dir: Optional[Path] = None,
) -> None:
    """记录最近一次确认的生成参数弹窗数值。"""
    base = _base_dir(base_dir)
    state = load_gui_state(base)
    state.last_generation_target_words = int(target_words)
    state.last_max_mermaid_flowcharts_per_section = int(max_mermaid_flowcharts_per_section)
    save_gui_state(state, base)


def get_startup_config_candidates(
    explicit_config_path: Optional[str] = None,
    base_dir: Optional[Path] = None,
    *,
    include_discovered_configs: bool = True,
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

    if include_discovered_configs:
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
    base_dir: Optional[Path] = None,
    *,
    include_discovered_configs: bool = True,
) -> str:
    """解析启动时应优先使用的配置文件"""
    for candidate in get_startup_config_candidates(
        explicit_config_path,
        base_dir,
        include_discovered_configs=include_discovered_configs,
    ):
        resolved = resolve_config_path(candidate, base_dir)
        if resolved.exists() and resolved.is_file():
            return str(resolved)

    return str(resolve_config_path("config.yaml", base_dir))
