from __future__ import annotations

from dataclasses import dataclass
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

from .fact_cards import (
    FactCard,
    FactCardDraft,
    FactCardSelection,
    normalize_fact_card_enforcement,
    normalize_fact_card_scope,
)
from .gui import (
    _bootstyle_kwargs,
    _compute_screen_limited_dialog_size,
    _set_centered_window_geometry,
    apply_window_surface,
    setup_gui_theme,
    style_canvas_widget,
    style_text_widget,
)


FACT_CARD_LIBRARY_WIDTH = 980
FACT_CARD_LIBRARY_HEIGHT = 820
FACT_CARD_LIBRARY_MIN_SIZE = (860, 720)
FACT_CARD_LIBRARY_CURRENT_TREE_ROWS = 7
FACT_CARD_LIBRARY_MANUAL_EDITOR_MIN_HEIGHT = 400
FACT_CARD_EXTRACTION_WORKSPACE_WIDTH = 1080
FACT_CARD_EXTRACTION_WORKSPACE_HEIGHT = 760
FACT_CARD_EXTRACTION_WORKSPACE_MIN_SIZE = (1080, 620)
FACT_CARD_DRAFT_REVIEW_WIDTH = 920
FACT_CARD_DRAFT_REVIEW_HEIGHT = 720
FACT_CARD_DRAFT_REVIEW_MIN_SIZE = (780, 560)
FACT_CARD_MANUAL_WIDTH = 920
FACT_CARD_MANUAL_HEIGHT = 520
FACT_CARD_MANUAL_MIN_SIZE = (820, 460)
FACT_CARD_INSTRUCTION_PLACEHOLDER_COLOR = "#6b7280"


@dataclass(frozen=True)
class FactCardExtractionDialogResult:
    instruction: str
    drafts: list[FactCardDraft]


