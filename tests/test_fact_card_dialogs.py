from pathlib import Path
from types import SimpleNamespace

import bid_writer.fact_card_dialogs as fact_card_dialogs
from bid_writer.fact_cards import FactCard, FactCardDraft, FactCardSource
from bid_writer.gui import MainWindow


class _FakeStatus:
    def __init__(self, value: str = "就绪"):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _FakeWidget:
    def __init__(self):
        self.configured: list[dict[str, str]] = []

    def configure(self, **kwargs):
        self.configured.append(kwargs)


class _FakeContainer(_FakeWidget):
    def __init__(self):
        super().__init__()
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def test_fact_card_extraction_workspace_dialog_save_returns_instruction_and_drafts():
    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog.result = None
    dialog._has_extracted = True
    dialog._last_extracted_instruction = "提取资质与承诺"
    dialog._get_instruction = lambda: "提取资质与承诺"
    dialog.editor = SimpleNamespace(
        get_drafts=lambda: [
            FactCardDraft(
                name="企业资质",
                content="一级资质",
                category="资质",
                scope="global",
                enforcement="strong",
            )
        ]
    )
    closed: list[str] = []
    dialog.destroy = lambda: closed.append("destroy")

    dialog._on_save()

    assert dialog.result == fact_card_dialogs.FactCardExtractionDialogResult(
        instruction="提取资质与承诺",
        drafts=[
            FactCardDraft(
                name="企业资质",
                content="一级资质",
                category="资质",
                scope="global",
                enforcement="strong",
            )
        ],
    )
    assert closed == ["destroy"]


def test_fact_card_extraction_workspace_dialog_save_requires_reextract_when_instruction_changed(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        fact_card_dialogs.messagebox,
        "showwarning",
        lambda _title, message, parent=None: warnings.append(message),
    )

    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog.result = None
    dialog._has_extracted = True
    dialog._last_extracted_instruction = "提取资质与承诺"
    dialog._get_instruction = lambda: "只提取人员信息"
    dialog.editor = SimpleNamespace(
        get_drafts=lambda: [
            FactCardDraft(
                name="企业资质",
                content="一级资质",
                category="资质",
                scope="global",
                enforcement="strong",
            )
        ]
    )
    dialog.destroy = lambda: warnings.append("destroy")

    dialog._on_save()

    assert warnings == ["提炼要求已修改，请先重新提炼草稿后再保存。"]
    assert dialog.result is None


def test_fact_card_extraction_workspace_dialog_starts_extract_in_background(monkeypatch):
    callback_calls: list[str] = []
    started_targets: list[object] = []

    class _FakeThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            started_targets.append(self.target)

    monkeypatch.setattr(fact_card_dialogs.threading, "Thread", _FakeThread)

    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog._is_extracting = False
    dialog._get_instruction = lambda: "提炼核心事实"
    dialog.extract_callback = lambda instruction: callback_calls.append(instruction)
    dialog.extract_button = _FakeWidget()
    dialog.save_button = _FakeWidget()
    dialog.status_var = _FakeStatus()

    dialog._on_extract()

    assert callback_calls == []
    assert len(started_targets) == 1
    assert dialog.extract_button.configured[-1] == {"state": "disabled"}
    assert dialog.save_button.configured[-1] == {"state": "disabled"}
    assert dialog.status_var.get() == "正在提炼草稿，请稍候..."


def test_fact_card_extraction_workspace_dialog_finish_extract_keeps_single_core_draft():
    replaced: list[list[FactCardDraft]] = []
    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog._is_extracting = True
    dialog._has_extracted = False
    dialog._last_extracted_instruction = ""
    dialog.extract_button = _FakeWidget()
    dialog.save_button = _FakeWidget()
    dialog.status_var = _FakeStatus()
    dialog.editor = SimpleNamespace(replace_drafts=lambda drafts: replaced.append(drafts))

    dialog._finish_extract(
        "提炼核心事实",
        [
            FactCardDraft(
                name="核心卡片",
                content="核心事实",
                category="综合",
                scope="local",
                enforcement="reference",
            ),
            FactCardDraft(
                name="次要卡片",
                content="次要事实",
                category="补充",
                scope="local",
                enforcement="reference",
            ),
        ],
        None,
    )

    assert replaced == [
        [
            FactCardDraft(
                name="核心卡片",
                content="核心事实",
                category="综合",
                scope="local",
                enforcement="reference",
            )
        ]
    ]
    assert dialog._has_extracted is True
    assert dialog._last_extracted_instruction == "提炼核心事实"
    assert dialog.status_var.get() == "已生成 1 张核心草稿，可继续编辑或调整要求后重提。"
    assert dialog.extract_button.configured[-1] == {"text": "重新提炼"}


