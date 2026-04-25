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
        get_drafts=lambda: [FactCardDraft(name="企业资质", content="一级资质", category="资质")]
    )
    closed: list[str] = []
    dialog.destroy = lambda: closed.append("destroy")

    dialog._on_save()

    assert dialog.result == fact_card_dialogs.FactCardExtractionDialogResult(
        instruction="提取资质与承诺",
        drafts=[FactCardDraft(name="企业资质", content="一级资质", category="资质")],
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
        get_drafts=lambda: [FactCardDraft(name="企业资质", content="一级资质", category="资质")]
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
            FactCardDraft(name="核心卡片", content="核心事实", category="综合"),
            FactCardDraft(name="次要卡片", content="次要事实", category="补充"),
        ],
        None,
    )

    assert replaced == [[FactCardDraft(name="核心卡片", content="核心事实", category="综合")]]
    assert dialog._has_extracted is True
    assert dialog._last_extracted_instruction == "提炼核心事实"
    assert dialog.status_var.get() == "已生成 1 张核心草稿，可继续编辑或调整要求后重提。"
    assert dialog.extract_button.configured[-1] == {"text": "重新提炼"}


def test_fact_card_library_dialog_builds_editable_manual_drafts_with_card_ids():
    manual_card = FactCard(
        id="manual-a",
        name="企业资质",
        content="一级资质",
        category="资质",
        source=FactCardSource(type="manual"),
    )
    extracted_card = FactCard(
        id="extract-a",
        name="服务承诺",
        content="7×24小时响应",
        category="承诺",
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
        )
    ]


def test_fact_card_library_dialog_layout_reserves_more_height_for_manual_editor():
    assert fact_card_dialogs.FACT_CARD_LIBRARY_CURRENT_TREE_ROWS <= 8
    assert fact_card_dialogs.FACT_CARD_LIBRARY_MANUAL_EDITOR_MIN_HEIGHT >= 360


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
            return [FactCardDraft(name="企业资质", content="一级资质", category="资质")]

        def replace_extracted_fact_cards(self, heading_arg, instruction: str, drafts):
            draft_list = list(drafts)
            replace_calls.append((heading_arg, instruction, draft_list))
            return [
                SimpleNamespace(name=draft.name, content=draft.content)
                for draft in draft_list
            ]

    class _FakeDialog:
        def __init__(self, _parent, *, heading_title: str, initial_instruction: str, extract_callback):
            dialog_calls.append(
                {
                    "heading_title": heading_title,
                    "initial_instruction": initial_instruction,
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
        }
    ]
    assert extract_calls == [(heading, "只提炼资质与承诺")]
    assert replace_calls == [
        (
            heading,
            "只提炼资质与承诺",
            [FactCardDraft(name="企业资质", content="一级资质", category="资质")],
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
