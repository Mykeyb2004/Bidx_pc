from __future__ import annotations

from dataclasses import dataclass
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

from .fact_cards import FactCard, FactCardDraft, FactCardSelection
from .gui import (
    _bootstyle_kwargs,
    apply_window_surface,
    setup_gui_theme,
    style_canvas_widget,
    style_text_widget,
)


FACT_CARD_LIBRARY_GEOMETRY = "980x820"
FACT_CARD_LIBRARY_MIN_SIZE = (860, 720)
FACT_CARD_LIBRARY_CURRENT_TREE_ROWS = 7
FACT_CARD_LIBRARY_MANUAL_EDITOR_MIN_HEIGHT = 400


@dataclass(frozen=True)
class FactCardExtractionDialogResult:
    instruction: str
    drafts: list[FactCardDraft]


class ScrollableBody(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
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
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)


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
        self._usage_vars: dict[str, tk.StringVar] = {}

        initial_map = {selection.card_id: selection.usage for selection in initial_selections or []}

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            actions,
            text="全选为参考",
            command=self.select_all_reference,
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
            selected_var = tk.BooleanVar(value=card.id in initial_map)
            usage_var = tk.StringVar(value=initial_map.get(card.id, "reference"))
            self._selection_vars[card.id] = selected_var
            self._usage_vars[card.id] = usage_var

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

            ttk.Label(title_row, text=f"来源：{self._format_source(card)}").pack(side=tk.LEFT, padx=(12, 0))

            usage_combo = ttk.Combobox(
                title_row,
                textvariable=usage_var,
                state="readonly",
                width=10,
                values=("strong", "reference"),
            )
            usage_combo.pack(side=tk.RIGHT)

            ttk.Label(title_row, text="用途：").pack(side=tk.RIGHT, padx=(0, 6))

            ttk.Label(
                row,
                text=card.content,
                justify=tk.LEFT,
                wraplength=620,
            ).pack(fill=tk.X, padx=(24, 0), pady=(4, 0))

            def _sync_usage(*_args, combo=usage_combo, flag=selected_var):
                combo.configure(state="readonly" if flag.get() else "disabled")

            selected_var.trace_add("write", _sync_usage)
            _sync_usage()

    @staticmethod
    def _format_source(card: FactCard) -> str:
        if card.source.type == "chapter_extract" and card.source.chapter_path:
            return f"提炼 · {card.source.chapter_path}"
        return "手工"

    def select_all_reference(self) -> None:
        for card_id, selected_var in self._selection_vars.items():
            selected_var.set(True)
            self._usage_vars[card_id].set("reference")

    def clear_all(self) -> None:
        for selected_var in self._selection_vars.values():
            selected_var.set(False)

    def get_selections(self) -> list[FactCardSelection]:
        selections: list[FactCardSelection] = []
        for card in self.cards:
            if not self._selection_vars.get(card.id) or not self._selection_vars[card.id].get():
                continue
            selections.append(
                FactCardSelection(
                    card_id=card.id,
                    usage=self._usage_vars.get(card.id, tk.StringVar(value="reference")).get() or "reference",
                )
            )
        return selections