def test_fact_card_extraction_workspace_dialog_keeps_only_current_initial_draft():
    current_draft = FactCardDraft(
        name="当前卡片",
        content="当前章节核心事实",
        category="综合",
        scope="local",
        enforcement="reference",
    )
    stale_draft = FactCardDraft(
        name="历史卡片",
        content="不应出现在提炼草稿框中",
        category="历史",
        scope="local",
        enforcement="reference",
    )

    assert fact_card_dialogs.FactCardExtractionWorkspaceDialog._current_drafts(
        [current_draft, stale_draft]
    ) == [current_draft]


def test_fact_card_extraction_dialog_reserves_width_for_delete_button():
    assert fact_card_dialogs.FACT_CARD_EXTRACTION_WORKSPACE_WIDTH >= 1080
    assert fact_card_dialogs.FACT_CARD_EXTRACTION_WORKSPACE_MIN_SIZE[0] >= fact_card_dialogs.FACT_CARD_EXTRACTION_WORKSPACE_WIDTH


def test_fact_card_extraction_workspace_dialog_uses_single_card_editor_options():
    assert fact_card_dialogs.FactCardExtractionWorkspaceDialog._editor_options() == {
        "allow_add": False,
        "show_card_frame": False,
        "max_rows": 1,
        "show_delete_button": True,
        "stretch_content": True,
    }


def test_fact_card_draft_editor_stretches_content_in_single_card_mode():
    assert fact_card_dialogs.FactCardDraftEditor._container_pack_options(True) == {
        "fill": fact_card_dialogs.tk.BOTH,
        "expand": True,
        "pady": (0, 10),
    }
    assert fact_card_dialogs.FactCardDraftEditor._content_pack_options(True) == {
        "fill": fact_card_dialogs.tk.BOTH,
        "expand": True,
    }


def test_manual_fact_card_dialog_stretches_content_editor():
    assert fact_card_dialogs.ManualFactCardDialog._editor_options() == {
        "allow_add": False,
        "show_card_frame": False,
        "max_rows": 1,
        "show_delete_button": False,
        "stretch_content": True,
    }


def test_fact_card_extraction_workspace_dialog_uses_default_instruction_as_placeholder():
    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog._default_instruction = "默认提炼要求"
    dialog._instruction_placeholder_active = True
    dialog.instruction_text = SimpleNamespace(get=lambda *_args: "")

    assert dialog._get_instruction() == "默认提炼要求"


def test_fact_card_extraction_workspace_dialog_prefers_user_instruction_over_placeholder():
    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog._default_instruction = "默认提炼要求"
    dialog._instruction_placeholder_active = False
    dialog.instruction_text = SimpleNamespace(get=lambda *_args: "只提炼资质")

    assert dialog._get_instruction() == "只提炼资质"


def test_fact_card_extraction_workspace_dialog_shows_empty_result_details(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        fact_card_dialogs.messagebox,
        "showwarning",
        lambda _title, message, parent=None: warnings.append(message),
    )
    dialog = fact_card_dialogs.FactCardExtractionWorkspaceDialog.__new__(
        fact_card_dialogs.FactCardExtractionWorkspaceDialog
    )
    dialog._is_extracting = True
    dialog.extract_button = _FakeWidget()
    dialog.save_button = _FakeWidget()
    dialog.status_var = _FakeStatus()

    dialog._finish_extract(
        "提炼核心事实",
        [],
        None,
        "模型返回不是合法 JSON，无法解析事实卡片。\n\n详细信息：\n解析错误：Expecting value",
    )

    assert warnings == [
        "模型返回不是合法 JSON，无法解析事实卡片。\n\n详细信息：\n解析错误：Expecting value"
    ]
    assert dialog.status_var.get() == "本次未生成可保存草稿，可查看提示详情。"


