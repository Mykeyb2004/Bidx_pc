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

    class _FakeBidWriter:
        def __init__(self):
            self.config = SimpleNamespace(fact_cards_enabled=True)
            self.file_saver = SimpleNamespace(find_existing_filepath=lambda _heading: output_path)

        def list_extracted_fact_cards(self, heading_arg):
            assert heading_arg is heading
            return [existing_card]

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
