#!/usr/bin/env python3
"""
Tkinter GUI 主界面
自动标书撰写系统的桌面版界面
"""

import os
import re
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timezone
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk
from typing import Any, Callable, List, Optional
from pathlib import Path

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from .main import BidWriter
from .gui_adapter import GUIAdapter
from .outline_parser import HeadingNode
from .gui_state import (
    get_startup_config_candidates,
    load_gui_state,
    remember_generation_dialog_settings,
    remember_last_config,
)
from .timing_logger import write_timing_log

import threading
import queue
import sys


DEFAULT_CONFIG_FILES = {"config.yaml", "config.yml"}
GUI_THEME_NAME = os.environ.get("BID_WRITER_GUI_THEME", "litera")
GUI_FALLBACK_THEME = "clam"
GUI_FONT_DELTA_ENV = "BID_WRITER_GUI_FONT_DELTA"
CONFIG_DIALOG_MIN_WIDTH = 680
CONFIG_DIALOG_MIN_HEIGHT = 260
CONFIG_DIALOG_MAX_WIDTH = 920
CONFIG_DIALOG_INFO_WRAP_PADDING = 60
MAIN_WINDOW_DEFAULT_WIDTH = 2000
MAIN_WINDOW_DEFAULT_HEIGHT = 1176
MAIN_WINDOW_SCREEN_MARGIN_WIDTH = 48
MAIN_WINDOW_SCREEN_MARGIN_HEIGHT = 50
MAIN_WINDOW_MIN_WIDTH = 800
MAIN_WINDOW_MIN_HEIGHT = 600
MAIN_WINDOW_SCREEN_WIDTH_RATIO = 0.65
MAIN_WINDOW_SCREEN_HEIGHT_RATIO = 0.65
MAIN_OUTLINE_DEFAULT_WIDTH = 520
MAIN_OUTLINE_DEFAULT_RATIO = 0.31
MAIN_OUTLINE_MIN_WIDTH = 360
MAIN_WORKSPACE_MIN_WIDTH = 460
MAIN_OUTLINE_TREE_COLUMN_RATIOS = (0.66, 0.17, 0.17)
MAIN_OUTLINE_TREE_STATUS_MIN_WIDTH = 72
MAIN_OUTLINE_TREE_PROGRESS_MIN_WIDTH = 72
POPUP_OUTLINE_DEFAULT_WIDTH = 320
POPUP_OUTLINE_MIN_WIDTH = 240
POPUP_CONTENT_MIN_WIDTH = 480
GENERATION_DIALOG_MIN_WIDTH = 520
GENERATION_DIALOG_MIN_HEIGHT = 280
GENERATION_DIALOG_EXTRA_WIDTH = 24
GENERATION_DIALOG_EXTRA_HEIGHT = 20
DIALOG_SCREEN_MARGIN_WIDTH = 48
DIALOG_SCREEN_MARGIN_HEIGHT = 50
DIALOG_SCREEN_WIDTH_RATIO = 0.9
DIALOG_SCREEN_HEIGHT_RATIO = 0.9
GUI_DEFAULT_FONT_SIZE = 11
GUI_COMPACT_FONT_SIZE = 10
GUI_HEADING_FONT_SIZE = 12
GUI_TREE_ROWHEIGHT = 28
GUI_DPI_MEDIUM_THRESHOLD = 120.0
GUI_DPI_LARGE_THRESHOLD = 160.0
GUI_SCREEN_WIDTH_MEDIUM_THRESHOLD = 1600
GUI_SCREEN_WIDTH_LARGE_THRESHOLD = 2200
GUI_SCREEN_HEIGHT_MEDIUM_THRESHOLD = 1000
GUI_SCREEN_HEIGHT_LARGE_THRESHOLD = 1400
_WORKSPACE_CHAR_COUNT_UNCHANGED = object()
_TK_ENV_READY = False
_TTKBOOTSTRAP_READY: Optional[bool] = None
_TTKBOOTSTRAP_MODULE = None
CHAPTER_MENU_FACT_CARD_INDEX = 1
CONTEXT_MENU_FACT_CARD_INDEX = 1


@dataclass
class TreeViewState:
    """大纲树展开状态"""

    mode: str = "all"
    expanded_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GuiScaleProfile:
    """GUI 字体与间距缩放档位。"""

    font_delta: int
    default_font_size: int
    compact_font_size: int
    heading_font_size: int
    tree_rowheight: int
    button_padding: tuple[int, int]
    field_padding: tuple[int, int]
    text_padding: tuple[int, int]


@dataclass(frozen=True)
class WindowSizeSpec:
    """屏幕约束后的窗口尺寸规格。"""

    width: int
    height: int
    min_width: int
    min_height: int


@dataclass(frozen=True)
class GuiColorPalette:
    """GUI 常用颜色面板。"""

    surface_background: str
    input_background: str
    input_foreground: str
    border_color: str
    accent_color: str


@dataclass(frozen=True)
class GenerationErrorFeedback:
    """扩写失败时展示给用户的结构化反馈。"""

    stage_label: str
    category_title: str
    short_message: str
    status_text: str
    workspace_meta_text: str
    workspace_body_text: str
    dialog_title: str
    dialog_message: str
    append_to_workspace: bool = False


@dataclass(frozen=True)
class GenerationFactCardSelectionDialogState:
    """生成参数对话框中的事实卡片选择状态。"""

    global_cards: list[Any]
    available_cards: list[Any]
    initial_selections: list[Any]
    default_mode: bool
    summary_text: str


class GenerationFailedError(RuntimeError):
    """包装扩写失败反馈，便于 UI 统一处理。"""

    def __init__(self, feedback: GenerationErrorFeedback):
        super().__init__(feedback.short_message)
        self.feedback = feedback


def _is_valid_tcl_dir(path: Path) -> bool:
    """判断是否是有效的 Tcl 脚本目录"""
    return path.is_dir() and (path / "init.tcl").exists()


def _is_valid_tk_dir(path: Path) -> bool:
    """判断是否是有效的 Tk 脚本目录"""
    return path.is_dir() and (path / "tk.tcl").exists()


def ensure_tk_runtime() -> None:
    """为 uv 管理的 Python 自动补齐 Tcl/Tk 脚本目录"""
    global _TK_ENV_READY

    if _TK_ENV_READY:
        return

    current_tcl = os.environ.get("TCL_LIBRARY", "")
    current_tk = os.environ.get("TK_LIBRARY", "")
    if _is_valid_tcl_dir(Path(current_tcl)) and _is_valid_tk_dir(Path(current_tk)):
        _TK_ENV_READY = True
        return

    candidate_lib_dirs: list[Path] = []
    for prefix in (sys.base_prefix, sys.prefix):
        if not prefix:
            continue
        lib_dir = Path(prefix).expanduser().resolve() / "lib"
        if lib_dir not in candidate_lib_dirs:
            candidate_lib_dirs.append(lib_dir)

    for lib_dir in candidate_lib_dirs:
        if not lib_dir.exists():
            continue

        tcl_dirs = {
            path.name.removeprefix("tcl"): path
            for path in lib_dir.glob("tcl*")
            if _is_valid_tcl_dir(path)
        }
        tk_dirs = {
            path.name.removeprefix("tk"): path
            for path in lib_dir.glob("tk*")
            if _is_valid_tk_dir(path)
        }

        common_versions = sorted(set(tcl_dirs) & set(tk_dirs), reverse=True)
        for version in common_versions:
            os.environ["TCL_LIBRARY"] = str(tcl_dirs[version])
            os.environ["TK_LIBRARY"] = str(tk_dirs[version])
            _TK_ENV_READY = True
            return


def _display_path(path: Path, base_dir: Path) -> str:
    """返回适合界面展示的路径"""
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _bootstyle_kwargs(bootstyle: Optional[str] = None) -> dict[str, str]:
    """保留调用位，当前仍使用标准 ttk 控件。"""
    if bootstyle:
        return {}
    return {}


def _can_use_ttkbootstrap() -> bool:
    """仅在 Pillow/Tk 桥接可用时启用 ttkbootstrap。"""
    global _TTKBOOTSTRAP_READY, _TTKBOOTSTRAP_MODULE

    if _TTKBOOTSTRAP_READY is not None:
        return _TTKBOOTSTRAP_READY

    try:
        from PIL import _imagingtk  # noqa: F401
        import ttkbootstrap as ttkbootstrap_module
    except Exception:
        _TTKBOOTSTRAP_READY = False
        _TTKBOOTSTRAP_MODULE = None
        return False

    _TTKBOOTSTRAP_READY = True
    _TTKBOOTSTRAP_MODULE = ttkbootstrap_module
    return True


def _safe_named_font(name: str) -> Optional[tkfont.Font]:
    try:
        return tkfont.nametofont(name)
    except tk.TclError:
        return None