def test_fact_card_draft_editor_returns_scope_and_enforcement():
    editor = fact_card_dialogs.FactCardDraftEditor.__new__(fact_card_dialogs.FactCardDraftEditor)
    editor._rows = [
        {
            "card_id": "card-a",
            "name_var": SimpleNamespace(get=lambda: "企业资质"),
            "category_var": SimpleNamespace(get=lambda: "资质"),
            "scope_var": SimpleNamespace(get=lambda: "global"),
            "enforcement_var": SimpleNamespace(get=lambda: "strong"),
            "content_text": SimpleNamespace(get=lambda *_args: "一级资质"),
        }
    ]

    assert editor.get_drafts() == [
        FactCardDraft(
            card_id="card-a",
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        )
    ]


def test_fact_card_draft_editor_remove_row_requires_confirmation(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        fact_card_dialogs.messagebox,
        "askyesno",
        lambda _title, message, parent=None: prompts.append(message) or False,
    )

    first_container = _FakeContainer()
    second_container = _FakeContainer()
    first_row = {"container": first_container}
    second_row = {"container": second_container}
    editor = fact_card_dialogs.FactCardDraftEditor.__new__(fact_card_dialogs.FactCardDraftEditor)
    editor._rows = [first_row, second_row]
    editor.winfo_toplevel = lambda: "parent"

    editor.remove_row(first_row)

    assert prompts == ["确定删除这张事实卡片草稿吗？"]
    assert editor._rows == [first_row, second_row]
    assert first_container.destroyed is False


def test_fact_card_draft_editor_remove_row_deletes_after_confirmation(monkeypatch):
    monkeypatch.setattr(
        fact_card_dialogs.messagebox,
        "askyesno",
        lambda _title, _message, parent=None: True,
    )

    first_container = _FakeContainer()
    second_container = _FakeContainer()
    first_row = {"container": first_container}
    second_row = {"container": second_container}
    editor = fact_card_dialogs.FactCardDraftEditor.__new__(fact_card_dialogs.FactCardDraftEditor)
    editor._rows = [first_row, second_row]
    editor.winfo_toplevel = lambda: "parent"

    editor.remove_row(first_row)

    assert editor._rows == [second_row]
    assert first_container.destroyed is True
    assert second_container.configured[-1] == {"text": "卡片 1"}


def test_fact_card_library_dialog_builds_editable_manual_drafts_with_card_ids():
    manual_card = FactCard(
        id="manual-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        scope="global",
        enforcement="strong",
        source=FactCardSource(type="manual"),
    )
    extracted_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="7×24小时响应",
        category="承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(type="chapter_extract", chapter_path="技术方案 > 质量保障措施"),
    )

    drafts = fact_card_dialogs.FactCardLibraryDialog._build_manual_drafts(
        [manual_card, extracted_card]
    )

    assert drafts == [
        FactCardDraft(
            card_id="manual-a",
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        )
    ]


def test_fact_card_library_dialog_builds_editable_drafts_for_all_cards_with_ids():
    manual_card = FactCard(
        id="manual-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        scope="global",
        enforcement="strong",
        source=FactCardSource(type="manual"),
    )
    extracted_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="7×24小时响应",
        category="承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(type="chapter_extract", chapter_path="技术方案 > 质量保障措施"),
    )

    drafts = fact_card_dialogs.FactCardLibraryDialog._build_library_drafts(
        [manual_card, extracted_card]
    )

    assert drafts == [
        FactCardDraft(
            card_id="manual-a",
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        ),
        FactCardDraft(
            card_id="extract-a",
            name="服务承诺",
            content="7×24小时响应",
            category="承诺",
            scope="local",
            enforcement="reference",
        ),
    ]


def test_fact_card_library_dialog_layout_reserves_more_height_for_manual_editor():
    assert fact_card_dialogs.FACT_CARD_LIBRARY_CURRENT_TREE_ROWS <= 8
    assert fact_card_dialogs.FACT_CARD_LIBRARY_MANUAL_EDITOR_MIN_HEIGHT >= 360


