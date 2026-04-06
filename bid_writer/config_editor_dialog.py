"""
Tkinter 配置编辑器窗口。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config_editor import (
    ConfigEditorDocument,
    ConnectionStatus,
    ValidationMessage,
    load_config_editor_document,
    summarize_model,
)
from .config_editor_tooltips import get_tooltip_text
from .gui import (
    _bootstyle_kwargs,
    apply_window_surface,
    setup_gui_theme,
    style_canvas_widget,
    style_text_widget,
)


class ScrollableSection(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        style_canvas_widget(self.canvas)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._mousewheel_bound = False
        self.bind("<Enter>", self._bind_mousewheel, add="+")
        self.canvas.bind("<Enter>", self._bind_mousewheel, add="+")
        self.content.bind("<Enter>", self._bind_mousewheel, add="+")
        self.bind("<Leave>", self._unbind_mousewheel, add="+")
        self.canvas.bind("<Leave>", self._unbind_mousewheel, add="+")
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_content_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event=None):
        if self._mousewheel_bound:
            return
        try:
            self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        except tk.TclError:
            return
        self._mousewheel_bound = True

    def _unbind_mousewheel(self, _event=None):
        if not self._mousewheel_bound:
            return
        try:
            self.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self._mousewheel_bound = False

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._unbind_mousewheel()

    def _on_mousewheel(self, event):
        try:
            if not self.winfo_exists() or not self.winfo_ismapped():
                self._unbind_mousewheel()
                return
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            self._unbind_mousewheel()
            return


class HoverTooltip:
    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450):
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self.tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

        if not self.text:
            return

        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule_show(self, _event=None):
        self._cancel_pending()
        if not self.text:
            return
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except tk.TclError:
            self._after_id = None

    def _cancel_pending(self):
        if self._after_id is None:
            return
        try:
            self.widget.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _show(self):
        self._after_id = None
        if self.tip_window is not None or not self.widget.winfo_exists():
            return

        try:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        except tk.TclError:
            return

        tip = tk.Toplevel(self.widget)
        apply_window_surface(tip)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")

        container = ttk.Frame(tip, padding=(10, 8))
        container.pack(fill=tk.BOTH, expand=True)
        label = ttk.Label(
            container,
            text=self.text,
            justify=tk.LEFT,
            wraplength=360,
        )
        label.pack(fill=tk.BOTH, expand=True)
        self.tip_window = tip

    def _hide(self, _event=None):
        self._cancel_pending()
        if self.tip_window is not None:
            try:
                self.tip_window.destroy()
            except tk.TclError:
                pass
            self.tip_window = None


class ConfigEditorDialog(tk.Toplevel):
    SECTION_LABELS = [
        ("project", "项目"),
        ("writing", "写作"),
        ("processing", "处理路径"),
        ("models", "模型"),
        ("runtime", "运行"),
    ]

    def __init__(self, parent: tk.Misc, config_path: str | Path):
        super().__init__(parent)
        self.parent_window = parent
        self.style = setup_gui_theme(self)
        apply_window_surface(self)
        self.active_config_path = Path(config_path).expanduser().resolve()
        self.document: ConfigEditorDocument | None = None
        self.result: dict[str, Any] = {"saved_path": None, "apply_path": None}
        self._refresh_pending = False
        self._saved_yaml = ""

        self.vars: dict[str, tk.Variable] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.section_pages: dict[str, ScrollableSection] = {}
        self._tooltips: list[HoverTooltip] = []

        self.title("配置编辑器")
        self.geometry("1280x860")
        self.minsize(1100, 760)
        self.transient(parent)
        self.grab_set()

        self.current_file_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="正在载入配置...")
        self.section_var = tk.StringVar(value="project")
        self.connection_text_var = tk.StringVar(value="")

        self._create_variables()
        self._create_widgets()
        self._load_document(self.active_config_path)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_variables(self) -> None:
        def add_var(key: str, variable: tk.Variable, watch: bool = True) -> None:
            self.vars[key] = variable
            if watch:
                variable.trace_add("write", lambda *_: self._schedule_refresh())

        add_var("project.root_dir", tk.StringVar())
        add_var("project.bidder_name", tk.StringVar())
        add_var("project.outline_file", tk.StringVar())
        add_var("project.bid_requirements_mode", tk.StringVar())
        add_var("project.bid_requirements_file", tk.StringVar())
        add_var("project.scoring_criteria_mode", tk.StringVar())
        add_var("project.scoring_criteria_file", tk.StringVar())
        add_var("project.output_dir", tk.StringVar())

        add_var("writing.role_mode", tk.StringVar())
        add_var("writing.role_file", tk.StringVar())
        add_var("writing.target_words.default", tk.StringVar())
        add_var("writing.target_words.min", tk.StringVar())
        add_var("writing.target_words.max", tk.StringVar())
        add_var("writing.target_words.step", tk.StringVar())
        add_var("writing.target_words.upper_ratio", tk.StringVar())
        add_var("writing.output_format", tk.StringVar())
        add_var("writing.first_line_template", tk.StringVar())
        add_var("writing.allow_markdown_headings", tk.BooleanVar())
        add_var("writing.allow_english_terms", tk.BooleanVar())
        add_var("writing.max_tables_per_section", tk.StringVar())
        add_var("writing.max_mermaid_flowcharts_per_section", tk.StringVar())
        add_var("writing.summary_title", tk.StringVar())

        add_var("processing.path", tk.StringVar())
        add_var("processing.context_view.include_ancestors", tk.BooleanVar())
        add_var("processing.context_view.include_siblings", tk.BooleanVar())
        add_var("processing.context_view.max_siblings", tk.StringVar())
        add_var("processing.project_background.enabled", tk.BooleanVar())
        add_var("processing.project_background.max_chars", tk.StringVar())
        add_var("processing.full_context.chapter_writing_plan.enabled", tk.BooleanVar())
        add_var("processing.full_context.chapter_writing_plan.max_chars", tk.StringVar())
        add_var("processing.auto.requirements_top_k", tk.StringVar())
        add_var("processing.auto.scoring_parse_mode", tk.StringVar())
        add_var("processing.auto.scoring_max_rows", tk.StringVar())
        add_var("processing.auto.retrieval.lexical_enabled", tk.BooleanVar())
        add_var("processing.auto.retrieval.vector_enabled", tk.BooleanVar())
        add_var("processing.auto.retrieval.top_k_lexical", tk.StringVar())
        add_var("processing.auto.retrieval.top_k_fused", tk.StringVar())
        add_var("processing.auto.retrieval.top_k_final", tk.StringVar())
        add_var("processing.auto.retrieval.min_fused_score", tk.StringVar())

        add_var("models.generation.model", tk.StringVar())
        add_var("models.generation.temperature", tk.StringVar())
        add_var("models.generation.max_tokens", tk.StringVar())
        add_var("models.generation.timeout_seconds", tk.StringVar())
        add_var("models.generation.max_retries", tk.StringVar())
        add_var("models.generation.top_p", tk.StringVar())
        add_var("models.generation.seed", tk.StringVar())
        add_var("models.pruning.model", tk.StringVar())
        add_var("models.pruning.temperature", tk.StringVar())
        add_var("models.pruning.max_tokens", tk.StringVar())
        add_var("models.pruning.timeout_seconds", tk.StringVar())
        add_var("models.pruning.max_retries", tk.StringVar())
        add_var("models.pruning.top_p", tk.StringVar())
        add_var("models.pruning.seed", tk.StringVar())
        add_var("models.embedding.model", tk.StringVar())
        add_var("models.embedding.batch_size", tk.StringVar())
        add_var("models.embedding.cache_dir", tk.StringVar())
        add_var("models.embedding.rebuild_on_source_change", tk.BooleanVar())
        add_var("models.embedding.query_prefix", tk.StringVar())
        add_var("models.embedding.document_prefix", tk.StringVar())

        add_var("runtime.stream.enabled", tk.BooleanVar())
        add_var("runtime.stream.idle_timeout_seconds", tk.StringVar())
        add_var("runtime.trace.enabled", tk.BooleanVar())
        add_var("runtime.trace.directory", tk.StringVar())
        add_var("runtime.trace.mode", tk.StringVar())
        add_var("runtime.trace.write_prompt", tk.BooleanVar())
        add_var("runtime.trace.write_output", tk.BooleanVar())
        add_var("runtime.trace.write_context", tk.BooleanVar())
        add_var("runtime.trace.write_summary", tk.BooleanVar())
        add_var("runtime.trace.redact_sensitive", tk.BooleanVar())
        add_var("runtime.debug.context_pruning_dump", tk.BooleanVar())
        add_var("runtime.output.prefix", tk.StringVar())
        add_var("runtime.output.include_title_header", tk.BooleanVar())
        add_var("runtime.output.overwrite_existing", tk.BooleanVar())
        add_var("runtime.output.filename_max_length", tk.StringVar())
        add_var("runtime.output.empty_filename_fallback", tk.StringVar())
        add_var("runtime.merge.normalize_soft_line_breaks", tk.BooleanVar())

        self.section_var.trace_add("write", lambda *_: self._show_current_section())
        self.vars["processing.path"].trace_add("write", lambda *_: self._update_processing_visibility())

    def _create_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 16, 16, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="配置编辑器", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.current_file_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        body = ttk.Frame(self, padding=(16, 0, 16, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0)
        body.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(body, padding=(0, 0, 12, 0))
        sidebar.grid(row=0, column=0, sticky="ns")
        ttk.Label(sidebar, text="配置分组", style="SummaryLabel.TLabel").pack(anchor="w", pady=(0, 10))
        for section, label in self.SECTION_LABELS:
            button = ttk.Radiobutton(
                sidebar,
                text=label,
                value=section,
                variable=self.section_var,
                command=self._show_current_section,
            )
            button.pack(anchor="w", fill=tk.X, pady=4)
            self._register_tooltip(button, f"section.{section}")

        self.content_container = ttk.Frame(body)
        self.content_container.grid(row=0, column=1, sticky="nsew")
        self.content_container.rowconfigure(0, weight=1)
        self.content_container.columnconfigure(0, weight=1)

        self.right_panel = ttk.Frame(body, padding=(16, 0, 0, 0))
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.rowconfigure(3, weight=1)
        self.right_panel.columnconfigure(0, weight=1)
        self._create_right_panel()

        self._build_project_section()
        self._build_writing_section()
        self._build_processing_section()
        self._build_models_section()
        self._build_runtime_section()
        self._show_current_section()

        footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        ttk.Button(
            footer,
            text="恢复加载值",
            command=self._reload_from_disk,
            **_bootstyle_kwargs("secondary"),
        ).grid(row=0, column=0, sticky="w")

        actions = ttk.Frame(footer)
        actions.grid(row=0, column=1, sticky="e")
        ttk.Button(
            actions,
            text="另存为",
            command=self._save_as,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="保存",
            command=self._save_current,
            **_bootstyle_kwargs("primary"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="关闭",
            command=self._on_close,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT)

    def _create_right_panel(self) -> None:
        env_frame = ttk.LabelFrame(self.right_panel, text="连接状态", padding=12)
        env_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(env_frame, textvariable=self.connection_text_var, justify=tk.LEFT).pack(anchor="w")

        summary_frame = ttk.LabelFrame(self.right_panel, text="摘要", padding=12)
        summary_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.summary_text = tk.Text(summary_frame, height=8, wrap=tk.WORD)
        style_text_widget(self.summary_text)
        self.summary_text.pack(fill=tk.BOTH, expand=True)

        validation_frame = ttk.LabelFrame(self.right_panel, text="校验", padding=12)
        validation_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.validation_text = tk.Text(validation_frame, height=10, wrap=tk.WORD)
        style_text_widget(self.validation_text)
        self.validation_text.pack(fill=tk.BOTH, expand=True)

        yaml_frame = ttk.LabelFrame(self.right_panel, text="YAML 预览", padding=12)
        yaml_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        self.yaml_preview = tk.Text(yaml_frame, wrap=tk.NONE)
        style_text_widget(self.yaml_preview)
        x_scroll = ttk.Scrollbar(yaml_frame, orient=tk.HORIZONTAL, command=self.yaml_preview.xview)
        y_scroll = ttk.Scrollbar(yaml_frame, orient=tk.VERTICAL, command=self.yaml_preview.yview)
        self.yaml_preview.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.yaml_preview.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        yaml_frame.rowconfigure(0, weight=1)
        yaml_frame.columnconfigure(0, weight=1)

    def _build_project_section(self) -> None:
        page = self._create_section_page("project")
        content = page.content

        basic = ttk.LabelFrame(content, text="项目信息", padding=12)
        basic.pack(fill=tk.X, pady=(0, 12))
        self._add_path_row(basic, 0, "项目根目录", "project.root_dir", browse_kind="dir", relative_to="config")
        self._add_entry_row(basic, 1, "投标主体名称", "project.bidder_name")
        self._add_path_row(basic, 2, "输出目录", "project.output_dir", browse_kind="dir", relative_to="project")

        inputs = ttk.LabelFrame(content, text="输入资源", padding=12)
        inputs.pack(fill=tk.X, pady=(0, 12))
        self._add_path_row(inputs, 0, "大纲文件", "project.outline_file", browse_kind="file", relative_to="project")

        self._add_mode_selector(inputs, 1, "采购需求", "project.bid_requirements_mode")
        self.project_bid_file_frame = ttk.Frame(inputs)
        self.project_bid_file_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_path_row(self.project_bid_file_frame, 0, "采购需求文件", "project.bid_requirements_file", browse_kind="file", relative_to="project")
        self.project_bid_text_frame = ttk.Frame(inputs)
        self.project_bid_text_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_text_block(
            self.project_bid_text_frame,
            "采购需求正文",
            "project.bid_requirements_text",
            help_text="兼容旧配置；推荐迁移为独立文件。",
        )

        self._add_mode_selector(inputs, 4, "评分标准", "project.scoring_criteria_mode")
        self.project_score_file_frame = ttk.Frame(inputs)
        self.project_score_file_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_path_row(self.project_score_file_frame, 0, "评分标准文件", "project.scoring_criteria_file", browse_kind="file", relative_to="project")
        self.project_score_text_frame = ttk.Frame(inputs)
        self.project_score_text_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_text_block(
            self.project_score_text_frame,
            "评分标准正文",
            "project.scoring_criteria_text",
            help_text="兼容旧配置；推荐迁移为独立文件。",
        )

        inputs.columnconfigure(1, weight=1)

    def _build_writing_section(self) -> None:
        page = self._create_section_page("writing")
        content = page.content

        role_card = ttk.LabelFrame(content, text="角色设定", padding=12)
        role_card.pack(fill=tk.X, pady=(0, 12))
        self._add_mode_selector(role_card, 0, "角色来源", "writing.role_mode")
        self.role_file_frame = ttk.Frame(role_card)
        self.role_file_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_path_row(self.role_file_frame, 0, "role_file", "writing.role_file", browse_kind="file", relative_to="config")
        self.role_text_frame = ttk.Frame(role_card)
        self.role_text_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._add_text_block(self.role_text_frame, "角色正文", "writing.role_text", help_text="内嵌文本模式下会直接写入 YAML。")
        role_card.columnconfigure(1, weight=1)

        target_words = ttk.LabelFrame(content, text="篇幅目标", padding=12)
        target_words.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(target_words, 0, "默认目标基准", "writing.target_words.default")
        self._add_entry_row(target_words, 1, "目标下限", "writing.target_words.min")
        self._add_entry_row(target_words, 2, "目标上限", "writing.target_words.max")
        self._add_entry_row(target_words, 3, "步长", "writing.target_words.step")
        self._add_entry_row(target_words, 4, "区间上沿倍率", "writing.target_words.upper_ratio")
        target_words.columnconfigure(1, weight=1)

        rules = ttk.LabelFrame(content, text="写作与格式", padding=12)
        rules.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(rules, 0, "输出格式", "writing.output_format")
        self._add_entry_row(rules, 1, "首行模板", "writing.first_line_template")
        self._add_entry_row(rules, 2, "单节最大表格数", "writing.max_tables_per_section")
        self._add_entry_row(rules, 3, "单节最大 Mermaid 流程图数", "writing.max_mermaid_flowcharts_per_section")
        self._add_entry_row(rules, 4, "总结标题", "writing.summary_title")
        self._add_check_row(rules, 5, "允许 Markdown 标题", "writing.allow_markdown_headings")
        self._add_check_row(rules, 6, "允许英文术语", "writing.allow_english_terms")
        rules.columnconfigure(1, weight=1)

        hard_constraints = ttk.LabelFrame(content, text="高优先级约束", padding=12)
        hard_constraints.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        self._add_text_block(hard_constraints, "hard_constraints", "writing.hard_constraints_text", help_text="每行一条规则。", height=8)

        extra_rules = ttk.LabelFrame(content, text="额外规则", padding=12)
        extra_rules.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        self._add_text_block(extra_rules, "extra_rules", "writing.extra_rules_text", help_text="每行一条规则。", height=6)

    def _build_processing_section(self) -> None:
        page = self._create_section_page("processing")
        content = page.content

        self.processing_path_frame = ttk.LabelFrame(content, text="处理路径", padding=12)
        self.processing_path_frame.pack(fill=tk.X, pady=(0, 12))
        path_label = ttk.Label(self.processing_path_frame, text="processing.path")
        path_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        path_box = ttk.Combobox(
            self.processing_path_frame,
            textvariable=self.vars["processing.path"],
            values=("auto", "full_context"),
        )
        path_box.grid(row=0, column=1, sticky="ew", pady=5)
        helper = ttk.Label(
            self.processing_path_frame,
            text="可选值：auto / full_context。若载入旧配置中的其他模式，可在这里切回受支持模式。",
            style="Muted.TLabel",
            justify=tk.LEFT,
        )
        helper.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.processing_path_frame.columnconfigure(1, weight=1)
        self._register_tooltip(path_label, "processing.path")
        self._register_tooltip(path_box, "processing.path")
        self._register_tooltip(helper, "processing.path")

        self.processing_full_context_frame = ttk.LabelFrame(content, text="full_context 说明", padding=12)
        ttk.Label(
            self.processing_full_context_frame,
            text=(
                "当前模式不会做章节级摘录或检索，而是把采购需求全文和评分标准全文直接拼入提示词。"
                " 下方仅保留对 full_context 仍然生效的项目背景参数。"
            ),
            justify=tk.LEFT,
            wraplength=760,
        ).pack(anchor="w")

        self.processing_context_view_frame = ttk.LabelFrame(content, text="上下文视图", padding=12)
        self._add_check_row(self.processing_context_view_frame, 0, "包含祖先标题", "processing.context_view.include_ancestors")
        self._add_check_row(self.processing_context_view_frame, 1, "包含同级标题", "processing.context_view.include_siblings")
        self._add_entry_row(self.processing_context_view_frame, 2, "同级标题上限", "processing.context_view.max_siblings")
        self.processing_context_view_frame.columnconfigure(1, weight=1)

        self.processing_project_background_frame = ttk.LabelFrame(content, text="项目背景", padding=12)
        self._add_check_row(self.processing_project_background_frame, 0, "启用项目背景生成", "processing.project_background.enabled")
        self._add_entry_row(self.processing_project_background_frame, 1, "背景最大字符数", "processing.project_background.max_chars")
        self.processing_project_background_frame.columnconfigure(1, weight=1)

        self.processing_chapter_plan_frame = ttk.LabelFrame(content, text="章节写作计划", padding=12)
        self._add_check_row(
            self.processing_chapter_plan_frame,
            0,
            "启用章节写作计划",
            "processing.full_context.chapter_writing_plan.enabled",
        )
        self._add_entry_row(
            self.processing_chapter_plan_frame,
            1,
            "计划最大字符数",
            "processing.full_context.chapter_writing_plan.max_chars",
        )
        self.processing_chapter_plan_frame.columnconfigure(1, weight=1)

        self.processing_req_frame = ttk.LabelFrame(content, text="需求检索", padding=12)
        self._add_entry_row(self.processing_req_frame, 0, "需求检索 top-K（原文段落数）", "processing.auto.requirements_top_k")
        self._add_entry_row(self.processing_req_frame, 1, "top_k_lexical", "processing.auto.retrieval.top_k_lexical")
        self._add_entry_row(self.processing_req_frame, 2, "top_k_fused", "processing.auto.retrieval.top_k_fused")
        self._add_entry_row(self.processing_req_frame, 3, "top_k_final", "processing.auto.retrieval.top_k_final")
        self._add_entry_row(self.processing_req_frame, 4, "min_fused_score", "processing.auto.retrieval.min_fused_score")
        self._add_check_row(self.processing_req_frame, 5, "lexical_enabled", "processing.auto.retrieval.lexical_enabled")
        self._add_check_row(self.processing_req_frame, 6, "vector_enabled（需配置 embedding）", "processing.auto.retrieval.vector_enabled")
        self.processing_req_frame.columnconfigure(1, weight=1)

        self.processing_scoring_frame = ttk.LabelFrame(content, text="评分检索", padding=12)
        self._add_entry_row(self.processing_scoring_frame, 0, "评分最多保留行数", "processing.auto.scoring_max_rows")
        self._add_entry_row(self.processing_scoring_frame, 1, "评分解析模式", "processing.auto.scoring_parse_mode")
        self.processing_scoring_frame.columnconfigure(1, weight=1)

        self._update_processing_visibility()

    def _build_models_section(self) -> None:
        page = self._create_section_page("models")
        content = page.content

        generation = ttk.LabelFrame(content, text="主生成模型", padding=12)
        generation.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(generation, 0, "model", "models.generation.model")
        self._add_entry_row(generation, 1, "temperature", "models.generation.temperature")
        self._add_entry_row(generation, 2, "max_tokens", "models.generation.max_tokens")
        self._add_entry_row(generation, 3, "timeout_seconds", "models.generation.timeout_seconds")
        self._add_entry_row(generation, 4, "max_retries", "models.generation.max_retries")
        self._add_entry_row(generation, 5, "top_p（可选）", "models.generation.top_p")
        self._add_entry_row(generation, 6, "seed（可选）", "models.generation.seed")
        generation.columnconfigure(1, weight=1)

        pruning = ttk.LabelFrame(content, text="辅助模型", padding=12)
        pruning.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(pruning, 0, "model", "models.pruning.model")
        self._add_entry_row(pruning, 1, "temperature", "models.pruning.temperature")
        self._add_entry_row(pruning, 2, "max_tokens", "models.pruning.max_tokens")
        self._add_entry_row(pruning, 3, "timeout_seconds", "models.pruning.timeout_seconds")
        self._add_entry_row(pruning, 4, "max_retries", "models.pruning.max_retries")
        self._add_entry_row(pruning, 5, "top_p（可选）", "models.pruning.top_p")
        self._add_entry_row(pruning, 6, "seed（可选）", "models.pruning.seed")
        pruning.columnconfigure(1, weight=1)

        embedding = ttk.LabelFrame(content, text="向量模型", padding=12)
        embedding.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(embedding, 0, "model", "models.embedding.model")
        self._add_entry_row(embedding, 1, "batch_size", "models.embedding.batch_size")
        self._add_path_row(embedding, 2, "cache_dir", "models.embedding.cache_dir", browse_kind="dir", relative_to="config")
        self._add_check_row(embedding, 3, "源文变化时重建缓存", "models.embedding.rebuild_on_source_change")
        self._add_entry_row(embedding, 4, "query_prefix", "models.embedding.query_prefix")
        self._add_entry_row(embedding, 5, "document_prefix", "models.embedding.document_prefix")
        embedding.columnconfigure(1, weight=1)

        note = ttk.LabelFrame(content, text="说明", padding=12)
        note.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(
            note,
            text="API Key / Base URL 等连接信息不在此处编辑；编辑器只展示当前是否已检测到连接配置。",
            justify=tk.LEFT,
        ).pack(anchor="w")

    def _build_runtime_section(self) -> None:
        page = self._create_section_page("runtime")
        content = page.content

        stream = ttk.LabelFrame(content, text="流式输出", padding=12)
        stream.pack(fill=tk.X, pady=(0, 12))
        self._add_check_row(stream, 0, "启用流式输出", "runtime.stream.enabled")
        self._add_entry_row(stream, 1, "静默超时（秒）", "runtime.stream.idle_timeout_seconds")
        stream.columnconfigure(1, weight=1)

        trace = ttk.LabelFrame(content, text="Trace 与调试", padding=12)
        trace.pack(fill=tk.X, pady=(0, 12))
        self._add_check_row(trace, 0, "启用 trace", "runtime.trace.enabled")
        self._add_path_row(trace, 1, "trace.directory", "runtime.trace.directory", browse_kind="dir", relative_to="config")
        self._add_entry_row(trace, 2, "trace.mode", "runtime.trace.mode")
        self._add_check_row(trace, 3, "write_prompt", "runtime.trace.write_prompt")
        self._add_check_row(trace, 4, "write_output", "runtime.trace.write_output")
        self._add_check_row(trace, 5, "write_context", "runtime.trace.write_context")
        self._add_check_row(trace, 6, "write_summary", "runtime.trace.write_summary")
        self._add_check_row(trace, 7, "redact_sensitive", "runtime.trace.redact_sensitive")
        self._add_check_row(trace, 8, "context_pruning_dump", "runtime.debug.context_pruning_dump")
        trace.columnconfigure(1, weight=1)

        output = ttk.LabelFrame(content, text="输出行为", padding=12)
        output.pack(fill=tk.X, pady=(0, 12))
        self._add_entry_row(output, 0, "文件名前缀", "runtime.output.prefix")
        self._add_check_row(output, 1, "include_title_header", "runtime.output.include_title_header")
        self._add_check_row(output, 2, "overwrite_existing", "runtime.output.overwrite_existing")
        self._add_entry_row(output, 3, "filename_max_length", "runtime.output.filename_max_length")
        self._add_entry_row(output, 4, "empty_filename_fallback", "runtime.output.empty_filename_fallback")
        self._add_check_row(output, 5, "整合时归一化软回车", "runtime.merge.normalize_soft_line_breaks")
        output.columnconfigure(1, weight=1)

    def _create_section_page(self, name: str) -> ScrollableSection:
        page = ScrollableSection(self.content_container)
        page.grid(row=0, column=0, sticky="nsew")
        self.section_pages[name] = page
        return page

    def _register_tooltip(self, widget: tk.Misc, key: str) -> None:
        text = get_tooltip_text(key)
        if not text:
            return
        self._tooltips.append(HoverTooltip(widget, text))

    def _add_entry_row(self, parent: tk.Misc, row: int, label: str, key: str) -> ttk.Entry:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        entry = ttk.Entry(parent, textvariable=self.vars[key])
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        self._register_tooltip(label_widget, key)
        self._register_tooltip(entry, key)
        return entry

    def _add_path_row(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        key: str,
        *,
        browse_kind: str,
        relative_to: str,
    ) -> None:
        self._add_entry_row(parent, row, label, key)
        browse_button = ttk.Button(
            parent,
            text="浏览...",
            command=lambda current_key=key, kind=browse_kind, rel=relative_to: self._browse_path(current_key, kind, rel),
            **_bootstyle_kwargs("secondary"),
        )
        browse_button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=5)
        self._register_tooltip(browse_button, key)

    def _add_check_row(self, parent: tk.Misc, row: int, label: str, key: str) -> None:
        check = ttk.Checkbutton(parent, text=label, variable=self.vars[key])
        check.grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
        self._register_tooltip(check, key)

    def _add_mode_selector(self, parent: tk.Misc, row: int, label: str, key: str) -> None:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=5)
        file_radio = ttk.Radiobutton(mode_frame, text="文件", value="file", variable=self.vars[key], command=self._update_mode_visibility)
        inline_radio = ttk.Radiobutton(mode_frame, text="内嵌文本", value="inline", variable=self.vars[key], command=self._update_mode_visibility)
        file_radio.pack(side=tk.LEFT, padx=(0, 12))
        inline_radio.pack(side=tk.LEFT)
        self._register_tooltip(label_widget, key)
        self._register_tooltip(file_radio, key)
        self._register_tooltip(inline_radio, key)

    def _add_text_block(
        self,
        parent: tk.Misc,
        label: str,
        key: str,
        *,
        help_text: str = "",
        height: int = 6,
    ) -> None:
        label_widget = ttk.Label(parent, text=label)
        label_widget.pack(anchor="w")
        if help_text:
            help_label = ttk.Label(parent, text=help_text, style="Muted.TLabel")
            help_label.pack(anchor="w", pady=(2, 6))
            self._register_tooltip(help_label, key)
        text = tk.Text(parent, height=height, wrap=tk.WORD)
        style_text_widget(text)
        text.pack(fill=tk.BOTH, expand=True)
        text.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        text.bind("<FocusOut>", lambda _event: self._schedule_refresh())
        self.text_widgets[key] = text
        self._register_tooltip(label_widget, key)
        self._register_tooltip(text, key)

    def _display_relative_path(self, path: Path, base_dir: Path) -> str:
        try:
            return str(path.relative_to(base_dir))
        except ValueError:
            return str(path)

    def _current_config_dir(self) -> Path:
        return (self.document.config_path if self.document else self.active_config_path).parent.resolve()

    def _current_project_root(self) -> Path:
        root_value = self.vars["project.root_dir"].get().strip() or "."
        root = Path(root_value).expanduser()
        if not root.is_absolute():
            root = self._current_config_dir() / root
        return root.resolve()

    def _browse_path(self, key: str, browse_kind: str, relative_to: str) -> None:
        current_value = self.vars[key].get().strip()
        base_dir = self._current_project_root() if relative_to == "project" else self._current_config_dir()
        initial_path = (base_dir / current_value).resolve() if current_value and not Path(current_value).is_absolute() else Path(current_value or base_dir)
        initial_dir = str(initial_path.parent if initial_path.suffix else initial_path)

        if browse_kind == "dir":
            selected = filedialog.askdirectory(parent=self, initialdir=initial_dir)
        else:
            selected = filedialog.askopenfilename(parent=self, initialdir=initial_dir)

        if not selected:
            return
        selected_path = Path(selected).resolve()
        self.vars[key].set(self._display_relative_path(selected_path, base_dir))

    def _load_document(self, config_path: Path) -> None:
        self.document = load_config_editor_document(config_path)
        self.current_file_var.set(f"当前文件：{self.document.config_path}")
        self._saved_yaml = self.document.render_yaml()
        self._populate_vars(self.document.model)
        self._update_connection_panel()
        self._refresh_side_panel()

    def _populate_vars(self, model: dict[str, Any]) -> None:
        data = {
            "project.root_dir": model["project"]["root_dir"],
            "project.bidder_name": model["project"]["bidder_name"],
            "project.outline_file": model["project"]["outline_file"],
            "project.bid_requirements_mode": model["project"]["bid_requirements_mode"],
            "project.bid_requirements_file": model["project"]["bid_requirements_file"],
            "project.scoring_criteria_mode": model["project"]["scoring_criteria_mode"],
            "project.scoring_criteria_file": model["project"]["scoring_criteria_file"],
            "project.output_dir": model["project"]["output_dir"],
            "writing.role_mode": model["writing"]["role_mode"],
            "writing.role_file": model["writing"]["role_file"],
            "writing.target_words.default": str(model["writing"]["target_words_default"]),
            "writing.target_words.min": str(model["writing"]["target_words_min"]),
            "writing.target_words.max": str(model["writing"]["target_words_max"]),
            "writing.target_words.step": str(model["writing"]["target_words_step"]),
            "writing.target_words.upper_ratio": str(model["writing"]["target_words_upper_ratio"]),
            "writing.output_format": model["writing"]["output_format"],
            "writing.first_line_template": model["writing"]["first_line_template"],
            "writing.allow_markdown_headings": model["writing"]["allow_markdown_headings"],
            "writing.allow_english_terms": model["writing"]["allow_english_terms"],
            "writing.max_tables_per_section": str(model["writing"]["max_tables_per_section"]),
            "writing.max_mermaid_flowcharts_per_section": str(model["writing"]["max_mermaid_flowcharts_per_section"]),
            "writing.summary_title": model["writing"]["summary_title"],
            "processing.path": model["processing"]["path"],
            "processing.context_view.include_ancestors": model["processing"]["context_view"]["include_ancestors"],
            "processing.context_view.include_siblings": model["processing"]["context_view"]["include_siblings"],
            "processing.context_view.max_siblings": str(model["processing"]["context_view"]["max_siblings"]),
            "processing.project_background.enabled": model["processing"]["project_background"]["enabled"],
            "processing.project_background.max_chars": str(model["processing"]["project_background"]["max_chars"]),
            "processing.full_context.chapter_writing_plan.enabled": model["processing"]["full_context"]["chapter_writing_plan"]["enabled"],
            "processing.full_context.chapter_writing_plan.max_chars": str(model["processing"]["full_context"]["chapter_writing_plan"]["max_chars"]),
            "processing.auto.requirements_top_k": str(model["processing"]["auto"]["requirements_top_k"]),
            "processing.auto.scoring_parse_mode": model["processing"]["auto"]["scoring_parse_mode"],
            "processing.auto.scoring_max_rows": str(model["processing"]["auto"]["scoring_max_rows"]),
            "processing.auto.retrieval.lexical_enabled": model["processing"]["auto"]["retrieval"]["lexical_enabled"],
            "processing.auto.retrieval.vector_enabled": model["processing"]["auto"]["retrieval"]["vector_enabled"],
            "processing.auto.retrieval.top_k_lexical": str(model["processing"]["auto"]["retrieval"]["top_k_lexical"]),
            "processing.auto.retrieval.top_k_fused": str(model["processing"]["auto"]["retrieval"]["top_k_fused"]),
            "processing.auto.retrieval.top_k_final": str(model["processing"]["auto"]["retrieval"]["top_k_final"]),
            "processing.auto.retrieval.min_fused_score": str(model["processing"]["auto"]["retrieval"]["min_fused_score"]),
            "models.generation.model": model["models"]["generation"]["model"],
            "models.generation.temperature": str(model["models"]["generation"]["temperature"]),
            "models.generation.max_tokens": str(model["models"]["generation"]["max_tokens"]),
            "models.generation.timeout_seconds": str(model["models"]["generation"]["timeout_seconds"]),
            "models.generation.max_retries": str(model["models"]["generation"]["max_retries"]),
            "models.generation.top_p": str(model["models"]["generation"]["top_p"]),
            "models.generation.seed": str(model["models"]["generation"]["seed"]),
            "models.pruning.model": model["models"]["pruning"]["model"],
            "models.pruning.temperature": str(model["models"]["pruning"]["temperature"]),
            "models.pruning.max_tokens": str(model["models"]["pruning"]["max_tokens"]),
            "models.pruning.timeout_seconds": str(model["models"]["pruning"]["timeout_seconds"]),
            "models.pruning.max_retries": str(model["models"]["pruning"]["max_retries"]),
            "models.pruning.top_p": str(model["models"]["pruning"]["top_p"]),
            "models.pruning.seed": str(model["models"]["pruning"]["seed"]),
            "models.embedding.model": model["models"]["embedding"]["model"],
            "models.embedding.batch_size": str(model["models"]["embedding"]["batch_size"]),
            "models.embedding.cache_dir": model["models"]["embedding"]["cache_dir"],
            "models.embedding.rebuild_on_source_change": model["models"]["embedding"]["rebuild_on_source_change"],
            "models.embedding.query_prefix": model["models"]["embedding"]["query_prefix"],
            "models.embedding.document_prefix": model["models"]["embedding"]["document_prefix"],
            "runtime.stream.enabled": model["runtime"]["stream"]["enabled"],
            "runtime.stream.idle_timeout_seconds": str(model["runtime"]["stream"]["idle_timeout_seconds"]),
            "runtime.trace.enabled": model["runtime"]["trace"]["enabled"],
            "runtime.trace.directory": model["runtime"]["trace"]["directory"],
            "runtime.trace.mode": model["runtime"]["trace"]["mode"],
            "runtime.trace.write_prompt": model["runtime"]["trace"]["write_prompt"],
            "runtime.trace.write_output": model["runtime"]["trace"]["write_output"],
            "runtime.trace.write_context": model["runtime"]["trace"]["write_context"],
            "runtime.trace.write_summary": model["runtime"]["trace"]["write_summary"],
            "runtime.trace.redact_sensitive": model["runtime"]["trace"]["redact_sensitive"],
            "runtime.debug.context_pruning_dump": model["runtime"]["debug"]["context_pruning_dump"],
            "runtime.output.prefix": model["runtime"]["output"]["prefix"],
            "runtime.output.include_title_header": model["runtime"]["output"]["include_title_header"],
            "runtime.output.overwrite_existing": model["runtime"]["output"]["overwrite_existing"],
            "runtime.output.filename_max_length": str(model["runtime"]["output"]["filename_max_length"]),
            "runtime.output.empty_filename_fallback": model["runtime"]["output"]["empty_filename_fallback"],
            "runtime.merge.normalize_soft_line_breaks": model["runtime"]["merge"]["normalize_soft_line_breaks"],
        }
        for key, value in data.items():
            self.vars[key].set(value)

        self._set_text_value("project.bid_requirements_text", model["project"]["bid_requirements_text"])
        self._set_text_value("project.scoring_criteria_text", model["project"]["scoring_criteria_text"])
        self._set_text_value("writing.role_text", model["writing"]["role_text"])
        self._set_text_value("writing.hard_constraints_text", "\n".join(model["writing"]["hard_constraints"]))
        self._set_text_value("writing.extra_rules_text", "\n".join(model["writing"]["extra_rules"]))
        self._update_mode_visibility()
        self._update_processing_visibility()

    def _set_text_value(self, key: str, value: str) -> None:
        widget = self.text_widgets[key]
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value or "")

    def _get_text_value(self, key: str) -> str:
        return self.text_widgets[key].get("1.0", tk.END).strip()

    def _collect_model(self) -> dict[str, Any]:
        return {
            "project": {
                "root_dir": self.vars["project.root_dir"].get().strip(),
                "bidder_name": self.vars["project.bidder_name"].get().strip(),
                "outline_file": self.vars["project.outline_file"].get().strip(),
                "bid_requirements_mode": self.vars["project.bid_requirements_mode"].get().strip() or "file",
                "bid_requirements_file": self.vars["project.bid_requirements_file"].get().strip(),
                "bid_requirements_text": self._get_text_value("project.bid_requirements_text"),
                "scoring_criteria_mode": self.vars["project.scoring_criteria_mode"].get().strip() or "file",
                "scoring_criteria_file": self.vars["project.scoring_criteria_file"].get().strip(),
                "scoring_criteria_text": self._get_text_value("project.scoring_criteria_text"),
                "output_dir": self.vars["project.output_dir"].get().strip(),
            },
            "writing": {
                "role_mode": self.vars["writing.role_mode"].get().strip() or "file",
                "role_file": self.vars["writing.role_file"].get().strip(),
                "role_text": self._get_text_value("writing.role_text"),
                "target_words_default": self.vars["writing.target_words.default"].get().strip(),
                "target_words_min": self.vars["writing.target_words.min"].get().strip(),
                "target_words_max": self.vars["writing.target_words.max"].get().strip(),
                "target_words_step": self.vars["writing.target_words.step"].get().strip(),
                "target_words_upper_ratio": self.vars["writing.target_words.upper_ratio"].get().strip(),
                "output_format": self.vars["writing.output_format"].get(),
                "first_line_template": self.vars["writing.first_line_template"].get(),
                "allow_markdown_headings": bool(self.vars["writing.allow_markdown_headings"].get()),
                "allow_english_terms": bool(self.vars["writing.allow_english_terms"].get()),
                "max_tables_per_section": self.vars["writing.max_tables_per_section"].get().strip(),
                "max_mermaid_flowcharts_per_section": self.vars["writing.max_mermaid_flowcharts_per_section"].get().strip(),
                "summary_title": self.vars["writing.summary_title"].get(),
                "hard_constraints": self._split_lines(self._get_text_value("writing.hard_constraints_text")),
                "extra_rules": self._split_lines(self._get_text_value("writing.extra_rules_text")),
            },
            "processing": {
                "path": self.vars["processing.path"].get().strip() or "auto",
                "context_view": {
                    "include_ancestors": bool(self.vars["processing.context_view.include_ancestors"].get()),
                    "include_siblings": bool(self.vars["processing.context_view.include_siblings"].get()),
                    "max_siblings": self.vars["processing.context_view.max_siblings"].get().strip(),
                },
                "project_background": {
                    "enabled": bool(self.vars["processing.project_background.enabled"].get()),
                    "max_chars": self.vars["processing.project_background.max_chars"].get().strip(),
                },
                "full_context": {
                    "chapter_writing_plan": {
                        "enabled": bool(self.vars["processing.full_context.chapter_writing_plan.enabled"].get()),
                        "max_chars": self.vars["processing.full_context.chapter_writing_plan.max_chars"].get().strip(),
                    },
                },
                "auto": {
                    "requirements_top_k": self.vars["processing.auto.requirements_top_k"].get().strip(),
                    "scoring_parse_mode": self.vars["processing.auto.scoring_parse_mode"].get().strip(),
                    "scoring_max_rows": self.vars["processing.auto.scoring_max_rows"].get().strip(),
                    "retrieval": {
                        "lexical_enabled": bool(self.vars["processing.auto.retrieval.lexical_enabled"].get()),
                        "vector_enabled": bool(self.vars["processing.auto.retrieval.vector_enabled"].get()),
                        "top_k_lexical": self.vars["processing.auto.retrieval.top_k_lexical"].get().strip(),
                        "top_k_fused": self.vars["processing.auto.retrieval.top_k_fused"].get().strip(),
                        "top_k_final": self.vars["processing.auto.retrieval.top_k_final"].get().strip(),
                        "min_fused_score": self.vars["processing.auto.retrieval.min_fused_score"].get().strip(),
                    },
                },
            },
            "models": {
                "generation": {
                    "model": self.vars["models.generation.model"].get().strip(),
                    "temperature": self.vars["models.generation.temperature"].get().strip(),
                    "max_tokens": self.vars["models.generation.max_tokens"].get().strip(),
                    "timeout_seconds": self.vars["models.generation.timeout_seconds"].get().strip(),
                    "max_retries": self.vars["models.generation.max_retries"].get().strip(),
                    "top_p": self.vars["models.generation.top_p"].get().strip(),
                    "seed": self.vars["models.generation.seed"].get().strip(),
                },
                "pruning": {
                    "model": self.vars["models.pruning.model"].get().strip(),
                    "temperature": self.vars["models.pruning.temperature"].get().strip(),
                    "max_tokens": self.vars["models.pruning.max_tokens"].get().strip(),
                    "timeout_seconds": self.vars["models.pruning.timeout_seconds"].get().strip(),
                    "max_retries": self.vars["models.pruning.max_retries"].get().strip(),
                    "top_p": self.vars["models.pruning.top_p"].get().strip(),
                    "seed": self.vars["models.pruning.seed"].get().strip(),
                },
                "embedding": {
                    "model": self.vars["models.embedding.model"].get().strip(),
                    "batch_size": self.vars["models.embedding.batch_size"].get().strip(),
                    "cache_dir": self.vars["models.embedding.cache_dir"].get().strip(),
                    "rebuild_on_source_change": bool(self.vars["models.embedding.rebuild_on_source_change"].get()),
                    "query_prefix": self.vars["models.embedding.query_prefix"].get(),
                    "document_prefix": self.vars["models.embedding.document_prefix"].get(),
                },
            },
            "runtime": {
                "stream": {
                    "enabled": bool(self.vars["runtime.stream.enabled"].get()),
                    "idle_timeout_seconds": self.vars["runtime.stream.idle_timeout_seconds"].get().strip(),
                },
                "trace": {
                    "enabled": bool(self.vars["runtime.trace.enabled"].get()),
                    "directory": self.vars["runtime.trace.directory"].get().strip(),
                    "mode": self.vars["runtime.trace.mode"].get().strip(),
                    "write_prompt": bool(self.vars["runtime.trace.write_prompt"].get()),
                    "write_output": bool(self.vars["runtime.trace.write_output"].get()),
                    "write_context": bool(self.vars["runtime.trace.write_context"].get()),
                    "write_summary": bool(self.vars["runtime.trace.write_summary"].get()),
                    "redact_sensitive": bool(self.vars["runtime.trace.redact_sensitive"].get()),
                },
                "debug": {
                    "context_pruning_dump": bool(self.vars["runtime.debug.context_pruning_dump"].get()),
                },
                "output": {
                    "prefix": self.vars["runtime.output.prefix"].get(),
                    "include_title_header": bool(self.vars["runtime.output.include_title_header"].get()),
                    "overwrite_existing": bool(self.vars["runtime.output.overwrite_existing"].get()),
                    "filename_max_length": self.vars["runtime.output.filename_max_length"].get().strip(),
                    "empty_filename_fallback": self.vars["runtime.output.empty_filename_fallback"].get().strip(),
                },
                "merge": {
                    "normalize_soft_line_breaks": bool(self.vars["runtime.merge.normalize_soft_line_breaks"].get()),
                },
            },
        }

    @staticmethod
    def _split_lines(value: str) -> list[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self.after_idle(self._refresh_side_panel)

    def _refresh_side_panel(self) -> None:
        self._refresh_pending = False
        if self.document is None:
            return
        model = self._collect_model()
        messages = self.document.validate(model)
        summary_lines = summarize_model(model, self.document.env_status)

        self._set_text_readonly(self.summary_text, "\n".join(summary_lines))
        self._set_text_readonly(self.validation_text, self._format_validation(messages))

        yaml_text: str
        try:
            yaml_text = self.document.render_yaml(model)
        except Exception as exc:
            yaml_text = f"# YAML 预览生成失败\n# {exc}\n"
        self._set_text_readonly(self.yaml_preview, yaml_text)

        is_dirty = yaml_text != self._saved_yaml
        base_status = "未保存变更" if is_dirty else "配置已同步"
        self.status_var.set(base_status)

    def _format_validation(self, messages: list[ValidationMessage]) -> str:
        if not messages:
            return "未发现问题。"
        prefix = {"error": "[错误]", "warning": "[警告]", "info": "[信息]"}
        return "\n".join(f"{prefix.get(item.level, '[信息]')} {item.text}" for item in messages)

    def _set_text_readonly(self, widget: tk.Text, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state=tk.DISABLED)

    def _update_connection_panel(self) -> None:
        if self.document is None:
            return
        self.connection_text_var.set(
            "\n".join(
                [
                    self._format_connection_line("generation", self.document.env_status["generation"]),
                    self._format_connection_line("pruning", self.document.env_status["pruning"]),
                    self._format_connection_line("embedding", self.document.env_status["embedding"]),
                ]
            )
        )

    @staticmethod
    def _format_connection_line(name: str, status: ConnectionStatus) -> str:
        if status.configured:
            source = f"（来源：{status.source}）" if status.source else ""
            return f"{name}: 已检测到连接配置 {source}"
        return f"{name}: 未检测到连接配置"

    def _update_mode_visibility(self) -> None:
        self._toggle_mode_frames(
            self.vars["project.bid_requirements_mode"].get(),
            self.project_bid_file_frame,
            self.project_bid_text_frame,
        )
        self._toggle_mode_frames(
            self.vars["project.scoring_criteria_mode"].get(),
            self.project_score_file_frame,
            self.project_score_text_frame,
        )
        self._toggle_mode_frames(
            self.vars["writing.role_mode"].get(),
            self.role_file_frame,
            self.role_text_frame,
        )

    def _toggle_mode_frames(self, mode: str, file_frame: tk.Misc, text_frame: tk.Misc) -> None:
        if mode == "inline":
            file_frame.grid_remove()
            text_frame.grid()
        else:
            text_frame.grid_remove()
            file_frame.grid()

    def _update_processing_visibility(self) -> None:
        path = self.vars["processing.path"].get().strip().lower()

        for frame in (
            self.processing_full_context_frame,
            self.processing_context_view_frame,
            self.processing_project_background_frame,
            self.processing_chapter_plan_frame,
            self.processing_req_frame,
            self.processing_scoring_frame,
        ):
            frame.pack_forget()

        if path == "full_context":
            self.processing_full_context_frame.pack(fill=tk.X, pady=(0, 12))
            self.processing_project_background_frame.pack(fill=tk.X, pady=(0, 12))
            self.processing_chapter_plan_frame.pack(fill=tk.X, pady=(0, 12))
        else:
            self.processing_context_view_frame.pack(fill=tk.X, pady=(0, 12))
            self.processing_project_background_frame.pack(fill=tk.X, pady=(0, 12))
            self.processing_req_frame.pack(fill=tk.X, pady=(0, 12))
            self.processing_scoring_frame.pack(fill=tk.X, pady=(0, 12))
        self._schedule_refresh()

    def _show_current_section(self) -> None:
        selected = self.section_var.get()
        for name, page in self.section_pages.items():
            if name == selected:
                page.tkraise()

    def _reload_from_disk(self) -> None:
        if self._has_unsaved_changes():
            if not messagebox.askyesno("确认", "当前有未保存变更，确定要从磁盘重新载入吗？", parent=self):
                return
        self._load_document(self.document.config_path if self.document else self.active_config_path)

    def _has_unsaved_changes(self) -> bool:
        if self.document is None:
            return False
        try:
            return self.document.render_yaml(self._collect_model()) != self._saved_yaml
        except Exception:
            return True

    def _save_current(self) -> None:
        self._save(target_path=self.document.config_path if self.document else self.active_config_path, ask_switch=False)

    def _save_as(self) -> None:
        initial_path = self.document.config_path if self.document else self.active_config_path
        selected = filedialog.asksaveasfilename(
            parent=self,
            initialdir=str(initial_path.parent),
            initialfile=initial_path.name,
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml *.yml")],
        )
        if not selected:
            return
        self._save(target_path=Path(selected), ask_switch=True)

    def _save(self, *, target_path: Path, ask_switch: bool) -> None:
        if self.document is None:
            return

        model = self._collect_model()
        messages = self.document.validate(model)
        errors = [item for item in messages if item.level == "error"]
        if errors:
            messagebox.showerror("校验失败", self._format_validation(errors), parent=self)
            return

        try:
            saved_path = self.document.save(model, target_path=target_path, create_backup=True)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return

        self._saved_yaml = self.document.render_yaml()
        self.current_file_var.set(f"当前文件：{saved_path}")
        self.result["saved_path"] = saved_path

        if saved_path.resolve() == self.active_config_path.resolve():
            self.result["apply_path"] = saved_path
            self.status_var.set("已保存，关闭窗口后会自动重载当前配置")
        elif ask_switch and messagebox.askyesno("保存成功", "已另存为新配置，是否在关闭窗口后切换到这个配置？", parent=self):
            self.result["apply_path"] = saved_path
            self.status_var.set("已另存为，关闭窗口后会切换到新配置")
        else:
            self.status_var.set("已保存")

        self._load_document(saved_path)

    def _on_close(self) -> None:
        if self._has_unsaved_changes():
            if not messagebox.askyesno("确认关闭", "当前有未保存变更，确定要关闭吗？", parent=self):
                return
        self.destroy()
