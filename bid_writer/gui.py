#!/usr/bin/env python3
"""
Tkinter GUI 主界面
自动标书撰写系统的桌面版界面
"""

import os
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
from typing import List, Optional
from pathlib import Path

from .main import BidWriter
from .gui_adapter import GUIAdapter
from .outline_parser import HeadingNode

import threading
import queue
import sys


DEFAULT_CONFIG_FILES = {"config.yaml", "config.yml"}
_TK_ENV_READY = False


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

        self.base_dir = Path.cwd().resolve()
        self.result: Optional[str] = None
        self._config_map: dict[str, Path] = {}

        self.title("选择配置文件")
        self.geometry("620x230")
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
            font=("TkDefaultFont", 11, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            container,
            text="默认列出当前目录下的 config*.yaml，可点击“浏览...”选择其它 YAML 文件。",
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
            padding=(12, 6)
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(
            container,
            textvariable=self.info_var,
            foreground="#555555",
            wraplength=560,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(14, 20))

        button_frame = ttk.Frame(container)
        button_frame.pack(anchor=tk.E)

        ttk.Button(
            button_frame,
            text="取消",
            command=self._on_cancel,
            width=10,
            padding=(12, 6)
        ).pack(side=tk.LEFT, padx=6)

        ttk.Button(
            button_frame,
            text="确定",
            command=self._on_confirm,
            width=10,
            padding=(12, 6)
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
            return

        self.info_var.set(f"当前将使用：{selected_path}")

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
        dialog_parent.withdraw()
        owns_root = True

    dialog = ConfigSelectionDialog(dialog_parent, initial_path=initial_path)
    dialog_parent.wait_window(dialog)
    result = dialog.result

    if owns_root:
        dialog_parent.destroy()

    return result


class MainWindow(tk.Tk):
    """主窗口类"""

    def __init__(self, bid_writer: BidWriter):
        ensure_tk_runtime()
        super().__init__()

        self.bid_writer = bid_writer
        self.adapter = GUIAdapter(bid_writer)

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

        # 加载大纲
        self.load_outline()

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
        file_menu.add_separator()
        file_menu.add_command(label="重新加载大纲", command=self.reload_outline)
        file_menu.add_command(label="刷新状态", command=self.refresh_status)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        # 操作菜单
        action_menu = tk.Menu(menubar, tearoff=0)
        action_menu.add_command(label="批量生成选中", command=self.batch_generate)
        action_menu.add_command(label="预览", command=self.preview_selected)
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
        toolbar = ttk.Frame(self)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # 文件管理区
        btn_reload = ttk.Button(toolbar, text="🔄 重新加载",
                               command=self.reload_outline,
                               padding=(10, 8))
        btn_reload.pack(side=tk.LEFT, padx=5)

        btn_config = ttk.Button(toolbar, text="⚙️ 配置",
                                command=self.select_and_switch_config,
                                padding=(10, 8))
        btn_config.pack(side=tk.LEFT, padx=5)

        btn_refresh = ttk.Button(toolbar, text="🔄 刷新状态",
                                command=self.refresh_status,
                                padding=(10, 8))
        btn_refresh.pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                       fill=tk.Y,
                                                       padx=15)

        # 树操作区
        self.btn_tree_expand = ttk.Button(toolbar, text="📂 展开/收缩",
                                          command=self.show_expand_menu,
                                          padding=(10, 8))
        self.btn_tree_expand.pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                       fill=tk.Y,
                                                       padx=15)

        # 内容生成区
        btn_generate = ttk.Button(toolbar, text="⚡ 批量生成",
                                 command=self.batch_generate,
                                 padding=(10, 8))
        btn_generate.pack(side=tk.LEFT, padx=5)

        btn_preview = ttk.Button(toolbar, text="👁️ 预览",
                                command=self.preview_selected,
                                padding=(10, 8))
        btn_preview.pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                       fill=tk.Y,
                                                       padx=15)

        # 其他区
        btn_output = ttk.Button(toolbar, text="📂 输出目录",
                               command=self.open_output_dir,
                               padding=(10, 8))
        btn_output.pack(side=tk.LEFT, padx=5)

    def create_main_panes(self):
        """创建主面板"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 标题和说明
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=5)

        ttk.Label(header_frame, text="📄 大纲结构（仅四级标题可多选）",
                 font=('TkDefaultFont', 10, 'bold')).pack(side=tk.LEFT)

        # 全选/全不选四级标题
        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(header_frame, text="全选四级标题",
                       variable=self.select_all_var,
                       command=self.toggle_select_all).pack(side=tk.RIGHT, padx=5)

        # 大纲树（支持多选）
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.outline_tree = ttk.Treeview(tree_frame, columns=("status", "progress"),
                                        height=30, show="tree headings",
                                        selectmode='extended')
        self.outline_tree.heading("#0", text="标题")
        self.outline_tree.heading("status", text="状态")
        self.outline_tree.heading("progress", text="进度")
        self.outline_tree.column("#0", width=600)
        self.outline_tree.column("status", width=80, anchor=tk.CENTER)
        self.outline_tree.column("progress", width=100, anchor=tk.CENTER)

        # 滚动条
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                          command=self.outline_tree.yview)
        self.outline_tree.config(yscrollcommand=sb.set)

        self.outline_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定选择事件
        self.outline_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def create_status_bar(self):
        """创建状态栏"""
        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # 状态文本
        self.status_text = tk.StringVar()
        self.status_text.set("就绪")
        status_label = ttk.Label(status_frame, textvariable=self.status_text)
        status_label.pack(side=tk.LEFT, padx=5)

        self.config_text = tk.StringVar()
        self.config_text.set("配置: -")
        config_label = ttk.Label(status_frame, textvariable=self.config_text)
        config_label.pack(side=tk.LEFT, padx=10)

        # 进度条
        self.progress_bar = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress_bar.pack(side=tk.RIGHT, padx=5)

        # 统计信息
        self.stats_text = tk.StringVar()
        self.stats_text.set("已生成: 0 / 总计: 0")
        stats_label = ttk.Label(status_frame, textvariable=self.stats_text)
        stats_label.pack(side=tk.RIGHT, padx=10)

    def update_window_context(self):
        """更新窗口标题和当前配置显示"""
        config_name = self.bid_writer.config.config_path.name
        self.title(f"自动标书撰写系统 - GUI版 [{config_name}]")
        self.config_text.set(f"配置: {config_name}")

    def create_expand_menu(self):
        """创建展开/收缩下拉菜单"""
        self.expand_menu = tk.Menu(self, tearoff=0)
        self.expand_menu.add_command(
            label="📂 展开至一级 (Ctrl+1)",
            command=self.expand_to_level_1
        )
        self.expand_menu.add_command(
            label="📂 展开至二级 (Ctrl+2)",
            command=self.expand_to_level_2
        )
        self.expand_menu.add_command(
            label="📂 展开至三级 (Ctrl+3)",
            command=self.expand_to_level_3
        )
        self.expand_menu.add_separator()
        self.expand_menu.add_command(
            label="📁 收缩全部 (Ctrl+0)",
            command=self.collapse_all
        )

    def bind_shortcuts(self):
        """绑定快捷键"""
        # 展开/收缩快捷键
        self.bind('<Control-Key-1>', lambda e: self.expand_to_level_1())
        self.bind('<Control-Key-2>', lambda e: self.expand_to_level_2())
        self.bind('<Control-Key-3>', lambda e: self.expand_to_level_3())
        self.bind('<Control-Key-0>', lambda e: self.collapse_all())

    def show_expand_menu(self):
        """显示展开/收缩菜单"""
        # 获取按钮的屏幕坐标
        x = self.btn_tree_expand.winfo_rootx()
        y = self.btn_tree_expand.winfo_rooty() + self.btn_tree_expand.winfo_height()
        # 在按钮下方显示菜单
        self.expand_menu.post(x, y)


    def load_outline(self):
        """加载大纲到树形视图"""
        # 加载大纲
        if not self.bid_writer.load_outline():
            messagebox.showerror(
                "错误",
                self.bid_writer.last_error_message or "加载大纲失败"
            )
            return False

        self.adapter.refresh_generated_titles()
        self._render_outline_tree()
        self.select_all_var.set(False)
        self.update_stats()
        self.status_text.set("大纲加载完成")
        return True

    def _render_outline_tree(self):
        """将已加载的大纲渲染到树形视图"""
        for item in self.outline_tree.get_children():
            self.outline_tree.delete(item)

        self.tree_node_map.clear()

        root_headings = self.adapter.get_outline_tree()
        for heading in root_headings:
            self._add_tree_node("", heading)

    def _add_tree_node(self, parent: str, heading: HeadingNode):
        """递归添加树节点"""
        # 获取状态
        status = self.adapter.get_status_icon(heading)
        progress_info = ""

        if heading.children:
            generated, total = self.adapter.get_progress(heading)
            if total > 0:
                progress_info = f"{generated}/{total}"

        # 插入节点
        node_id = self.outline_tree.insert(
            parent, 'end',
            text=f" {heading.title}",
            values=(status, progress_info)
        )

        # 保存节点映射
        self.tree_node_map[node_id] = heading

        # 递归添加子节点
        for child in heading.children:
            self._add_tree_node(node_id, child)

    def on_tree_select(self, event):
        """当选择树节点时 - 只允许选择四级标题（叶子节点）"""
        selection = self.outline_tree.selection()
        if not selection:
            self.status_text.set("未选择任何标题")
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
        if count == 0:
            self.status_text.set("请选择四级标题（叶子节点）")
        elif count == 1:
            heading = self.tree_node_map.get(valid_selection[0])
            self.status_text.set(f"已选择: {heading.title if heading else ''}")
        else:
            self.status_text.set(f"已选择 {count} 个四级标题")

    def on_title_select(self, event):
        """保留空方法，避免旧绑定报错"""
        pass

    def reload_outline(self):
        """重新加载大纲"""
        self.status_text.set("正在重新加载大纲...")
        if self.load_outline():
            self.status_text.set("大纲重新加载完成")

    def refresh_status(self):
        """刷新状态"""
        self.status_text.set("正在刷新状态...")
        if self.load_outline():
            self.status_text.set("状态刷新完成")

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
        self._render_outline_tree()
        self.select_all_var.set(False)
        self.update_window_context()
        self.update_stats()
        self.status_text.set(f"已切换配置: {selected_path.name}")

    def batch_generate(self):
        """批量生成选中的标题"""
        selection = self.outline_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要生成的四级标题")
            return

        # 获取选中的HeadingNode列表
        selected_headings = []
        for item_id in selection:
            heading = self.tree_node_map.get(item_id)
            if heading and not heading.children:
                selected_headings.append(heading)

        if not selected_headings:
            messagebox.showwarning("警告", "请选择四级标题（叶子节点）")
            return

        # 获取生成参数
        params = self._get_generation_params()
        if params is None:
            return  # 用户取消了

        additional_requirements, min_words = params

        # 确认对话框
        if not messagebox.askyesno("确认",
            f"确定要生成 {len(selected_headings)} 个标题吗？\n\n" +
            f"附加要求：{additional_requirements or '（无）'}\n" +
            f"最低字数：{min_words}"):
            return

        # 在主线程执行生成（避免线程安全问题），批量生成模式自动保存
        self._do_batch_generate(selected_headings, additional_requirements, min_words, auto_save=True)

    def _do_batch_generate(self, headings: List[HeadingNode],
                           additional_requirements: str, min_words: int, auto_save: bool = False):
        """执行批量生成（主线程）"""
        # 开始进度条
        self.progress_bar.start()

        total = len(headings)
        success_count = 0
        skip_count = 0
        fail_count = 0

        for i, heading in enumerate(headings, 1):
            self.status_text.set(f"[{i}/{total}] 正在生成: {heading.title}")
            self.update_idletasks()  # 保持界面响应

            # 生成内容（批量生成时自动保存，单个生成时需要预览确认）
            result = self._generate_with_preview(heading, additional_requirements, min_words, auto_save=auto_save)

            if result == "success":
                success_count += 1
            elif result == "skip":
                skip_count += 1
            else:
                fail_count += 1

        # 停止进度条
        self.progress_bar.stop()

        # 只在状态栏显示批量生成结果，不弹窗
        self.refresh_status()
        self.status_text.set(f"批量生成完成 - 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")

    def preview_selected(self):
        """预览选中的标题"""
        selection = self.outline_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要预览的标题")
            return

        if len(selection) > 1:
            messagebox.showwarning("警告", "只能预览单个标题")
            return

        item_id = selection[0]
        heading = self.tree_node_map.get(item_id)

        if not heading or heading.children:
            messagebox.showwarning("警告", "请选择四级标题（叶子节点）")
            return

        # 查找文件（优先使用稳定 ID，兼容旧命名规则）
        file_saver = self.bid_writer.file_saver
        filepath = file_saver.find_existing_filepath(heading)

        if filepath and filepath.exists():
            # 读取并预览
            content = filepath.read_text(encoding='utf-8')
            preview_window = tk.Toplevel(self)
            preview_window.title(f"预览 - {filepath.name}")
            preview_window.geometry("800x600")

            text_widget = tk.Text(preview_window, wrap=tk.WORD, font=('Consolas', 10))
            scrollbar = ttk.Scrollbar(preview_window, command=text_widget.yview)
            text_widget.config(yscrollcommand=scrollbar.set)

            text_widget.insert('1.0', content)
            text_widget.config(state=tk.DISABLED)

            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            messagebox.showinfo("预览", f"文件未生成\n标题：{heading.title}")

    def toggle_select_all(self):
        """全选/全不选四级标题（叶子节点）"""
        # 清空当前选择
        for item_id in self.outline_tree.selection():
            self.outline_tree.selection_remove(item_id)

        if self.select_all_var.get():
            # 全选所有叶子节点
            self._select_all_leaf_nodes("")

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

    def expand_to_level_1(self):
        """展开至一级节点"""
        self._expand_to_level(1)
        self.status_text.set("已展开至一级节点")

    def expand_to_level_2(self):
        """展开至二级节点"""
        self._expand_to_level(2)
        self.status_text.set("已展开至二级节点")

    def expand_to_level_3(self):
        """展开至三级节点"""
        self._expand_to_level(3)
        self.status_text.set("已展开至三级节点")

    def collapse_all(self):
        """收缩全部节点"""
        self._collapse_all_nodes("")
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
            (additional_requirements, min_words) 或 None（用户取消）
        """
        dialog = tk.Toplevel(self)
        dialog.title("生成参数设置")
        dialog.geometry("500x250")
        dialog.transient(self)
        dialog.grab_set()

        # 居中对话框
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        result = {"cancelled": True}

        # 附加要求
        ttk.Label(dialog, text="附加扩写要求：",
                 font=('TkDefaultFont', 10)).pack(pady=(20, 5), padx=20, anchor=tk.W)

        req_text = tk.Text(dialog, height=5, width=60, font=('Consolas', 10))
        req_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        req_text.insert('1.0', "")

        # 最低字数
        words_frame = ttk.Frame(dialog)
        words_frame.pack(pady=10, padx=20, fill=tk.X)

        ttk.Label(words_frame, text="最低字数：",
                 font=('TkDefaultFont', 10)).pack(side=tk.LEFT)

        min_words_default = self.bid_writer.config.generation_default_min_words
        min_words_min = self.bid_writer.config.generation_min_words_min
        min_words_max = self.bid_writer.config.generation_min_words_max
        min_words_step = self.bid_writer.config.generation_min_words_step

        words_var = tk.IntVar(value=min_words_default)
        words_spinbox = ttk.Spinbox(words_frame, from_=min_words_min, to=min_words_max,
                                    textvariable=words_var, width=10,
                                    increment=min_words_step)
        words_spinbox.pack(side=tk.LEFT, padx=10)

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_ok():
            try:
                min_words = words_var.get()
                if min_words < min_words_min or min_words > min_words_max:
                    messagebox.showwarning("警告", f"字数必须在{min_words_min}-{min_words_max}之间")
                    return

                additional_req = req_text.get('1.0', tk.END).strip()
                result["cancelled"] = False
                result["requirements"] = additional_req
                result["min_words"] = min_words
                dialog.destroy()
            except tk.TclError:
                messagebox.showwarning("警告", "请输入有效的字数")

        def on_cancel():
            dialog.destroy()

        ttk.Button(button_frame, text="确定", command=on_ok,
                  width=10, padding=(15, 8)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel,
                  width=10, padding=(15, 8)).pack(side=tk.LEFT, padx=5)

        # 等待对话框关闭
        self.wait_window(dialog)

        if result["cancelled"]:
            return None
        return (result["requirements"], result["min_words"])

    class GenerationWindow:
        """生成进度窗口 - 异步流式显示"""

        def __init__(self, parent, heading_title: str):
            self.window = tk.Toplevel(parent)
            self.window.title(f"正在生成 - {heading_title}")
            self.window.geometry("800x600")
            self.window.transient(parent)

            # 不使用 grab_set()，允许用户查看其他窗口

            # 标题
            title_frame = ttk.Frame(self.window)
            title_frame.pack(fill=tk.X, padx=10, pady=10)

            ttk.Label(title_frame, text=f"正在生成：{heading_title}",
                     font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)

            self.status_label = ttk.Label(title_frame, text="准备中...",
                                         font=('TkDefaultFont', 9))
            self.status_label.pack(anchor=tk.W)

            # 文本显示区域
            text_frame = ttk.Frame(self.window)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            self.text_widget = tk.Text(text_frame, wrap=tk.WORD,
                                      font=('Consolas', 10), state=tk.DISABLED)
            scrollbar = ttk.Scrollbar(text_frame, command=self.text_widget.yview)
            self.text_widget.config(yscrollcommand=scrollbar.set)

            self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # 进度条
            self.progress = ttk.Progressbar(self.window, mode='indeterminate')
            self.progress.pack(fill=tk.X, padx=10, pady=5)
            self.progress.start()

            # 居中窗口
            self.window.update_idletasks()
            x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
            y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
            self.window.geometry(f"+{x}+{y}")

            # 队列和状态
            self.text_queue = queue.Queue()
            self.is_generating = False
            self.error = None
            self.result_data = None

            # 注意：不在这里启动定时检查
            # 定时器将在 start_generation() 中启动

        def _check_queue(self):
            """定时检查队列并更新UI（主线程）"""
            try:
                while True:
                    msg_type, data = self.text_queue.get_nowait()

                    if msg_type == "text":
                        # 追加文本
                        self.text_widget.config(state=tk.NORMAL)
                        self.text_widget.insert(tk.END, data)
                        self.text_widget.see(tk.END)
                        self.text_widget.config(state=tk.DISABLED)

                    elif msg_type == "status":
                        # 更新状态
                        self.status_label.config(text=data)

                    elif msg_type == "done":
                        # 生成完成
                        self.is_generating = False
                        self.result_data = data
                        self.progress.stop()
                        return

                    elif msg_type == "error":
                        # 发生错误
                        self.error = data
                        self.is_generating = False
                        self.progress.stop()
                        return

            except queue.Empty:
                pass

            # 如果还在生成，继续定时检查（50ms）
            if self.is_generating:
                self.window.after(50, self._check_queue)

        def start_generation(self, heading, ai_writer, requirements, min_words):
            """启动后台生成线程"""
            self.is_generating = True
            self.progress.start()

            def _background_generate():
                """后台线程执行生成"""
                try:
                    self.text_queue.put(("status", "正在生成内容..."))

                    content_parts = []
                    result = ai_writer.expand(
                        heading,
                        requirements,
                        min_words,
                        stream=ai_writer.config.generation_stream
                    )

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
                    self.text_queue.put(("done", (content, word_count)))

                except Exception as e:
                    self.text_queue.put(("error", str(e)))

            # 启动后台线程
            thread = threading.Thread(target=_background_generate, daemon=True)
            thread.start()

            # 启动定时检查队列（在主线程中）
            self._check_queue()

        def wait_completion(self):
            """等待生成完成并返回结果"""
            while self.is_generating:
                self.window.update()
                self.window.after(100)

            if self.error:
                raise Exception(self.error)

            return self.result_data  # (content, word_count)

        def close(self):
            """关闭窗口"""
            self.progress.stop()
            self.window.destroy()

    def _generate_with_preview(self, heading: HeadingNode,
                               additional_requirements: str,
                               min_words: int, auto_save: bool = False) -> str:
        """
        生成内容并预览确认（支持修改重新生成）- 完全异步

        Args:
            auto_save: 是否自动保存，跳过后续确认步骤（批量生成时使用）

        Returns:
            "success" / "skip" / "failed"
        """
        current_requirements = additional_requirements

        while True:
            # 创建生成窗口
            gen_window = self.GenerationWindow(self, heading.title)

            # 启动后台生成
            gen_window.start_generation(
                heading,
                self.bid_writer.ai_writer,
                current_requirements,
                min_words
            )

            # 等待完成（不阻塞，窗口可交互）
            try:
                content, word_count = gen_window.wait_completion()
            except Exception as e:
                gen_window.close()
                # 在状态栏显示错误信息，不弹窗
                self.status_text.set(f"❌ 生成失败: {str(e)[:50]}...")
                return "failed"

            # 关闭生成窗口
            gen_window.close()

            # 批量生成时自动保存，跳过预览对话框
            if auto_save:
                filepath = self.bid_writer.file_saver.save(heading, content)
                # 在状态栏显示保存成功信息
                self.status_text.set(f"✓ 自动保存: {filepath.name}" )
                return "success"

            # 单个生成时显示预览对话框并获取用户操作
            action, modification = self._show_preview_dialog(heading, content, word_count)

            if action == "save":
                filepath = self.bid_writer.file_saver.save(heading, content)
                # 在状态栏显示保存成功信息
                self.status_text.set(f"✓ 文件已保存: {filepath.name}")
                return "success"

            elif action == "modify":
                # 追加修改要求，重新生成
                if modification:
                    current_requirements = f"{current_requirements}\n\n用户修改要求：{modification}"
                continue

            else:  # action == "skip"
                return "skip"

    def _show_preview_dialog(self, heading: HeadingNode, content: str, word_count: int):
        """
        显示预览对话框

        Returns:
            (action, modification) where action is "save"/"modify"/"skip"
        """
        dialog = tk.Toplevel(self)
        dialog.title(f"预览 - {heading.title}")
        dialog.geometry("900x700")
        dialog.transient(self)
        dialog.grab_set()

        result = {"action": "skip", "modification": None}

        # 标题和字数信息
        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(info_frame, text=f"标题：{heading.title}",
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"字数：{word_count} 字",
                 font=('TkDefaultFont', 9)).pack(anchor=tk.W)

        # 内容预览
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.config(yscrollcommand=scrollbar.set)

        text_widget.insert('1.0', content)
        text_widget.config(state=tk.DISABLED)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_save():
            result["action"] = "save"
            dialog.destroy()

        def on_modify():
            # 弹出修改要求输入框
            mod_dialog = tk.Toplevel(dialog)
            mod_dialog.title("输入修改要求")
            mod_dialog.geometry("500x200")
            mod_dialog.transient(dialog)
            mod_dialog.grab_set()

            ttk.Label(mod_dialog, text="请输入修改要求：",
                     font=('TkDefaultFont', 10)).pack(pady=10, padx=20, anchor=tk.W)

            mod_text = tk.Text(mod_dialog, height=5, width=60, font=('Consolas', 10))
            mod_text.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)

            def submit_modification():
                modification = mod_text.get('1.0', tk.END).strip()
                if not modification:
                    messagebox.showwarning("警告", "请输入修改要求")
                    return
                result["action"] = "modify"
                result["modification"] = modification
                mod_dialog.destroy()
                dialog.destroy()

            ttk.Button(mod_dialog, text="确定", command=submit_modification,
                      padding=(15, 8)).pack(pady=10)

            self.wait_window(mod_dialog)

        def on_skip():
            result["action"] = "skip"
            dialog.destroy()

        ttk.Button(button_frame, text="✅ 保存", command=on_save,
                  width=15, padding=(15, 8)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="✏️ 修改后重新生成", command=on_modify,
                  width=20, padding=(15, 8)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="⏭️ 跳过", command=on_skip,
                  width=15, padding=(15, 8)).pack(side=tk.LEFT, padx=5)

        # 等待对话框关闭
        self.wait_window(dialog)

        return result["action"], result["modification"]

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
        self.stats_text.set(f"已生成: {generated} / 总计: {total}")

    def show_help(self):
        """显示帮助"""
        help_text = """使用说明：

1. 在左侧大纲树中选择节点
2. 右侧会显示该节点下的四级标题
3. 使用 Ctrl+点击 多选标题
4. 点击"批量生成"按钮开始生成
5. 生成完成后状态会自动更新

快捷键：
- Ctrl+A: 全选
- Delete: 删除选中
- F5: 刷新状态
"""
        messagebox.showinfo("使用说明", help_text)

    def show_about(self):
        """显示关于"""
        about_text = """自动标书撰写系统（GUI版）

版本：1.0.0
基于：Python + Tkinter
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

    if config_path is None:
        config_path = choose_config_file(initial_path="config.yaml")
        if not config_path:
            return

    bid_writer = BidWriter(config_path)
    app = MainWindow(bid_writer)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
