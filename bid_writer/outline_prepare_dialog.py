"""
大纲准备窗口。
"""

from __future__ import annotations

import inspect
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import Config
from .env_local_prompt import open_file_for_edit, prompt_missing_model_config
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
from .outline_generator import OutlineGenerationError, OutlineGenerator, format_outline_numbering, validate_outline_text
from .outline_prepare import OutlinePrepareError, confirm_outline_and_lock, load_existing_outline
from .ui_icons import configure_icon_button


class OutlinePrepareDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config: Config):
        super().__init__(parent)
        self.config = config
        self.result = {"confirmed": False}
        self._generator_factory = lambda: OutlineGenerator(self.config)
        self._generation_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._generation_in_progress = False
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
        ttk.Label(header, text=f"大纲保存位置 / 已有大纲文件：{self.config.outline_file}", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
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
        load_button = ttk.Button(
            footer,
            text="读取已有大纲",
            command=self._load_existing_outline,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(load_button, self, "outline")
        load_button.grid(row=0, column=0, sticky="w")
        generate_button = ttk.Button(
            footer,
            text="生成大纲",
            command=self._generate_outline,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(generate_button, self, "generate")
        generate_button.grid(row=0, column=1, padx=(8, 0))
        format_button = ttk.Button(
            footer,
            text="格式化大纲",
            command=self._format_current_text,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(format_button, self, "format")
        format_button.grid(row=0, column=2, padx=(8, 0))
        self.confirm_button = ttk.Button(
            footer,
            text="确认大纲并进入扩写",
            command=self._confirm,
            **_bootstyle_kwargs("primary"),
        )
        configure_icon_button(self.confirm_button, self, "next")
        self.confirm_button.grid(row=0, column=3, padx=(8, 0))
        cancel_button = ttk.Button(
            footer,
            text="取消",
            command=self._cancel,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(cancel_button, self, "close")
        cancel_button.grid(row=0, column=4, padx=(8, 0))

    def _set_text(self, value: str) -> None:
        self.outline_text.delete("1.0", tk.END)
        if value:
            self.outline_text.insert("1.0", value)

    def _current_text(self) -> str:
        return self.outline_text.get("1.0", tk.END).strip()

    def _load_existing_outline(self) -> None:
        content = load_existing_outline(self.config)
        self._set_text(content)
        if content.strip():
            self.status_var.set("已读取已有大纲")
            self._validate_current_text()
            return
        self.status_var.set("尚未准备大纲，可点击“生成大纲”或粘贴已有大纲")
        self.validation_var.set("")
        if hasattr(self, "confirm_button"):
            self.confirm_button.configure(state="disabled")

    def _generate_outline(self) -> None:
        if not self._ensure_outline_generation_model_configured():
            return
        self._start_generation()

    def _reload_config_before_env_check(self) -> bool:
        """重新读取配置，让刚保存的 `.env.local` 可以立即参与检查。"""
        try:
            self.config.reload()
        except Exception as exc:
            messagebox.showerror("配置加载失败", f"重新读取配置失败：\n{exc}", parent=self)
            self.status_var.set("配置重新读取失败")
            return False
        return True

    def _ensure_outline_generation_model_configured(self) -> bool:
        """生成大纲前检查大纲/主生成模型连接。"""
        if not self.config.outline_api_key and not self._reload_config_before_env_check():
            return False
        result = prompt_missing_model_config(
            self.config,
            parent=self,
            purpose="outline",
            ask_yes_no=messagebox.askyesno,
            show_error=messagebox.showerror,
            show_warning=messagebox.showwarning,
            open_editor=open_file_for_edit,
        )
        if result.configured:
            return True
        if result.opened:
            self.status_var.set(".env.local 已打开，保存后请重新载入当前配置再生成大纲")
        elif result.created:
            self.status_var.set(".env.local 已准备好，请手动填写模型连接")
        else:
            self.status_var.set("尚未配置模型连接，生成大纲前请填写 .env.local")
        return False

    def _start_generation(self) -> None:
        self.status_var.set("正在生成大纲...")
        self.validation_var.set("")
        if hasattr(self, "confirm_button"):
            self.confirm_button.configure(state="disabled")
        self._set_text("")
        self._generation_in_progress = True
        thread = threading.Thread(target=self._run_generate_outline, daemon=True)
        thread.start()
        self._schedule_generation_poll()

    def _schedule_generation_poll(self) -> None:
        if self._generation_in_progress:
            self.after(50, self._poll_generation_queue)

    def _poll_generation_queue(self) -> None:
        self._drain_generation_queue()
        if self._generation_in_progress:
            self._schedule_generation_poll()

    def _run_generate_outline(self) -> None:
        generator = self._generator_factory()

        def _publish_status(stage: str, message: str) -> None:
            self._generation_queue.put(("status", (stage, message)))

        def _publish_chunk(chunk: str) -> None:
            if chunk:
                self._generation_queue.put(("chunk", chunk))

        generate_kwargs = self._build_generate_kwargs(generator, _publish_status, _publish_chunk)
        try:
            result = generator.generate(**generate_kwargs)
        except OutlineGenerationError as exc:
            self._generation_queue.put(("error", str(exc)))
            return
        self._generation_queue.put(("done", result))

    def _build_generate_kwargs(
        self,
        generator: OutlineGenerator,
        status_callback,
        chunk_callback,
    ) -> dict[str, object]:
        params = inspect.signature(generator.generate).parameters
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())
        kwargs: dict[str, object] = {}
        if accepts_kwargs or "stream" in params:
            kwargs["stream"] = self.config.generation_stream
        if accepts_kwargs or "status_callback" in params:
            kwargs["status_callback"] = status_callback
        if accepts_kwargs or "chunk_callback" in params:
            kwargs["chunk_callback"] = chunk_callback
        return kwargs

    def _drain_generation_queue(self, *, stop_before_done: bool = False) -> None:
        while True:
            try:
                item_type, payload = self._generation_queue.get_nowait()
            except queue.Empty:
                return

            if item_type == "status":
                stage, message = payload
                self._enqueue_status(stage, message)
                continue
            if item_type == "chunk":
                self._append_outline_text(payload)
                continue
            if item_type == "done":
                if stop_before_done:
                    self._generation_queue.put((item_type, payload))
                    return
                self._generation_in_progress = False
                self._apply_generated_outline(payload.outline_text, payload.warnings)
                return
            if item_type == "error":
                self._generation_in_progress = False
                self._show_generation_error(payload)
                return

    def _enqueue_status(self, stage: str, message: str) -> None:
        self.status_var.set(f"{stage}：{message}")

    def _append_outline_text(self, chunk: str) -> None:
        self.outline_text.insert(tk.END, chunk)
        self.outline_text.see(tk.END)

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
        is_valid = not any(item.level == "error" for item in messages)
        if hasattr(self, "confirm_button"):
            self.confirm_button.configure(state="normal" if is_valid else "disabled")
        return is_valid

    def _format_current_text(self) -> bool:
        formatted = format_outline_numbering(self._current_text())
        self._set_text(formatted)
        is_valid = self._validate_current_text()
        self.status_var.set("已格式化大纲编号")
        return is_valid

    def _confirm(self) -> None:
        if not self._format_current_text():
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
        self._generation_in_progress = False
        self.destroy()
