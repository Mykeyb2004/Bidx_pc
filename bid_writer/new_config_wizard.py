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
from bid_writer.tender_import_dialog import confirm_low_confidence
from bid_writer.tender_import_service import TenderImportError, TenderImportService


SUPPORTED_TENDER_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls"}


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
        self.vars = self._create_vars()
        self.status_var = tk.StringVar(value="")
        self.config_summary_var = tk.StringVar(value="")
        self.source_hint_var = tk.StringVar(value="")
        self.import_status_var = tk.StringVar(value="")
        self.review_summary_var = tk.StringVar(value="")
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
        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._show_step()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _create_vars(self) -> dict[str, tk.StringVar]:
        return {
            "source_path": tk.StringVar(value=""),
            "project_root": tk.StringVar(value=""),
            "config_path": tk.StringVar(value=""),
            "requirements_path": tk.StringVar(value=""),
            "scoring_path": tk.StringVar(value=""),
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
        frame = self._create_step_frame(
            "source",
            "资料来源",
            "先选择招标文件，系统会根据文件位置推导项目目录和配置路径；也可以跳过导入，后续手动填写资料文件。",
        )
        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, text="招标文件").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.vars["source_path"]).grid(row=1, column=0, sticky="ew", pady=(4, 8))
        ttk.Button(
            controls,
            text="选择招标文件...",
            command=self._select_source_file,
            **_bootstyle_kwargs("primary"),
        ).grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(4, 8))
        ttk.Button(
            controls,
            text="跳过导入，手动填写",
            command=self._skip_source_selection,
            **_bootstyle_kwargs("secondary"),
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(controls, textvariable=self.source_hint_var, style="Muted.TLabel", wraplength=620, justify=tk.LEFT).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(10, 0),
        )

    def _build_location_step(self) -> None:
        frame = self._create_step_frame("location", "项目位置", "确认项目根目录与配置文件保存位置。")
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        self._add_path_row(form, 0, "项目根目录", "project_root", browse_kind="dir")
        self._add_path_row(form, 1, "配置文件保存位置", "config_path", browse_kind="file")

    def _build_materials_step(self) -> None:
        frame = self._create_step_frame(
            "materials",
            "项目材料",
            "可先自动抽取采购需求和评分标准；抽取失败或无需导入时，直接填写已有资料文件路径。",
        )
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        ttk.Button(
            form,
            text="开始抽取",
            command=self._run_import,
            **_bootstyle_kwargs("primary"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(form, textvariable=self.import_status_var, style="Muted.TLabel", wraplength=620, justify=tk.LEFT).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 10),
        )
        self._add_path_row(form, 1, "采购需求文件", "requirements_path", browse_kind="file")
        self._add_path_row(form, 2, "评分标准文件", "scoring_path", browse_kind="file")

    def _build_basics_step(self) -> None:
        frame = self._create_step_frame("basics", "基本信息", "填写新项目启动前必须确认的信息。")
        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        form.columnconfigure(1, weight=1)
        self._add_entry_row(form, 0, "投标主体名称", "bidder_name")
        self._add_path_row(form, 1, "大纲保存位置 / 已有大纲文件", "outline_path", browse_kind="file")
        self._add_path_row(form, 2, "输出目录", "output_dir", browse_kind="dir")

    def _build_review_step(self) -> None:
        frame = self._create_step_frame("review", "确认保存", "检查配置摘要，保存后将切换到新配置。")
        ttk.Label(
            frame,
            textvariable=self.review_summary_var,
            style="Muted.TLabel",
            wraplength=680,
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky="ew", pady=(18, 0))

    def _add_entry_row(self, parent: tk.Misc, row: int, label: str, key: str) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
        entry = ttk.Entry(parent, textvariable=self.vars[key])
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def _add_path_row(self, parent: tk.Misc, row: int, label: str, key: str, *, browse_kind: str) -> ttk.Entry:
        entry = self._add_entry_row(parent, row, label, key)
        ttk.Button(
            parent,
            text="选择...",
            command=lambda: self._browse_path(key, browse_kind),
            **_bootstyle_kwargs("secondary"),
        ).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=6)
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
        self.back_button.configure(state=tk.DISABLED if self.current_step_index == 0 else tk.NORMAL)
        next_text = "保存并应用" if self.current_step_index == total_steps - 1 else "下一步"
        self.next_button.configure(text=next_text)

        for index, button in enumerate(self.step_buttons):
            state = tk.NORMAL if index <= self.max_completed_step_index else tk.DISABLED
            button.configure(state=state)

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
        self.vars["outline_path"].set(str(self.state.outline_path))
        self.vars["output_dir"].set(str(self.state.output_dir))
        self.vars["bidder_name"].set(self.state.bidder_name)
        if hasattr(self, "config_summary_var"):
            self.config_summary_var.set(f"目标配置：{self.state.config_path}")
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
            self.source_hint_var.set("未选择招标文件时，将按手动资料路径创建配置。")
            return
        if self.state.should_copy_source and self.state.source_copy_path is not None:
            self.source_hint_var.set(f"招标文件位于项目外，导入时将复制到：{self.state.source_copy_path}")
        else:
            self.source_hint_var.set("招标文件已位于项目目录内，不会重复复制。")

    def _sync_review_summary(self) -> None:
        if not hasattr(self, "review_summary_var"):
            return
        created = "\n".join(f"- {path}" for path in self.state.created_paths) or "- 暂无"
        self.review_summary_var.set(
            "\n".join(
                [
                    f"配置文件：{self.state.config_path}",
                    f"项目根目录：{self.state.project_root}",
                    f"采购需求：{self.state.requirements_path or '未填写'}",
                    f"评分标准：{self.state.scoring_path or '未填写'}",
                    f"投标大纲：{self.state.outline_path}",
                    f"输出目录：{self.state.output_dir}",
                    "可清理的本次生成内容：",
                    created,
                ]
            )
        )

    def _skip_source_selection(self) -> None:
        self.vars["source_path"].set("")
        self.state.source_path = None
        self.state.import_dir = None
        self.state.should_copy_source = False
        self.state.source_copy_path = None
        self.state.manual_inputs = True
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
        else:
            selected = filedialog.askopenfilename(parent=self, initialdir=str(initial_dir))
        if selected:
            self.vars[key].set(str(Path(selected).expanduser().resolve()))

    def _run_import(self) -> None:
        self._sync_state_from_fields()
        if self.state.source_path is None:
            messagebox.showwarning("缺少招标文件", "请先选择招标文件，或手动选择采购需求和评分标准文件。", parent=self)
            return

        self.state.project_root.mkdir(parents=True, exist_ok=True)
        existing_paths = self._snapshot_existing_import_paths()
        try:
            copy_source_file_if_needed(self.state)
            result = TenderImportService().import_document(
                source_path=self.state.source_path,
                project_root=self.state.project_root,
                import_dir=self.state.import_dir,
                confirm_overwrite=self._confirm_overwrite,
                confirm_low_confidence=lambda extraction: confirm_low_confidence(self, extraction),
            )
        except TenderImportError as exc:
            self.import_status_var.set("导入失败，可手动填写资料文件。")
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        except Exception as exc:
            self.import_status_var.set("导入失败，可手动填写资料文件。")
            messagebox.showerror("导入失败", f"{type(exc).__name__}: {exc}", parent=self)
            return

        self._register_new_created_paths(result.created_paths, existing_paths)
        if result.cancelled:
            self.import_status_var.set("已取消写入，未修改资料路径。")
            return

        self.state.requirements_path = result.requirements_path
        self.state.scoring_path = result.scoring_path
        self._sync_fields_from_state()
        self.import_status_var.set(f"导入完成：{result.import_dir}")

    def _snapshot_existing_import_paths(self) -> set[Path]:
        paths = {
            self.state.project_root / "项目要求" / "项目采购需求.md",
            self.state.project_root / "项目要求" / "评分标准.md",
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
            if resolved not in existing_paths and resolved.exists():
                register_created_path(self.state, resolved)

    def _confirm_overwrite(self, path: Path) -> bool:
        return messagebox.askyesno(
            "确认覆盖",
            f"{path.name} 已存在且非空。是否覆盖并生成 .bak 备份？",
            parent=self,
        )
