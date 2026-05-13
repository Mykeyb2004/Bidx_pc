from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from bid_writer.gui import (
    _activate_window,
    _bootstyle_kwargs,
    _compute_screen_limited_dialog_size,
    _set_centered_window_geometry,
    apply_window_surface,
    setup_gui_theme,
)
from bid_writer.config_editor_tooltips import get_tooltip_text
from bid_writer.hover_tooltip import HoverTooltip
from bid_writer.new_config_flow import (
    NewConfigWizardState,
    build_editor_document_from_state,
    build_initial_state_from_source,
    build_manual_state,
    cleanup_created_paths,
    copy_source_file_if_needed,
    register_created_path,
    should_copy_source_file,
)
from bid_writer.tender_import_dialog import confirm_tender_sections
from bid_writer.tender_import_service import TenderImportError, TenderImportResult, TenderImportService
from bid_writer.ui_icons import configure_icon_button


SUPPORTED_TENDER_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls"}


def _has_visible_parent(parent: tk.Misc | None) -> bool:
    """Return whether a dialog should be transient for its parent window."""
    if parent is None:
        return False

    try:
        return bool(parent.winfo_exists()) and parent.state() != "withdrawn"
    except (AttributeError, tk.TclError):
        return False


@dataclass(frozen=True)
class WizardStep:
    key: str
    title: str


@dataclass(frozen=True)
class _ImportJob:
    state: NewConfigWizardState
    existing_paths: set[Path]


@dataclass
class _ImportUiRequest:
    callback: Callable[[], object]
    event: threading.Event
    result: object | None = None
    error: BaseException | None = None


@dataclass(frozen=True)
class _ImportWorkerOutcome:
    job: _ImportJob
    result: TenderImportResult | None = None
    error: BaseException | None = None


WIZARD_STEPS = [
    WizardStep("source", "选择起点"),
    WizardStep("location", "项目位置"),
    WizardStep("materials", "资料整理"),
    WizardStep("basics", "基础设置"),
    WizardStep("review", "保存确认"),
]


class NewConfigWizardDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config_path: str | Path | None = None):
        super().__init__(parent)
        self.parent_window = parent
        self.style = setup_gui_theme(self)
        apply_window_surface(self)

        initial_config_path = Path(config_path or "config_新项目.yaml").expanduser().resolve()
        self.result: dict[str, Path | None] = {"saved_path": None, "apply_path": None}
        self.current_step_index = 0
        self.max_completed_step_index = 0
        self._import_in_progress = False
        self._import_ui_requests: queue.Queue[_ImportUiRequest] = queue.Queue()
        self._import_result_queue: queue.Queue[_ImportWorkerOutcome] = queue.Queue()
        self._import_poll_after_id: str | None = None
        self._tooltips: list[HoverTooltip] = []
        self.state = build_manual_state(
            project_root=initial_config_path.parent,
            config_path=initial_config_path,
        )

        self.step_buttons: list[ttk.Button] = []
        self.step_frames: dict[str, ttk.Frame] = {}
        self.vars = self._create_vars()
        self.vars["outline_source"].trace_add("write", lambda *_: self._sync_outline_source_ui())
        self.status_var = tk.StringVar(value="")
        self.config_summary_var = tk.StringVar(value="")
        self.source_hint_var = tk.StringVar(value="")
        self.import_status_var = tk.StringVar(value="")
        self.review_summary_var = tk.StringVar(value="")
        self.step_state_vars = [tk.StringVar(value="") for _ in WIZARD_STEPS]
        self.outline_path_label_var = tk.StringVar(value="大纲保存位置")
        self.outline_path_action_var = tk.StringVar(value="选择保存位置...")
        self.outline_path_hint_var = tk.StringVar(
            value="可以先不创建文件；进入大纲准备窗口后会在此位置生成大纲。"
        )
        self._sync_fields_from_state()

        self.title("新建配置向导")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=900,
            desired_height=620,
            min_width=760,
            min_height=520,
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        if _has_visible_parent(parent):
            self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._show_step()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._show_dialog()

    def _show_dialog(self) -> None:
        """Make the wizard visible even when launched from a hidden startup root."""
        _activate_window(self)

    def _create_vars(self) -> dict[str, tk.StringVar]:
        return {
            "source_path": tk.StringVar(value=""),
            "project_root": tk.StringVar(value=""),
            "config_path": tk.StringVar(value=""),
            "requirements_path": tk.StringVar(value=""),
            "scoring_path": tk.StringVar(value=""),
            "outline_source": tk.StringVar(value="generate"),
            "outline_path": tk.StringVar(value=""),
            "output_dir": tk.StringVar(value=""),
            "bidder_name": tk.StringVar(value=""),
        }

    def _create_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="新建配置向导", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            textvariable=self.config_summary_var,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ttk.Frame(self, padding=(16, 0, 16, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(body, padding=(0, 0, 12, 0))
        sidebar.grid(row=0, column=0, sticky="ns")
        ttk.Label(sidebar, text="步骤", style="SummaryLabel.TLabel").pack(anchor="w", pady=(0, 10))
        for index, step in enumerate(WIZARD_STEPS):
            row = ttk.Frame(sidebar)
            row.pack(fill=tk.X, pady=4)
            button = ttk.Button(
                row,
                text=f"{index + 1}. {step.title}",
                command=lambda step_index=index: self._jump_to_step(step_index),
                **_bootstyle_kwargs("secondary"),
            )
            configure_icon_button(button, self, "outline")
            button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._register_tooltip(button, f"new_config.step.{step.key}")
            state_label = ttk.Label(row, textvariable=self.step_state_vars[index], style="Muted.TLabel", width=8, anchor="e")
            state_label.pack(side=tk.RIGHT, padx=(8, 0))
            self.step_buttons.append(button)

        self.content_container = ttk.Frame(body)
        self.content_container.grid(row=0, column=1, sticky="nsew")
        self.content_container.rowconfigure(0, weight=1)
        self.content_container.columnconfigure(0, weight=1)

        self._build_source_step()
        self._build_location_step()
        self._build_materials_step()
        self._build_basics_step()
        self._build_review_step()

        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        actions = ttk.Frame(footer)
        actions.grid(row=0, column=1, sticky="e")
        self.back_button = ttk.Button(
            actions,
            text="上一步",
            command=self._go_back,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(self.back_button, self, "back")
        self.back_button.pack(side=tk.LEFT, padx=(0, 8))
        self._register_tooltip(self.back_button, "new_config.footer.back")
        self.next_button = ttk.Button(
            actions,
            text="下一步",
            command=self._go_next,
            **_bootstyle_kwargs("primary"),
        )
        configure_icon_button(self.next_button, self, "next")
        self.next_button.pack(side=tk.LEFT, padx=(0, 8))
        self._register_tooltip(self.next_button, "new_config.footer.next")
        cancel_button = ttk.Button(
            actions,
            text="取消",
            command=self._cancel,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(cancel_button, self, "close")
        cancel_button.pack(side=tk.LEFT)
        self._register_tooltip(cancel_button, "new_config.footer.cancel")

    def _create_step_frame(self, key: str, title: str, description: str) -> ttk.Frame:
        frame = ttk.Frame(self.content_container, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="Muted.TLabel", wraplength=640, justify=tk.LEFT).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        self.step_frames[key] = frame
        return frame

    def _build_source_step(self) -> None:
        frame = self._create_step_frame(
            "source",
            "选择起点",
            "先选招标文件开始，系统会自动推导项目位置；也可以直接走手动创建，后续再补资料文件。",
        )
        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        controls.columnconfigure(0, weight=1)
        choice_row = ttk.Frame(controls)
        choice_row.grid(row=0, column=0, sticky="ew")
        choice_row.columnconfigure(0, weight=1)
        choice_row.columnconfigure(1, weight=1)

        import_card = ttk.LabelFrame(choice_row, text="从招标文件开始", padding=(12, 10))
        import_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        import_card.columnconfigure(0, weight=1)
        ttk.Label(
            import_card,
            text="适合你手上已经有招标文件，希望系统帮你推导项目目录并自动整理资料。",
            style="Muted.TLabel",
            wraplength=280,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="w")
        source_entry = ttk.Entry(import_card, textvariable=self.vars["source_path"])
        source_entry.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        self._register_tooltip(source_entry, "new_config.source_path")
        select_source_button = ttk.Button(
            import_card,
            text="选择招标文件...",
            command=self._select_source_file,
            **_bootstyle_kwargs("primary"),
        )
        configure_icon_button(select_source_button, self, "import")
        select_source_button.grid(row=2, column=0, sticky="w")
        self._register_tooltip(select_source_button, "new_config.source.select_file")

        manual_card = ttk.LabelFrame(choice_row, text="直接手动创建", padding=(12, 10))
        manual_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        manual_card.columnconfigure(0, weight=1)
        ttk.Label(
            manual_card,
            text="适合先建立项目骨架，再手动指定采购需求、评分标准和大纲文件。",
            style="Muted.TLabel",
            wraplength=280,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="w")
        manual_button = ttk.Button(
            manual_card,
            text="进入手动创建",
            command=self._skip_source_selection,
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(manual_button, self, "add")
        manual_button.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._register_tooltip(manual_button, "new_config.source.manual_create")
        ttk.Label(controls, textvariable=self.source_hint_var, style="Muted.TLabel", wraplength=620, justify=tk.LEFT).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )

    def _build_location_step(self) -> None:
        frame = self._create_step_frame("location", "项目位置", "确认系统推导出的项目根目录和配置文件保存位置。")
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        self._add_path_row(form, 0, "项目根目录", "project_root", browse_kind="dir", tooltip_key="new_config.location.project_root")
        self._add_path_row(form, 1, "配置文件保存位置", "config_path", browse_kind="file", tooltip_key="new_config.location.config_path")

    def _build_materials_step(self) -> None:
        frame = self._create_step_frame(
            "materials",
            "资料整理",
            "可以先自动抽取采购需求和评分标准；如果不导入，也可以直接指定已有文件。",
        )
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        self.import_button = ttk.Button(
            form,
            text="开始抽取",
            command=self._run_import,
            **_bootstyle_kwargs("primary"),
        )
        configure_icon_button(self.import_button, self, "scan")
        self.import_button.grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._register_tooltip(self.import_button, "new_config.materials.import")
        ttk.Label(form, textvariable=self.import_status_var, style="Muted.TLabel", wraplength=620, justify=tk.LEFT).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 10),
        )
        self._add_path_row(form, 1, "采购需求文件", "requirements_path", browse_kind="file", tooltip_key="new_config.materials.requirements")
        self._add_path_row(form, 2, "评分标准文件", "scoring_path", browse_kind="file", tooltip_key="new_config.materials.scoring")

    def _build_basics_step(self) -> None:
        frame = self._create_step_frame("basics", "基础设置", "填写投标主体、大纲来源和输出目录。")
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        bidder_box = ttk.LabelFrame(form, text="投标主体", padding=(12, 10))
        bidder_box.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        bidder_box.columnconfigure(1, weight=1)
        self._add_entry_row(bidder_box, 0, "投标主体名称", "bidder_name", tooltip_key="new_config.basics.bidder_name")

        source_box = ttk.LabelFrame(form, text="大纲来源", padding=(12, 10))
        source_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        source_box.columnconfigure(1, weight=1)

        existing_radio = ttk.Radiobutton(
            source_box,
            text="已有 Markdown 大纲",
            value="existing",
            variable=self.vars["outline_source"],
        )
        existing_radio.grid(row=0, column=0, sticky="w")
        self._register_tooltip(existing_radio, "new_config.basics.outline_source.existing")
        ttk.Label(
            source_box,
            text="选择一个已经存在的 .md 大纲文件，系统会直接读取它。",
            style="Muted.TLabel",
            wraplength=540,
            justify=tk.LEFT,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        generate_radio = ttk.Radiobutton(
            source_box,
            text="生成后保存",
            value="generate",
            variable=self.vars["outline_source"],
        )
        generate_radio.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._register_tooltip(generate_radio, "new_config.basics.outline_source.generate")
        ttk.Label(
            source_box,
            text="先保留保存位置，后续在大纲准备窗口生成完毕后写入这里。",
            style="Muted.TLabel",
            wraplength=540,
            justify=tk.LEFT,
        ).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

        outline_box = ttk.LabelFrame(form, text="大纲文件与输出", padding=(12, 10))
        outline_box.grid(row=2, column=0, columnspan=3, sticky="ew")
        outline_box.columnconfigure(1, weight=1)
        self._add_outline_path_row(outline_box, 0, tooltip_key="new_config.basics.outline_path")
        self._add_path_row(outline_box, 2, "输出目录", "output_dir", browse_kind="dir", tooltip_key="new_config.basics.output_dir")

    def _build_review_step(self) -> None:
        frame = self._create_step_frame("review", "保存确认", "保存前再核对一次配置摘要，确认后将切换到新配置。")
        ttk.Label(
            frame,
            textvariable=self.review_summary_var,
            style="Muted.TLabel",
            wraplength=680,
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky="ew", pady=(18, 0))

    def _add_entry_row(self, parent: tk.Misc, row: int, label: str, key: str, *, tooltip_key: str | None = None) -> ttk.Entry:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
        entry = ttk.Entry(parent, textvariable=self.vars[key])
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        if tooltip_key is not None:
            self._register_tooltip(label_widget, tooltip_key)
            self._register_tooltip(entry, tooltip_key)
        return entry

    def _add_path_row(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        key: str,
        *,
        browse_kind: str,
        tooltip_key: str | None = None,
    ) -> ttk.Entry:
        entry = self._add_entry_row(parent, row, label, key, tooltip_key=tooltip_key)
        browse_button = ttk.Button(
            parent,
            text="选择...",
            command=lambda: self._browse_path(key, browse_kind),
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(browse_button, self, "browse")
        browse_button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=6)
        if tooltip_key is not None:
            self._register_tooltip(browse_button, tooltip_key)
        return entry

    def _add_outline_path_row(self, parent: tk.Misc, row: int, *, tooltip_key: str | None = None) -> ttk.Entry:
        label_widget = ttk.Label(parent, textvariable=self.outline_path_label_var)
        label_widget.grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=6,
        )
        entry = ttk.Entry(parent, textvariable=self.vars["outline_path"])
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        outline_button = ttk.Button(
            parent,
            textvariable=self.outline_path_action_var,
            command=lambda: self._browse_path("outline_path", "outline"),
            **_bootstyle_kwargs("secondary"),
        )
        configure_icon_button(outline_button, self, "browse")
        outline_button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=6)
        ttk.Label(
            parent,
            textvariable=self.outline_path_hint_var,
            style="Muted.TLabel",
            wraplength=620,
            justify=tk.LEFT,
        ).grid(row=row + 1, column=0, columnspan=3, sticky="ew", padx=(0, 0), pady=(0, 6))
        if tooltip_key is not None:
            self._register_tooltip(label_widget, tooltip_key)
            self._register_tooltip(entry, tooltip_key)
            self._register_tooltip(outline_button, tooltip_key)
        return entry

    def _go_next(self) -> None:
        if self.current_step_index >= len(WIZARD_STEPS) - 1:
            self._save_and_apply()
            return

        if not self._validate_current_step():
            return

        self.current_step_index += 1
        self.max_completed_step_index = max(self.max_completed_step_index, self.current_step_index)
        self._show_step()

    def _go_back(self) -> None:
        if self.current_step_index <= 0:
            return
        self.current_step_index -= 1
        self._show_step()

    def _jump_to_step(self, index: int) -> None:
        if index < 0 or index >= len(WIZARD_STEPS):
            return
        if index > self.max_completed_step_index:
            return
        if index > self.current_step_index and not self._validate_current_step():
            return
        self.current_step_index = index
        self._show_step()

    def _validate_current_step(self) -> bool:
        try:
            self._sync_state_from_fields()
        except ValueError as exc:
            messagebox.showerror("路径无效", str(exc), parent=self)
            return False

        step_key = WIZARD_STEPS[self.current_step_index].key
        if step_key == "source":
            source_value = self.vars["source_path"].get().strip()
            if source_value:
                source_path = Path(source_value).expanduser()
                if not source_path.exists():
                    messagebox.showerror("文件不存在", f"招标文件不存在：{source_path}", parent=self)
                    return False
                if source_path.suffix.lower() not in SUPPORTED_TENDER_SUFFIXES:
                    messagebox.showwarning("格式可能不支持", f"当前文件格式可能无法自动抽取：{source_path.suffix or '无扩展名'}", parent=self)
            return True

        if step_key == "location":
            if not self.state.project_root:
                messagebox.showerror("路径无效", "项目根目录不能为空。", parent=self)
                return False
            if not self.state.config_path.name:
                messagebox.showerror("路径无效", "配置文件保存位置不能为空。", parent=self)
                return False
            return True

        if step_key == "materials":
            missing = []
            for label, path in (("采购需求文件", self.state.requirements_path), ("评分标准文件", self.state.scoring_path)):
                if path is None:
                    missing.append(f"{label}不能为空。")
                elif not path.exists():
                    missing.append(f"{label}不存在：{path}")
            if missing:
                messagebox.showerror("资料不完整", "\n".join(missing), parent=self)
                return False
            return True

        if step_key == "basics":
            if not self.state.bidder_name:
                messagebox.showerror("基本信息不完整", "请填写投标主体名称。", parent=self)
                return False
            outline_source = self.vars["outline_source"].get().strip() or "generate"
            if outline_source == "existing" and not self.state.outline_path.exists():
                messagebox.showerror(
                    "大纲文件不存在",
                    f"大纲文件不存在，请选择一个已存在的 Markdown 大纲文件：{self.state.outline_path}",
                    parent=self,
                )
                return False
            return True

        return True

    def _show_step(self) -> None:
        self._sync_state_from_fields(silent=True)
        step = WIZARD_STEPS[self.current_step_index]
        if step.key == "review":
            self._sync_review_summary()
        self.step_frames[step.key].tkraise()
        self._sync_footer()

    def _sync_footer(self) -> None:
        total_steps = len(WIZARD_STEPS)
        step_number = self.current_step_index + 1
        self.status_var.set(f"第 {step_number} 步，共 {total_steps} 步")
        if getattr(self, "_import_in_progress", False):
            self.back_button.configure(state=tk.DISABLED)
            self.next_button.configure(state=tk.DISABLED)
            for button in self.step_buttons:
                button.configure(state=tk.DISABLED)
            return

        self.back_button.configure(state=tk.DISABLED if self.current_step_index == 0 else tk.NORMAL)
        next_text = "保存并应用" if self.current_step_index == total_steps - 1 else "下一步"
        self.next_button.configure(text=next_text, state=tk.NORMAL)

        for index, button in enumerate(self.step_buttons):
            state = tk.NORMAL if index <= self.max_completed_step_index else tk.DISABLED
            button.configure(state=state)
        for index, state_var in enumerate(getattr(self, "step_state_vars", [])):
            if index < self.current_step_index:
                state_var.set("已完成")
            elif index == self.current_step_index:
                state_var.set("当前")
            else:
                state_var.set("已完成" if index <= self.max_completed_step_index else "未开始")

    def _save_and_apply(self) -> None:
        try:
            self._sync_state_from_fields()
            self.state.project_root.mkdir(parents=True, exist_ok=True)
            self.state.config_path.parent.mkdir(parents=True, exist_ok=True)
            document = build_editor_document_from_state(self.state)
            messages = document.validate(document.model, config_path=self.state.config_path)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return

        errors = [item.text for item in messages if item.level == "error"]
        if errors:
            messagebox.showerror("校验失败", "\n".join(errors), parent=self)
            return

        try:
            saved_path = document.save(document.model, target_path=self.state.config_path, create_backup=True)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return

        self.result["saved_path"] = saved_path
        self.result["apply_path"] = saved_path
        self.destroy()

    def _cancel(self) -> None:
        if getattr(self, "_import_in_progress", False):
            messagebox.showwarning("正在抽取", "招标文件正在转换和抽取，请等待完成后再关闭向导。", parent=self)
            return
        if self.state.created_paths:
            choice = messagebox.askyesnocancel(
                "取消新建配置",
                "本次向导已经生成了一些资料。选择“是”保留资料，选择“否”清理本次生成内容，选择“取消”返回向导。",
                parent=self,
            )
            if choice is None:
                return
            if choice is False:
                failures = cleanup_created_paths(self.state)
                if failures:
                    message = "\n".join(f"{path}: {reason}" for path, reason in failures)
                    messagebox.showerror("清理失败", message, parent=self)
                    return
        self.destroy()

    def _sync_fields_from_state(self) -> None:
        self.vars["source_path"].set("" if self.state.source_path is None else str(self.state.source_path))
        self.vars["project_root"].set(str(self.state.project_root))
        self.vars["config_path"].set(str(self.state.config_path))
        self.vars["requirements_path"].set("" if self.state.requirements_path is None else str(self.state.requirements_path))
        self.vars["scoring_path"].set("" if self.state.scoring_path is None else str(self.state.scoring_path))
        self.vars["outline_source"].set(getattr(self.state, "outline_source", self.vars["outline_source"].get() or "generate"))
        self.vars["outline_path"].set(str(self.state.outline_path))
        self.vars["output_dir"].set(str(self.state.output_dir))
        self.vars["bidder_name"].set(self.state.bidder_name)
        if hasattr(self, "config_summary_var"):
            self.config_summary_var.set(f"目标配置：{self.state.config_path}")
        self._sync_outline_source_ui()
        self._sync_source_hint()

    def _sync_state_from_fields(self, *, silent: bool = False) -> None:
        previous_project_root = self.state.project_root
        try:
            source_value = self.vars["source_path"].get().strip()
            source_path = Path(source_value).expanduser().resolve() if source_value else None
            project_root = self._path_from_var("project_root")
            config_path = self._path_from_var("config_path")
            requirements_path = self._optional_path_from_var("requirements_path")
            scoring_path = self._optional_path_from_var("scoring_path")
            outline_path = self._path_from_var("outline_path")
            output_dir = self._path_from_var("output_dir")
        except RuntimeError as exc:
            if silent:
                return
            raise ValueError(str(exc)) from exc

        self.state.source_path = source_path
        self.state.project_root = project_root
        self.state.config_path = config_path
        requirements_path, scoring_path = self._rebase_default_material_paths(
            previous_project_root=previous_project_root,
            project_root=project_root,
            requirements_path=requirements_path,
            scoring_path=scoring_path,
        )
        self.state.requirements_path = requirements_path
        self.state.scoring_path = scoring_path
        self.state.outline_path = outline_path
        self.state.output_dir = output_dir
        self.state.bidder_name = self.vars["bidder_name"].get().strip()
        if self.state.source_path is not None:
            self.state.should_copy_source = should_copy_source_file(self.state.source_path, self.state.project_root)
            self.state.source_copy_path = (
                self.state.project_root / "招标文件" / self.state.source_path.name
                if self.state.should_copy_source
                else None
            )
        self.state.import_dir = (
            self.state.project_root / ".bid_writer" / "imports" / "pending"
            if self.state.source_path is not None
            else None
        )
        self._sync_outline_source_ui()
        self._sync_source_hint()

    def _rebase_default_material_paths(
        self,
        *,
        previous_project_root: Path,
        project_root: Path,
        requirements_path: Path | None,
        scoring_path: Path | None,
    ) -> tuple[Path | None, Path | None]:
        if previous_project_root == project_root:
            return requirements_path, scoring_path

        old_requirements = previous_project_root / "项目要求" / "项目采购需求.md"
        old_scoring = previous_project_root / "项目要求" / "评分标准.md"
        new_requirements = project_root / "项目要求" / "项目采购需求.md"
        new_scoring = project_root / "项目要求" / "评分标准.md"

        if requirements_path == old_requirements:
            requirements_path = new_requirements
            self.vars["requirements_path"].set(str(new_requirements))
        if scoring_path == old_scoring:
            scoring_path = new_scoring
            self.vars["scoring_path"].set(str(new_scoring))
        return requirements_path, scoring_path

    def _path_from_var(self, key: str) -> Path:
        raw = self.vars[key].get().strip()
        if not raw:
            raise RuntimeError(f"{key} 不能为空。")
        return Path(raw).expanduser().resolve()

    def _optional_path_from_var(self, key: str) -> Path | None:
        raw = self.vars[key].get().strip()
        return Path(raw).expanduser().resolve() if raw else None

    def _sync_source_hint(self) -> None:
        if not hasattr(self, "source_hint_var"):
            return
        if self.state.source_path is None:
            self.source_hint_var.set("未选择招标文件时，将直接进入手动创建流程，按你指定的资料路径创建配置。")
            return
        if self.state.should_copy_source and self.state.source_copy_path is not None:
            self.source_hint_var.set(f"招标文件位于项目外，导入时将复制到：{self.state.source_copy_path}")
        else:
            self.source_hint_var.set("招标文件已位于项目目录内，不会重复复制。")

    def _sync_outline_source_ui(self) -> None:
        if not hasattr(self, "vars") or "outline_source" not in self.vars:
            return

        outline_source = self.vars["outline_source"].get().strip() or "generate"
        if outline_source not in {"existing", "generate"}:
            outline_source = "generate"
            self.vars["outline_source"].set(outline_source)

        if not hasattr(self, "outline_path_label_var") or not hasattr(self, "outline_path_action_var") or not hasattr(self, "outline_path_hint_var"):
            return

        if outline_source == "existing":
            self.outline_path_label_var.set("已有大纲文件")
            self.outline_path_action_var.set("选择已有大纲...")
            self.outline_path_hint_var.set(
                "选择一个已经存在的 Markdown 大纲文件，保存后系统会直接读取它。"
            )
        else:
            self.outline_path_label_var.set("大纲保存位置")
            self.outline_path_action_var.set("选择保存位置...")
            self.outline_path_hint_var.set(
                "可以先不创建文件；生成完毕后再进入大纲准备窗口时，会在此位置写入大纲。"
            )

    def _sync_review_summary(self) -> None:
        if not hasattr(self, "review_summary_var"):
            return
        created = "\n".join(f"- {path}" for path in self.state.created_paths) or "- 暂无"
        outline_source = self.vars["outline_source"].get().strip() or "generate"
        outline_source_text = "已有 Markdown 大纲" if outline_source == "existing" else "生成后保存"
        self.review_summary_var.set(
            "\n".join(
                [
                    f"配置文件：{self.state.config_path}",
                    f"项目根目录：{self.state.project_root}",
                    f"大纲来源：{outline_source_text}",
                    f"采购需求：{self.state.requirements_path or '未填写'}",
                    f"评分标准：{self.state.scoring_path or '未填写'}",
                    f"投标大纲：{self.state.outline_path}",
                    f"输出目录：{self.state.output_dir}",
                    "可清理的本次生成内容：",
                    created,
                ]
            )
        )

    def _register_tooltip(self, widget: tk.Misc, key: str) -> None:
        text = get_tooltip_text(key)
        if not text:
            return
        self._tooltips.append(HoverTooltip(widget, text))

    def _skip_source_selection(self) -> None:
        self.vars["source_path"].set("")
        self.state.source_path = None
        self.state.import_dir = None
        self.state.should_copy_source = False
        self.state.source_copy_path = None
        self.state.manual_inputs = True
        self.vars["outline_source"].set("generate")
        self.current_step_index = 1
        self.max_completed_step_index = max(self.max_completed_step_index, 1)
        self._sync_fields_from_state()
        self._show_step()

    def _select_source_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择招标文件",
            filetypes=[
                ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx *.doc"),
                ("Excel", "*.xlsx *.xls"),
                ("全部文件", "*.*"),
            ],
        )
        if not selected:
            return

        selected_path = Path(selected).expanduser().resolve()
        if selected_path.suffix.lower() not in SUPPORTED_TENDER_SUFFIXES:
            if not messagebox.askyesno(
                "格式可能不支持",
                f"当前文件格式可能无法自动抽取：{selected_path.suffix or '无扩展名'}。是否仍继续？",
                parent=self,
            ):
                return

        self.state = build_initial_state_from_source(selected_path, current_config_path=self.state.config_path)
        self._sync_fields_from_state()
        self.current_step_index = 1
        self.max_completed_step_index = max(self.max_completed_step_index, 1)
        self._show_step()

    def _browse_path(self, key: str, browse_kind: str) -> None:
        current_value = self.vars[key].get().strip()
        initial = Path(current_value).expanduser() if current_value else self.state.project_root
        initial_dir = initial.parent if initial.suffix else initial
        if browse_kind == "dir":
            selected = filedialog.askdirectory(parent=self, initialdir=str(initial_dir))
        elif browse_kind == "outline":
            outline_source = self.vars["outline_source"].get().strip() or "generate"
            if outline_source == "existing":
                selected = filedialog.askopenfilename(
                    parent=self,
                    title="选择已有 Markdown 大纲",
                    initialdir=str(initial_dir),
                    filetypes=[
                        ("Markdown", "*.md"),
                        ("全部文件", "*.*"),
                    ],
                )
            else:
                selected = filedialog.asksaveasfilename(
                    parent=self,
                    title="选择大纲保存位置",
                    initialdir=str(initial_dir),
                    initialfile=Path(current_value).name if current_value else "投标大纲.md",
                    defaultextension=".md",
                    filetypes=[
                        ("Markdown", "*.md"),
                        ("全部文件", "*.*"),
                    ],
                )
        else:
            selected = filedialog.askopenfilename(parent=self, initialdir=str(initial_dir))
        if selected:
            self.vars[key].set(str(Path(selected).expanduser().resolve()))

    def _run_import(self) -> None:
        if getattr(self, "_import_in_progress", False):
            messagebox.showinfo("正在抽取", "招标文件正在转换和抽取，请稍候。", parent=self)
            return

        self._sync_state_from_fields()
        if self.state.source_path is None:
            messagebox.showwarning("缺少招标文件", "请先选择招标文件，或手动选择采购需求和评分标准文件。", parent=self)
            return

        self.state.project_root.mkdir(parents=True, exist_ok=True)
        existing_paths = self._snapshot_existing_import_paths()
        job = _ImportJob(state=self._snapshot_import_state(), existing_paths=existing_paths)
        self._import_ui_requests = queue.Queue()
        self._import_result_queue = queue.Queue()
        self._set_import_in_progress(True)
        self.import_status_var.set("正在转换和抽取招标文件，请稍候...")
        self._start_import_worker(job)

    def _snapshot_import_state(self) -> NewConfigWizardState:
        return NewConfigWizardState(
            source_path=self.state.source_path,
            project_root=self.state.project_root,
            config_path=self.state.config_path,
            import_dir=self.state.import_dir,
            should_copy_source=self.state.should_copy_source,
            source_copy_path=self.state.source_copy_path,
            copied_source_path=self.state.copied_source_path,
            requirements_path=self.state.requirements_path,
            scoring_path=self.state.scoring_path,
            outline_path=self.state.outline_path,
            output_dir=self.state.output_dir,
            bidder_name=self.state.bidder_name,
            created_paths=list(getattr(self.state, "created_paths", [])),
            manual_inputs=self.state.manual_inputs,
        )

    def _start_import_worker(self, job: _ImportJob) -> None:
        threading.Thread(target=lambda: self._run_import_worker(job), daemon=True).start()
        self._schedule_import_poll()

    def _run_import_worker(self, job: _ImportJob) -> None:
        try:
            copy_source_file_if_needed(job.state)
            result = TenderImportService().import_document(
                source_path=job.state.source_path,
                project_root=job.state.project_root,
                import_dir=job.state.import_dir,
                confirm_overwrite=lambda path: self._run_on_import_ui(lambda: self._confirm_overwrite(path)),
                confirm_sections=lambda **kwargs: self._run_on_import_ui(
                    lambda: confirm_tender_sections(self, **kwargs)
                ),
            )
            outcome = _ImportWorkerOutcome(job=job, result=result)
        except TenderImportError as exc:
            outcome = _ImportWorkerOutcome(job=job, error=exc)
        except Exception as exc:
            outcome = _ImportWorkerOutcome(job=job, error=exc)
        self._import_result_queue.put(outcome)

    def _run_on_import_ui(self, callback: Callable[[], object]) -> object:
        if threading.current_thread() is threading.main_thread():
            return callback()
        request = _ImportUiRequest(callback=callback, event=threading.Event())
        self._import_ui_requests.put(request)
        request.event.wait()
        if request.error is not None:
            raise request.error
        return request.result

    def _schedule_import_poll(self) -> None:
        try:
            self._import_poll_after_id = self.after(50, self._poll_import_queues)
        except (AttributeError, tk.TclError):
            self._import_poll_after_id = None

    def _poll_import_queues(self) -> None:
        self._drain_import_ui_requests()
        try:
            outcome = self._import_result_queue.get_nowait()
        except queue.Empty:
            if getattr(self, "_import_in_progress", False):
                self._schedule_import_poll()
            return

        self._finish_import(outcome)

    def _drain_import_ui_requests(self) -> None:
        while True:
            try:
                request = self._import_ui_requests.get_nowait()
            except queue.Empty:
                return
            try:
                request.result = request.callback()
            except BaseException as exc:
                request.error = exc
            finally:
                request.event.set()

    def _finish_import(self, outcome: _ImportWorkerOutcome) -> None:
        self._adopt_import_worker_state(outcome.job.state)
        self._set_import_in_progress(False)
        if outcome.error is not None:
            self.import_status_var.set("导入失败，可手动填写资料文件。")
            if isinstance(outcome.error, TenderImportError):
                messagebox.showerror("导入失败", str(outcome.error), parent=self)
            else:
                messagebox.showerror(
                    "导入失败",
                    f"{type(outcome.error).__name__}: {outcome.error}",
                    parent=self,
                )
            return

        result = outcome.result
        if result is None:
            self.import_status_var.set("导入失败，可手动填写资料文件。")
            messagebox.showerror("导入失败", "导入服务未返回结果。", parent=self)
            return

        self._register_new_created_paths(result.created_paths, outcome.job.existing_paths)
        if result.cancelled:
            self.state.requirements_path = None
            self.state.scoring_path = None
            self._sync_fields_from_state()
            self.import_status_var.set("已取消确认，未完成资料写入。")
            return

        self.state.requirements_path = result.requirements_path
        self.state.scoring_path = result.scoring_path
        self._sync_fields_from_state()
        self.import_status_var.set(f"导入完成：{result.import_dir}")

    def _adopt_import_worker_state(self, worker_state: NewConfigWizardState) -> None:
        self.state.source_copy_path = worker_state.source_copy_path
        self.state.copied_source_path = worker_state.copied_source_path
        for path in worker_state.created_paths:
            register_created_path(self.state, path)

    def _set_import_in_progress(self, is_in_progress: bool) -> None:
        self._import_in_progress = is_in_progress
        state = tk.DISABLED if is_in_progress else tk.NORMAL
        if hasattr(self, "import_button"):
            self.import_button.configure(state=state)
        if is_in_progress:
            if hasattr(self, "back_button"):
                self.back_button.configure(state=tk.DISABLED)
            if hasattr(self, "next_button"):
                self.next_button.configure(state=tk.DISABLED)
            for button in getattr(self, "step_buttons", []):
                button.configure(state=tk.DISABLED)
        elif hasattr(self, "back_button") and hasattr(self, "next_button"):
            self._sync_footer()

    def _snapshot_existing_import_paths(self) -> set[Path]:
        requirements = self.state.project_root / "项目要求" / "项目采购需求.md"
        scoring = self.state.project_root / "项目要求" / "评分标准.md"
        paths = {
            requirements,
            scoring,
            requirements.with_suffix(requirements.suffix + ".bak"),
            scoring.with_suffix(scoring.suffix + ".bak"),
        }
        if self.state.import_dir is not None:
            paths.update(
                {
                    self.state.import_dir / "extraction_report.json",
                    self.state.import_dir / "converted.md",
                    self.state.import_dir / "conversion_map.json",
                }
            )
        return {path.resolve() for path in paths if path.exists()}

    def _register_new_created_paths(self, paths: tuple[Path, ...], existing_paths: set[Path]) -> None:
        for path in paths:
            resolved = Path(path).expanduser().resolve()
            if self._is_import_backup_path(resolved):
                continue
            if resolved not in existing_paths and resolved.exists():
                register_created_path(self.state, resolved)

    def _is_import_backup_path(self, path: Path) -> bool:
        material_dir = (self.state.project_root / "项目要求").resolve()
        backup_paths = {
            (material_dir / "项目采购需求.md.bak").resolve(),
            (material_dir / "评分标准.md.bak").resolve(),
        }
        return path.resolve() in backup_paths

    def _confirm_overwrite(self, path: Path) -> bool:
        return messagebox.askyesno(
            "确认覆盖",
            f"{path.name} 已存在且非空。是否覆盖并生成 .bak 备份？",
            parent=self,
        )