def _parse_gui_font_delta(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return int(value.strip())
    except ValueError:
        return 0


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _shift_hex_color(color: str, delta: int) -> str:
    if not color.startswith("#") or len(color) != 7:
        return color

    channels = []
    for index in range(1, 7, 2):
        channel = int(color[index:index + 2], 16)
        channels.append(max(0, min(255, channel + delta)))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def _count_text_characters(text: str) -> int:
    """统计正文字符数，保留空白和换行。"""
    return len(text)


def _format_workspace_char_count(count: Optional[int]) -> str:
    """格式化正文工作区的字符数标签。"""
    if count is None:
        return "当前节点已生成字符数：-"
    return f"当前节点已生成字符数：{max(0, count):,}"


def _format_heading_tree_title(title: str) -> str:
    """格式化章节树标题。"""
    return title


def _matches_exception_type(
    exc: BaseException,
    *,
    names: tuple[str, ...] = (),
    types: tuple[type[BaseException], ...] = (),
) -> bool:
    """同时兼容真实 SDK 异常和测试里的同名伪异常。"""
    return isinstance(exc, types) or type(exc).__name__ in names


def _normalize_generation_error_detail(exc: BaseException) -> str:
    detail = _first_non_empty(str(exc), repr(exc))
    if detail:
        return " ".join(detail.split())
    return f"{type(exc).__name__}: 未提供详细错误信息"


def _classify_generation_error(exc: BaseException) -> tuple[str, str, list[str]]:
    """把底层异常归类成用户可读的失败原因。"""
    detail = _normalize_generation_error_detail(exc)
    detail_lower = detail.lower()
    status_code = getattr(exc, "status_code", None)

    if _matches_exception_type(
        exc,
        names=("APITimeoutError", "TimeoutError"),
        types=(APITimeoutError, TimeoutError),
    ) or "timeout" in detail_lower or "timed out" in detail_lower or "未收到任何内容" in detail:
        return (
            "模型调用超时",
            "模型长时间未返回可用内容。",
            [
                "稍后重试，确认当前模型服务没有卡住或排队过久。",
                "如果经常发生，可检查超时时间配置是否过短，或更换更稳定的模型服务。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("AuthenticationError",),
        types=(AuthenticationError,),
    ):
        return (
            "模型鉴权失败",
            "当前 API Key 或鉴权配置不可用。",
            [
                "检查当前使用的 API Key 是否填写正确、是否已过期。",
                "确认 base URL、模型服务商和鉴权方式彼此匹配。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("PermissionDeniedError",),
        types=(PermissionDeniedError,),
    ):
        return (
            "模型权限不足",
            "当前账号没有调用该模型或该接口的权限。",
            [
                "检查所选模型是否在当前账号或代理服务中可用。",
                "确认服务端没有对该模型或接口做权限限制。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("RateLimitError",),
        types=(RateLimitError,),
    ) or status_code == 429 or "rate limit" in detail_lower or "too many requests" in detail_lower or "quota" in detail_lower:
        return (
            "模型请求受限",
            "请求频率、并发或额度已触发限制。",
            [
                "稍后重试，避免短时间内连续高频调用。",
                "检查当前账号额度、并发上限或代理服务的限流策略。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("APIConnectionError", "ConnectionError", "OSError"),
        types=(APIConnectionError, ConnectionError, OSError),
    ) or any(
        keyword in detail_lower
        for keyword in (
            "connection error",
            "failed to establish a new connection",
            "connection refused",
            "temporary failure in name resolution",
            "name or service not known",
            "nodename nor servname provided",
            "no route to host",
        )
    ):
        return (
            "无法连接模型服务",
            "本地程序未能连通当前模型接口。",
            [
                "检查网络连通性，以及 base URL 是否填写正确。",
                "如果通过代理或中转服务调用，确认该服务当前可访问且没有拦截请求。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("BadRequestError",),
        types=(BadRequestError,),
    ) or status_code == 400 or "invalid_request" in detail_lower or "context length" in detail_lower or "maximum context length" in detail_lower:
        return (
            "模型请求参数无效",
            "当前请求内容或参数不符合模型接口要求。",
            [
                "检查模型名称、最大输出长度、上下文长度和代理兼容性是否正确。",
                "如果近期改过配置，优先排查 base URL、model、max_tokens 等字段。",
            ],
        )

    if _matches_exception_type(
        exc,
        names=("InternalServerError",),
        types=(InternalServerError,),
    ) or (
        _matches_exception_type(exc, names=("APIStatusError",), types=(APIStatusError,))
        and isinstance(status_code, int)
        and status_code >= 500
    ) or "server error" in detail_lower:
        return (
            "模型服务内部错误",
            "模型服务端返回了异常状态。",
            [
                "稍后重试，确认服务端当前没有故障或维护。",
                "如果问题持续出现，优先排查代理服务或更换模型节点。",
            ],
        )

    return (
        "模型调用失败",
        "模型接口返回了未分类异常。",
        [
            "检查当前配置中的模型地址、模型名和密钥是否一致。",
            "查看日志中的原始报错信息，确认是请求参数问题还是服务端异常。",
        ],
    )


def _build_generation_error_feedback(
    *,
    heading_title: str,
    heading_full_path: str,
    stage_label: str,
    exc: BaseException,
    has_partial_output: bool,
) -> GenerationErrorFeedback:
    """生成扩写失败时展示在工作区和弹窗中的完整文案。"""
    normalized_stage = stage_label.strip() or "调用模型"
    category_title, summary, suggestions = _classify_generation_error(exc)
    detail = _normalize_generation_error_detail(exc)

    if has_partial_output:
        progress_hint = "当前章节已经返回部分正文，已返回内容会保留在工作区。"
        workspace_body = "\n".join(
            [
                "",
                "",
                "【生成中断提示】",
                progress_hint,
                f"中断阶段：{normalized_stage}",
                f"判断结果：{category_title}",
                f"详细信息：{detail}",
                "",
                "建议排查：",
                *[f"{index}. {item}" for index, item in enumerate(suggestions, 1)],
            ]
        )
    else:
        progress_hint = "当前章节在正文开始输出前就失败了，所以右侧暂时没有生成内容。"
        workspace_body = "\n".join(
            [
                "本次扩写未能完成。",
                progress_hint,
                "",
                f"章节：{heading_full_path}",
                f"失败阶段：{normalized_stage}",
                f"判断结果：{category_title}",
                f"详细信息：{detail}",
                "",
                "建议排查：",
                *[f"{index}. {item}" for index, item in enumerate(suggestions, 1)],
            ]
        )

    dialog_lines = [
        f"章节“{heading_title}”扩写失败。",
        progress_hint,
        "",
        f"失败阶段：{normalized_stage}",
        f"判断结果：{category_title}",
        f"详细信息：{detail}",
        "",
        "建议排查：",
        *[f"{index}. {item}" for index, item in enumerate(suggestions, 1)],
    ]

    short_message = f"{category_title}：{summary}"
    return GenerationErrorFeedback(
        stage_label=normalized_stage,
        category_title=category_title,
        short_message=short_message,
        status_text=f"扩写失败：{heading_title}（{category_title}）",
        workspace_meta_text=f"扩写失败：{category_title}（阶段：{normalized_stage}）",
        workspace_body_text=workspace_body,
        dialog_title="章节扩写失败",
        dialog_message="\n".join(dialog_lines),
        append_to_workspace=has_partial_output,
    )


def _format_batch_generation_failure_message(failed_titles: list[str]) -> str:
    """批量生成结束后，对失败章节做一次集中提示。"""
    if not failed_titles:
        return ""

    display_titles = failed_titles[:5]
    remaining = len(failed_titles) - len(display_titles)
    lines = [
        f"本次批量生成中有 {len(failed_titles)} 个章节失败：",
        "",
    ]
    lines.extend(f"- {title}" for title in display_titles)
    if remaining > 0:
        lines.append(f"- 其余 {remaining} 个章节请查看右侧工作区和底部状态栏")
    lines.extend(
        [
            "",
            "系统已经把最近一次失败的详细原因写到右侧工作区，可直接按提示排查后重试。",
        ]
    )
    return "\n".join(lines)


def _compute_gui_font_delta(
    *,
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
    dpi: Optional[float] = None,
    manual_delta: int = 0,
) -> int:
    auto_delta = 0
    if (
        (dpi is not None and dpi >= GUI_DPI_MEDIUM_THRESHOLD)
        or (screen_width is not None and screen_width >= GUI_SCREEN_WIDTH_MEDIUM_THRESHOLD)
        or (screen_height is not None and screen_height >= GUI_SCREEN_HEIGHT_MEDIUM_THRESHOLD)
    ):
        auto_delta = 1
    if (
        (dpi is not None and dpi >= GUI_DPI_LARGE_THRESHOLD)
        or (screen_width is not None and screen_width >= GUI_SCREEN_WIDTH_LARGE_THRESHOLD)
        or (screen_height is not None and screen_height >= GUI_SCREEN_HEIGHT_LARGE_THRESHOLD)
    ):
        auto_delta = 2
    return max(-1, min(3, auto_delta + manual_delta))


def _build_gui_scale_profile(
    *,
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
    dpi: Optional[float] = None,
    manual_delta: int = 0,
) -> GuiScaleProfile:
    font_delta = _compute_gui_font_delta(
        screen_width=screen_width,
        screen_height=screen_height,
        dpi=dpi,
        manual_delta=manual_delta,
    )
    default_font_size = max(10, GUI_DEFAULT_FONT_SIZE + font_delta)
    compact_font_size = max(10, GUI_COMPACT_FONT_SIZE + font_delta)
    heading_font_size = max(11, GUI_HEADING_FONT_SIZE + font_delta)
    return GuiScaleProfile(
        font_delta=font_delta,
        default_font_size=default_font_size,
        compact_font_size=compact_font_size,
        heading_font_size=heading_font_size,
        tree_rowheight=max(GUI_TREE_ROWHEIGHT, GUI_TREE_ROWHEIGHT + font_delta * 4),
        button_padding=(max(10, 12 + font_delta * 2), max(6, 7 + font_delta)),
        field_padding=(max(5, 6 + font_delta), max(4, 5 + font_delta)),
        text_padding=(max(8, 10 + font_delta), max(6, 8 + font_delta)),
    )


def _compute_dialog_target_size(
    *,
    requested_width: int,
    requested_height: int,
    min_width: int,
    min_height: int,
    current_width: int = 0,
    current_height: int = 0,
    extra_width: int = 0,
    extra_height: int = 0,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
) -> tuple[int, int]:
    width = max(requested_width + extra_width, min_width, current_width)
    height = max(requested_height + extra_height, min_height, current_height)

    if max_width is not None:
        width = min(width, max_width)
    if max_height is not None:
        height = min(height, max_height)

    return width, height


def _compute_centered_window_geometry(
    *,
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
) -> str:
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def _set_centered_window_geometry(window: tk.Misc, width: int, height: int) -> None:
    window.geometry(
        _compute_centered_window_geometry(
            width=width,
            height=height,
            screen_width=window.winfo_screenwidth(),
            screen_height=window.winfo_screenheight(),
        )
    )


def _compute_screen_size_limit(
    screen_size: Optional[int],
    *,
    margin: int,
    ratio: Optional[float] = None,
    ratio_threshold: Optional[int] = None,
) -> Optional[int]:
    if not screen_size or screen_size <= 0:
        return None

    limit = max(1, screen_size - margin)
    if ratio is not None and (ratio_threshold is None or screen_size <= ratio_threshold):
        limit = min(limit, max(1, int(screen_size * ratio)))
    return limit


def _compute_screen_limited_dialog_size(
    *,
    desired_width: int,
    desired_height: int,
    min_width: int,
    min_height: int,
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
    width_ratio: float = DIALOG_SCREEN_WIDTH_RATIO,
    height_ratio: float = DIALOG_SCREEN_HEIGHT_RATIO,
    margin_width: int = DIALOG_SCREEN_MARGIN_WIDTH,
    margin_height: int = DIALOG_SCREEN_MARGIN_HEIGHT,
) -> WindowSizeSpec:
    max_width = _compute_screen_size_limit(
        screen_width,
        margin=margin_width,
        ratio=width_ratio,
    )
    max_height = _compute_screen_size_limit(
        screen_height,
        margin=margin_height,
        ratio=height_ratio,
    )

    width, height = _compute_dialog_target_size(
        requested_width=desired_width,
        requested_height=desired_height,
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
    )
    limited_min_width, limited_min_height = _compute_dialog_target_size(
        requested_width=min_width,
        requested_height=min_height,
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
    )

    return WindowSizeSpec(
        width=width,
        height=height,
        min_width=limited_min_width,
        min_height=limited_min_height,
    )


def _compute_main_window_target_size(
    *,
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
) -> tuple[int, int]:
    """计算主窗口初始尺寸，优先匹配当前截图宽度并避免超出屏幕。"""

    max_width = _compute_screen_size_limit(
        screen_width,
        margin=MAIN_WINDOW_SCREEN_MARGIN_WIDTH,
        ratio=MAIN_WINDOW_SCREEN_WIDTH_RATIO,
    )
    if max_width is not None:
        width = min(MAIN_WINDOW_DEFAULT_WIDTH, max_width)
    else:
        width = MAIN_WINDOW_DEFAULT_WIDTH

    max_height = _compute_screen_size_limit(
        screen_height,
        margin=MAIN_WINDOW_SCREEN_MARGIN_HEIGHT,
        ratio=MAIN_WINDOW_SCREEN_HEIGHT_RATIO,
    )
    if max_height is not None:
        height = min(MAIN_WINDOW_DEFAULT_HEIGHT, max_height)
    else:
        height = MAIN_WINDOW_DEFAULT_HEIGHT

    return width, height


def _compute_main_window_min_size(
    *,
    screen_width: Optional[int] = None,
    screen_height: Optional[int] = None,
) -> tuple[int, int]:
    max_width = _compute_screen_size_limit(
        screen_width,
        margin=MAIN_WINDOW_SCREEN_MARGIN_WIDTH,
        ratio=MAIN_WINDOW_SCREEN_WIDTH_RATIO,
    )
    max_height = _compute_screen_size_limit(
        screen_height,
        margin=MAIN_WINDOW_SCREEN_MARGIN_HEIGHT,
        ratio=MAIN_WINDOW_SCREEN_HEIGHT_RATIO,
    )

    width = min(MAIN_WINDOW_MIN_WIDTH, max_width) if max_width is not None else MAIN_WINDOW_MIN_WIDTH
    height = min(MAIN_WINDOW_MIN_HEIGHT, max_height) if max_height is not None else MAIN_WINDOW_MIN_HEIGHT
    return width, height


def _compute_main_outline_pane_width(
    *,
    total_width: int,
    min_left_width: int = MAIN_OUTLINE_MIN_WIDTH,
    min_right_width: int = MAIN_WORKSPACE_MIN_WIDTH,
    default_ratio: float = MAIN_OUTLINE_DEFAULT_RATIO,
) -> int:
    """按主窗口左右栏比例计算左侧目录栏默认宽度。"""

    if total_width <= min_left_width + min_right_width:
        return min_left_width

    ratio_width = round(total_width * default_ratio)
    max_left_width = total_width - min_right_width
    return max(min_left_width, min(ratio_width, max_left_width))


def _compute_outline_tree_column_widths(*, total_width: int) -> tuple[int, int, int]:
    """按“标题 / 状态 / 进度”的比例计算大纲树列宽。"""

    available_width = max(1, total_width)
    _, status_ratio, progress_ratio = MAIN_OUTLINE_TREE_COLUMN_RATIOS

    use_minimums = (
        available_width
        >= MAIN_OUTLINE_TREE_STATUS_MIN_WIDTH + MAIN_OUTLINE_TREE_PROGRESS_MIN_WIDTH + 1
    )
    status_width = round(available_width * status_ratio)
    progress_width = round(available_width * progress_ratio)
    if use_minimums:
        status_width = max(MAIN_OUTLINE_TREE_STATUS_MIN_WIDTH, status_width)
        progress_width = max(MAIN_OUTLINE_TREE_PROGRESS_MIN_WIDTH, progress_width)

    title_width = max(1, available_width - status_width - progress_width)
    return title_width, status_width, progress_width


def _clamp_persisted_int(value: Optional[int], *, fallback: int, min_value: int, max_value: int) -> int:
    """把持久化数值约束到当前界面允许范围内。"""
    if value is None:
        return fallback
    return max(min_value, min(max_value, int(value)))


def _resolve_generation_dialog_defaults(
    *,
    persisted_target_words: Optional[int],
    persisted_max_mermaid_flowcharts_per_section: Optional[int],
    target_words_default: int,
    target_words_min: int,
    target_words_max: int,
    mermaid_default: int = 0,
    mermaid_max: int = 999,
) -> tuple[int, int]:
    """计算生成参数弹窗的默认值。"""
    return (
        _clamp_persisted_int(
            persisted_target_words,
            fallback=target_words_default,
            min_value=target_words_min,
            max_value=target_words_max,
        ),
        _clamp_persisted_int(
            persisted_max_mermaid_flowcharts_per_section,
            fallback=mermaid_default,
            min_value=0,
            max_value=mermaid_max,
        ),
    )


def _build_gui_color_palette(style: ttk.Style) -> GuiColorPalette:
    surface_background = _first_non_empty(
        style.lookup("TFrame", "background"),
        style.lookup("TLabel", "background"),
        "#dcdad5",
    )
    input_background = _first_non_empty(
        style.lookup("TEntry", "fieldbackground"),
        style.lookup("Treeview", "background"),
        "#ffffff",
    )
    input_foreground = _first_non_empty(
        style.lookup("TEntry", "foreground"),
        style.lookup("Treeview", "foreground"),
        style.lookup("TLabel", "foreground"),
        "black",
    )
    return GuiColorPalette(
        surface_background=surface_background,
        input_background=input_background,
        input_foreground=input_foreground,
        border_color=_shift_hex_color(surface_background, -18),
        accent_color="#3b82f6",
    )


def _get_gui_scale_profile(master: tk.Misc) -> GuiScaleProfile:
    root = master._root()
    existing_profile = getattr(root, "_bid_writer_gui_scale_profile", None)
    if existing_profile is not None:
        return existing_profile

    screen_width: Optional[int]
    screen_height: Optional[int]
    dpi: Optional[float]

    try:
        screen_width = int(root.winfo_screenwidth())
        screen_height = int(root.winfo_screenheight())
    except (tk.TclError, ValueError, TypeError):
        screen_width = None
        screen_height = None

    try:
        dpi = float(root.winfo_fpixels("1i"))
        if dpi <= 0:
            dpi = None
    except (tk.TclError, ValueError, TypeError):
        dpi = None

    profile = _build_gui_scale_profile(
        screen_width=screen_width,
        screen_height=screen_height,
        dpi=dpi,
        manual_delta=_parse_gui_font_delta(os.environ.get(GUI_FONT_DELTA_ENV)),
    )
    setattr(root, "_bid_writer_gui_scale_profile", profile)
    return profile


def _get_gui_color_palette(master: tk.Misc) -> GuiColorPalette:
    root = master._root()
    existing_palette = getattr(root, "_bid_writer_gui_color_palette", None)
    if existing_palette is not None:
        return existing_palette

    palette = _build_gui_color_palette(ttk.Style(master))
    setattr(root, "_bid_writer_gui_color_palette", palette)
    return palette


def apply_window_surface(widget: tk.Misc) -> None:
    """让 Tk 顶层窗口背景与 ttk 主题底色一致。"""
    palette = _get_gui_color_palette(widget)
    try:
        widget.configure(background=palette.surface_background)
    except tk.TclError:
        return


def style_canvas_widget(widget: tk.Canvas) -> None:
    """统一 Canvas 背景，避免与 ttk 容器出现色差。"""
    palette = _get_gui_color_palette(widget)
    widget.configure(background=palette.surface_background, highlightbackground=palette.surface_background)


def style_paned_window(widget: tk.PanedWindow) -> None:
    """统一 PanedWindow 分隔色，避免出现突兀的硬编码色块。"""
    palette = _get_gui_color_palette(widget)
    widget.configure(background=palette.border_color)


class TreeviewHoverTooltip:
    """为 Treeview 行提供悬浮提示。"""

    def __init__(
        self,
        tree: ttk.Treeview,
        text_provider: Callable[[str], str],
        *,
        delay_ms: int = 450,
    ) -> None:
        self.tree = tree
        self.text_provider = text_provider
        self.delay_ms = delay_ms
        self.tip_window: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        self._pending_item_id = ""
        self._pending_text = ""
        self._last_pointer = (0, 0)
        self._active_item_id = ""

        tree.bind("<Motion>", self._on_motion, add="+")
        tree.bind("<Leave>", self._hide, add="+")
        tree.bind("<ButtonPress>", self._hide, add="+")
        tree.bind("<Destroy>", self._hide, add="+")

    def _cancel_pending(self) -> None:
        if self._after_id is None:
            return
        try:
            self.tree.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _on_motion(self, event) -> None:
        try:
            item_id = self.tree.identify_row(event.y)
        except tk.TclError:
            self._hide()
            return

        text = self.text_provider(item_id) if item_id else ""
        if not item_id or not text:
            self._hide()
            return

        self._last_pointer = (event.x_root, event.y_root)
        if item_id == self._active_item_id and self.tip_window is not None:
            return
        if item_id == self._pending_item_id and text == self._pending_text:
            return

        self._hide()
        self._pending_item_id = item_id
        self._pending_text = text
        try:
            self._after_id = self.tree.after(self.delay_ms, self._show)
        except tk.TclError:
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if (
            not self._pending_item_id
            or not self._pending_text
            or self.tip_window is not None
        ):
            return
        try:
            if not self.tree.winfo_exists():
                return
        except tk.TclError:
            return

        x = self._last_pointer[0] + 16
        y = self._last_pointer[1] + 18

        tip = tk.Toplevel(self.tree)
        apply_window_surface(tip)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")

        container = ttk.Frame(tip, padding=(10, 8))
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            container,
            text=self._pending_text,
            justify=tk.LEFT,
            wraplength=360,
        ).pack(fill=tk.BOTH, expand=True)

        self.tip_window = tip
        self._active_item_id = self._pending_item_id

    def _hide(self, _event=None) -> None:
        self._cancel_pending()
        self._pending_item_id = ""
        self._pending_text = ""
        self._active_item_id = ""
        if self.tip_window is not None:
            try:
                self.tip_window.destroy()
            except tk.TclError:
                pass
            self.tip_window = None


def _configure_named_fonts(profile: GuiScaleProfile) -> None:
    """统一调整 Tk 默认字体，保证 ttk 与原生控件观感一致。"""
    font_updates = {
        "TkDefaultFont": {"size": profile.default_font_size},
        "TkTextFont": {"size": profile.default_font_size},
        "TkMenuFont": {"size": profile.default_font_size},
        "TkFixedFont": {"size": profile.default_font_size},
        "TkHeadingFont": {"size": profile.heading_font_size, "weight": "bold"},
    }
    for font_name, options in font_updates.items():
        named_font = _safe_named_font(font_name)
        if named_font is not None:
            named_font.configure(**options)


def setup_gui_theme(master: tk.Misc) -> ttk.Style:
    """为当前 Tk 应用启用统一主题和基础控件样式。"""
    root = master._root()
    profile = _get_gui_scale_profile(root)
    existing_style = getattr(root, "_bid_writer_style", None)
    if existing_style is not None:
        return existing_style

    root.option_add("*tearOff", False)
    _configure_named_fonts(profile)

    bootstrap_style = None
    if _can_use_ttkbootstrap() and _TTKBOOTSTRAP_MODULE is not None:
        try:
            bootstrap_style = _TTKBOOTSTRAP_MODULE.Style(theme=GUI_THEME_NAME)
        except Exception:
            bootstrap_style = None

    style = ttk.Style(master)
    if bootstrap_style is None and GUI_FALLBACK_THEME in style.theme_names():
        style.theme_use(GUI_FALLBACK_THEME)

    muted_foreground = "#5f6b7a"
    style.configure("TButton", padding=profile.button_padding)
    style.configure("TEntry", padding=profile.field_padding)
    style.configure("TCombobox", padding=profile.field_padding)
    style.configure("TSpinbox", padding=profile.field_padding)
    style.configure("Treeview", rowheight=profile.tree_rowheight)
    style.configure("Treeview.Heading", font=("TkDefaultFont", profile.compact_font_size, "bold"))
    style.configure("SummaryLabel.TLabel", font=("TkDefaultFont", profile.compact_font_size, "bold"))
    style.configure("SummaryValue.TLabel", font=("TkDefaultFont", profile.compact_font_size))
    style.configure("SectionTitle.TLabel", font=("TkDefaultFont", profile.default_font_size, "bold"))
    style.configure("Muted.TLabel", foreground=muted_foreground)

    palette = _build_gui_color_palette(style)
    setattr(root, "_bid_writer_gui_color_palette", palette)
    setattr(root, "_bid_writer_bootstrap_style", bootstrap_style)
    setattr(root, "_bid_writer_style", style)
    return style


def style_text_widget(widget: tk.Text) -> None:
    """统一原生 Text 控件的观感。"""
    profile = _get_gui_scale_profile(widget)
    palette = _get_gui_color_palette(widget)
    widget.configure(
        font="TkFixedFont",
        background=palette.input_background,
        foreground=palette.input_foreground,
        relief=tk.FLAT,
        borderwidth=0,
        padx=profile.text_padding[0],
        pady=profile.text_padding[1],
        highlightthickness=1,
        highlightbackground=palette.border_color,
        highlightcolor=palette.accent_color,
        insertbackground=palette.input_foreground,
        selectbackground=palette.accent_color,
        selectforeground="#ffffff",
        insertwidth=2,
    )


def discover_config_files(base_dir: Optional[Path] = None) -> list[Path]:
    """发现当前工作目录中的配置文件"""
    search_dir = (base_dir or Path.cwd()).resolve()
    config_paths: list[Path] = []
    seen: set[Path] = set()

    for pattern in ("config*.yaml", "config*.yml"):
        for path in search_dir.glob(pattern):
            if not path.is_file():
                continue
            if "example" in path.name.lower():
                continue

            resolved = path.resolve()
            if resolved in seen:
                continue

            seen.add(resolved)
            config_paths.append(resolved)

    config_paths.sort(
        key=lambda path: (
            0 if path.name.lower() in DEFAULT_CONFIG_FILES else 1,
            path.name.lower()
        )
    )
    return config_paths


class ConfigSelectionDialog(tk.Toplevel):
    """配置文件选择对话框"""

    def __init__(self, parent, initial_path: Optional[str] = None):
        super().__init__(parent)
        apply_window_surface(self)

        self.base_dir = Path.cwd().resolve()
        self.result: Optional[str] = None
        self._config_map: dict[str, Path] = {}

        self.title("选择配置文件")
        self.resizable(False, False)
        self._has_visible_parent = bool(
            parent is not None
            and parent.winfo_exists()
            and parent.state() != "withdrawn"
        )

        if self._has_visible_parent:
            self.transient(parent)

        self.grab_set()

        self.config_var = tk.StringVar()
        self.info_var = tk.StringVar()

        self._create_widgets()
        self._load_config_choices(initial_path)
        self._fit_to_content()
        self._center_window()
        self._show_dialog()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Return>", lambda event: self._on_confirm())
        self.bind("<Escape>", lambda event: self._on_cancel())

    def _create_widgets(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="请选择本次运行使用的配置文件",
            style="SectionTitle.TLabel"
        ).pack(anchor=tk.W)

        ttk.Label(
            container,
            text="默认列出当前目录下的 config*.yaml，可点击“浏览...”选择其它 YAML 文件。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(6, 16))

        select_frame = ttk.Frame(container)
        select_frame.pack(fill=tk.X)

        self.config_combo = ttk.Combobox(
            select_frame,
            textvariable=self.config_var,
            state="readonly",
            width=58
        )
        self.config_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.config_combo.bind("<<ComboboxSelected>>", lambda event: self._update_info())

        ttk.Button(
            select_frame,
            text="浏览...",
            command=self._browse_config_file,
            padding=(12, 6),
            **_bootstyle_kwargs("secondary")
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.info_label = ttk.Label(
            container,
            textvariable=self.info_var,
            wraplength=560,
            justify=tk.LEFT,
            style="Muted.TLabel",
        )
        self.info_label.pack(anchor=tk.W, pady=(14, 20))

        button_frame = ttk.Frame(container)
        button_frame.pack(anchor=tk.E)

        ttk.Button(
            button_frame,
            text="取消",
            command=self._on_cancel,
            width=10,
            padding=(12, 6),
            **_bootstyle_kwargs("secondary")
        ).pack(side=tk.LEFT, padx=6)

        ttk.Button(
            button_frame,
            text="确定",
            command=self._on_confirm,
            width=10,
            padding=(12, 6),
            **_bootstyle_kwargs("primary")
        ).pack(side=tk.LEFT)

    def _load_config_choices(self, initial_path: Optional[str]) -> None:
        config_paths = discover_config_files(self.base_dir)
        initial_resolved = self._resolve_existing_path(initial_path)

        if initial_resolved and initial_resolved not in config_paths:
            config_paths.append(initial_resolved)

        config_paths.sort(
            key=lambda path: (
                0 if path.name.lower() in DEFAULT_CONFIG_FILES else 1,
                path.name.lower()
            )
        )

        values: list[str] = []
        self._config_map.clear()

        for path in config_paths:
            display_value = _display_path(path, self.base_dir)
            values.append(display_value)
            self._config_map[display_value] = path

        self.config_combo["values"] = values

        if initial_resolved:
            self.config_var.set(_display_path(initial_resolved, self.base_dir))
        elif values:
            self.config_var.set(values[0])
        else:
            self.config_var.set("")

        self._update_info()

    def _resolve_existing_path(self, path_value: Optional[str]) -> Optional[Path]:
        if not path_value:
            return None

        candidate = Path(path_value).expanduser()
        if not candidate.is_absolute():
            candidate = (self.base_dir / candidate).resolve()

        if candidate.exists() and candidate.is_file():
            return candidate
        return None

    def _browse_config_file(self) -> None:
        initial_dir = self.base_dir
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择配置文件",
            initialdir=str(initial_dir),
            filetypes=[
                ("YAML 配置文件", "*.yaml"),
                ("YAML 配置文件", "*.yml"),
                ("所有文件", "*.*"),
            ],
        )
        if not selected:
            return

        selected_path = Path(selected).expanduser().resolve()
        self._load_config_choices(str(selected_path))
        self.config_var.set(_display_path(selected_path, self.base_dir))
        self._update_info()

    def _update_info(self) -> None:
        selected_key = self.config_var.get().strip()
        selected_path = self._config_map.get(selected_key)
        if not selected_path:
            self.info_var.set("未发现可用配置文件，请点击“浏览...”选择 YAML 配置。")
            self._fit_to_content()
            return

        self.info_var.set(f"当前将使用：{selected_path}")
        self._fit_to_content()

    def _on_confirm(self) -> None:
        selected_key = self.config_var.get().strip()
        selected_path = self._config_map.get(selected_key)
        if not selected_path:
            messagebox.showwarning("提示", "请先选择配置文件。", parent=self)
            return

        self.result = str(selected_path)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        _set_centered_window_geometry(self, width, height)

    def _fit_to_content(self) -> None:
        """根据当前内容调整对话框尺寸，避免路径换行时遮挡按钮。"""
        self.update_idletasks()

        current_width = max(self.winfo_width(), 1)
        requested_width = max(self.winfo_reqwidth(), CONFIG_DIALOG_MIN_WIDTH)
        target_width, _ = _compute_dialog_target_size(
            requested_width=requested_width,
            requested_height=CONFIG_DIALOG_MIN_HEIGHT,
            min_width=CONFIG_DIALOG_MIN_WIDTH,
            min_height=CONFIG_DIALOG_MIN_HEIGHT,
            current_width=current_width,
            max_width=CONFIG_DIALOG_MAX_WIDTH,
        )

        self.info_label.configure(
            wraplength=max(target_width - CONFIG_DIALOG_INFO_WRAP_PADDING, 400)
        )
        self.update_idletasks()

        current_height = max(self.winfo_height(), 1)
        requested_height = max(self.winfo_reqheight(), CONFIG_DIALOG_MIN_HEIGHT)
        _, target_height = _compute_dialog_target_size(
            requested_width=target_width,
            requested_height=requested_height,
            min_width=target_width,
            min_height=CONFIG_DIALOG_MIN_HEIGHT,
            current_height=current_height,
        )

        _set_centered_window_geometry(self, target_width, target_height)

    def _show_dialog(self) -> None:
        """确保对话框在 macOS 上可见并获得焦点"""
        self.deiconify()
        self.lift()
        self.update_idletasks()

        try:
            self.focus_force()
        except tk.TclError:
            pass

        try:
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass


def choose_config_file(parent=None, initial_path: Optional[str] = None) -> Optional[str]:
    """打开配置文件选择对话框"""
    ensure_tk_runtime()

    owns_root = False
    dialog_parent = parent

    if dialog_parent is None:
        dialog_parent = tk.Tk()
        setup_gui_theme(dialog_parent)
        dialog_parent.withdraw()
        owns_root = True

    dialog = ConfigSelectionDialog(dialog_parent, initial_path=initial_path)
    dialog_parent.wait_window(dialog)
    result = dialog.result

    if owns_root:
        dialog_parent.destroy()

    return result


def _build_startup_bid_writer(config_path: Optional[str] = None) -> tuple[BidWriter, bool]:
    """按候选顺序构建启动时使用的 BidWriter"""
    fallback_bid_writer: Optional[BidWriter] = None
    last_error: Optional[Exception] = None

    for candidate in get_startup_config_candidates(config_path):
        try:
            bid_writer = BidWriter(candidate)
        except Exception as e:
            last_error = e
            continue

        if fallback_bid_writer is None:
            fallback_bid_writer = bid_writer

        if bid_writer.load_outline():
            return bid_writer, True

        last_error = FileNotFoundError(
            bid_writer.last_error_message or f"加载配置失败: {candidate}"
        )

    if fallback_bid_writer is not None:
        return fallback_bid_writer, False

    raise FileNotFoundError(str(last_error) if last_error else "未找到可用配置文件")


class MainWindow(tk.Tk):
    """主窗口类"""

    def __init__(self, bid_writer: BidWriter, outline_preloaded: bool = False):
        ensure_tk_runtime()
        super().__init__()
        self.style = setup_gui_theme(self)
        apply_window_surface(self)

        self.bid_writer = bid_writer
        self.adapter = GUIAdapter(bid_writer)
        self.tree_view_state = TreeViewState()
        self._suppress_tree_view_events = False
        self.is_generating = False
        self.stop_requested = False
        self.visible_leaf_count = 0
        self.generated_leaf_count = 0
        self._responsive_layout_pending = False
        self._responsive_layout_force = False
        self._action_layout_mode = ""
        self._control_layout_mode = ""
        self._preserve_workspace_on_sync = False
        self._outline_tree_tooltips: dict[str, str] = {}

        # 树节点到HeadingNode的映射
        self.tree_node_map = {}

        # 窗口配置
        self.title("自动标书撰写系统 - GUI版")
        target_width, target_height = _compute_main_window_target_size(
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, target_width, target_height)

        # 最小尺寸
        min_width, min_height = _compute_main_window_min_size(
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        self.minsize(min_width, min_height)

        # 窗口居中
        self.center_window()

        # 图标（如果有的话）
        # self.iconbitmap('assets/icon.ico')

        # 创建组件
        self.create_menu_bar()
        self.create_tool_bar()
        self.create_main_panes()
        self.create_status_bar()
        self.update_window_context()

        # 创建展开/收缩菜单
        self.create_expand_menu()
        self.create_outline_context_menu()

        # 绑定快捷键
        self.bind_shortcuts()
        self.bind("<Configure>", self.on_window_resize)
        self.after_idle(lambda: self.schedule_responsive_layout(force=True))

        # 加载大纲
        if outline_preloaded:
            self._sync_loaded_outline(reset_tree_view=True)
            self.status_text.set("大纲加载完成")
        else:
            self.load_outline(preserve_tree_view=False, reset_tree_view=True)

    def _create_info_item(self, parent, label: str, textvariable: tk.StringVar, padx: tuple[int, int] = (0, 18)):
        """创建顶部信息项"""
        group = ttk.Frame(parent)
        group.pack(side=tk.LEFT, padx=padx)
        ttk.Label(group, text=f"{label}:", style="SummaryLabel.TLabel").pack(side=tk.LEFT)
        ttk.Label(group, textvariable=textvariable, style="SummaryValue.TLabel").pack(side=tk.LEFT, padx=(4, 0))

    def center_window(self):
        """居中窗口"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        _set_centered_window_geometry(self, width, height)

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = tk.Menu(self)

        self.project_menu = tk.Menu(menubar, tearoff=0)
        self._populate_project_menu(self.project_menu)
        menubar.add_cascade(label="项目", menu=self.project_menu)

        self.chapter_menu = tk.Menu(menubar, tearoff=0)
        self._populate_chapter_menu(self.chapter_menu)
        menubar.add_cascade(label="章节", menu=self.chapter_menu)

        self.view_menu = tk.Menu(menubar, tearoff=0)
        self._populate_view_menu(self.view_menu)
        menubar.add_cascade(label="视图", menu=self.view_menu)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.config(menu=menubar)

    def create_tool_bar(self):
        """创建工具栏"""
        toolbar = ttk.Frame(self, padding=(12, 12, 12, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.config_text = tk.StringVar(value="-")
        self.selection_text = tk.StringVar(value="0")
        self.stats_text = tk.StringVar(value="0 / 0")
        self.status_text = tk.StringVar(value="就绪")

        self.action_bar = ttk.Frame(toolbar)
        self.action_bar.pack(fill=tk.X)

        self.top_outline_controls = ttk.Frame(self.action_bar)
        self._create_outline_controls(self.top_outline_controls)

        self.action_frame = ttk.Frame(self.action_bar)

        self.btn_merge = ttk.Button(
            self.action_frame,
            text="整合标书",
            command=self.merge_generated_sections,
            padding=(12, 8),
            **_bootstyle_kwargs("info")
        )
        self.btn_merge.pack(side=tk.LEFT, padx=6)

        self.btn_generate = ttk.Button(
            self.action_frame,
            text="生成所选 0",
            command=self.batch_generate,
            padding=(16, 8),
            default=tk.ACTIVE,
            **_bootstyle_kwargs("primary")
        )
        self.btn_generate.pack(side=tk.LEFT, padx=(6, 0))

    def _create_outline_controls(self, parent: tk.Misc) -> None:
        """创建顶部大纲搜索、筛选和选择控件。"""
        title_group = ttk.Frame(parent)
        title_group.pack(fill=tk.X)
        ttk.Label(
            title_group,
            text="大纲结构",
            style="SectionTitle.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            title_group,
            text="仅四级标题支持多选生成",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.control_group = ttk.Frame(parent)
        self.control_group.pack(fill=tk.X, pady=(8, 0))
        self.search_filter_group = ttk.Frame(self.control_group)
        self.selection_action_group = ttk.Frame(self.control_group)

        ttk.Label(self.search_filter_group, text="搜索").grid(row=0, column=0, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_tree_filters())
        self.search_entry = ttk.Entry(
            self.search_filter_group,
            textvariable=self.search_var,
            width=18
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(self.search_filter_group, text="筛选").grid(row=0, column=2, padx=(0, 6))
        self.status_filter_var = tk.StringVar(value="全部")
        self.status_filter_combo = ttk.Combobox(
            self.search_filter_group,
            textvariable=self.status_filter_var,
            values=("全部", "未生成", "已生成", "已完成", "部分完成"),
            state="readonly",
            width=10
        )
        self.status_filter_combo.grid(row=0, column=3, padx=(0, 10))
        self.status_filter_combo.bind("<<ComboboxSelected>>", lambda event: self.apply_tree_filters())
        self.search_filter_group.columnconfigure(1, weight=1)

        self.btn_selection_menu = ttk.Menubutton(
            self.selection_action_group,
            text="选择",
            padding=(10, 6),
            **_bootstyle_kwargs("secondary")
        )
        self.selection_tools_menu = tk.Menu(self.btn_selection_menu, tearoff=0)
        self.selection_tools_menu.add_command(label="全选四级标题", command=self.select_all_leaf_titles)
        self.selection_tools_menu.add_command(label="清空选择", command=self.clear_selection)
        self.btn_selection_menu["menu"] = self.selection_tools_menu
        self.btn_selection_menu.pack(side=tk.LEFT)

    def _populate_project_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="新建配置...", command=self.open_new_config_editor)
        menu.add_command(label="切换配置...", command=self.select_and_switch_config)
        menu.add_command(label="编辑当前配置...", command=self.open_config_editor)
        menu.add_separator()
        menu.add_command(label="重载大纲", command=self.reload_outline)
        menu.add_command(label="扫描输出状态", command=self.refresh_status)
        menu.add_separator()
        menu.add_command(label="打开输出目录", command=self.open_output_dir)
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)

    def _populate_chapter_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="生成所选", command=self.batch_generate)
        MainWindow._populate_chapter_tools_menu(self, menu)
        menu.add_separator()
        menu.add_command(label="整合标书", command=self.merge_generated_sections)

    def _populate_chapter_tools_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="提炼当前章节事实卡片", command=self.extract_selected_facts)
        menu.add_command(label="新增事实卡片...", command=self.open_manual_fact_card_dialog)
        menu.add_command(label="管理事实卡片", command=self.open_fact_card_library_dialog)

    def _populate_view_menu(self, menu: tk.Menu) -> None:
        menu.add_command(label="全部展开", command=self.expand_all)
        menu.add_separator()
        menu.add_command(label="展开至一级 (Ctrl+1)", command=self.expand_to_level_1)
        menu.add_command(label="展开至二级 (Ctrl+2)", command=self.expand_to_level_2)
        menu.add_command(label="展开至三级 (Ctrl+3)", command=self.expand_to_level_3)
        menu.add_separator()
        menu.add_command(label="收缩全部 (Ctrl+0)", command=self.collapse_all)

    def create_main_panes(self):
        """创建主面板"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.main_paned_window = tk.PanedWindow(
            main_frame,
            orient=tk.HORIZONTAL,
            sashwidth=8,
            sashrelief=tk.RAISED,
            relief=tk.FLAT,
            bd=0,
            opaqueresize=True,
        )
        style_paned_window(self.main_paned_window)
        self.main_paned_window.pack(fill=tk.BOTH, expand=True)

        outline_panel = ttk.Frame(self.main_paned_window)
        workspace_panel = ttk.Frame(self.main_paned_window)
        self.main_paned_window.add(outline_panel, minsize=MAIN_OUTLINE_MIN_WIDTH)
        self.main_paned_window.add(workspace_panel, minsize=MAIN_WORKSPACE_MIN_WIDTH)
        self._set_paned_window_default_sash(
            self.main_paned_window,
            default_width=MAIN_OUTLINE_DEFAULT_WIDTH,
            default_ratio=MAIN_OUTLINE_DEFAULT_RATIO,
            min_left_width=MAIN_OUTLINE_MIN_WIDTH,
            min_right_width=MAIN_WORKSPACE_MIN_WIDTH,
        )

        # 大纲树（支持多选）
        tree_frame = ttk.Frame(outline_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.outline_tree = ttk.Treeview(
            tree_frame,
            columns=("status", "progress"),
            height=30,
            show="tree headings",
            selectmode='extended'
        )
        self.outline_tree.heading("#0", text="标题")
        self.outline_tree.heading("status", text="状态")
        self.outline_tree.heading("progress", text="进度")
        self._resize_outline_tree_columns(MAIN_OUTLINE_DEFAULT_WIDTH)
        self._configure_heading_tree_tags(self.outline_tree)

        # 滚动条
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                          command=self.outline_tree.yview)
        self.outline_tree.config(yscrollcommand=sb.set)

        self.outline_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定选择事件
        self.outline_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.outline_tree.bind("<<TreeviewOpen>>", self.on_tree_open_close)
        self.outline_tree.bind("<<TreeviewClose>>", self.on_tree_open_close)
        self.outline_tree.bind("<Configure>", self.on_outline_tree_resize, add="+")
        self.outline_tree.bind("<Button-2>", self.on_tree_context_menu)
        self.outline_tree.bind("<Button-3>", self.on_tree_context_menu)
        self.outline_tree.bind("<Control-Button-1>", self.on_tree_context_menu)
        self._outline_tree_tooltip = TreeviewHoverTooltip(
            self.outline_tree,
            lambda item_id: self._outline_tree_tooltips.get(item_id, ""),
        )

        self._create_workspace_panel(workspace_panel)

    def _create_workspace_panel(self, parent: tk.Misc) -> None:
        """创建主窗口右侧正文工作区。"""
        workspace_frame = ttk.Frame(parent, padding=(12, 12, 12, 12))
        workspace_frame.pack(fill=tk.BOTH, expand=True)

        workspace_header = ttk.Frame(workspace_frame)
        workspace_header.pack(fill=tk.X)

        ttk.Label(workspace_header, text="正文工作区", style="SectionTitle.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        self.workspace_char_count_var = tk.StringVar(value=_format_workspace_char_count(None))
        ttk.Label(
            workspace_header,
            textvariable=self.workspace_char_count_var,
            style="Muted.TLabel",
            justify=tk.RIGHT,
        ).pack(side=tk.RIGHT, anchor=tk.E)

        self.workspace_heading_var = tk.StringVar(value="未选择章节")
        self.workspace_meta_var = tk.StringVar(
            value="选择单个四级标题后，这里会显示已生成正文；点击“生成所选”时，这里会实时显示当前扩写内容。"
        )
        self._workspace_generated_char_count: Optional[int] = None

        self.workspace_heading_label = ttk.Label(
            workspace_frame,
            textvariable=self.workspace_heading_var,
            style="SummaryLabel.TLabel",
            justify=tk.LEFT,
        )
        self.workspace_heading_label.pack(fill=tk.X, anchor=tk.W, pady=(8, 4))

        self.workspace_meta_label = ttk.Label(
            workspace_frame,
            textvariable=self.workspace_meta_var,
            style="Muted.TLabel",
            justify=tk.LEFT,
        )
        self.workspace_meta_label.pack(fill=tk.X, anchor=tk.W, pady=(0, 10))
        self._bind_label_wrap_to_parent(self.workspace_heading_label, workspace_frame, min_width=280)
        self._bind_label_wrap_to_parent(self.workspace_meta_label, workspace_frame, min_width=280)

        text_frame = ttk.Frame(workspace_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.workspace_text = tk.Text(text_frame, wrap=tk.WORD)
        style_text_widget(self.workspace_text)
        self.workspace_text.configure(state=tk.DISABLED)

        scrollbar = ttk.Scrollbar(text_frame, command=self.workspace_text.yview)
        self.workspace_text.configure(yscrollcommand=scrollbar.set)
        self.workspace_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._show_workspace_idle()

    def _set_workspace_generated_char_count(self, count: Optional[int]) -> None:
        """更新正文工作区显示的当前节点字符数。"""
        normalized_count = None if count is None else max(0, count)
        self._workspace_generated_char_count = normalized_count
        if hasattr(self, "workspace_char_count_var"):
            self.workspace_char_count_var.set(_format_workspace_char_count(normalized_count))

    def _set_workspace_text(
        self,
        content: str,
        *,
        append: bool = False,
        scroll_to_end: bool = False,
        generated_char_count: Optional[int] | object = _WORKSPACE_CHAR_COUNT_UNCHANGED,
    ) -> None:
        """更新右侧正文工作区文本。"""
        if not hasattr(self, "workspace_text"):
            return

        self.workspace_text.configure(state=tk.NORMAL)
        if append:
            self.workspace_text.insert(tk.END, content)
        else:
            self.workspace_text.delete("1.0", tk.END)
            if content:
                self.workspace_text.insert("1.0", content)

        if scroll_to_end:
            self.workspace_text.see(tk.END)
        else:
            self.workspace_text.see("1.0")
        self.workspace_text.configure(state=tk.DISABLED)

        if generated_char_count is not _WORKSPACE_CHAR_COUNT_UNCHANGED:
            self._set_workspace_generated_char_count(generated_char_count)
        elif append and self._workspace_generated_char_count is not None:
            self._set_workspace_generated_char_count(
                self._workspace_generated_char_count + _count_text_characters(content)
            )

    def _show_workspace_message(
        self,
        heading_text: str,
        meta_text: str,
        body_text: str,
        *,
        generated_char_count: Optional[int],
    ) -> None:
        """显示正文工作区的标题、说明和正文内容。"""
        self.workspace_heading_var.set(heading_text)
        self.workspace_meta_var.set(meta_text)
        self._set_workspace_text(body_text, generated_char_count=generated_char_count)

    def _show_workspace_idle(self) -> None:
        """正文工作区空状态。"""
        self._show_workspace_message(
            "未选择章节",
            "选择单个四级标题后，右侧会直接显示已生成正文；批量生成时，这里会显示当前处理章节的实时输出。",
            "可在左侧大纲树中选择一个四级标题查看正文，或多选后点击“生成所选”开始批量扩写。",
            generated_char_count=None,
        )

    def _show_workspace_selection_summary(self, selected_count: int) -> None:
        """多选时显示概览信息。"""
        self._show_workspace_message(
            f"已选择 {selected_count} 个章节",
            "当前为多选模式。点击“生成所选”后，右侧会实时显示当前处理章节的正文内容。",
            "若要查看某个章节的已生成正文，请只保留一个四级标题为选中状态。",
            generated_char_count=None,
        )

    def _show_heading_preview_in_workspace(self, heading: HeadingNode) -> None:
        """在主窗口右侧显示指定章节的已生成正文。"""
        filepath = self.bid_writer.file_saver.find_existing_filepath(heading)
        if filepath and filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            self._show_workspace_message(
                f"当前章节：{heading.full_path}",
                f"已生成文件：{filepath.name}",
                content,
                generated_char_count=_count_text_characters(content),
            )
            return

        self._show_workspace_message(
            f"当前章节：{heading.full_path}",
            "尚未生成正文",
            "该章节当前没有已生成正文。\n\n点击“生成所选”开始扩写后，正文会在这里实时显示，并在完成后自动保存。",
            generated_char_count=0,
        )

    def _refresh_workspace_from_selection(self) -> None:
        """按当前选择刷新右侧工作区内容。"""
        if self.is_generating:
            return

        selected_headings = self._get_selected_leaf_headings()
        if len(selected_headings) == 1:
            self._show_heading_preview_in_workspace(selected_headings[0])
        elif len(selected_headings) > 1:
            self._show_workspace_selection_summary(len(selected_headings))
        else:
            self._show_workspace_idle()

    def _show_generation_start_in_workspace(self, heading: HeadingNode) -> None:
        """在右侧工作区初始化当前章节的流式生成视图。"""
        self._show_workspace_message(
            f"当前章节：{heading.full_path}",
            "正在准备扩写请求...",
            "",
            generated_char_count=0,
        )

    def _show_generated_content_in_workspace(
        self,
        heading: HeadingNode,
        content: str,
        *,
        meta_text: str,
    ) -> None:
        """在右侧工作区显示当前章节正文。"""
        self._show_workspace_message(
            f"当前章节：{heading.full_path}",
            meta_text,
            content,
            generated_char_count=_count_text_characters(content),
        )

    def _show_generation_failure_in_workspace(
        self,
        heading: HeadingNode,
        feedback: GenerationErrorFeedback,
    ) -> None:
        """将扩写失败信息直接写到右侧工作区。"""
        heading_text = f"当前章节：{heading.full_path}"
        if feedback.append_to_workspace:
            self.workspace_heading_var.set(heading_text)
            self.workspace_meta_var.set(feedback.workspace_meta_text)
            self._set_workspace_text(
                feedback.workspace_body_text,
                append=True,
                scroll_to_end=True,
                generated_char_count=self._workspace_generated_char_count,
            )
            return

        self._show_workspace_message(
            heading_text,
            feedback.workspace_meta_text,
            feedback.workspace_body_text,
            generated_char_count=0,
        )

    def _report_generation_failure(
        self,
        heading: HeadingNode,
        feedback: GenerationErrorFeedback,
        *,
        show_dialog: bool,
    ) -> None:
        """统一处理扩写失败后的工作区、状态栏和弹窗。"""
        self._show_generation_failure_in_workspace(heading, feedback)
        self.status_text.set(feedback.status_text)
        if show_dialog:
            messagebox.showerror(
                feedback.dialog_title,
                feedback.dialog_message,
                parent=self,
            )

    def on_window_resize(self, event):
        """窗口尺寸变化后刷新自适应布局"""
        if event.widget is not self:
            return
        self.schedule_responsive_layout()

    def on_outline_tree_resize(self, event):
        """左侧树宽度变化时按比例重算列宽。"""
        if event.widget is not self.outline_tree:
            return
        self._resize_outline_tree_columns(event.width)

    def schedule_responsive_layout(self, force: bool = False):
        """合并连续布局刷新请求，避免频繁重排"""
        if not hasattr(self, "action_bar"):
            return

        self._responsive_layout_force = self._responsive_layout_force or force
        if self._responsive_layout_pending:
            return

        self._responsive_layout_pending = True
        self.after_idle(self._flush_responsive_layout)

    def _flush_responsive_layout(self):
        """在空闲时执行一次布局刷新"""
        self._responsive_layout_pending = False
        force = self._responsive_layout_force
        self._responsive_layout_force = False
        self.refresh_responsive_layout(force=force)

    def refresh_responsive_layout(self, force: bool = False):
        """根据窗口宽度调整工具栏和筛选区布局"""
        if not hasattr(self, "action_bar"):
            return

        action_layout_mode = self._get_action_layout_mode()
        control_layout_mode = self._get_control_layout_mode()

        if force or action_layout_mode != self._action_layout_mode:
            self._layout_action_bar(action_layout_mode)
            self._action_layout_mode = action_layout_mode

        if force or control_layout_mode != self._control_layout_mode:
            self._layout_control_group(control_layout_mode)
            self._control_layout_mode = control_layout_mode

        self._update_status_wraplength()

    def _get_action_layout_mode(self) -> str:
        """计算工具按钮区域应使用的布局模式"""
        return "single"

    def _layout_action_bar(self, layout_mode: str):
        """工具按钮区域宽度不足时拆分为两行"""
        del layout_mode
        self.top_outline_controls.grid_forget()
        self.action_frame.grid_forget()
        self.action_bar.grid_columnconfigure(0, weight=0)
        self.action_bar.grid_columnconfigure(1, weight=0)
        self.action_bar.grid_columnconfigure(0, weight=1)
        self.top_outline_controls.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.action_frame.grid(row=0, column=1, sticky="se")

    def _get_control_layout_mode(self) -> str:
        """计算筛选控制区域应使用的布局模式"""
        available_width = self.control_group.winfo_width()
        if available_width <= 1:
            toolbar_width = (
                self.action_bar.winfo_width()
                if hasattr(self, "action_bar")
                else self.winfo_width() - 32
            )
            available_width = max(toolbar_width, self.winfo_width() - 32)
            if hasattr(self, "action_frame"):
                available_width -= self.action_frame.winfo_reqwidth() + 24
            available_width = max(available_width, 1)

        required_width = (
            self.search_filter_group.winfo_reqwidth()
            + self.selection_action_group.winfo_reqwidth()
            + 24
        )
        return "single" if required_width <= available_width else "stacked"

    def _layout_control_group(self, layout_mode: str):
        """筛选控制区域宽度不足时拆分为两行"""
        self.search_filter_group.grid_forget()
        self.selection_action_group.grid_forget()
        self.control_group.grid_columnconfigure(0, weight=0)
        self.control_group.grid_columnconfigure(1, weight=0)

        self.control_group.grid_columnconfigure(0, weight=1)
        self.search_filter_group.grid(row=0, column=0, sticky="ew")

        if layout_mode == "single":
            self.selection_action_group.grid(row=0, column=1, sticky="e")
            return

        self.selection_action_group.grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _update_status_wraplength(self):
        """状态摘要保持单行左右布局，不启用自动换行。"""
        if not hasattr(self, "summary_status_value"):
            return

        self.summary_status_value.configure(wraplength=0)

    def create_status_bar(self):
        """创建状态栏"""
        status_frame = ttk.Frame(self, padding=(12, 8))
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        summary_metrics_bar = ttk.Frame(status_frame)
        summary_metrics_bar.pack(fill=tk.X, pady=(0, 6))
        self._create_info_item(summary_metrics_bar, "配置", self.config_text)
        self._create_info_item(summary_metrics_bar, "已选", self.selection_text)
        self._create_info_item(summary_metrics_bar, "已生成", self.stats_text)

        progress_bar_row = ttk.Frame(status_frame)
        progress_bar_row.pack(fill=tk.X)

        self.task_text = tk.StringVar(value="当前任务: 空闲")
        ttk.Label(progress_bar_row, textvariable=self.task_text).pack(side=tk.LEFT)

        self.batch_progress_text = tk.StringVar(value="0 / 0")
        ttk.Label(progress_bar_row, textvariable=self.batch_progress_text).pack(side=tk.RIGHT)

        self.btn_stop_generation = ttk.Button(
            progress_bar_row,
            text="停止本轮",
            command=self.request_stop_generation,
            padding=(10, 6),
            **_bootstyle_kwargs("danger")
        )
        self.btn_stop_generation.pack(side=tk.RIGHT, padx=(10, 0))
        self.btn_stop_generation.config(state=tk.DISABLED)

        self.progress_bar = ttk.Progressbar(
            progress_bar_row,
            mode='determinate',
            length=220,
            maximum=1,
            value=0,
            **_bootstyle_kwargs("success-striped")
        )
        self.progress_bar.pack(side=tk.RIGHT, padx=(10, 0))

    def update_window_context(self):
        """更新窗口标题和当前配置显示"""
        config_name = self.bid_writer.config.config_path.name
        self.title(f"自动标书撰写系统 - GUI版 [{config_name}]")
        self.config_text.set(config_name)

    def create_expand_menu(self):
        """创建展开/收缩下拉菜单"""
        if hasattr(self, "view_menu"):
            self.expand_menu = self.view_menu
            return

        self.expand_menu = tk.Menu(self, tearoff=0)
        self._populate_view_menu(self.expand_menu)

    def create_outline_context_menu(self):
        """创建章节树右键菜单。"""
        self.outline_context_menu = tk.Menu(self, tearoff=0)
        self.outline_context_menu.add_command(
            label="生成所选",
            command=self.generate_context_menu_selection,
        )
        self.outline_context_menu.add_command(
            label="提炼事实卡片",
            command=self.extract_context_menu_facts,
        )
        self._context_menu_heading: Optional[HeadingNode] = None

    def _list_extracted_fact_cards_for_heading(self, heading: HeadingNode) -> list[Any]:
        """读取当前章节已保存的正文提炼事实卡片。"""
        list_method = getattr(self.bid_writer, "list_extracted_fact_cards", None)
        if callable(list_method):
            return list(list_method(heading) or [])

        store = getattr(self.bid_writer, "fact_card_store", None)
        store_method = getattr(store, "list_chapter_extracted_cards", None)
        if callable(store_method):
            return list(store_method(getattr(heading, "full_path", "")) or [])
        return []

    def _fact_card_menu_label_for_heading(self, heading: HeadingNode) -> str:
        """根据章节是否已有提炼结果生成右键菜单文案。"""
        if MainWindow._list_extracted_fact_cards_for_heading(self, heading):
            return "查看/更新事实卡片"
        return "提炼事实卡片"

    def _selected_fact_card_action_label(self, selected_headings: list[HeadingNode]) -> str:
        """根据当前选择生成顶部菜单中的事实卡片入口文案。"""
        if len(selected_headings) == 1 and MainWindow._list_extracted_fact_cards_for_heading(self, selected_headings[0]):
            return "查看/更新当前章节事实卡片"
        return "提炼当前章节事实卡片"

    @staticmethod
    def _fact_card_drafts_from_cards(cards: list[Any]) -> list[Any]:
        """将已保存事实卡片转换为提炼工作台可编辑草稿。"""
        from .fact_cards import FactCardDraft

        return [
            FactCardDraft(
                card_id=str(getattr(card, "id", "") or ""),
                name=str(getattr(card, "name", "") or ""),
                content=str(getattr(card, "content", "") or ""),
                category=str(getattr(card, "category", "") or ""),
                scope=str(getattr(card, "scope", "") or ""),
                enforcement=str(getattr(card, "enforcement", "") or ""),
            )
            for card in cards
            if str(getattr(card, "name", "") or "").strip() and str(getattr(card, "content", "") or "").strip()
        ]

    def _fact_card_initial_instruction(self, heading: HeadingNode, cards: list[Any]) -> str:
        """优先复用上次提炼要求，没有则使用默认要求。"""
        for card in cards:
            source = getattr(card, "source", None)
            instruction = str(getattr(source, "extraction_instruction", "") or "").strip()
            if instruction:
                return instruction
        return self._default_fact_card_extraction_instruction(heading)

    @classmethod
    def _fact_card_initial_status(cls, cards: list[Any], output_path: Path) -> str:
        """生成已有事实卡片的初始状态提示。"""
        if not cards:
            return ""

        count = len(cards)
        output_time = cls._file_modified_datetime(output_path)
        latest_extract_time = max(
            (
                parsed
                for parsed in (cls._parse_datetime(getattr(card, "updated_at", "")) for card in cards)
                if parsed is not None
            ),
            default=None,
        )
        if output_time is not None and latest_extract_time is not None and output_time > latest_extract_time:
            return f"已存在上次提炼结果（{count} 张），但章节正文更新时间较新，建议重新提炼后再保存。"
        return f"已存在上次提炼结果（{count} 张），当前正文未检测到更新，可直接复用或编辑后保存。"

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _file_modified_datetime(path: Path) -> Optional[datetime]:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            return None

    def bind_shortcuts(self):
        """绑定快捷键"""
        # 展开/收缩快捷键
        self.bind('<Control-Key-1>', lambda e: self.expand_to_level_1())
        self.bind('<Control-Key-2>', lambda e: self.expand_to_level_2())
        self.bind('<Control-Key-3>', lambda e: self.expand_to_level_3())
        self.bind('<Control-Key-0>', lambda e: self.collapse_all())
        self.bind('<Control-a>', lambda e: self.select_all_leaf_titles())
        self.bind('<Control-f>', lambda e: self.focus_search())
        self.bind('<Escape>', lambda e: self.clear_selection())

    def show_expand_menu(self):
        """显示展开/收缩菜单"""
        anchor = getattr(self, "btn_view_menu", None)
        if anchor is None:
            return
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        self.expand_menu.post(x, y)

    def focus_search(self):
        """聚焦到搜索框"""
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _get_selected_heading_paths(self) -> set[str]:
        """记录当前选中的叶子节点路径"""
        selected_paths: set[str] = set()
        for item_id in self.outline_tree.selection():
            heading = self.tree_node_map.get(item_id)
            if heading and not heading.children:
                selected_paths.add(heading.full_path)
        return selected_paths

    def _restore_selected_heading_paths(self, selected_paths: set[str]):
        """在树重绘后恢复叶子节点选择"""
        if not selected_paths:
            return

        for item_id, heading in self.tree_node_map.items():
            if heading.children:
                continue
            if heading.full_path in selected_paths:
                self.outline_tree.selection_add(item_id)

    def _has_active_filters(self) -> bool:
        """是否启用了搜索或状态筛选"""
        query = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        status_filter = self.status_filter_var.get() if hasattr(self, "status_filter_var") else "全部"
        return bool(query) or status_filter != "全部"

    def _heading_matches_search(self, heading: HeadingNode, query: str) -> bool:
        """标题是否命中搜索条件"""
        if not query:
            return True

        query_lower = query.lower()
        return query_lower in heading.title.lower() or query_lower in heading.full_path.lower()

    def _heading_matches_status_filter(self, heading: HeadingNode, status_filter: str) -> bool:
        """标题是否命中状态筛选"""
        if status_filter == "全部":
            return True

        status = self.adapter.get_status_text(heading)
        if status_filter == "已生成":
            return status in {"已完成", "部分完成"}
        return status == status_filter

    def _heading_or_descendant_matches(self, heading: HeadingNode, query: str, status_filter: str) -> bool:
        """标题本身或子节点是否命中过滤条件"""
        self_matches = (
            self._heading_matches_search(heading, query)
            and self._heading_matches_status_filter(heading, status_filter)
        )
        if self_matches:
            return True
        return any(
            self._heading_or_descendant_matches(child, query, status_filter)
            for child in heading.children
        )

    def apply_tree_filters(self):
        """应用搜索和状态筛选"""
        if not hasattr(self, "outline_tree"):
            return

        self._remember_current_tree_view_state()
        selected_paths = self._get_selected_heading_paths()
        self._render_outline_tree()
        if self._has_active_filters():
            self._set_all_nodes_open("", True)
        else:
            self._apply_tree_view_state()
        self._restore_selected_heading_paths(selected_paths)
        self.update_stats()
        self.update_action_states()
        self._refresh_workspace_from_selection()

    def load_outline(self, preserve_tree_view: bool = True, reset_tree_view: bool = False):
        """加载大纲到树形视图"""
        if preserve_tree_view:
            self._remember_current_tree_view_state()

        # 加载大纲
        if not self.bid_writer.load_outline():
            messagebox.showerror(
                "错误",
                self.bid_writer.last_error_message or "加载大纲失败",
                parent=self,
            )
            return False

        self._sync_loaded_outline(reset_tree_view=reset_tree_view)
        self.status_text.set("大纲加载完成")
        return True

    def _sync_loaded_outline(self, reset_tree_view: bool = False):
        """同步已加载的大纲到界面"""
        selected_paths = set() if reset_tree_view else self._get_selected_heading_paths()
        if reset_tree_view:
            self.reset_tree_view_state()

        self.adapter.refresh_generated_titles()
        self._render_outline_tree()
        if self._has_active_filters():
            self._set_all_nodes_open("", True)
        else:
            self._apply_tree_view_state()
        self._restore_selected_heading_paths(selected_paths)
        self.update_window_context()
        self.update_stats()
        self.update_action_states()
        if not self._preserve_workspace_on_sync:
            self._refresh_workspace_from_selection()
        remember_last_config(str(self.bid_writer.config.config_path))

    def _render_outline_tree(self):
        """将已加载的大纲渲染到树形视图"""
        for item in self.outline_tree.get_children():
            self.outline_tree.delete(item)

        self.tree_node_map.clear()
        self._outline_tree_tooltips.clear()
        self.visible_leaf_count = 0

        root_headings = self.adapter.get_outline_tree()
        query = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        status_filter = self.status_filter_var.get() if hasattr(self, "status_filter_var") else "全部"
        for heading in root_headings:
            self._add_tree_node(
                "",
                heading,
                query,
                status_filter,
            )

    def reset_tree_view_state(self):
        """重置大纲树视图状态为默认全部展开"""
        self.tree_view_state = TreeViewState(mode="all")

    def _remember_current_tree_view_state(self):
        """在重绘前记录当前树展开状态"""
        if not self.tree_node_map:
            return

        if self.tree_view_state.mode == "custom":
            self.tree_view_state.expanded_paths = self._collect_expanded_paths()

    def _collect_expanded_paths(self) -> list[str]:
        """收集当前已展开的节点路径"""
        expanded_paths: list[str] = []
        for item_id, heading in self.tree_node_map.items():
            if heading.children and bool(self.outline_tree.item(item_id, "open")):
                expanded_paths.append(heading.full_path)
        return sorted(expanded_paths)

    def _apply_tree_view_state(self):
        """在树重绘后恢复展开状态"""
        if not self.tree_node_map:
            return

        self._suppress_tree_view_events = True
        try:
            if self.tree_view_state.mode == "all":
                self._set_all_nodes_open("", True)
            elif self.tree_view_state.mode == "level_1":
                self._expand_to_level(1)
            elif self.tree_view_state.mode == "level_2":
                self._expand_to_level(2)
            elif self.tree_view_state.mode == "level_3":
                self._expand_to_level(3)
            elif self.tree_view_state.mode == "collapsed":
                self._set_all_nodes_open("", False)
            elif self.tree_view_state.mode == "custom":
                self._restore_expanded_paths(set(self.tree_view_state.expanded_paths))
            else:
                self._set_all_nodes_open("", True)
        finally:
            self._suppress_tree_view_events = False

    def _restore_expanded_paths(self, expanded_paths: set[str]):
        """按路径恢复自定义展开状态"""
        self._set_all_nodes_open("", False)
        self._restore_expanded_paths_recursive("", expanded_paths)

    def _restore_expanded_paths_recursive(self, parent_id: str, expanded_paths: set[str]):
        """递归恢复节点展开状态"""
        children = self.outline_tree.get_children(parent_id)
        for child_id in children:
            heading = self.tree_node_map.get(child_id)
            if not heading:
                continue

            if heading.children:
                self.outline_tree.item(child_id, open=heading.full_path in expanded_paths)

            self._restore_expanded_paths_recursive(child_id, expanded_paths)

    def _set_all_nodes_open(self, parent_id: str, is_open: bool):
        """递归展开或收缩所有节点"""
        children = self.outline_tree.get_children(parent_id)
        for child_id in children:
            heading = self.tree_node_map.get(child_id)
            if heading and heading.children:
                self.outline_tree.item(child_id, open=is_open)
            self._set_all_nodes_open(child_id, is_open)

    @staticmethod
    def _status_to_row_tag(status: str) -> str:
        if status == "已完成":
            return "completed"
        if status == "部分完成":
            return "partial"
        return "pending"

    def _get_heading_tree_row_values(self, heading: HeadingNode) -> tuple[str, str, str]:
        """返回树节点展示所需的状态、进度和颜色标签。"""
        status = self.adapter.get_status_text(heading)
        progress_info = "-"
        if heading.children:
            generated, total = self.adapter.get_progress(heading)
            progress_info = f"{generated}/{total}" if total > 0 else "-"
        return status, progress_info, self._status_to_row_tag(status)

    def _resize_outline_tree_columns(self, total_width: int) -> None:
        """按当前目录栏宽度重算大纲树三列。"""
        title_width, status_width, progress_width = _compute_outline_tree_column_widths(
            total_width=total_width
        )
        self.outline_tree.column("#0", width=title_width, anchor=tk.W, stretch=True)
        self.outline_tree.column("status", width=status_width, anchor=tk.CENTER, stretch=False)
        self.outline_tree.column("progress", width=progress_width, anchor=tk.CENTER, stretch=False)

    def _configure_heading_tree_tags(self, tree: ttk.Treeview) -> None:
        """统一配置大纲树状态颜色与当前焦点高亮。"""
        profile = _get_gui_scale_profile(tree)
        tree.tag_configure("completed", foreground="#1f7a4d")
        tree.tag_configure("partial", foreground="#8a5a00")
        tree.tag_configure("pending", foreground="#666666")
        tree.tag_configure(
            "current_focus",
            background="#dbeafe",
            foreground="#0f172a",
            font=("TkDefaultFont", profile.compact_font_size, "bold"),
        )

    @staticmethod
    def _bind_label_wrap_to_parent(label: ttk.Label, parent: tk.Misc, min_width: int = 220) -> None:
        """让说明文本随父容器宽度自动换行。"""

        def on_resize(event):
            label.configure(wraplength=max(event.width - 4, min_width))

        parent.bind("<Configure>", on_resize, add="+")

    @staticmethod
    def _set_paned_window_default_sash(
        paned_window: tk.PanedWindow,
        *,
        default_width: int = POPUP_OUTLINE_DEFAULT_WIDTH,
        default_ratio: Optional[float] = None,
        min_left_width: int = POPUP_OUTLINE_MIN_WIDTH,
        min_right_width: int = POPUP_CONTENT_MIN_WIDTH,
    ) -> None:
        """为左右分栏设置一个稳定的默认分割宽度。"""

        def place_sash() -> None:
            if not paned_window.winfo_exists():
                return

            total_width = paned_window.winfo_width()
            if total_width <= 1:
                paned_window.after(50, place_sash)
                return

            if default_ratio is None:
                target_width = max(
                    min_left_width,
                    min(default_width, total_width - min_right_width),
                )
            else:
                target_width = _compute_main_outline_pane_width(
                    total_width=total_width,
                    min_left_width=min_left_width,
                    min_right_width=min_right_width,
                    default_ratio=default_ratio,
                )
            try:
                paned_window.sash_place(0, target_width, 1)
            except tk.TclError:
                pass

        paned_window.after_idle(place_sash)

    def _add_tree_node(
        self,
        parent: str,
        heading: HeadingNode,
        query: str = "",
        status_filter: str = "全部",
    ):
        """递归添加树节点"""
        if not self._heading_or_descendant_matches(heading, query, status_filter):
            return

        status, progress_info, row_tag = self._get_heading_tree_row_values(heading)
        if not heading.children:
            self.visible_leaf_count += 1
        display_title = _format_heading_tree_title(heading.title)

        node_id = self.outline_tree.insert(
            parent, 'end',
            text=display_title,
            values=(status, progress_info),
            tags=(row_tag,)
        )

        # 保存节点映射
        self.tree_node_map[node_id] = heading
        # 递归添加子节点
        for child in heading.children:
            self._add_tree_node(
                node_id,
                child,
                query,
                status_filter,
            )

    def _get_selected_leaf_headings(self) -> List[HeadingNode]:
        """返回当前选中的四级标题"""
        selected_headings: List[HeadingNode] = []
        seen_paths: set[str] = set()
        for item_id in self.outline_tree.selection():
            heading = self.tree_node_map.get(item_id)
            if not heading or heading.children or heading.full_path in seen_paths:
                continue
            seen_paths.add(heading.full_path)
            selected_headings.append(heading)
        return selected_headings

    def _get_single_selected_leaf_heading(self) -> Optional[HeadingNode]:
        """返回唯一选中的叶子章节。"""
        selected = self._get_selected_leaf_headings()
        if len(selected) != 1:
            return None
        return selected[0]

    def _set_single_heading_selection(self, heading: HeadingNode) -> None:
        """将树选择切换为指定单个叶子章节。"""
        for item_id, node in self.tree_node_map.items():
            if node.full_path != heading.full_path:
                continue
            self.outline_tree.selection_set(item_id)
            self.outline_tree.focus(item_id)
            self.outline_tree.see(item_id)
            break

    def update_action_states(self):
        """同步顶部操作按钮和统计信息"""
        selected_headings = self._get_selected_leaf_headings()
        selected_count = len(selected_headings)
        single_selection = selected_count == 1
        tool_button_state = tk.DISABLED if self.is_generating else tk.NORMAL
        selection_menu_state = (
            tk.DISABLED
            if self.is_generating or (self.visible_leaf_count == 0 and selected_count == 0)
            else tk.NORMAL
        )
        chapter_tools_state = (
            tk.DISABLED
            if self.is_generating or self.bid_writer.parser is None
            else tk.NORMAL
        )
        self.selection_text.set(str(selected_count))
        self.btn_generate.config(
            text=f"生成所选 {selected_count}",
            state=(tk.DISABLED if self.is_generating or selected_count == 0 else tk.NORMAL)
        )
        self.btn_merge.config(
            state=(tk.DISABLED if self.is_generating or self.generated_leaf_count == 0 else tk.NORMAL)
        )
        self.btn_selection_menu.config(state=selection_menu_state)

        if hasattr(self, "project_menu"):
            for entry_index in (0, 1, 2, 4, 5, 7):
                self.project_menu.entryconfigure(entry_index, state=tool_button_state)
        if hasattr(self, "view_menu"):
            for entry_index in (0, 2, 3, 4, 6):
                self.view_menu.entryconfigure(entry_index, state=tool_button_state)
        if hasattr(self, "chapter_menu"):
            self.chapter_menu.entryconfigure(
                0,
                label=f"生成所选 {selected_count}",
                state=(tk.DISABLED if self.is_generating or selected_count == 0 else tk.NORMAL),
            )
            self.chapter_menu.entryconfigure(
                1,
                state=(tk.DISABLED if self.is_generating or not single_selection else tk.NORMAL),
            )
            self.chapter_menu.entryconfigure(
                2,
                state=(tk.DISABLED if self.is_generating or self.bid_writer.parser is None else tk.NORMAL),
            )
            self.chapter_menu.entryconfigure(
                CHAPTER_MENU_FACT_CARD_INDEX,
                label=self._selected_fact_card_action_label(selected_headings),
                state=(tk.DISABLED if self.is_generating or not single_selection else tk.NORMAL),
            )
            self.chapter_menu.entryconfigure(2, state=chapter_tools_state)
            self.chapter_menu.entryconfigure(3, state=chapter_tools_state)
            self.chapter_menu.entryconfigure(
                5,
                state=(tk.DISABLED if self.is_generating or self.generated_leaf_count == 0 else tk.NORMAL),
            )

        self.selection_tools_menu.entryconfigure(
            "全选四级标题",
            state=(tk.DISABLED if self.is_generating or self.visible_leaf_count == 0 else tk.NORMAL),
        )
        self.selection_tools_menu.entryconfigure(
            "清空选择",
            state=(tk.DISABLED if self.is_generating or selected_count == 0 else tk.NORMAL),
        )

        self.search_entry.config(state=(tk.DISABLED if self.is_generating else tk.NORMAL))
        self.status_filter_combo.config(state=("disabled" if self.is_generating else "readonly"))

        self.btn_stop_generation.config(
            state=(tk.NORMAL if self.is_generating else tk.DISABLED)
        )
        self.schedule_responsive_layout()

    def on_tree_select(self, event):
        """当选择树节点时 - 只允许选择四级标题（叶子节点）"""
        selection = self.outline_tree.selection()
        if not selection:
            if not self.is_generating:
                self.status_text.set("未选择任何标题")
            self.update_action_states()
            self._refresh_workspace_from_selection()
            return

        # 过滤掉非叶子节点
        valid_selection = []
        invalid_count = 0

        for item_id in selection:
            heading = self.tree_node_map.get(item_id)
            if heading and not heading.children:
                # 这是叶子节点（四级标题），保留选择
                valid_selection.append(item_id)
            else:
                # 这不是叶子节点，取消选择
                invalid_count += 1

        # 如果有无效选择，重新设置选择
        if invalid_count > 0:
            # 清空当前选择
            for item_id in selection:
                self.outline_tree.selection_remove(item_id)
            # 只选择有效的
            for item_id in valid_selection:
                self.outline_tree.selection_add(item_id)

        # 更新状态栏
        count = len(valid_selection)
        if not self.is_generating:
            if count == 0:
                self.status_text.set("请选择四级标题（叶子节点）")
            elif count == 1:
                heading = self.tree_node_map.get(valid_selection[0])
                self.status_text.set(f"已选择: {heading.title if heading else ''}")
            else:
                self.status_text.set(f"已选择 {count} 个四级标题")
        self.update_action_states()
        self._refresh_workspace_from_selection()

    def on_tree_context_menu(self, event):
        """在叶子章节上显示右键菜单。"""
        if self.is_generating:
            return "break"

        item_id = self.outline_tree.identify_row(event.y)
        if not item_id:
            return "break"

        heading = self.tree_node_map.get(item_id)
        if heading is None or heading.children:
            return "break"

        if item_id not in self.outline_tree.selection():
            self.outline_tree.selection_set(item_id)
        self.outline_tree.focus(item_id)
        self._context_menu_heading = heading
        self.outline_context_menu.entryconfigure(
            CONTEXT_MENU_FACT_CARD_INDEX,
            label=self._fact_card_menu_label_for_heading(heading),
        )
        self.outline_context_menu.tk_popup(event.x_root, event.y_root)
        self.outline_context_menu.grab_release()
        return "break"

    def on_title_select(self, event):
        """保留空方法，避免旧绑定报错"""
        pass

    def _get_context_menu_heading(self) -> Optional[HeadingNode]:
        heading = getattr(self, "_context_menu_heading", None)
        if heading is not None:
            return heading
        return self._get_single_selected_leaf_heading()

    def on_tree_open_close(self, event):
        """记录用户手动展开/收缩的树状态"""
        if self._suppress_tree_view_events:
            return

        self.tree_view_state = TreeViewState(
            mode="custom",
            expanded_paths=self._collect_expanded_paths()
        )

    def reload_outline(self):
        """重新加载大纲"""
        self.status_text.set("正在重载大纲...")
        if self.load_outline(preserve_tree_view=True):
            self.status_text.set("大纲重载完成")

    def refresh_status(self):
        """刷新状态"""
        self.status_text.set("正在扫描输出状态...")
        if self.load_outline(preserve_tree_view=True):
            self.status_text.set("输出状态刷新完成")

    def select_and_switch_config(self):
        """选择并切换配置文件"""
        selected_config = choose_config_file(
            parent=self,
            initial_path=str(self.bid_writer.config.config_path)
        )
        if not selected_config:
            return

        selected_path = Path(selected_config).expanduser().resolve()
        current_path = self.bid_writer.config.config_path.resolve()

        if selected_path == current_path:
            self.status_text.set(f"当前已在使用配置: {selected_path.name}")
            return

        self._switch_to_config_path(selected_path)

    def _switch_to_config_path(self, selected_path: Path, *, force_reload: bool = False) -> bool:
        """切换到指定配置文件；必要时可对同一路径强制重载。"""
        selected_path = selected_path.expanduser().resolve()
        current_path = self.bid_writer.config.config_path.resolve()

        if selected_path == current_path and not force_reload:
            self.status_text.set(f"当前已在使用配置: {selected_path.name}")
            return False

        self.status_text.set(f"正在切换配置: {selected_path.name}")
        self.update_idletasks()

        try:
            next_bid_writer = BidWriter(str(selected_path))
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败：\n{e}", parent=self)
            self.status_text.set("配置切换失败")
            return

        if not next_bid_writer.load_outline():
            messagebox.showerror(
                "错误",
                next_bid_writer.last_error_message or "切换配置后加载大纲失败",
                parent=self,
            )
            self.status_text.set("配置切换失败")
            return

        self.bid_writer = next_bid_writer
        self.adapter = GUIAdapter(next_bid_writer)
        self._sync_loaded_outline(reset_tree_view=True)
        if selected_path == current_path:
            self.status_text.set(f"已重载配置: {selected_path.name}")
        else:
            self.status_text.set(f"已切换配置: {selected_path.name}")
        return True

    def open_new_config_editor(self):
        """打开新配置创建编辑器。"""
        from .config_editor_dialog import ConfigEditorDialog

        current_config_path = self.bid_writer.config.config_path.resolve()
        default_path = current_config_path.parent / "config_新项目.yaml"
        dialog = ConfigEditorDialog(self, default_path, new_config=True)
        self.wait_window(dialog)

        apply_path = dialog.result.get("apply_path")
        if not apply_path:
            return

        apply_resolved = Path(apply_path).expanduser().resolve()
        self._switch_to_config_path(
            apply_resolved,
            force_reload=(apply_resolved == current_config_path),
        )

    def open_config_editor(self):
        """打开当前配置的可视化编辑器。"""
        from .config_editor_dialog import ConfigEditorDialog

        dialog = ConfigEditorDialog(self, self.bid_writer.config.config_path)
        self.wait_window(dialog)

        apply_path = dialog.result.get("apply_path")
        if not apply_path:
            return

        apply_resolved = Path(apply_path).expanduser().resolve()
        current_resolved = self.bid_writer.config.config_path.resolve()
        self._switch_to_config_path(
            apply_resolved,
            force_reload=(apply_resolved == current_resolved),
        )

    def batch_generate(self):
        """批量生成选中的标题"""
        selected_headings = self._get_selected_leaf_headings()
        if not selected_headings:
            messagebox.showwarning("警告", "请先选择要生成的四级标题", parent=self)
            return

        # 获取生成参数
        params = self._get_generation_params(selected_headings)
        if params is None:
            return  # 用户取消了

        (
            additional_requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
            fact_card_mode,
            manual_fact_card_selections,
            remember_fact_card_defaults,
        ) = params
        target_word_range = self.bid_writer.config.build_target_word_range(target_words)
        is_single_heading = len(selected_headings) == 1

        # 确认对话框
        warning_line = ""
        if len(selected_headings) >= 20:
            warning_line = "\n\n本次任务较大，建议确认筛选范围后再执行。"

        if not messagebox.askyesno(
            "确认",
            f"确定要生成 {len(selected_headings)} 个标题吗？\n\n"
            f"附加要求：{additional_requirements or '（无）'}\n"
            f"目标篇幅：{target_word_range.display_text} 字\n"
            f"Mermaid图示上限：{max_mermaid_flowcharts_per_section}"
            f"{warning_line}",
            parent=self,
        ):
            return

        # 在主线程执行生成（避免线程安全问题）
        self._do_batch_generate(
            selected_headings,
            additional_requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
            fact_card_mode=fact_card_mode,
            manual_fact_card_selections=(manual_fact_card_selections if is_single_heading else None),
            remember_fact_card_defaults=(remember_fact_card_defaults if is_single_heading else False),
            auto_extract_facts=(
                (not is_single_heading)
                and self.bid_writer.config.chapter_facts_enabled
                and self.bid_writer.config.chapter_facts_auto_extract_on_batch
            ),
        )

    def _do_batch_generate(
        self,
        headings: List[HeadingNode],
        additional_requirements: str,
        target_words: int,
        max_mermaid_flowcharts_per_section: int,
        fact_card_mode: bool = False,
        manual_fact_card_selections: Optional[list["FactCardSelection"]] = None,
        remember_fact_card_defaults: bool = False,
        auto_extract_facts: bool = False,
    ):
        """执行批量生成（主线程）"""
        total = len(headings)
        success_count = 0
        fail_count = 0
        failed_titles: list[str] = []
        completed_count = 0
        stopped_early = False

        self.is_generating = True
        self.stop_requested = False
        self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.batch_progress_text.set(f"0 / {total}")
        self.task_text.set("当前任务: 准备开始")
        self.update_action_states()

        try:
            for i, heading in enumerate(headings, 1):
                if self.stop_requested:
                    stopped_early = True
                    break

                self.progress_bar.configure(value=i - 1)
                self.batch_progress_text.set(f"{i - 1} / {total}")
                self.task_text.set(f"当前任务 {i}/{total}: {heading.title}")
                self.status_text.set(f"[{i}/{total}] 正在生成: {heading.title}")
                self.update_idletasks()

                result = self._generate_into_workspace(
                    heading,
                    additional_requirements,
                    target_words,
                    max_mermaid_flowcharts_per_section,
                    fact_card_mode=fact_card_mode,
                    manual_fact_card_selections=manual_fact_card_selections if total == 1 else None,
                    remember_fact_card_defaults=remember_fact_card_defaults if total == 1 else False,
                    auto_extract_facts=auto_extract_facts,
                    show_error_dialog=(total == 1),
                )

                completed_count = i
                self.progress_bar.configure(value=i)
                self.batch_progress_text.set(f"{i} / {total}")

                if result == "success":
                    success_count += 1
                else:
                    fail_count += 1
                    failed_titles.append(heading.title)

                if self.stop_requested:
                    stopped_early = True
                    break
        finally:
            self.is_generating = False
            self.stop_requested = False
            self.update_action_states()

        self._preserve_workspace_on_sync = True
        try:
            self.refresh_status()
        finally:
            self._preserve_workspace_on_sync = False
        self.progress_bar.configure(value=(completed_count if stopped_early else total))
        self.batch_progress_text.set(f"{completed_count if stopped_early else total} / {total}")
        self.task_text.set("当前任务: 空闲")
        if stopped_early:
            self.status_text.set(
                f"批量生成已停止 - 成功: {success_count}, 失败: {fail_count}"
            )
        else:
            self.status_text.set(
                f"批量生成完成 - 成功: {success_count}, 失败: {fail_count}"
            )
            if fail_count > 0 and total > 1:
                messagebox.showwarning(
                    "批量生成有失败章节",
                    _format_batch_generation_failure_message(failed_titles),
                    parent=self,
                )

    def preview_selected(self):
        """将当前选中章节显示到主窗口右侧工作区。"""
        selected_headings = self._get_selected_leaf_headings()
        if not selected_headings:
            self._show_workspace_idle()
            return

        if len(selected_headings) > 1:
            self._show_workspace_selection_summary(len(selected_headings))
            return

        self._show_heading_preview_in_workspace(selected_headings[0])

    def merge_generated_sections(self):
        """整合所有已生成章节为一个 Markdown 文件。"""
        if self.is_generating:
            return

        if self.generated_leaf_count == 0:
            messagebox.showwarning("提示", "当前没有可整合的已生成章节", parent=self)
            return

        output_title = self._prompt_merge_output_title()
        if output_title is None:
            self.status_text.set("已取消整合标书")
            return

        self.status_text.set("正在整合已生成章节...")
        self.update_idletasks()

        try:
            result = self.bid_writer.merge_generated_sections(output_title=output_title)
        except Exception as e:
            self.status_text.set("整合标书失败")
            messagebox.showerror("错误", f"生成整合标书失败：\n{e}", parent=self)
            return

        output_path = _display_path(result.filepath.resolve(), Path.cwd().resolve())
        merged_message = (
            f"已整合 {result.merged_sections}/{result.total_sections} 个章节。"
        )
        if result.missing_sections:
            merged_message += f"\n有 {result.missing_sections} 个章节未生成，已自动跳过。"

        merged_message += f"\n\n输出文件：\n{output_path}"
        self.status_text.set(f"整合标书已生成: {result.filepath.name}")
        messagebox.showinfo("整合完成", merged_message, parent=self)

    def _prompt_merge_output_title(self) -> Optional[str]:
        """提示用户输入整合标书文件名。"""
        while True:
            value = simpledialog.askstring(
                "整合标书",
                "请输入整合标书文件名（无需填写 .md）：",
                parent=self,
                initialvalue="整合标书"
            )
            if value is None:
                return None

            normalized = value.strip()
            if normalized.lower().endswith(".md"):
                normalized = normalized[:-3].rstrip()

            if normalized:
                return normalized

            messagebox.showwarning("提示", "文件名不能为空", parent=self)

    def clear_selection(self):
        """清空当前选择"""
        # 清空当前选择
        for item_id in self.outline_tree.selection():
            self.outline_tree.selection_remove(item_id)
        if not self.is_generating:
            self.status_text.set("已清空选择")
        self.update_action_states()
        self._refresh_workspace_from_selection()
        return "break"

    def select_all_leaf_titles(self):
        """全选当前结果中的四级标题"""
        for item_id in self.outline_tree.selection():
            self.outline_tree.selection_remove(item_id)

        self._select_all_leaf_nodes("")
        selected_count = len(self._get_selected_leaf_headings())
        if selected_count == 0:
            if not self.is_generating:
                self.status_text.set("当前结果中没有可选择的四级标题")
        else:
            if not self.is_generating:
                self.status_text.set(f"已选择 {selected_count} 个四级标题")
        self.update_action_states()
        self._refresh_workspace_from_selection()
        return "break"

    def _select_all_leaf_nodes(self, parent):
        """递归选择所有叶子节点"""
        children = self.outline_tree.get_children(parent)
        for child_id in children:
            heading = self.tree_node_map.get(child_id)
            if heading:
                if not heading.children:
                    # 这是叶子节点，选择它
                    self.outline_tree.selection_add(child_id)
                else:
                    # 递归处理子节点
                    self._select_all_leaf_nodes(child_id)

    def extract_selected_facts(self):
        """为当前唯一选中的章节提炼事实卡片。"""
        heading = self._get_single_selected_leaf_heading()
        if heading is None:
            messagebox.showwarning("提示", "请先选中一个可扩写章节。", parent=self)
            return
        self._extract_facts_for_heading(heading)

    def generate_context_menu_selection(self):
        """从章节树右键菜单生成当前选中的章节。"""
        if self.is_generating:
            return "break"

        if not self._get_selected_leaf_headings():
            heading = self._get_context_menu_heading()
            if heading is None:
                messagebox.showwarning("提示", "请先在可扩写章节上右键，再执行该操作。", parent=self)
                return "break"
            self._set_single_heading_selection(heading)

        self.batch_generate()
        return "break"

    def extract_context_menu_facts(self):
        """为右键选中的章节提炼事实卡片。"""
        heading = self._get_context_menu_heading()
        if heading is None:
            messagebox.showwarning("提示", "请先在可扩写章节上右键，再执行该操作。", parent=self)
            return
        self._set_single_heading_selection(heading)
        self._extract_facts_for_heading(heading)

    def _extract_facts_for_heading(self, heading: HeadingNode):
        """从已生成正文提炼并审阅事实卡片。"""
        if not self.bid_writer.config.fact_cards_enabled:
            messagebox.showinfo("提示", "当前配置已关闭事实卡片功能。", parent=self)
            return

        output_path = self.bid_writer.file_saver.find_existing_filepath(heading)
        if output_path is None or not output_path.exists():
            messagebox.showwarning("提示", "该章节当前还没有已生成正文，无法提炼事实卡片。", parent=self)
            return

        from .fact_card_dialogs import FactCardExtractionWorkspaceDialog

        existing_cards = MainWindow._list_extracted_fact_cards_for_heading(self, heading)
        current_cards = existing_cards[:1]
        initial_drafts = MainWindow._fact_card_drafts_from_cards(current_cards)
        initial_instruction = MainWindow._fact_card_initial_instruction(self, heading, current_cards)
        initial_status = MainWindow._fact_card_initial_status(current_cards, output_path)

        def _extract_callback(instruction: str):
            if hasattr(self.bid_writer, "extract_fact_card_drafts_from_output_with_diagnostics"):
                return self.bid_writer.extract_fact_card_drafts_from_output_with_diagnostics(heading, instruction)
            return self.bid_writer.extract_fact_card_drafts_from_output(heading, instruction)

        dialog = FactCardExtractionWorkspaceDialog(
            self,
            heading_title=heading.title,
            initial_instruction=initial_instruction,
            extract_callback=_extract_callback,
            initial_drafts=initial_drafts,
            initial_status=initial_status,
        )
        self.wait_window(dialog)
        extraction_result = dialog.result
        if extraction_result is None:
            self.status_text.set(f"已取消提炼事实卡片：{heading.title}")
            return

        saved_cards = self.bid_writer.replace_extracted_fact_cards(
            heading,
            extraction_result.instruction,
            extraction_result.drafts,
        )
        detail = (
            "\n".join(f"- {card.name}：{card.content}" for card in saved_cards)
            if saved_cards
            else "已清空该章节提炼出的事实卡片"
        )
        self._show_workspace_message(
            f"事实卡片：{heading.full_path}",
            "已保存章节事实卡片",
            detail,
            generated_char_count=_count_text_characters(detail),
        )
        self.status_text.set(f"已保存事实卡片：{heading.title}")

    def _default_fact_card_extraction_instruction(self, heading: HeadingNode) -> str:
        del heading
        return (
            "请围绕当前选中章节的已生成正文，提炼一张最能代表本章节核心内容的事实卡片。"
            "优先选择具体、可验证、信息密度高、后续章节可复用或引用的事实；"
            "避免泛泛总结、修饰性评价、空泛承诺和重复表述。"
        )

    def open_fact_card_library_dialog(self):
        """打开事实卡片库管理对话框。"""
        from .fact_card_dialogs import FactCardLibraryDialog

        while True:
            dialog = FactCardLibraryDialog(
                self,
                cards=self.bid_writer.fact_card_store.list_cards(active_only=False),
            )
            self.wait_window(dialog)
            result = dialog.result
            if result is None:
                return
            if result.action == "new":
                MainWindow.open_manual_fact_card_dialog(self)
                continue
            if result.action == "edit" and result.card is not None:
                MainWindow._edit_fact_card_from_library(self, result.card)
                continue
            if result.action == "delete" and result.card is not None:
                MainWindow._delete_fact_card_from_library(self, result.card)
                continue
            return

    def _delete_fact_card_from_library(self, card):
        """从完整事实卡片库删除单张卡片。"""
        existing_cards = self.bid_writer.fact_card_store.list_cards(active_only=False)
        remaining_cards = [existing_card for existing_card in existing_cards if existing_card.id != card.id]
        remaining_drafts = MainWindow._fact_card_library_drafts_from_cards(remaining_cards)
        self.bid_writer.save_fact_card_library(remaining_drafts)
        detail = f"- {card.name}：{card.content}"
        self._show_workspace_message(
            "事实卡片库",
            "已删除事实卡片",
            detail,
            generated_char_count=_count_text_characters(detail),
        )
        self.status_text.set(f"已删除事实卡片：{card.name}")

    def _edit_fact_card_from_library(self, card):
        """打开单卡编辑弹窗，并把修改合并回完整事实卡片库。"""
        from .fact_card_dialogs import FactCardExtractionWorkspaceDialog, ManualFactCardDialog
        from .fact_cards import FactCardDraft, FactCardSource

        initial_draft = MainWindow._fact_card_library_drafts_from_cards([card])[0]
        source_text = MainWindow._format_fact_card_source_text(card)
        source_override = None

        source_heading = MainWindow._find_fact_card_source_heading(self, card)
        if source_heading is not None:
            initial_instruction = (
                card.source.extraction_instruction
                or MainWindow._default_fact_card_extraction_instruction(self, source_heading)
            )

            def _extract_callback(instruction: str):
                if hasattr(self.bid_writer, "extract_fact_card_drafts_from_output_with_diagnostics"):
                    return self.bid_writer.extract_fact_card_drafts_from_output_with_diagnostics(
                        source_heading,
                        instruction,
                    )
                return self.bid_writer.extract_fact_card_drafts_from_output(source_heading, instruction)

            dialog = FactCardExtractionWorkspaceDialog(
                self,
                heading_title=source_heading.title,
                initial_instruction=initial_instruction,
                extract_callback=_extract_callback,
                initial_drafts=[initial_draft],
                initial_status=f"来源：{source_text}",
            )
            self.wait_window(dialog)
            extraction_result = dialog.result
            if extraction_result is None:
                self.status_text.set(f"已取消编辑事实卡片：{card.name}")
                return
            draft = extraction_result.drafts[0] if extraction_result.drafts else initial_draft
            source_override = FactCardSource(
                type=card.source.type,
                chapter_path=card.source.chapter_path,
                extraction_instruction=extraction_result.instruction,
            )
        else:
            dialog = ManualFactCardDialog(
                self,
                initial_draft=initial_draft,
                window_title="编辑事实卡片",
                heading_text="编辑事实卡片",
                description=(
                    "可修改名称、分类、作用域、约束和内容；"
                    f"来源信息会保留不变。来源：{source_text}"
                ),
            )
            self.wait_window(dialog)
            draft = dialog.result
            if draft is None:
                self.status_text.set(f"已取消编辑事实卡片：{card.name}")
                return

        if not draft.card_id:
            draft = FactCardDraft(
                card_id=card.id,
                name=draft.name,
                content=draft.content,
                category=draft.category,
                scope=draft.scope,
                enforcement=draft.enforcement,
            )
        saved_cards = MainWindow._save_single_fact_card_draft(self, draft, source=source_override)
        saved_card = next((saved for saved in saved_cards if saved.id == draft.card_id), None)
        detail_card = saved_card or card
        detail = f"- {detail_card.name}：{detail_card.content}"
        self._show_workspace_message(
            "事实卡片库",
            "已更新事实卡片",
            detail,
            generated_char_count=_count_text_characters(detail),
        )
        self.status_text.set(f"已更新事实卡片：{detail_card.name}")

    @staticmethod
    def _find_fact_card_source_heading(window, card):
        if card.source.type != "chapter_extract" or not card.source.chapter_path:
            return None
        parser = getattr(window.bid_writer, "parser", None)
        find_by_path = getattr(parser, "find_heading_by_full_path", None)
        if not callable(find_by_path):
            return None
        return find_by_path(card.source.chapter_path)

    def open_manual_fact_card_dialog(self):
        """打开手工新增事实卡片对话框。"""
        from .fact_card_dialogs import ManualFactCardDialog

        dialog = ManualFactCardDialog(self)
        self.wait_window(dialog)
        draft = dialog.result
        if draft is None:
            self.status_text.set("已取消新增事实卡片")
            return

        MainWindow._save_single_fact_card_draft(self, draft)
        detail = f"- {draft.name}：{draft.content}"
        self._show_workspace_message(
            "事实卡片库",
            "已新增事实卡片",
            detail,
            generated_char_count=_count_text_characters(detail),
        )
        self.status_text.set(f"已新增事实卡片：{draft.name}")

    def _save_single_fact_card_draft(self, draft, *, source=None):
        """用单张草稿更新完整事实卡片库，避免整库覆盖接口误删其他卡片。"""
        if source is not None and hasattr(self.bid_writer, "save_fact_card_library_card"):
            return self.bid_writer.save_fact_card_library_card(draft, source=source)

        existing_cards = self.bid_writer.fact_card_store.list_cards(active_only=False)
        existing_drafts = MainWindow._fact_card_library_drafts_from_cards(existing_cards)
        drafts = [*existing_drafts, draft]
        if draft.card_id:
            replaced = False
            merged_drafts = []
            for existing_draft in existing_drafts:
                if existing_draft.card_id == draft.card_id:
                    merged_drafts.append(draft)
                    replaced = True
                else:
                    merged_drafts.append(existing_draft)
            drafts = merged_drafts if replaced else [*merged_drafts, draft]
        return self.bid_writer.save_fact_card_library(drafts)

    @staticmethod
    def _fact_card_library_drafts_from_cards(cards):
        from .fact_cards import FactCardDraft

        return [
            FactCardDraft(
                card_id=card.id,
                name=card.name,
                content=card.content,
                category=card.category,
                scope=card.scope,
                enforcement=card.enforcement,
            )
            for card in cards
        ]

    @staticmethod
    def _format_fact_card_source_text(card) -> str:
        if card.source.type == "chapter_extract" and card.source.chapter_path:
            return f"提炼 · {card.source.chapter_path}"
        return "手工"

    @staticmethod
    def _build_generation_fact_card_dialog_state(
        all_active_cards: list[Any],
        initial_selections: list[Any],
    ) -> GenerationFactCardSelectionDialogState:
        global_cards = [card for card in all_active_cards if card.scope == "global"]
        local_cards = [card for card in all_active_cards if card.scope == "local"]
        available_cards = [*global_cards, *local_cards]
        return GenerationFactCardSelectionDialogState(
            global_cards=global_cards,
            available_cards=available_cards,
            initial_selections=initial_selections,
            default_mode=bool(global_cards or available_cards or initial_selections),
            summary_text=(
                "全局事实卡片默认勾选，可按当前章节需要取消；"
                "局部卡片会读取本章节已保存的默认方案。"
            ),
        )

    @staticmethod
    def _format_fact_card_generation_error(exc: Exception) -> str:
        conflicts = getattr(exc, "conflicts", None)
        if not conflicts:
            return str(exc)

        lines = ["检测到事实卡片强冲突，请调整后再生成：", ""]
        for conflict in conflicts:
            lines.append(f"- {conflict.normalized_name}")
            for card in conflict.cards:
                lines.append(f"  • {card.name}：{card.content}")
        return "\n".join(lines)

    def _run_background_task_with_busy_dialog(
        self,
        *,
        title: str,
        message: str,
        status_text: str,
        task_text: str,
        worker: Callable[[], Any],
        show_after_ms: int = 180,
    ) -> Any:
        """在后台线程执行任务，必要时显示忙碌提示弹窗。"""
        result: dict[str, Any] = {
            "done": False,
            "value": None,
            "error": None,
        }
        previous_status = self.status_text.get()
        previous_task = self.task_text.get()
        self.status_text.set(status_text)
        self.task_text.set(task_text)

        dialog: Optional[tk.Toplevel] = None
        progress_bar: Optional[ttk.Progressbar] = None

        def _create_dialog() -> tuple[tk.Toplevel, ttk.Progressbar]:
            busy_dialog = tk.Toplevel(self)
            busy_dialog.title(title)
            apply_window_surface(busy_dialog)
            busy_dialog.transient(self)
            busy_dialog.grab_set()
            busy_dialog.resizable(False, False)
            busy_dialog.protocol("WM_DELETE_WINDOW", lambda: None)

            container = ttk.Frame(busy_dialog, padding=(20, 18, 20, 18))
            container.pack(fill=tk.BOTH, expand=True)

            ttk.Label(
                container,
                text=title,
                style="SectionTitle.TLabel",
            ).pack(anchor=tk.W)
            ttk.Label(
                container,
                text=message,
                style="Muted.TLabel",
                justify=tk.LEFT,
                wraplength=360,
            ).pack(anchor=tk.W, pady=(8, 14))

            indicator = ttk.Progressbar(
                container,
                mode="indeterminate",
                length=340,
            )
            indicator.pack(fill=tk.X)
            indicator.start(10)

            busy_dialog.update_idletasks()
            width, height = _compute_dialog_target_size(
                requested_width=busy_dialog.winfo_reqwidth(),
                requested_height=busy_dialog.winfo_reqheight(),
                min_width=420,
                min_height=150,
                extra_width=20,
                extra_height=16,
            )
            _set_centered_window_geometry(busy_dialog, width, height)
            return busy_dialog, indicator

        def _worker_wrapper() -> None:
            try:
                result["value"] = worker()
            except Exception as exc:  # pragma: no cover - exercised via caller path
                result["error"] = exc
            finally:
                result["done"] = True

        thread = threading.Thread(target=_worker_wrapper, daemon=True)
        thread.start()
        started_at = time.monotonic()

        try:
            while not result["done"]:
                elapsed_ms = (time.monotonic() - started_at) * 1000
                if dialog is None and elapsed_ms >= show_after_ms:
                    dialog, progress_bar = _create_dialog()
                self.update()
                self.after(50)
        finally:
            self.task_text.set(previous_task)
            self.status_text.set(previous_status)
            if progress_bar is not None:
                progress_bar.stop()
            if dialog is not None and dialog.winfo_exists():
                dialog.destroy()

        if result["error"] is not None:
            raise result["error"]
        return result["value"]

    def request_stop_generation(self):
        """请求在当前标题完成后停止批量生成"""
        if not self.is_generating:
            return

        self.stop_requested = True
        self.task_text.set("当前任务: 将在本标题完成后停止")
        self.status_text.set("已请求停止，等待当前标题生成完成")

    def expand_to_level_1(self):
        """展开至一级节点"""
        self.tree_view_state = TreeViewState(mode="level_1")
        self._apply_tree_view_state()
        self.status_text.set("已展开至一级节点")

    def expand_to_level_2(self):
        """展开至二级节点"""
        self.tree_view_state = TreeViewState(mode="level_2")
        self._apply_tree_view_state()
        self.status_text.set("已展开至二级节点")

    def expand_to_level_3(self):
        """展开至三级节点"""
        self.tree_view_state = TreeViewState(mode="level_3")
        self._apply_tree_view_state()
        self.status_text.set("已展开至三级节点")

    def expand_all(self):
        """展开全部节点"""
        self.tree_view_state = TreeViewState(mode="all")
        self._apply_tree_view_state()
        self.status_text.set("已展开所有节点")

    def collapse_all(self):
        """收缩全部节点"""
        self.tree_view_state = TreeViewState(mode="collapsed")
        self._apply_tree_view_state()
        self.status_text.set("已收缩所有节点")

    def _expand_to_level(self, max_level: int):
        """
        递归展开到指定级别

        Args:
            max_level: 最大展开级别 (1=一级, 2=二级, 3=三级)
        """
        def expand_recursive(parent_id, current_level):
            """递归展开节点"""
            children = self.outline_tree.get_children(parent_id)
            for child_id in children:
                heading = self.tree_node_map.get(child_id)
                if heading:
                    # 根据节点的level属性判断是否展开
                    if heading.level <= max_level and heading.children:
                        self.outline_tree.item(child_id, open=True)
                        # 递归展开子节点
                        expand_recursive(child_id, heading.level + 1)
                    else:
                        # 超过max_level的节点收缩
                        self.outline_tree.item(child_id, open=False)

        # 从根节点开始
        expand_recursive("", 0)

    def _collapse_all_nodes(self, parent_id):
        """
        递归收缩所有节点

        Args:
            parent_id: 父节点ID，空字符串表示根节点
        """
        children = self.outline_tree.get_children(parent_id)
        for child_id in children:
            # 收缩当前节点
            self.outline_tree.item(child_id, open=False)
            # 递归收缩子节点
            self._collapse_all_nodes(child_id)

    def _get_generation_params(
        self,
        headings: list[HeadingNode],
        *,
        initial_requirements: str = "",
    ):
        """
        获取生成参数对话框

        Returns:
            (
                additional_requirements,
                target_words,
                max_mermaid_flowcharts_per_section,
                fact_card_mode,
                manual_fact_card_selections,
                remember_fact_card_defaults,
            ) 或 None（用户取消）
        """
        dialog = tk.Toplevel(self)
        dialog.title("生成参数设置")
        apply_window_surface(dialog)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        result = {"cancelled": True}
        is_single_heading = len(headings) == 1
        fact_card_panel = None
        fact_card_mode_var = tk.BooleanVar(value=False)
        remember_fact_card_defaults_var = tk.BooleanVar(value=False)

        # 附加要求
        ttk.Label(dialog, text="附加扩写要求：", style="SectionTitle.TLabel").pack(
            pady=(20, 5), padx=20, anchor=tk.W
        )

        req_text = tk.Text(dialog, height=5, width=60)
        style_text_widget(req_text)
        req_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        req_text.insert('1.0', initial_requirements)

        # 目标篇幅基准值
        words_frame = ttk.Frame(dialog)
        words_frame.pack(pady=10, padx=20, fill=tk.X)

        ttk.Label(words_frame, text="目标篇幅基准：", style="SummaryLabel.TLabel").pack(side=tk.LEFT)

        target_words_default = self.bid_writer.config.generation_default_target_words
        target_words_min = self.bid_writer.config.generation_target_words_min
        target_words_max = self.bid_writer.config.generation_target_words_max
        target_words_step = self.bid_writer.config.generation_target_words_step
        persisted_state = load_gui_state()
        initial_target_words, initial_mermaid_limit = _resolve_generation_dialog_defaults(
            persisted_target_words=persisted_state.last_generation_target_words,
            persisted_max_mermaid_flowcharts_per_section=(
                persisted_state.last_max_mermaid_flowcharts_per_section
            ),
            target_words_default=target_words_default,
            target_words_min=target_words_min,
            target_words_max=target_words_max,
        )

        words_var = tk.IntVar(value=initial_target_words)
        words_spinbox = ttk.Spinbox(words_frame, from_=target_words_min, to=target_words_max,
                                    textvariable=words_var, width=10,
                                    increment=target_words_step)
        words_spinbox.pack(side=tk.LEFT, padx=10)
        range_hint_var = tk.StringVar()
        ttk.Label(words_frame, textvariable=range_hint_var, style="SummaryLabel.TLabel").pack(side=tk.LEFT)

        def update_target_range_hint(*_args):
            try:
                target_word_range = self.bid_writer.config.build_target_word_range(words_var.get())
            except (tk.TclError, ValueError):
                range_hint_var.set("系统会自动推导目标区间")
                return
            range_hint_var.set(f"自动推导区间：{target_word_range.display_text} 字")

        words_var.trace_add("write", update_target_range_hint)
        update_target_range_hint()

        mermaid_frame = ttk.Frame(dialog)
        mermaid_frame.pack(pady=(0, 10), padx=20, fill=tk.X)

        ttk.Label(mermaid_frame, text="Mermaid图示上限：", style="SummaryLabel.TLabel").pack(side=tk.LEFT)

        mermaid_var = tk.IntVar(value=initial_mermaid_limit)
        mermaid_spinbox = ttk.Spinbox(
            mermaid_frame,
            from_=0,
            to=999,
            textvariable=mermaid_var,
            width=10,
            increment=1,
        )
        mermaid_spinbox.pack(side=tk.LEFT, padx=10)

        ttk.Label(
            mermaid_frame,
            text="本次生成覆盖配置值；0 表示不注入流程图控制提示",
            style="SummaryLabel.TLabel",
        ).pack(side=tk.LEFT)

        if self.bid_writer.config.fact_cards_enabled:
            fact_card_frame = ttk.Frame(dialog)
            fact_card_frame.pack(pady=(0, 12), padx=20, fill=tk.BOTH, expand=True)

            if is_single_heading:
                from .fact_card_dialogs import FactCardSelectionPanel

                heading = headings[0]
                all_active_cards = self.bid_writer.fact_card_store.list_cards(active_only=True)
                initial_selections = self.bid_writer.list_chapter_default_fact_cards(heading)
                fact_card_dialog_state = self._build_generation_fact_card_dialog_state(
                    all_active_cards,
                    initial_selections,
                )
                fact_card_mode_var.set(fact_card_dialog_state.default_mode)

                ttk.Checkbutton(
                    fact_card_frame,
                    text="本次生成启用事实卡片模式",
                    variable=fact_card_mode_var,
                ).pack(anchor=tk.W, pady=(0, 8))

                ttk.Label(
                    fact_card_frame,
                    text=fact_card_dialog_state.summary_text,
                    justify=tk.LEFT,
                    wraplength=GENERATION_DIALOG_MIN_WIDTH + GENERATION_DIALOG_EXTRA_WIDTH - 80,
                ).pack(anchor=tk.W, pady=(0, 8))

                fact_card_panel = FactCardSelectionPanel(
                    fact_card_frame,
                    cards=fact_card_dialog_state.available_cards,
                    initial_selections=fact_card_dialog_state.initial_selections,
                )
                fact_card_panel.pack(fill=tk.BOTH, expand=True)

                ttk.Checkbutton(
                    fact_card_frame,
                    text="记住为本章节默认卡片方案",
                    variable=remember_fact_card_defaults_var,
                ).pack(anchor=tk.W, pady=(8, 0))
            else:
                fact_card_mode_var.set(True)
                ttk.Label(
                    fact_card_frame,
                    text="批量生成会自动加入启用的全局事实卡片，并读取各章节已保存的局部默认卡片方案；本次不提供整批共享临时局部卡片选择。",
                    justify=tk.LEFT,
                    wraplength=GENERATION_DIALOG_MIN_WIDTH + GENERATION_DIALOG_EXTRA_WIDTH - 80,
                ).pack(anchor=tk.W)

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=(16, 20))

        def collect_fact_card_selections():
            return (
                fact_card_panel.get_selections()
                if fact_card_panel is not None
                else None
            )

        def on_save_fact_card_defaults():
            if not is_single_heading or fact_card_panel is None:
                return
            heading = headings[0]
            selections_to_save = collect_fact_card_selections() or []
            self.bid_writer.save_chapter_default_fact_cards(heading.full_path, selections_to_save)
            self.status_text.set(f"已保存默认卡片方案：{heading.title}")
            messagebox.showinfo(
                "已保存",
                "已保存本章节默认卡片方案。",
                parent=dialog,
            )
            dialog.destroy()

        def on_ok():
            try:
                target_words = words_var.get()
                if target_words < target_words_min or target_words > target_words_max:
                    messagebox.showwarning(
                        "警告",
                        f"目标篇幅基准必须在{target_words_min}-{target_words_max}之间",
                        parent=dialog,
                    )
                    return

                additional_req = req_text.get('1.0', tk.END).strip()
                max_mermaid_flowcharts_per_section = mermaid_var.get()
                if max_mermaid_flowcharts_per_section < 0:
                    messagebox.showwarning("警告", "Mermaid图示上限不能小于 0", parent=dialog)
                    return
                fact_card_mode = bool(fact_card_mode_var.get()) if self.bid_writer.config.fact_cards_enabled else False
                manual_fact_card_selections = collect_fact_card_selections()
                result["cancelled"] = False
                result["requirements"] = additional_req
                result["target_words"] = target_words
                result["max_mermaid_flowcharts_per_section"] = max_mermaid_flowcharts_per_section
                result["fact_card_mode"] = fact_card_mode
                result["manual_fact_card_selections"] = manual_fact_card_selections
                result["remember_fact_card_defaults"] = bool(remember_fact_card_defaults_var.get())
                remember_generation_dialog_settings(
                    target_words,
                    max_mermaid_flowcharts_per_section,
                )
                dialog.destroy()
            except tk.TclError:
                messagebox.showwarning(
                    "警告",
                    "请输入有效的目标篇幅和 Mermaid 图示上限",
                    parent=dialog,
                )

        def on_cancel():
            dialog.destroy()

        save_defaults_button = ttk.Button(
            button_frame,
            text="保存默认方案",
            command=on_save_fact_card_defaults,
            width=14,
            **_bootstyle_kwargs("secondary")
        )
        save_defaults_button.pack(side=tk.LEFT, padx=5)
        if not (is_single_heading and fact_card_panel is not None):
            save_defaults_button.configure(state="disabled")
        ttk.Button(
            button_frame,
            text="确定",
            command=on_ok,
            width=10,
            **_bootstyle_kwargs("primary")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="取消",
            command=on_cancel,
            width=10,
            **_bootstyle_kwargs("secondary")
        ).pack(side=tk.LEFT, padx=5)

        dialog.update_idletasks()
        dialog_width, dialog_height = _compute_dialog_target_size(
            requested_width=dialog.winfo_reqwidth(),
            requested_height=dialog.winfo_reqheight(),
            min_width=GENERATION_DIALOG_MIN_WIDTH,
            min_height=GENERATION_DIALOG_MIN_HEIGHT,
            extra_width=GENERATION_DIALOG_EXTRA_WIDTH,
            extra_height=GENERATION_DIALOG_EXTRA_HEIGHT,
        )
        _set_centered_window_geometry(dialog, dialog_width, dialog_height)

        # 等待对话框关闭
        self.wait_window(dialog)

        if result["cancelled"]:
            return None
        return (
            result["requirements"],
            result["target_words"],
            result["max_mermaid_flowcharts_per_section"],
            result["fact_card_mode"],
            result["manual_fact_card_selections"],
            result["remember_fact_card_defaults"],
        )

    class GenerationSession:
        """主窗口右侧工作区的生成会话控制器。"""

        def __init__(self, parent, heading: HeadingNode):
            self.parent = parent
            self.heading = heading
            self.text_queue = queue.Queue()
            self.is_generating = False
            self.error: Optional[GenerationErrorFeedback] = None
            self.result_data = None
            self._queue_poll_id = None
            self.parent._show_generation_start_in_workspace(heading)

        @staticmethod
        def _widget_exists(widget) -> bool:
            try:
                return widget is not None and bool(widget.winfo_exists())
            except tk.TclError:
                return False

        def _cancel_queue_poll(self) -> None:
            if self._queue_poll_id is None:
                return
            if self._widget_exists(self.parent):
                try:
                    self.parent.after_cancel(self._queue_poll_id)
                except tk.TclError:
                    pass
            self._queue_poll_id = None

        def _check_queue(self):
            """定时检查队列并更新UI（主线程）"""
            try:
                while True:
                    msg_type, data = self.text_queue.get_nowait()

                    if msg_type == "text":
                        # 追加文本
                        self.parent._set_workspace_text(
                            data,
                            append=True,
                            scroll_to_end=True,
                        )

                    elif msg_type == "replace":
                        # 后处理修复了格式，替换整个显示内容
                        self.parent._set_workspace_text(
                            data,
                            generated_char_count=_count_text_characters(data),
                        )
                        if hasattr(self.parent, "workspace_meta_var"):
                            self.parent.workspace_meta_var.set("格式已自动修复")

                    elif msg_type == "status":
                        # 更新状态
                        if hasattr(self.parent, "workspace_meta_var"):
                            self.parent.workspace_meta_var.set(data)
                        if hasattr(self.parent, "status_text"):
                            self.parent.status_text.set(f"{self.heading.title}：{data}")

                    elif msg_type == "done":
                        # 生成完成
                        self.is_generating = False
                        self.result_data = data
                        self._cancel_queue_poll()
                        return

                    elif msg_type == "error":
                        # 发生错误
                        self.error = data
                        self.is_generating = False
                        self._cancel_queue_poll()
                        return

            except queue.Empty:
                pass

            # 如果还在生成，继续定时检查（50ms）
            if self.is_generating and self._widget_exists(self.parent):
                self._queue_poll_id = self.parent.after(50, self._check_queue)

        def start_generation(
            self,
            heading,
            ai_writer,
            requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
            fact_card_mode=False,
            selected_fact_cards=None,
        ):
            """启动后台生成线程"""
            self.is_generating = True

            def _background_generate():
                """后台线程执行生成"""
                current_stage = "准备扩写请求"
                content_parts: list[str] = []

                def _publish_status(stage_label: str, message: str) -> None:
                    nonlocal current_stage
                    current_stage = stage_label
                    self.text_queue.put(("status", message))

                try:
                    _publish_status("准备扩写请求", "正在准备扩写请求...")
                    prepared = ai_writer.prepare_generation(
                        heading,
                        requirements,
                        target_words,
                        stream=ai_writer.config.generation_stream,
                        max_mermaid_flowcharts_per_section_override=max_mermaid_flowcharts_per_section,
                        status_callback=_publish_status,
                        fact_card_mode=fact_card_mode,
                        selected_fact_cards=selected_fact_cards,
                    )
                    if prepared.stream:
                        _publish_status("等待模型首批输出", "正在请求大模型并等待首批内容...")
                    else:
                        _publish_status("请求大模型", "正在请求大模型并等待完整返回...")
                    result = ai_writer.expand_raw(prepared)

                    if isinstance(result, str):
                        _publish_status("接收模型输出", "已收到模型完整输出，正在写入工作区...")
                        content_parts.append(result)
                        self.text_queue.put(("text", result))
                    else:
                        received_first_chunk = False
                        for chunk in result:
                            if not received_first_chunk:
                                _publish_status("接收模型输出", "正在接收模型输出...")
                                received_first_chunk = True
                            content_parts.append(chunk)
                            self.text_queue.put(("text", chunk))

                    content = "".join(content_parts)
                    word_count = ai_writer.count_chinese_words(content)

                    self.text_queue.put(("status", f"生成完成 - {word_count} 字"))
                    write_timing_log(
                        "generation_done_enqueued",
                        heading_title=heading.title,
                        heading_full_path=heading.full_path,
                        trace_id=prepared.trace_id,
                        raw_chars=len(content),
                        word_count=word_count,
                    )
                    self.text_queue.put(("done", (content, word_count, prepared.trace_session)))

                except Exception as e:
                    write_timing_log(
                        "generation_background_error",
                        heading_title=heading.title,
                        heading_full_path=heading.full_path,
                        stage=current_stage,
                        error=str(e),
                    )
                    self.text_queue.put(
                        (
                            "error",
                            _build_generation_error_feedback(
                                heading_title=heading.title,
                                heading_full_path=heading.full_path,
                                stage_label=current_stage,
                                exc=e,
                                has_partial_output=bool(content_parts),
                            ),
                        )
                    )

            # 启动后台线程
            thread = threading.Thread(target=_background_generate, daemon=True)
            thread.start()

            # 启动定时检查队列（在主线程中）
            self._check_queue()

        def wait_completion(self):
            """等待生成完成并返回结果"""
            while self.is_generating:
                if not self._widget_exists(self.parent):
                    raise RuntimeError("主窗口已关闭，无法继续等待生成结果")
                self.parent.update()
                self.parent.after(100)

            if self.error:
                raise GenerationFailedError(self.error)

            return self.result_data  # (content, word_count)

        def close(self):
            """结束当前生成会话轮询。"""
            self._cancel_queue_poll()

    def _generate_into_workspace(
        self,
        heading: HeadingNode,
        additional_requirements: str,
        target_words: int,
        max_mermaid_flowcharts_per_section: int,
        fact_card_mode: bool = False,
        manual_fact_card_selections: Optional[list["FactCardSelection"]] = None,
        remember_fact_card_defaults: bool = False,
        auto_extract_facts: bool = False,
        show_error_dialog: bool = True,
    ) -> str:
        """
        生成内容并在主窗口右侧工作区展示，完成后自动保存。

        Returns:
            "success" / "failed"
        """
        try:
            selected_fact_cards = self.bid_writer.resolve_generation_fact_cards(
                heading,
                manual_fact_card_selections,
                fact_card_mode=fact_card_mode,
            )
        except Exception as exc:
            conflict_message = self._format_fact_card_generation_error(exc)
            messagebox.showerror("事实卡片冲突", conflict_message, parent=self)
            self.status_text.set(f"已阻断生成：{heading.title}")
            return "failed"

        if remember_fact_card_defaults:
            selections_to_save = manual_fact_card_selections or []
            self.bid_writer.save_chapter_default_fact_cards(heading.full_path, selections_to_save)

        gen_window = self.GenerationSession(self, heading)

        gen_window.start_generation(
            heading,
            self.bid_writer.ai_writer,
            additional_requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
            fact_card_mode=fact_card_mode,
            selected_fact_cards=selected_fact_cards,
        )

        try:
            raw_content, _word_count, trace_session = gen_window.wait_completion()
        except GenerationFailedError as e:
            gen_window.close()
            self._report_generation_failure(
                heading,
                e.feedback,
                show_dialog=show_error_dialog,
            )
            return "failed"
        except Exception as e:
            gen_window.close()
            feedback = _build_generation_error_feedback(
                heading_title=heading.title,
                heading_full_path=heading.full_path,
                stage_label="等待生成结果",
                exc=e,
                has_partial_output=False,
            )
            self._report_generation_failure(
                heading,
                feedback,
                show_dialog=show_error_dialog,
            )
            return "failed"

        write_timing_log(
            "workspace_generation_completed",
            heading_title=heading.title,
            heading_full_path=heading.full_path,
            trace_id=trace_session.trace_id if trace_session is not None else "",
            raw_chars=len(raw_content),
        )
        gen_window.close()

        self.status_text.set(f"正在整理输出: {heading.title}")
        finalize_result = self.bid_writer.ai_writer.finalize_generation(
            heading,
            raw_content,
            trace_session=trace_session,
        )
        content = finalize_result.content
        word_count = self.bid_writer.ai_writer.count_chinese_words(content)

        try:
            filepath = self.bid_writer.file_saver.save(heading, content)
        except Exception as e:
            self._show_generated_content_in_workspace(
                heading,
                content,
                meta_text=f"生成完成，但保存失败：{str(e)[:80]}",
            )
            self.status_text.set(f"保存失败: {heading.title}")
            return "failed"

        self._show_generated_content_in_workspace(
            heading,
            content,
            meta_text=f"已自动保存：{filepath.name} · {word_count} 字",
        )
        if auto_extract_facts and self.bid_writer.config.chapter_facts_enabled:
            self._trigger_async_fact_extraction(heading)
        self.status_text.set(f"已自动保存: {filepath.name}")
        return "success"

    def _trigger_async_fact_extraction(self, heading: HeadingNode) -> None:
        """批量生成后异步提炼章节 facts，不阻塞 UI。"""

        def worker() -> None:
            try:
                self.bid_writer.ensure_output_chapter_facts(heading)
                write_timing_log(
                    "chapter_fact_extraction_finished",
                    heading_title=heading.title,
                    heading_full_path=heading.full_path,
                )
            except Exception as exc:
                write_timing_log(
                    "chapter_fact_extraction_failed",
                    heading_title=heading.title,
                    heading_full_path=heading.full_path,
                    error=str(exc),
                )

        threading.Thread(target=worker, daemon=True).start()

    def open_output_dir(self):
        """打开输出目录"""
        output_dir = self.bid_writer.file_saver.output_directory
        if output_dir.exists():
            import subprocess
            if sys.platform == "win32":
                subprocess.Popen(f'explorer "{output_dir}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        else:
            messagebox.showerror("错误", "输出目录不存在", parent=self)

    def update_stats(self):
        """更新统计信息"""
        all_headings = self.adapter.get_all_headings()
        leaf_nodes = [h for h in all_headings if not h.children]

        generated = 0
        for node in leaf_nodes:
            if self.adapter.is_heading_generated(node):
                generated += 1

        total = len(leaf_nodes)
        self.generated_leaf_count = generated
        self.stats_text.set(f"{generated} / {total}")

    def show_help(self):
        """显示帮助"""
        help_text = """使用说明：

1. 在大纲树中选择四级标题，可使用 Ctrl+点击 多选
2. 可通过顶部搜索框和状态筛选快速定位未生成章节
3. 点击“生成所选”开始批量生成，生成过程中可请求停止下一项
4. 单选章节时，右侧正文工作区会直接显示已生成内容；生成过程中也会实时刷新当前章节正文
5. 点击“整合标书”可按大纲顺序合并所有已生成章节正文，并自定义输出文件名
6. “扫描输出状态”会重新读取输出目录并刷新完成情况

快捷键：
- Ctrl+A: 全选当前结果中的四级标题
- Ctrl+F: 聚焦搜索框
- Ctrl+1 / Ctrl+2 / Ctrl+3: 分级展开
- Ctrl+0: 收缩全部
- Esc: 清空当前选择
"""
        messagebox.showinfo("使用说明", help_text, parent=self)

    def show_about(self):
        """显示关于"""
        about_text = """自动标书撰写系统（GUI版）

版本：1.0.0
基于：Python + Tkinter + 可选 ttkbootstrap 主题
功能：AI辅助标书撰写

功能特点：
- 大纲导航
- 批量生成
- 状态跟踪
- 进度显示
"""
        messagebox.showinfo("关于", about_text, parent=self)


def run_gui(config_path: Optional[str] = None):
    """运行GUI应用"""
    ensure_tk_runtime()
    bid_writer, outline_preloaded = _build_startup_bid_writer(config_path)
    app = MainWindow(bid_writer, outline_preloaded=outline_preloaded)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
