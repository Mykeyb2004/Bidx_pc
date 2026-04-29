"""
大纲准备窗口。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import Config
from .config_editor_dialog import (
    CONFIG_EDITOR_DEFAULT_HEIGHT,
    CONFIG_EDITOR_DEFAULT_WIDTH,
    _bootstyle_kwargs,
    _compute_screen_limited_dialog_size,
    _set_centered_window_geometry,
    apply_window_surface,
    setup_gui_theme,
    style_text_widget,
)
from .outline_generator import OutlineGenerationError, OutlineGenerator, validate_outline_text
from .outline_prepare import OutlinePrepareError, confirm_outline_and_lock, load_existing_outline


class OutlinePrepareDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config: Config):
        super().__init__(parent)
        self.config = config
        self.result = {"confirmed": False}
        self.style = setup_gui_theme(self)
        apply_window_surface(self)
        self.title("大纲准备")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=CONFIG_EDITOR_DEFAULT_WIDTH,
            desired_height=CONFIG_EDITOR_DEFAULT_HEIGHT,
            min_width=900,
            min_height=680,
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        self.status_var = tk.StringVar(value="请准备并确认投标大纲")
        self.validation_var = tk.StringVar(value="")
        self._build_widgets()
        self._load_existing_outline()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="大纲准备", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"大纲文件：{self.config.outline_file}", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        body = ttk.Frame(self, padding=(16, 0, 16, 10))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.outline_text = tk.Text(body, wrap=tk.WORD)
        style_text_widget(self.outline_text)
        y_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.outline_text.yview)
        self.outline_text.configure(yscrollcommand=y_scroll.set)
        self.outline_text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")

        validation = ttk.Label(
            body,
            textvariable=self.validation_var,
            justify=tk.LEFT,
            wraplength=900,
            style="Muted.TLabel",
        )
        validation.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(
            footer,
            text="读取已有大纲",
            command=self._load_existing_outline,
            **_bootstyle_kwargs("secondary"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            footer,
            text="生成大纲",
            command=self._generate_outline,
            **_bootstyle_kwargs("secondary"),
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            footer,
            text="确认大纲并进入扩写",
            command=self._confirm,
            **_bootstyle_kwargs("primary"),
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(
            footer,
            text="取消",
            command=self._cancel,
            **_bootstyle_kwargs("secondary"),
        ).grid(row=0, column=3, padx=(8, 0))

    def _set_text(self, value: str) -> None:
        self.outline_text.delete("1.0", tk.END)
        self.outline_text.insert("1.0", value or "")

    def _current_text(self) -> str:
        return self.outline_text.get("1.0", tk.END).strip()

    def _load_existing_outline(self) -> None:
        content = load_existing_outline(self.config)
        self._set_text(content)
        self.status_var.set("已读取已有大纲" if content.strip() else "当前大纲文件不存在或为空")
        self._validate_current_text()

    def _generate_outline(self) -> None:
        self.status_var.set("正在生成大纲...")
        thread = threading.Thread(target=self._run_generate_outline, daemon=True)
        thread.start()

    def _run_generate_outline(self) -> None:
        try:
            result = OutlineGenerator(self.config).generate()
        except OutlineGenerationError as exc:
            self.after(0, lambda: self._show_generation_error(str(exc)))
            return
        self.after(0, lambda: self._apply_generated_outline(result.outline_text, result.warnings))

    def _show_generation_error(self, message: str) -> None:
        self.status_var.set("大纲生成失败")
        messagebox.showerror("大纲生成失败", message, parent=self)

    def _apply_generated_outline(self, outline_text: str, warnings: list[str]) -> None:
        self._set_text(outline_text)
        self.status_var.set("大纲生成完成")
        self.validation_var.set("\n".join(warnings))
        self._validate_current_text()

    def _validate_current_text(self) -> bool:
        messages = validate_outline_text(self._current_text())
        prefix = {"error": "[错误]", "warning": "[警告]", "info": "[信息]"}
        self.validation_var.set("\n".join(f"{prefix.get(item.level, '[信息]')} {item.text}" for item in messages))
        return not any(item.level == "error" for item in messages)

    def _confirm(self) -> None:
        if not self._validate_current_text():
            messagebox.showerror("大纲校验失败", self.validation_var.get(), parent=self)
            return
        try:
            confirm_outline_and_lock(self.config, self._current_text())
        except OutlinePrepareError as exc:
            messagebox.showerror("保存大纲失败", str(exc), parent=self)
            return
        self.result["confirmed"] = True
        self.status_var.set("大纲已确认")
        self.destroy()

    def _cancel(self) -> None:
        self.result["confirmed"] = False
        self.destroy()