def test_mainwindow_fact_card_library_saves_entire_library(monkeypatch):
    saved_drafts: list[FactCardDraft] = []
    workspace_messages: list[tuple[str, str, str, int]] = []

    class _FakeDialog:
        def __init__(self, _parent, *, cards):
            self.cards = cards
            self.result = [
                FactCardDraft(
                    card_id="extract-a",
                    name="服务响应承诺",
                    content="提供 7×24 小时响应支持",
                    category="服务承诺",
                    scope="local",
                    enforcement="reference",
                )
            ]

    monkeypatch.setattr(
        fact_card_dialogs,
        "FactCardLibraryDialog",
        _FakeDialog,
    )

    fake_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="7×24小时响应",
        category="承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(type="chapter_extract", chapter_path="技术方案 > 质量保障措施"),
    )

    class _FakeBidWriter:
        def __init__(self):
            self.fact_card_store = SimpleNamespace(list_cards=lambda active_only=False: [fake_card])

        def save_fact_card_library(self, drafts):
            saved_drafts.extend(drafts)
            return [
                FactCard(
                    id=draft.card_id,
                    name=draft.name,
                    content=draft.content,
                    category=draft.category,
                    scope=draft.scope,
                    enforcement=draft.enforcement,
                    source=fake_card.source,
                )
                for draft in drafts
            ]

    fake_window = SimpleNamespace(
        bid_writer=_FakeBidWriter(),
        status_text=_FakeStatus(),
        wait_window=lambda _dialog: None,
        _show_workspace_message=lambda title, subtitle, detail, generated_char_count=0: workspace_messages.append(
            (title, subtitle, detail, generated_char_count)
        ),
    )

    MainWindow.open_fact_card_library_dialog(fake_window)

    assert saved_drafts == [
        FactCardDraft(
            card_id="extract-a",
            name="服务响应承诺",
            content="提供 7×24 小时响应支持",
            category="服务承诺",
            scope="local",
            enforcement="reference",
        )
    ]
    assert workspace_messages == [
        (
            "事实卡片库",
            "已保存事实卡片库",
            "- 服务响应承诺：提供 7×24 小时响应支持",
            len("- 服务响应承诺：提供 7×24 小时响应支持"),
        )
    ]
    assert fake_window.status_text.get() == "已保存事实卡片库：1 张"


def test_mainwindow_manual_fact_card_dialog_appends_to_library(monkeypatch):
    saved_drafts: list[FactCardDraft] = []
    workspace_messages: list[tuple[str, str, str, int]] = []
    manual_card = FactCard(
        id="manual-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        scope="global",
        enforcement="strong",
        source=FactCardSource(type="manual"),
    )
    extracted_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="7×24小时响应",
        category="承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(type="chapter_extract", chapter_path="技术方案 > 质量保障措施"),
    )
    new_draft = FactCardDraft(
        name="项目经理",
        content="项目经理具备高级职称",
        category="人员",
        scope="local",
        enforcement="reference",
    )

    class _FakeDialog:
        def __init__(self, _parent):
            self.result = new_draft

    monkeypatch.setattr(fact_card_dialogs, "ManualFactCardDialog", _FakeDialog)

    class _FakeBidWriter:
        def __init__(self):
            self.fact_card_store = SimpleNamespace(list_cards=lambda active_only=False: [manual_card, extracted_card])

        def save_fact_card_library(self, drafts):
            saved_drafts.extend(drafts)
            return [
                FactCard(
                    id=draft.card_id or f"fact-card-{index}",
                    name=draft.name,
                    content=draft.content,
                    category=draft.category,
                    scope=draft.scope,
                    enforcement=draft.enforcement,
                    source=FactCardSource(type="manual" if not draft.card_id else "manual"),
                )
                for index, draft in enumerate(drafts, start=1)
            ]

    fake_window = SimpleNamespace(
        bid_writer=_FakeBidWriter(),
        status_text=_FakeStatus(),
        wait_window=lambda _dialog: None,
        _show_workspace_message=lambda title, subtitle, detail, generated_char_count=0: workspace_messages.append(
            (title, subtitle, detail, generated_char_count)
        ),
    )

    MainWindow.open_manual_fact_card_dialog(fake_window)

    assert saved_drafts == [
        FactCardDraft(
            card_id="manual-a",
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        ),
        FactCardDraft(
            card_id="extract-a",
            name="服务承诺",
            content="7×24小时响应",
            category="承诺",
            scope="local",
            enforcement="reference",
        ),
        new_draft,
    ]
    assert workspace_messages == [
        (
            "事实卡片库",
            "已新增事实卡片",
            "- 项目经理：项目经理具备高级职称",
            len("- 项目经理：项目经理具备高级职称"),
        )
    ]
    assert fake_window.status_text.get() == "已新增事实卡片：项目经理"