class ScrollableBody(ttk.Frame):
    def __init__(self, master, *, stretch_height: bool = False):
        super().__init__(master)
        self.stretch_height = stretch_height
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        style_canvas_widget(self.canvas)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_body_configure(self, _event):
        if self.stretch_height:
            self._resize_body_window(self.canvas.winfo_width(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._resize_body_window(event.width, event.height)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_body_window(self, width: int, height: int) -> None:
        self.canvas.itemconfigure(self.window_id, width=width)
        if self.stretch_height:
            self.canvas.itemconfigure(self.window_id, height=max(height, self.body.winfo_reqheight()))


class FactCardSelectionPanel(ttk.LabelFrame):
    def __init__(
        self,
        master,
        *,
        cards: list[FactCard],
        initial_selections: list[FactCardSelection] | None = None,
    ):
        super().__init__(master, text="事实卡片选择", padding=(12, 10))
        self.cards = cards
        self._selection_vars: dict[str, tk.BooleanVar] = {}

        initial_card_ids = {selection.card_id for selection in initial_selections or []}

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            actions,
            text="全选局部卡片",
            command=self.select_all,
            width=12,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="全部清空",
            command=self.clear_all,
            width=10,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=(8, 0))

        if not cards:
            ttk.Label(
                self,
                text="当前还没有可用事实卡片，可先在“管理事实卡片”中录入或提炼。",
                justify=tk.LEFT,
            ).pack(fill=tk.X)
            return

        scrollable = ScrollableBody(self)
        scrollable.pack(fill=tk.BOTH, expand=True)

        for card in cards:
            selected_var = tk.BooleanVar(value=card.id in initial_card_ids)
            self._selection_vars[card.id] = selected_var

            row = ttk.Frame(scrollable.body, padding=(0, 6))
            row.pack(fill=tk.X)

            title_row = ttk.Frame(row)
            title_row.pack(fill=tk.X)
            check = ttk.Checkbutton(
                title_row,
                text=card.name,
                variable=selected_var,
            )
            check.pack(side=tk.LEFT, anchor=tk.W)

            meta = f"{self._format_source(card)} · {card.scope}/{card.enforcement}"
            ttk.Label(title_row, text=f"来源：{meta}").pack(side=tk.LEFT, padx=(12, 0))

            ttk.Label(
                row,
                text=card.content,
                justify=tk.LEFT,
                wraplength=620,
            ).pack(fill=tk.X, padx=(24, 0), pady=(4, 0))

    @staticmethod
    def _format_source(card: FactCard) -> str:
        if card.source.type == "chapter_extract" and card.source.chapter_path:
            return f"提炼 · {card.source.chapter_path}"
        return "手工"

    def select_all(self) -> None:
        for selected_var in self._selection_vars.values():
            selected_var.set(True)

    def clear_all(self) -> None:
        for selected_var in self._selection_vars.values():
            selected_var.set(False)

    def get_selections(self) -> list[FactCardSelection]:
        selections: list[FactCardSelection] = []
        for card in self.cards:
            if not self._selection_vars.get(card.id) or not self._selection_vars[card.id].get():
                continue
            selections.append(FactCardSelection(card_id=card.id))
        return selections


class FactCardDraftEditor(ttk.Frame):
    def __init__(
        self,
        master,
        drafts: list[FactCardDraft] | None = None,
        *,
        list_min_height: int | None = None,
        allow_add: bool = True,
        show_card_frame: bool = True,
        max_rows: int | None = None,
        show_delete_button: bool = True,
        stretch_content: bool = False,
    ):
        super().__init__(master)
        self._rows: list[dict[str, object]] = []
        self._show_card_frame = show_card_frame
        self._max_rows = max_rows
        self._show_delete_button = show_delete_button
        self._stretch_content = stretch_content

        self.scrollable = ScrollableBody(self, stretch_height=stretch_content)
        if list_min_height is not None:
            self.scrollable.canvas.configure(height=list_min_height)
        self.scrollable.pack(fill=tk.BOTH, expand=True)

        if allow_add:
            action_bar = ttk.Frame(self)
            action_bar.pack(fill=tk.X, pady=(8, 0))
            ttk.Button(
                action_bar,
                text="新增卡片",
                command=self.add_empty_row,
                width=10,
                **_bootstyle_kwargs("secondary"),
            ).pack(side=tk.LEFT)

        for draft in drafts or []:
            self.add_row(draft)
        if not self._rows:
            self.add_empty_row()

    def replace_drafts(self, drafts: list[FactCardDraft] | None = None) -> None:
        for row in self._rows:
            container = row.get("container")
            if container is not None:
                container.destroy()
        self._rows = []
        for draft in drafts or []:
            self.add_row(draft)
        if not self._rows:
            self.add_empty_row()

    def add_empty_row(self) -> None:
        self.add_row(FactCardDraft(name="", content="", category="", scope="local", enforcement="reference"))

    def add_row(self, draft: FactCardDraft) -> None:
        if self._max_rows is not None and len(self._rows) >= self._max_rows:
            return

        row_data: dict[str, object] = {}
        if self._show_card_frame:
            container = ttk.LabelFrame(self.scrollable.body, text=f"卡片 {len(self._rows) + 1}", padding=(10, 8))
        else:
            container = ttk.Frame(self.scrollable.body, padding=(0, 0))
        container.pack(**self._container_pack_options(self._stretch_content))
        row_data["container"] = container
        row_data["card_id"] = draft.card_id

        top_row = ttk.Frame(container)
        top_row.pack(fill=tk.X)
        top_row.columnconfigure(8, weight=1)

        name_var = tk.StringVar(value=draft.name)
        category_var = tk.StringVar(value=draft.category)
        scope_var = tk.StringVar(value=draft.scope or "local")
        enforcement_var = tk.StringVar(value=draft.enforcement or "reference")
        row_data["name_var"] = name_var
        row_data["category_var"] = category_var
        row_data["scope_var"] = scope_var
        row_data["enforcement_var"] = enforcement_var

        ttk.Label(top_row, text="名称").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(top_row, textvariable=name_var, width=22).grid(row=0, column=1, sticky=tk.W, padx=(6, 12))
        ttk.Label(top_row, text="分类").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(top_row, textvariable=category_var, width=18).grid(row=0, column=3, sticky=tk.W, padx=(6, 12))
        ttk.Label(top_row, text="作用域").grid(row=0, column=4, sticky=tk.W)
        ttk.Combobox(
            top_row,
            textvariable=scope_var,
            values=("global", "local"),
            state="readonly",
            width=9,
        ).grid(row=0, column=5, sticky=tk.W, padx=(6, 12))
        ttk.Label(top_row, text="约束").grid(row=0, column=6, sticky=tk.W)
        ttk.Combobox(
            top_row,
            textvariable=enforcement_var,
            values=("strong", "reference"),
            state="readonly",
            width=11,
        ).grid(row=0, column=7, sticky=tk.W, padx=(6, 12))
        if self._show_delete_button:
            ttk.Button(
                top_row,
                text="删除",
                command=lambda data=row_data: self.remove_row(data),
                width=8,
                **_bootstyle_kwargs("secondary"),
            ).grid(row=0, column=9, sticky=tk.E)

        ttk.Label(container, text="内容").pack(anchor=tk.W, pady=(8, 4))
        content_text = tk.Text(container, height=4, width=72)
        style_text_widget(content_text)
        content_text.pack(**self._content_pack_options(self._stretch_content))
        content_text.insert("1.0", draft.content)
        row_data["content_text"] = content_text

        self._rows.append(row_data)

    @staticmethod
    def _container_pack_options(stretch_content: bool) -> dict[str, object]:
        return {
            "fill": tk.BOTH if stretch_content else tk.X,
            "expand": bool(stretch_content),
            "pady": (0, 10),
        }

    @staticmethod
    def _content_pack_options(stretch_content: bool) -> dict[str, object]:
        return {
            "fill": tk.BOTH if stretch_content else tk.X,
            "expand": bool(stretch_content),
        }

    def remove_row(self, row_data: dict[str, object]) -> None:
        if not messagebox.askyesno("确认删除", "确定删除这张事实卡片草稿吗？", parent=self.winfo_toplevel()):
            return
        container = row_data.get("container")
        if container is not None:
            container.destroy()
        self._rows = [row for row in self._rows if row is not row_data]
        if getattr(self, "_show_card_frame", True):
            for index, row in enumerate(self._rows, start=1):
                container = row.get("container")
                if container is not None:
                    container.configure(text=f"卡片 {index}")
        if not self._rows:
            self.add_empty_row()

    def get_drafts(self) -> list[FactCardDraft]:
        drafts: list[FactCardDraft] = []
        for row in self._rows:
            name = str(row["name_var"].get()).strip()
            category = str(row["category_var"].get()).strip()
            content = row["content_text"].get("1.0", tk.END).strip()
            if not name and not content and not category:
                continue
            if not name or not content:
                raise ValueError("每张卡片都需要同时填写名称和内容。")
            scope = normalize_fact_card_scope(str(row["scope_var"].get()).strip())
            enforcement = normalize_fact_card_enforcement(str(row["enforcement_var"].get()).strip())
            if not scope:
                raise ValueError("每张卡片都需要选择作用域：global 或 local。")
            if not enforcement:
                raise ValueError("每张卡片都需要选择约束：strong 或 reference。")
            drafts.append(
                FactCardDraft(
                    card_id=str(row.get("card_id", "") or "").strip(),
                    name=name,
                    content=content,
                    category=category,
                    scope=scope,
                    enforcement=enforcement,
                )
            )
        return drafts


class FactCardExtractionWorkspaceDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        heading_title: str,
        initial_instruction: str,
        extract_callback: Callable[[str], Any],
        initial_drafts: Optional[list[FactCardDraft]] = None,
        initial_status: str = "",
    ):
        super().__init__(parent)
        setup_gui_theme(self)
        apply_window_surface(self)
        self.extract_callback = extract_callback
        self.result: Optional[FactCardExtractionDialogResult] = None
        initial_drafts = self._current_drafts(list(initial_drafts or []))
        has_initial_drafts = bool(initial_drafts)
        self._default_instruction = initial_instruction.strip()
        self._has_extracted = has_initial_drafts
        self._is_extracting = False
        self._last_extracted_instruction = initial_instruction if has_initial_drafts else ""
        self._instruction_placeholder_active = False
        self._instruction_normal_foreground = ""

        self.title("提炼章节事实卡片")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=FACT_CARD_EXTRACTION_WORKSPACE_WIDTH,
            desired_height=FACT_CARD_EXTRACTION_WORKSPACE_HEIGHT,
            min_width=FACT_CARD_EXTRACTION_WORKSPACE_MIN_SIZE[0],
            min_height=FACT_CARD_EXTRACTION_WORKSPACE_MIN_SIZE[1],
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text=f"章节：{heading_title}", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="先填写提炼要求，再生成草稿；如结果不满意，可直接修改要求并重新提炼。",
            justify=tk.LEFT,
            wraplength=1000,
        ).pack(anchor=tk.W, pady=(6, 10))

        instruction_frame = ttk.LabelFrame(container, text="提炼要求", padding=(10, 8))
        instruction_frame.pack(fill=tk.X)

        self.instruction_text = tk.Text(instruction_frame, height=5, width=90)
        style_text_widget(self.instruction_text)
        self.instruction_text.pack(fill=tk.X)
        self._instruction_normal_foreground = str(self.instruction_text.cget("foreground") or "")
        self.instruction_text.bind("<FocusIn>", self._on_instruction_focus_in)
        self.instruction_text.bind("<FocusOut>", self._on_instruction_focus_out)
        if has_initial_drafts and initial_instruction.strip():
            self.instruction_text.insert("1.0", initial_instruction)
        else:
            self._show_instruction_placeholder()

        action_row = ttk.Frame(instruction_frame)
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.extract_button = ttk.Button(
            action_row,
            text="重新提炼" if has_initial_drafts else "提炼草稿",
            command=self._on_extract,
            width=12,
            **_bootstyle_kwargs("primary"),
        )
        self.extract_button.pack(side=tk.LEFT)

        initial_status_text = (
            initial_status
            if has_initial_drafts and initial_status
            else "可直接使用默认提炼要求，也可输入自定义要求后点击“提炼草稿”。"
        )
        self.status_var = tk.StringVar(value=initial_status_text)
        ttk.Label(action_row, textvariable=self.status_var).pack(side=tk.LEFT, padx=(10, 0))

        editor_frame = ttk.LabelFrame(container, text="提炼草稿", padding=(10, 8))
        editor_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.editor = FactCardDraftEditor(editor_frame, drafts=initial_drafts, **self._editor_options())
        self.editor.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(anchor=tk.E, pady=(12, 0))
        ttk.Button(
            button_row,
            text="取消",
            command=self._on_cancel,
            width=10,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=6)
        self.save_button = ttk.Button(
            button_row,
            text="保存卡片",
            command=self._on_save,
            width=10,
            **_bootstyle_kwargs("primary"),
        )
        self.save_button.pack(side=tk.LEFT)

    def _get_instruction(self) -> str:
        if getattr(self, "_instruction_placeholder_active", False):
            return self._default_instruction
        return self.instruction_text.get("1.0", tk.END).strip() or self._default_instruction

    def _show_instruction_placeholder(self) -> None:
        self.instruction_text.delete("1.0", tk.END)
        if self._default_instruction:
            self.instruction_text.insert("1.0", self._default_instruction)
            self.instruction_text.configure(foreground=FACT_CARD_INSTRUCTION_PLACEHOLDER_COLOR)
            self._instruction_placeholder_active = True

    def _hide_instruction_placeholder(self) -> None:
        if not getattr(self, "_instruction_placeholder_active", False):
            return
        self.instruction_text.delete("1.0", tk.END)
        self.instruction_text.configure(foreground=self._instruction_normal_foreground)
        self._instruction_placeholder_active = False

    def _on_instruction_focus_in(self, _event) -> None:
        self._hide_instruction_placeholder()

    def _on_instruction_focus_out(self, _event) -> None:
        if not self.instruction_text.get("1.0", tk.END).strip():
            self._show_instruction_placeholder()

    def _on_extract(self) -> None:
        if self._is_extracting:
            return

        instruction = self._get_instruction()
        if not instruction:
            messagebox.showwarning("提示", "请先输入提炼要求。", parent=self)
            return

        self._set_extracting_state(True)
        threading.Thread(
            target=lambda: self._run_extract_worker(instruction),
            daemon=True,
        ).start()

    def _run_extract_worker(self, instruction: str) -> None:
        try:
            extract_result = self.extract_callback(instruction)
            drafts, empty_detail_message = self._coerce_extract_result(extract_result)
            error_message = None
        except Exception as exc:
            drafts = []
            empty_detail_message = ""
            error_message = str(exc) or exc.__class__.__name__

        try:
            self.after(0, lambda: self._finish_extract(instruction, drafts, error_message, empty_detail_message))
        except tk.TclError:
            return

    @staticmethod
    def _coerce_extract_result(result: Any) -> tuple[list[FactCardDraft], str]:
        if result is None:
            return [], ""
        if isinstance(result, list):
            return result, ""
        drafts = getattr(result, "drafts", None)
        if isinstance(drafts, list):
            user_message = getattr(result, "user_message", None)
            if callable(user_message):
                return drafts, str(user_message() or "").strip()
            return drafts, str(getattr(result, "message", "") or "").strip()
        return [], ""

    @staticmethod
    def _current_drafts(drafts: list[FactCardDraft]) -> list[FactCardDraft]:
        return drafts[:1]

    @staticmethod
    def _editor_options() -> dict[str, object]:
        return {
            "allow_add": False,
            "show_card_frame": False,
            "max_rows": 1,
            "show_delete_button": True,
            "stretch_content": True,
        }

    def _finish_extract(
        self,
        instruction: str,
        drafts: list[FactCardDraft],
        error_message: Optional[str],
        empty_detail_message: str = "",
    ) -> None:
        self._set_extracting_state(False)
        if error_message:
            self.status_var.set("本次提炼失败，可调整要求后重试。")
            messagebox.showwarning("提示", f"提炼事实卡片失败：{error_message}", parent=self)
            return

        if not drafts:
            message = empty_detail_message or "当前未能提炼出可保存的事实卡片草稿。"
            self.status_var.set("本次未生成可保存草稿，可查看提示详情。")
            messagebox.showwarning("提示", message, parent=self)
            return

        core_drafts = self._current_drafts(drafts)
        self.editor.replace_drafts(core_drafts)
        self._has_extracted = True
        self._last_extracted_instruction = instruction
        self.extract_button.configure(text="重新提炼")
        self.status_var.set("已生成 1 张核心草稿，可继续编辑或调整要求后重提。")

    def _set_extracting_state(self, is_extracting: bool) -> None:
        self._is_extracting = is_extracting
        state = "disabled" if is_extracting else "normal"
        if hasattr(self, "extract_button"):
            self.extract_button.configure(state=state)
        if hasattr(self, "save_button"):
            self.save_button.configure(state=state)
        if hasattr(self, "status_var") and is_extracting:
            self.status_var.set("正在提炼草稿，请稍候...")

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_save(self) -> None:
        if getattr(self, "_is_extracting", False):
            messagebox.showwarning("提示", "事实卡片正在提炼中，请等待完成后再保存。", parent=self)
            return

        if not self._has_extracted:
            messagebox.showwarning("提示", "请先提炼草稿，再决定是否保存。", parent=self)
            return

        instruction = self._get_instruction()
        if instruction != self._last_extracted_instruction:
            messagebox.showwarning("提示", "提炼要求已修改，请先重新提炼草稿后再保存。", parent=self)
            return

        try:
            drafts = self.editor.get_drafts()
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc), parent=self)
            return

        self.result = FactCardExtractionDialogResult(
            instruction=self._last_extracted_instruction,
            drafts=drafts,
        )
        self.destroy()


class FactCardDraftReviewDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        heading_title: str,
        instruction: str,
        drafts: list[FactCardDraft],
    ):
        super().__init__(parent)
        setup_gui_theme(self)
        apply_window_surface(self)
        self.result: Optional[list[FactCardDraft]] = None

        self.title("提炼事实卡片草稿")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=FACT_CARD_DRAFT_REVIEW_WIDTH,
            desired_height=FACT_CARD_DRAFT_REVIEW_HEIGHT,
            min_width=FACT_CARD_DRAFT_REVIEW_MIN_SIZE[0],
            min_height=FACT_CARD_DRAFT_REVIEW_MIN_SIZE[1],
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text=f"章节：{heading_title}", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text=f"提炼要求：{instruction or '（未填写）'}",
            justify=tk.LEFT,
            wraplength=840,
        ).pack(anchor=tk.W, pady=(6, 10))

        self.editor = FactCardDraftEditor(container, drafts=drafts)
        self.editor.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(anchor=tk.E, pady=(12, 0))
        ttk.Button(
            button_row,
            text="取消",
            command=self._on_cancel,
            width=10,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            button_row,
            text="保存卡片",
            command=self._on_save,
            width=10,
            **_bootstyle_kwargs("primary"),
        ).pack(side=tk.LEFT)

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_save(self) -> None:
        try:
            self.result = self.editor.get_drafts()
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc), parent=self)
            return
        self.destroy()


class ManualFactCardDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        setup_gui_theme(self)
        apply_window_surface(self)
        self.result: Optional[FactCardDraft] = None

        self.title("新增事实卡片")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=FACT_CARD_MANUAL_WIDTH,
            desired_height=FACT_CARD_MANUAL_HEIGHT,
            min_width=FACT_CARD_MANUAL_MIN_SIZE[0],
            min_height=FACT_CARD_MANUAL_MIN_SIZE[1],
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="新增事实卡片", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="手工录入一张项目事实卡片；保存后会加入事实卡片库，后续可在生成参数中引用。",
            justify=tk.LEFT,
            wraplength=840,
        ).pack(anchor=tk.W, pady=(6, 10))

        self.editor = FactCardDraftEditor(
            container,
            drafts=[
                FactCardDraft(
                    name="",
                    content="",
                    category="",
                    scope="local",
                    enforcement="reference",
                )
            ],
            **self._editor_options(),
        )
        self.editor.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(anchor=tk.E, pady=(12, 0))
        ttk.Button(
            button_row,
            text="取消",
            command=self._on_cancel,
            width=10,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            button_row,
            text="保存卡片",
            command=self._on_save,
            width=10,
            **_bootstyle_kwargs("primary"),
        ).pack(side=tk.LEFT)

    @staticmethod
    def _editor_options() -> dict[str, object]:
        return {
            "allow_add": False,
            "show_card_frame": False,
            "max_rows": 1,
            "show_delete_button": False,
            "stretch_content": True,
        }

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_save(self) -> None:
        try:
            drafts = self.editor.get_drafts()
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc), parent=self)
            return
        if not drafts:
            messagebox.showwarning("提示", "请填写事实卡片名称和内容。", parent=self)
            return
        self.result = drafts[0]
        self.destroy()


class FactCardLibraryDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, cards: list[FactCard]):
        super().__init__(parent)
        setup_gui_theme(self)
        apply_window_surface(self)
        self.result: Optional[list[FactCardDraft]] = None
        self.cards = cards

        self.title("事实卡片库")
        window_size = _compute_screen_limited_dialog_size(
            desired_width=FACT_CARD_LIBRARY_WIDTH,
            desired_height=FACT_CARD_LIBRARY_HEIGHT,
            min_width=FACT_CARD_LIBRARY_MIN_SIZE[0],
            min_height=FACT_CARD_LIBRARY_MIN_SIZE[1],
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        _set_centered_window_geometry(self, window_size.width, window_size.height)
        self.minsize(window_size.min_width, window_size.min_height)
        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="事实卡片库管理", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="上半区展示当前卡片；下半区可直接编辑全部卡片名称、分类和内容。保存时会按下方结构化列表覆盖现有事实卡片库，并保留已有卡片来源。",
            justify=tk.LEFT,
            wraplength=900,
        ).pack(anchor=tk.W, pady=(6, 12))

        tree_frame = ttk.LabelFrame(container, text="当前卡片", padding=(8, 8))
        tree_frame.pack(fill=tk.X)

        columns = ("name", "source", "scope", "enforcement", "category", "content")
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=FACT_CARD_LIBRARY_CURRENT_TREE_ROWS,
        )
        tree.heading("name", text="名称")
        tree.heading("source", text="来源")
        tree.heading("scope", text="作用域")
        tree.heading("enforcement", text="约束")
        tree.heading("category", text="分类")
        tree.heading("content", text="内容")
        tree.column("name", width=180, anchor=tk.W)
        tree.column("source", width=170, anchor=tk.W)
        tree.column("scope", width=80, anchor=tk.W)
        tree.column("enforcement", width=90, anchor=tk.W)
        tree.column("category", width=100, anchor=tk.W)
        tree.column("content", width=320, anchor=tk.W)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)

        for card in cards:
            source_text = "手工" if card.source.type == "manual" else f"提炼 · {card.source.chapter_path or '-'}"
            tree.insert(
                "",
                tk.END,
                values=(
                    card.name,
                    source_text,
                    card.scope,
                    card.enforcement,
                    card.category or "-",
                    card.content,
                ),
            )

        edit_frame = ttk.LabelFrame(container, text="卡片库编辑", padding=(8, 8))
        edit_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        library_drafts = self._build_library_drafts(cards)
        self.editor = FactCardDraftEditor(
            edit_frame,
            drafts=library_drafts,
            list_min_height=FACT_CARD_LIBRARY_MANUAL_EDITOR_MIN_HEIGHT,
        )
        self.editor.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(anchor=tk.E, pady=(12, 0))
        ttk.Button(
            button_row,
            text="取消",
            command=self._on_cancel,
            width=10,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            button_row,
            text="保存卡片库",
            command=self._on_save,
            width=12,
            **_bootstyle_kwargs("primary"),
        ).pack(side=tk.LEFT)

    @staticmethod
    def _build_library_drafts(cards: list[FactCard]) -> list[FactCardDraft]:
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
    def _build_manual_drafts(cards: list[FactCard]) -> list[FactCardDraft]:
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
            if card.source.type == "manual"
        ]

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _on_save(self) -> None:
        try:
            self.result = self.editor.get_drafts()
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc), parent=self)
            return
        self.destroy()
