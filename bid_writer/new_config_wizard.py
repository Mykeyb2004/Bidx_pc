from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from bid_writer.gui import (
    _bootstyle_kwargs,
    _compute_screen_limited_dialog_size,
    _set_centered_window_geometry,
    apply_window_surface,
    setup_gui_theme,
)
from bid_writer.new_config_flow import build_manual_state


@dataclass(frozen=True)
class WizardStep:
    key: str
    title: str


WIZARD_STEPS = [
    WizardStep("source", "资料来源"),
    WizardStep("location", "项目位置"),
    WizardStep("materials", "项目材料"),
    WizardStep("basics", "基本信息"),
    WizardStep("review", "确认保存"),
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
        self.state = build_manual_state(
            project_root=initial_config_path.parent,
            config_path=initial_config_path,
        )

        self.step_buttons: list[ttk.Button] = []
        self.step_frames: dict[str, ttk.Frame] = {}
        self.status_var = tk.StringVar(value="")

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
        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._show_step()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _create_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="新建配置向导", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=f"目标配置：{self.state.config_path}",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
        )

        body = ttk.Frame(self, padding=(16, 0, 16, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(body, padding=(0, 0, 12, 0))
        sidebar.grid(row=0, column=0, sticky="ns")
        ttk.Label(sidebar, text="步骤", style="SummaryLabel.TLabel").pack(anchor="w", pady=(0, 10))
        for index, step in enumerate(WIZARD_STEPS):
            button = ttk.Button(
                sidebar,
                text=f"{index + 1}. {step.title}",
                command=lambda step_index=index: self._jump_to_step(step_index),
                **_bootstyle_kwargs("secondary"),
            )
            button.pack(fill=tk.X, pady=4)
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
        self.back_button.pack(side=tk.LEFT, padx=(0, 8))
        self.next_button = ttk.Button(
            actions,
            text="下一步",
            command=self._go_next,
            **_bootstyle_kwargs("primary"),
        )
        self.next_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="取消",
            command=self._cancel,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT)

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
        self._create_step_frame("source", "资料来源", "选择或确认招标资料来源。后续任务会在这里接入导入动作。")

    def _build_location_step(self) -> None:
        self._create_step_frame("location", "项目位置", "确认项目根目录与配置文件保存位置。")

    def _build_materials_step(self) -> None:
        self._create_step_frame("materials", "项目材料", "确认采购需求、评分标准和投标大纲等材料路径。")

    def _build_basics_step(self) -> None:
        self._create_step_frame("basics", "基本信息", "填写投标主体等项目基本信息。")

    def _build_review_step(self) -> None:
        self._create_step_frame("review", "确认保存", "检查配置摘要并保存应用。")

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
        self.current_step_index = index
        self._show_step()

    def _validate_current_step(self) -> bool:
        return True

    def _show_step(self) -> None:
        step = WIZARD_STEPS[self.current_step_index]
        self.step_frames[step.key].tkraise()
        self._sync_footer()

    def _sync_footer(self) -> None:
        total_steps = len(WIZARD_STEPS)
        step_number = self.current_step_index + 1
        self.status_var.set(f"第 {step_number} 步，共 {total_steps} 步")
        self.back_button.configure(state=tk.DISABLED if self.current_step_index == 0 else tk.NORMAL)
        next_text = "保存并应用" if self.current_step_index == total_steps - 1 else "下一步"
        self.next_button.configure(text=next_text)

        for index, button in enumerate(self.step_buttons):
            state = tk.NORMAL if index <= self.max_completed_step_index else tk.DISABLED
            button.configure(state=state)

    def _save_and_apply(self) -> None:
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()