def test_mainwindow_chapter_menu_hides_dependency_entries():
    class _FakeMenu:
        def __init__(self):
            self.labels: list[str] = []

        def add_command(self, *, label, command):
            del command
            self.labels.append(label)

    fake_window = SimpleNamespace(
        extract_selected_facts=lambda: None,
        open_manual_fact_card_dialog=lambda: None,
        open_fact_card_library_dialog=lambda: None,
    )
    menu = _FakeMenu()

    MainWindow._populate_chapter_tools_menu(fake_window, menu)

    assert menu.labels == [
        "提炼当前章节事实卡片",
        "新增事实卡片...",
        "管理事实卡片",
    ]


def test_mainwindow_top_menus_expose_project_chapter_and_view_groups():
    class _FakeMenu:
        def __init__(self):
            self.labels: list[str] = []

        def add_command(self, *, label, command):
            del command
            self.labels.append(label)

        def add_separator(self):
            self.labels.append("---")

    fake_window = SimpleNamespace(
        select_and_switch_config=lambda: None,
        open_config_editor=lambda: None,
        reload_outline=lambda: None,
        refresh_status=lambda: None,
        open_output_dir=lambda: None,
        quit=lambda: None,
        batch_generate=lambda: None,
        extract_selected_facts=lambda: None,
        open_manual_fact_card_dialog=lambda: None,
        open_fact_card_library_dialog=lambda: None,
        merge_generated_sections=lambda: None,
        expand_all=lambda: None,
        expand_to_level_1=lambda: None,
        expand_to_level_2=lambda: None,
        expand_to_level_3=lambda: None,
        collapse_all=lambda: None,
    )

    project_menu = _FakeMenu()
    chapter_menu = _FakeMenu()
    view_menu = _FakeMenu()

    MainWindow._populate_project_menu(fake_window, project_menu)
    MainWindow._populate_chapter_menu(fake_window, chapter_menu)
    MainWindow._populate_view_menu(fake_window, view_menu)

    assert project_menu.labels == [
        "切换配置...",
        "编辑当前配置...",
        "---",
        "重载大纲",
        "扫描输出状态",
        "---",
        "打开输出目录",
        "---",
        "退出",
    ]
    assert chapter_menu.labels == [
        "生成所选",
        "提炼当前章节事实卡片",
        "新增事实卡片...",
        "管理事实卡片",
        "---",
        "整合标书",
    ]
    assert view_menu.labels == [
        "全部展开",
        "---",
        "展开至一级 (Ctrl+1)",
        "展开至二级 (Ctrl+2)",
        "展开至三级 (Ctrl+3)",
        "---",
        "收缩全部 (Ctrl+0)",
    ]


def test_generation_fact_card_dialog_state_exposes_only_local_cards():
    global_card = FactCard(
        id="global-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        scope="global",
        enforcement="strong",
        source=FactCardSource(type="manual"),
    )
    local_card = FactCard(
        id="local-a",
        name="章节承诺",
        content="本章节服务承诺",
        category="承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(type="chapter_extract", chapter_path="项目 > 技术方案"),
    )

    dialog_state = MainWindow._build_generation_fact_card_dialog_state(
        [global_card, local_card],
        initial_selections=[],
    )

    assert dialog_state.global_cards == [global_card]
    assert dialog_state.available_cards == [local_card]
    assert dialog_state.default_mode is True
    assert dialog_state.summary_text == "本次将自动加入 1 张全局事实卡片；下方仅选择当前章节局部卡片。"


