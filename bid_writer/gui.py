#!/usr/bin/env python3
"""
Tkinter GUI 主界面
自动标书撰写系统的桌面版界面
"""

import os
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk
from typing import List, Optional
from pathlib import Path

from .main import BidWriter
from .gui_adapter import GUIAdapter
from .outline_parser import HeadingNode
from .gui_state import get_startup_config_candidates, remember_last_config
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
MAIN_OUTLINE_DEFAULT_WIDTH = 520
MAIN_OUTLINE_MIN_WIDTH = 360
MAIN_WORKSPACE_MIN_WIDTH = 460
POPUP_OUTLINE_DEFAULT_WIDTH = 320
POPUP_OUTLINE_MIN_WIDTH = 240
POPUP_CONTENT_MIN_WIDTH = 480
GENERATION_DIALOG_MIN_WIDTH = 520
GENERATION_DIALOG_MIN_HEIGHT = 280
GENERATION_DIALOG_EXTRA_WIDTH = 24
GENERATION_DIALOG_EXTRA_HEIGHT = 20
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
class GuiColorPalette:
    """GUI 常用颜色面板。"""

    surface_background: str
    input_background: str
    input_foreground: str
    border_color: str
    accent_color: str


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
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

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

        self.geometry(f"{target_width}x{target_height}")

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

        # 树节点到HeadingNode的映射
        self.tree_node_map = {}

        # 窗口配置
        self.title("自动标书撰写系统 - GUI版")
        self.geometry("1000x800")

        # 最小尺寸
        self.minsize(800, 600)

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
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = tk.Menu(self)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="选择配置文件...", command=self.select_and_switch_config)
        file_menu.add_command(label="编辑当前配置...", command=self.open_config_editor)
        file_menu.add_separator()
        file_menu.add_command(label="重载大纲", command=self.reload_outline)
        file_menu.add_command(label="扫描输出状态", command=self.refresh_status)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        # 操作菜单
        action_menu = tk.Menu(menubar, tearoff=0)
        action_menu.add_command(label="生成所选", command=self.batch_generate)
        action_menu.add_command(label="生成整合标书", command=self.merge_generated_sections)
        action_menu.add_separator()
        action_menu.add_command(label="打开输出目录", command=self.open_output_dir)
        menubar.add_cascade(label="操作", menu=action_menu)

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

        self.utility_frame = ttk.Frame(self.action_bar)

        self.btn_config = ttk.Button(
            self.utility_frame,
            text="切换配置",
            command=self.select_and_switch_config,
            padding=(12, 8),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_config.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_edit_config = ttk.Button(
            self.utility_frame,
            text="编辑配置",
            command=self.open_config_editor,
            padding=(12, 8),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_edit_config.pack(side=tk.LEFT, padx=6)

        self.btn_reload = ttk.Button(
            self.utility_frame,
            text="重载大纲",
            command=self.reload_outline,
            padding=(12, 8),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_reload.pack(side=tk.LEFT, padx=6)

        self.btn_refresh = ttk.Button(
            self.utility_frame,
            text="扫描输出状态",
            command=self.refresh_status,
            padding=(12, 8),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=6)

        self.btn_tree_expand = ttk.Button(
            self.utility_frame,
            text="展开全部▼",
            command=self.show_expand_menu,
            padding=(12, 8),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_tree_expand.pack(side=tk.LEFT, padx=6)

        self.btn_output = ttk.Button(
            self.utility_frame,
            text="打开输出目录",
            command=self.open_output_dir,
            padding=(12, 8),
            **_bootstyle_kwargs("info")
        )
        self.btn_output.pack(side=tk.LEFT, padx=(6, 0))

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
            min_left_width=MAIN_OUTLINE_MIN_WIDTH,
            min_right_width=MAIN_WORKSPACE_MIN_WIDTH,
        )

        header_frame = ttk.Frame(outline_panel)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        title_group = ttk.Frame(header_frame)
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

        self.control_group = ttk.Frame(header_frame)
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

        self.btn_select_all = ttk.Button(
            self.selection_action_group,
            text="全选四级标题",
            command=self.select_all_leaf_titles,
            padding=(10, 6),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_select_all.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_clear_selection = ttk.Button(
            self.selection_action_group,
            text="清空选择",
            command=self.clear_selection,
            padding=(10, 6),
            **_bootstyle_kwargs("secondary")
        )
        self.btn_clear_selection.pack(side=tk.LEFT)

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
        self.outline_tree.column("#0", width=680)
        self.outline_tree.column("status", width=110, anchor=tk.CENTER)
        self.outline_tree.column("progress", width=110, anchor=tk.CENTER)
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
            "正在生成正文...",
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

    def on_window_resize(self, event):
        """窗口尺寸变化后刷新自适应布局"""
        if event.widget is not self:
            return
        self.schedule_responsive_layout()

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
        available_width = max(self.action_bar.winfo_width(), self.winfo_width() - 32)
        if available_width <= 1:
            return self._action_layout_mode or "stacked"

        required_width = self.utility_frame.winfo_reqwidth() + self.action_frame.winfo_reqwidth() + 24
        return "single" if required_width <= available_width else "stacked"

    def _layout_action_bar(self, layout_mode: str):
        """工具按钮区域宽度不足时拆分为两行"""
        self.utility_frame.grid_forget()
        self.action_frame.grid_forget()
        self.action_bar.grid_columnconfigure(0, weight=0)
        self.action_bar.grid_columnconfigure(1, weight=0)

        if layout_mode == "single":
            self.action_bar.grid_columnconfigure(0, weight=1)
            self.utility_frame.grid(row=0, column=0, sticky="w")
            self.action_frame.grid(row=0, column=1, sticky="e")
            return

        self.action_bar.grid_columnconfigure(0, weight=1)
        self.utility_frame.grid(row=0, column=0, sticky="w")
        self.action_frame.grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _get_control_layout_mode(self) -> str:
        """计算筛选控制区域应使用的布局模式"""
        available_width = max(self.control_group.winfo_width(), self.winfo_width() - 32)
        if available_width <= 1:
            return self._control_layout_mode or "stacked"

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
        self.expand_menu = tk.Menu(self, tearoff=0)
        self.expand_menu.add_command(
            label="全部展开",
            command=self.expand_all
        )
        self.expand_menu.add_separator()
        self.expand_menu.add_command(
            label="展开至一级 (Ctrl+1)",
            command=self.expand_to_level_1
        )
        self.expand_menu.add_command(
            label="展开至二级 (Ctrl+2)",
            command=self.expand_to_level_2
        )
        self.expand_menu.add_command(
            label="展开至三级 (Ctrl+3)",
            command=self.expand_to_level_3
        )
        self.expand_menu.add_separator()
        self.expand_menu.add_command(
            label="收缩全部 (Ctrl+0)",
            command=self.collapse_all
        )

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
        # 获取按钮的屏幕坐标
        x = self.btn_tree_expand.winfo_rootx()
        y = self.btn_tree_expand.winfo_rooty() + self.btn_tree_expand.winfo_height()
        # 在按钮下方显示菜单
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
                self.bid_writer.last_error_message or "加载大纲失败"
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
        self.visible_leaf_count = 0

        root_headings = self.adapter.get_outline_tree()
        query = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        status_filter = self.status_filter_var.get() if hasattr(self, "status_filter_var") else "全部"

        for heading in root_headings:
            self._add_tree_node("", heading, query, status_filter)

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

            target_width = max(
                min_left_width,
                min(default_width, total_width - min_right_width),
            )
            try:
                paned_window.sash_place(0, target_width, 1)
            except tk.TclError:
                pass

        paned_window.after_idle(place_sash)

    def _add_tree_node(self, parent: str, heading: HeadingNode, query: str = "", status_filter: str = "全部"):
        """递归添加树节点"""
        if not self._heading_or_descendant_matches(heading, query, status_filter):
            return

        status, progress_info, row_tag = self._get_heading_tree_row_values(heading)
        if not heading.children:
            self.visible_leaf_count += 1

        node_id = self.outline_tree.insert(
            parent, 'end',
            text=heading.title,
            values=(status, progress_info),
            tags=(row_tag,)
        )

        # 保存节点映射
        self.tree_node_map[node_id] = heading

        # 递归添加子节点
        for child in heading.children:
            self._add_tree_node(node_id, child, query, status_filter)

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

    def update_action_states(self):
        """同步顶部操作按钮和统计信息"""
        selected_headings = self._get_selected_leaf_headings()
        selected_count = len(selected_headings)
        self.selection_text.set(str(selected_count))
        self.btn_generate.config(
            text=f"生成所选 {selected_count}",
            state=(tk.DISABLED if self.is_generating or selected_count == 0 else tk.NORMAL)
        )
        self.btn_merge.config(
            state=(tk.DISABLED if self.is_generating or self.generated_leaf_count == 0 else tk.NORMAL)
        )
        self.btn_select_all.config(
            state=(tk.DISABLED if self.is_generating or self.visible_leaf_count == 0 else tk.NORMAL)
        )
        self.btn_clear_selection.config(
            state=(tk.DISABLED if self.is_generating or selected_count == 0 else tk.NORMAL)
        )

        button_state = tk.DISABLED if self.is_generating else tk.NORMAL
        for widget in (
            self.btn_config,
            self.btn_edit_config,
            self.btn_reload,
            self.btn_refresh,
            self.btn_tree_expand,
            self.btn_output,
        ):
            widget.config(state=button_state)

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

    def on_title_select(self, event):
        """保留空方法，避免旧绑定报错"""
        pass

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
            messagebox.showerror("错误", f"加载配置失败：\n{e}")
            self.status_text.set("配置切换失败")
            return

        if not next_bid_writer.load_outline():
            messagebox.showerror(
                "错误",
                next_bid_writer.last_error_message or "切换配置后加载大纲失败"
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
            messagebox.showwarning("警告", "请先选择要生成的四级标题")
            return

        # 获取生成参数
        params = self._get_generation_params()
        if params is None:
            return  # 用户取消了

        additional_requirements, target_words, max_mermaid_flowcharts_per_section = params
        target_word_range = self.bid_writer.config.build_target_word_range(target_words)

        # 确认对话框
        warning_line = ""
        if len(selected_headings) >= 20:
            warning_line = "\n\n本次任务较大，建议确认筛选范围后再执行。"

        if not messagebox.askyesno(
            "确认",
            f"确定要生成 {len(selected_headings)} 个标题吗？\n\n"
            f"附加要求：{additional_requirements or '（无）'}\n"
            f"目标篇幅：{target_word_range.display_text} 字\n"
            f"Mermaid流程图上限：{max_mermaid_flowcharts_per_section}"
            f"{warning_line}"
        ):
            return

        # 在主线程执行生成（避免线程安全问题）
        self._do_batch_generate(
            selected_headings,
            additional_requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
        )

    def _do_batch_generate(
        self,
        headings: List[HeadingNode],
        additional_requirements: str,
        target_words: int,
        max_mermaid_flowcharts_per_section: int,
    ):
        """执行批量生成（主线程）"""
        total = len(headings)
        success_count = 0
        fail_count = 0
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
                )

                completed_count = i
                self.progress_bar.configure(value=i)
                self.batch_progress_text.set(f"{i} / {total}")

                if result == "success":
                    success_count += 1
                else:
                    fail_count += 1

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
            messagebox.showwarning("提示", "当前没有可整合的已生成章节")
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
            messagebox.showerror("错误", f"生成整合标书失败：\n{e}")
            return

        output_path = _display_path(result.filepath.resolve(), Path.cwd().resolve())
        merged_message = (
            f"已整合 {result.merged_sections}/{result.total_sections} 个章节。"
        )
        if result.missing_sections:
            merged_message += f"\n有 {result.missing_sections} 个章节未生成，已自动跳过。"

        merged_message += f"\n\n输出文件：\n{output_path}"
        self.status_text.set(f"整合标书已生成: {result.filepath.name}")
        messagebox.showinfo("整合完成", merged_message)

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

    def _get_generation_params(self):
        """
        获取生成参数对话框

        Returns:
            (additional_requirements, target_words, max_mermaid_flowcharts_per_section) 或 None（用户取消）
        """
        dialog = tk.Toplevel(self)
        dialog.title("生成参数设置")
        apply_window_surface(dialog)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        result = {"cancelled": True}

        # 附加要求
        ttk.Label(dialog, text="附加扩写要求：", style="SectionTitle.TLabel").pack(
            pady=(20, 5), padx=20, anchor=tk.W
        )

        req_text = tk.Text(dialog, height=5, width=60)
        style_text_widget(req_text)
        req_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        req_text.insert('1.0', "")

        # 目标篇幅基准值
        words_frame = ttk.Frame(dialog)
        words_frame.pack(pady=10, padx=20, fill=tk.X)

        ttk.Label(words_frame, text="目标篇幅基准：", style="SummaryLabel.TLabel").pack(side=tk.LEFT)

        target_words_default = self.bid_writer.config.generation_default_target_words
        target_words_min = self.bid_writer.config.generation_target_words_min
        target_words_max = self.bid_writer.config.generation_target_words_max
        target_words_step = self.bid_writer.config.generation_target_words_step

        words_var = tk.IntVar(value=target_words_default)
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

        ttk.Label(mermaid_frame, text="Mermaid流程图上限：", style="SummaryLabel.TLabel").pack(side=tk.LEFT)

        mermaid_var = tk.IntVar(value=0)
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

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=(16, 20))

        def on_ok():
            try:
                target_words = words_var.get()
                if target_words < target_words_min or target_words > target_words_max:
                    messagebox.showwarning("警告", f"目标篇幅基准必须在{target_words_min}-{target_words_max}之间")
                    return

                additional_req = req_text.get('1.0', tk.END).strip()
                max_mermaid_flowcharts_per_section = mermaid_var.get()
                if max_mermaid_flowcharts_per_section < 0:
                    messagebox.showwarning("警告", "Mermaid流程图上限不能小于 0")
                    return
                result["cancelled"] = False
                result["requirements"] = additional_req
                result["target_words"] = target_words
                result["max_mermaid_flowcharts_per_section"] = max_mermaid_flowcharts_per_section
                dialog.destroy()
            except tk.TclError:
                messagebox.showwarning("警告", "请输入有效的目标篇幅和 Mermaid 流程图上限")

        def on_cancel():
            dialog.destroy()

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
        dialog.geometry(f"{dialog_width}x{dialog_height}")

        x = (dialog.winfo_screenwidth() // 2) - (dialog_width // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog_height // 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 等待对话框关闭
        self.wait_window(dialog)

        if result["cancelled"]:
            return None
        return (
            result["requirements"],
            result["target_words"],
            result["max_mermaid_flowcharts_per_section"],
        )

    class GenerationSession:
        """主窗口右侧工作区的生成会话控制器。"""

        def __init__(self, parent, heading: HeadingNode):
            self.parent = parent
            self.heading = heading
            self.text_queue = queue.Queue()
            self.is_generating = False
            self.error = None
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
        ):
            """启动后台生成线程"""
            self.is_generating = True

            def _background_generate():
                """后台线程执行生成"""
                try:
                    self.text_queue.put(("status", "正在生成内容..."))

                    content_parts = []
                    prepared = ai_writer.prepare_generation(
                        heading,
                        requirements,
                        target_words,
                        stream=ai_writer.config.generation_stream,
                        max_mermaid_flowcharts_per_section_override=max_mermaid_flowcharts_per_section,
                    )
                    result = ai_writer.expand_raw(prepared)

                    if isinstance(result, str):
                        content_parts.append(result)
                        self.text_queue.put(("text", result))
                    else:
                        for chunk in result:
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
                        error=str(e),
                    )
                    self.text_queue.put(("error", str(e)))

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
                raise Exception(self.error)

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
    ) -> str:
        """
        生成内容并在主窗口右侧工作区展示，完成后自动保存。

        Returns:
            "success" / "failed"
        """
        gen_window = self.GenerationSession(self, heading)

        gen_window.start_generation(
            heading,
            self.bid_writer.ai_writer,
            additional_requirements,
            target_words,
            max_mermaid_flowcharts_per_section,
        )

        try:
            raw_content, _word_count, trace_session = gen_window.wait_completion()
        except Exception as e:
            gen_window.close()
            self.workspace_meta_var.set(f"生成失败：{str(e)[:80]}")
            self.status_text.set(f"生成失败: {str(e)[:50]}...")
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
        self.status_text.set(f"已自动保存: {filepath.name}")
        return "success"

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
            messagebox.showerror("错误", "输出目录不存在")

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
        messagebox.showinfo("使用说明", help_text)

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
        messagebox.showinfo("关于", about_text)


def run_gui(config_path: Optional[str] = None):
    """运行GUI应用"""
    ensure_tk_runtime()
    bid_writer, outline_preloaded = _build_startup_bid_writer(config_path)
    app = MainWindow(bid_writer, outline_preloaded=outline_preloaded)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