class FactCardDraftEditor(ttk.Frame):
    def __init__(
        self,
        master,
        drafts: list[FactCardDraft] | None = None,
        *,
        list_min_height: int | None = None,
    ):
        super().__init__(master)
        self._rows: list[dict[str, object]] = []

        self.scrollable = ScrollableBody(self)
        if list_min_height is not None:
            self.scrollable.canvas.configure(height=list_min_height)
        self.scrollable.pack(fill=tk.BOTH, expand=True)

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
        self.add_row(FactCardDraft(name="", content="", category=""))

    def add_row(self, draft: FactCardDraft) -> None:
        row_data: dict[str, object] = {}
        container = ttk.LabelFrame(self.scrollable.body, text=f"卡片 {len(self._rows) + 1}", padding=(10, 8))
        container.pack(fill=tk.X, pady=(0, 10))
        row_data["container"] = container
        row_data["card_id"] = draft.card_id

        top_row = ttk.Frame(container)
        top_row.pack(fill=tk.X)

        name_var = tk.StringVar(value=draft.name)
        category_var = tk.StringVar(value=draft.category)
        row_data["name_var"] = name_var
        row_data["category_var"] = category_var

        ttk.Label(top_row, text="名称").pack(side=tk.LEFT)
        ttk.Entry(top_row, textvariable=name_var, width=22).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(top_row, text="分类").pack(side=tk.LEFT)
        ttk.Entry(top_row, textvariable=category_var, width=18).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(
            top_row,
            text="删除",
            command=lambda data=row_data: self.remove_row(data),
            width=8,
            **_bootstyle_kwargs("secondary"),
        ).pack(side=tk.RIGHT)

        ttk.Label(container, text="内容").pack(anchor=tk.W, pady=(8, 4))
        content_text = tk.Text(container, height=4, width=72)
        style_text_widget(content_text)
        content_text.pack(fill=tk.X)
        content_text.insert("1.0", draft.content)
        row_data["content_text"] = content_text

        self._rows.append(row_data)

    def remove_row(self, row_data: dict[str, object]) -> None:
        container = row_data.get("container")
        if container is not None:
            container.destroy()
        self._rows = [row for row in self._rows if row is not row_data]
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
            drafts.append(
                FactCardDraft(
                    card_id=str(row.get("card_id", "") or "").strip(),
                    name=name,
                    content=content,
                    category=category,
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
        initial_drafts = list(initial_drafts or [])
        has_initial_drafts = bool(initial_drafts)
        self._has_extracted = has_initial_drafts
        self._is_extracting = False
        self._last_extracted_instruction = initial_instruction if has_initial_drafts else ""

        self.title("提炼章节事实卡片")
        self.geometry("980x760")
        self.minsize(820, 620)
        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text=f"章节：{heading_title}", style="SectionTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="先填写提炼要求，再生成草稿；如结果不满意，可直接修改要求并重新提炼。",
            justify=tk.LEFT,
            wraplength=900,
        ).pack(anchor=tk.W, pady=(6, 10))

        instruction_frame = ttk.LabelFrame(container, text="提炼要求", padding=(10, 8))
        instruction_frame.pack(fill=tk.X)

        self.instruction_text = tk.Text(instruction_frame, height=5, width=90)
        style_text_widget(self.instruction_text)
        self.instruction_text.pack(fill=tk.X)
        self.instruction_text.insert("1.0", initial_instruction)

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
            else "请先输入提炼要求，再点击“提炼草稿”。"
        )
        self.status_var = tk.StringVar(value=initial_status_text)
        ttk.Label(action_row, textvariable=self.status_var).pack(side=tk.LEFT, padx=(10, 0))

        editor_frame = ttk.LabelFrame(container, text="提炼草稿", padding=(10, 8))
        editor_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.editor = FactCardDraftEditor(editor_frame, drafts=initial_drafts)
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
        return self.instruction_text.get("1.0", tk.END).strip()

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

        core_drafts = drafts[:1]
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
        self.geometry("920x720")
        self.minsize(780, 560)
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


class FactCardLibraryDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, cards: list[FactCard]):
        super().__init__(parent)
        setup_gui_theme(self)
        apply_window_surface(self)
        self.result: Optional[list[FactCardDraft]] = None
        self.cards = cards

        self.title("事实卡片库")
        self.geometry(FACT_CARD_LIBRARY_GEOMETRY)
        self.minsize(*FACT_CARD_LIBRARY_MIN_SIZE)
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

        columns = ("name", "source", "category", "content")
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=FACT_CARD_LIBRARY_CURRENT_TREE_ROWS,
        )
        tree.heading("name", text="名称")
        tree.heading("source", text="来源")
        tree.heading("category", text="分类")
        tree.heading("content", text="内容")
        tree.column("name", width=180, anchor=tk.W)
        tree.column("source", width=170, anchor=tk.W)
        tree.column("category", width=100, anchor=tk.W)
        tree.column("content", width=420, anchor=tk.W)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)

        for card in cards:
            source_text = "手工" if card.source.type == "manual" else f"提炼 · {card.source.chapter_path or '-'}"
            tree.insert(
                "",
                tk.END,
                values=(card.name, source_text, card.category or "-", card.content),
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