def test_mainwindow_extract_facts_for_heading_uses_workspace_dialog_result(monkeypatch, tmp_path: Path):
    output_path = tmp_path / "chapter.md"
    output_path.write_text("已有正文", encoding="utf-8")
    extract_calls: list[tuple[object, str]] = []
    replace_calls: list[tuple[object, str, list[FactCardDraft]]] = []
    workspace_messages: list[tuple[str, str, str, int]] = []
    dialog_calls: list[dict[str, object]] = []

    heading = SimpleNamespace(title="质量保障措施", full_path="项目 > 技术方案 > 质量保障措施")

    class _FakeBidWriter:
        def __init__(self):
            self.config = SimpleNamespace(fact_cards_enabled=True)
            self.file_saver = SimpleNamespace(find_existing_filepath=lambda _heading: output_path)

        def extract_fact_card_drafts_from_output(self, heading_arg, instruction: str = ""):
            extract_calls.append((heading_arg, instruction))
            return [
                FactCardDraft(
                    name="企业资质",
                    content="一级资质",
                    category="资质",
                    scope="global",
                    enforcement="strong",
                )
            ]

        def replace_extracted_fact_cards(self, heading_arg, instruction: str, drafts):
            draft_list = list(drafts)
            replace_calls.append((heading_arg, instruction, draft_list))
            return [
                SimpleNamespace(name=draft.name, content=draft.content)
                for draft in draft_list
            ]

    class _FakeDialog:
        def __init__(
            self,
            _parent,
            *,
            heading_title: str,
            initial_instruction: str,
            extract_callback,
            initial_drafts=None,
            initial_status: str = "",
        ):
            dialog_calls.append(
                {
                    "heading_title": heading_title,
                    "initial_instruction": initial_instruction,
                    "initial_drafts": list(initial_drafts or []),
                    "initial_status": initial_status,
                }
            )
            drafts = extract_callback("只提炼资质与承诺")
            self.result = fact_card_dialogs.FactCardExtractionDialogResult(
                instruction="只提炼资质与承诺",
                drafts=drafts,
            )

    monkeypatch.setattr(
        fact_card_dialogs,
        "FactCardExtractionWorkspaceDialog",
        _FakeDialog,
    )

    fake_window = SimpleNamespace(
        bid_writer=_FakeBidWriter(),
        status_text=_FakeStatus(),
        update_idletasks=lambda: None,
        wait_window=lambda _dialog: None,
        _show_workspace_message=lambda title, subtitle, detail, generated_char_count=0: workspace_messages.append(
            (title, subtitle, detail, generated_char_count)
        ),
        _default_fact_card_extraction_instruction=lambda _heading: "提取可复用事实",
    )

    MainWindow._extract_facts_for_heading(fake_window, heading)

    assert dialog_calls == [
        {
            "heading_title": "质量保障措施",
            "initial_instruction": "提取可复用事实",
            "initial_drafts": [],
            "initial_status": "",
        }
    ]
    assert extract_calls == [(heading, "只提炼资质与承诺")]
    assert replace_calls == [
        (
            heading,
            "只提炼资质与承诺",
            [
                FactCardDraft(
                    name="企业资质",
                    content="一级资质",
                    category="资质",
                    scope="global",
                    enforcement="strong",
                )
            ],
        )
    ]
    assert workspace_messages == [
        (
            "事实卡片：项目 > 技术方案 > 质量保障措施",
            "已保存章节事实卡片",
            "- 企业资质：一级资质",
            len("- 企业资质：一级资质"),
        )
    ]


def test_mainwindow_extract_facts_for_heading_loads_existing_cards(monkeypatch, tmp_path: Path):
    output_path = tmp_path / "chapter.md"
    output_path.write_text("已有正文", encoding="utf-8")
    replace_calls: list[tuple[object, str, list[FactCardDraft]]] = []
    dialog_calls: list[dict[str, object]] = []

    heading = SimpleNamespace(title="质量保障措施", full_path="项目 > 技术方案 > 质量保障措施")
    existing_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="提供 7×24 小时响应支持",
        category="服务承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(
            type="chapter_extract",
            chapter_path="项目 > 技术方案 > 质量保障措施",
            extraction_instruction="提炼服务承诺",
        ),
        updated_at="2099-01-01T00:00:00+00:00",
    )
    stale_card = FactCard(
        id="extract-b",
        name="历史承诺",
        content="旧版承诺不应出现在当前提炼草稿框中",
        category="服务承诺",
        scope="local",
        enforcement="reference",
        source=FactCardSource(
            type="chapter_extract",
            chapter_path="项目 > 技术方案 > 质量保障措施",
            extraction_instruction="历史提炼要求",
        ),
        updated_at="2099-01-01T00:00:00+00:00",
    )

    class _FakeBidWriter:
        def __init__(self):
            self.config = SimpleNamespace(fact_cards_enabled=True)
            self.file_saver = SimpleNamespace(find_existing_filepath=lambda _heading: output_path)

        def list_extracted_fact_cards(self, heading_arg):
            assert heading_arg is heading
            return [existing_card, stale_card]

        def extract_fact_card_drafts_from_output(self, _heading_arg, _instruction: str = ""):
            raise AssertionError("不应在打开已有结果时立即重新提炼")

        def replace_extracted_fact_cards(self, heading_arg, instruction: str, drafts):
            draft_list = list(drafts)
            replace_calls.append((heading_arg, instruction, draft_list))
            return [
                SimpleNamespace(name=draft.name, content=draft.content)
                for draft in draft_list
            ]

    class _FakeDialog:
        def __init__(
            self,
            _parent,
            *,
            heading_title: str,
            initial_instruction: str,
            extract_callback,
            initial_drafts=None,
            initial_status: str = "",
        ):
            dialog_calls.append(
                {
                    "heading_title": heading_title,
                    "initial_instruction": initial_instruction,
                    "initial_drafts": list(initial_drafts or []),
                    "initial_status": initial_status,
                }
            )
            self.result = fact_card_dialogs.FactCardExtractionDialogResult(
                instruction=initial_instruction,
                drafts=list(initial_drafts or []),
            )

    monkeypatch.setattr(
        fact_card_dialogs,
        "FactCardExtractionWorkspaceDialog",
        _FakeDialog,
    )

    fake_window = SimpleNamespace(
        bid_writer=_FakeBidWriter(),
        status_text=_FakeStatus(),
        update_idletasks=lambda: None,
        wait_window=lambda _dialog: None,
        _show_workspace_message=lambda *args, **kwargs: None,
        _default_fact_card_extraction_instruction=lambda _heading: "默认提炼要求",
    )

    MainWindow._extract_facts_for_heading(fake_window, heading)

    assert dialog_calls == [
        {
            "heading_title": "质量保障措施",
            "initial_instruction": "提炼服务承诺",
            "initial_drafts": [
                FactCardDraft(
                    card_id="extract-a",
                    name="服务承诺",
                    content="提供 7×24 小时响应支持",
                    category="服务承诺",
                    scope="local",
                    enforcement="reference",
                )
            ],
            "initial_status": "已存在上次提炼结果（1 张），当前正文未检测到更新，可直接复用或编辑后保存。",
        }
    ]
    assert replace_calls == [
        (
            heading,
            "提炼服务承诺",
            [
                FactCardDraft(
                    card_id="extract-a",
                    name="服务承诺",
                    content="提供 7×24 小时响应支持",
                    category="服务承诺",
                    scope="local",
                    enforcement="reference",
                )
            ],
        )
    ]


def test_mainwindow_fact_card_menu_label_reflects_existing_extraction():
    heading = SimpleNamespace(full_path="项目 > 技术方案 > 质量保障措施")

    class _FakeBidWriter:
        def list_extracted_fact_cards(self, heading_arg):
            assert heading_arg is heading
            return [SimpleNamespace()]

    fake_window = SimpleNamespace(bid_writer=_FakeBidWriter())

    assert MainWindow._fact_card_menu_label_for_heading(fake_window, heading) == "查看/更新事实卡片"
