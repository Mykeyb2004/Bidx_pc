from types import SimpleNamespace

import pytest

import bid_writer.gui as gui
from bid_writer import fact_card_dialogs
from bid_writer.gui import MainWindow
from bid_writer.writing_plan_store import (
    WritingPlanCoverage,
    WritingPlanExternalModificationError,
    WritingPlanItem,
    WritingPlanSnapshot,
    WritingPlanStoreError,
    WritingPlanValidationError,
)


class _FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args, **_kwargs):
        return None


class _FakeWidget:
    def __init__(self, *_args, **_kwargs):
        self.configure_calls = []
        self.kwargs = _kwargs

    def pack(self, *_args, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)
        self.kwargs.update(kwargs)


class _FakeText(_FakeWidget):
    instances = []

    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.content = ""
        self.bindings = {}
        self.modified = False
        self.instances.append(self)

    def insert(self, _index, value):
        self.content += value

    def get(self, *_args):
        return self.content

    def delete(self, *_args):
        self.content = ""

    def bind(self, event_name, callback):
        self.bindings[event_name] = callback

    def edit_modified(self, value=None):
        if value is None:
            return self.modified
        self.modified = bool(value)

    def simulate_user_edit(self, value):
        self.content = value
        self.modified = True
        callback = self.bindings.get("<<Modified>>")
        if callback is not None:
            callback(SimpleNamespace(widget=self))


class _FakeDialog(_FakeWidget):
    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.destroy_calls = 0
        self.protocols = {}

    def title(self, _value):
        return None

    def resizable(self, *_args):
        return None

    def transient(self, *_args):
        return None

    def grab_set(self):
        return None

    def update_idletasks(self):
        return None

    def winfo_reqwidth(self):
        return 620

    def winfo_reqheight(self):
        return 420

    def destroy(self):
        self.destroy_calls += 1

    def protocol(self, name, callback):
        self.protocols[name] = callback


class _FakeFactCardSelectionPanel(_FakeWidget):
    instances = []

    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.instances.append(self)

    def get_selections(self):
        return ["card-a"]


def _install_generation_dialog_fakes(monkeypatch):
    buttons = {}
    dialogs = []
    widgets = []

    class _TrackedWidget(_FakeWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__(*_args, **_kwargs)
            widgets.append(self)

    class _FakeButton(_FakeWidget):
        def __init__(self, *_args, text="", command=None, **_kwargs):
            super().__init__()
            self.text = text
            self.command = command
            buttons[text] = self

        def invoke(self):
            if self.kwargs.get("state") != "disabled" and self.command is not None:
                return self.command()
            return None

    def _new_dialog(*args, **kwargs):
        dialog = _FakeDialog(*args, **kwargs)
        dialogs.append(dialog)
        return dialog

    monkeypatch.setattr(gui.tk, "Toplevel", _new_dialog)
    monkeypatch.setattr(gui.tk, "Text", _FakeText)
    monkeypatch.setattr(gui.tk, "IntVar", _FakeVar)
    monkeypatch.setattr(gui.tk, "BooleanVar", _FakeVar)
    monkeypatch.setattr(gui.tk, "StringVar", _FakeVar)
    monkeypatch.setattr(gui.ttk, "Frame", _TrackedWidget)
    monkeypatch.setattr(gui.ttk, "Label", _TrackedWidget)
    monkeypatch.setattr(gui.ttk, "Checkbutton", _TrackedWidget)
    monkeypatch.setattr(gui.ttk, "Spinbox", _TrackedWidget)
    monkeypatch.setattr(gui.ttk, "Button", _FakeButton)
    _FakeFactCardSelectionPanel.instances = []
    monkeypatch.setattr(fact_card_dialogs, "FactCardSelectionPanel", _FakeFactCardSelectionPanel)
    monkeypatch.setattr(gui, "apply_window_surface", lambda _widget: None)
    monkeypatch.setattr(gui, "style_text_widget", lambda _widget: None)
    monkeypatch.setattr(gui, "_set_centered_window_geometry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        gui,
        "load_gui_state",
        lambda: SimpleNamespace(
            last_generation_target_words=None,
            last_max_mermaid_flowcharts_per_section=None,
        ),
    )
    monkeypatch.setattr(gui, "remember_generation_dialog_settings", lambda *_args: None)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *_args, **_kwargs: False)
    _FakeText.instances = []

    return buttons, dialogs, widgets


def _fake_generation_window(
    wait_window,
    save_callback=None,
    *,
    writing_plan_store=None,
    load_writing_plan_snapshot=None,
    save_writing_plan=None,
    summarize_writing_plans=None,
):
    summary = SimpleNamespace(
        total_chapters=2,
        reference_enabled_chapters=1,
        cards=[
            SimpleNamespace(
                card=SimpleNamespace(id="personnel", name="人员配置"),
                referenced_chapters=1,
            )
        ],
    )
    return SimpleNamespace(
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(
                generation_default_target_words=1200,
                generation_target_words_min=100,
                generation_target_words_max=5000,
                generation_target_words_step=100,
                fact_cards_enabled=True,
                build_target_word_range=lambda _value: SimpleNamespace(display_text="1000-1400"),
            ),
            fact_card_store=SimpleNamespace(list_cards=lambda active_only=True: []),
            list_chapter_default_fact_cards=lambda _heading: [],
            get_chapter_default_fact_card_state=lambda _heading: SimpleNamespace(
                should_reference_fact_cards=None,
                selections=[],
            ),
            save_chapter_default_fact_cards=save_callback or (lambda *_args, **_kwargs: None),
            summarize_chapter_default_fact_cards=lambda _headings: summary,
            apply_batch_chapter_default_fact_cards=lambda *_args, **_kwargs: None,
            writing_plan_store=writing_plan_store,
            load_writing_plan_snapshot=(
                load_writing_plan_snapshot
                or (lambda: WritingPlanSnapshot((), None))
            ),
            save_writing_plan=(
                save_writing_plan
                or (lambda _node, _text, snapshot: snapshot)
            ),
            summarize_writing_plans=(
                summarize_writing_plans
                or (
                    lambda headings, _snapshot: WritingPlanCoverage(
                        total_headings=len(headings),
                        numbered_headings=len(headings),
                        planned_headings=0,
                    )
                )
            ),
        ),
        status_text=SimpleNamespace(set=lambda _value: None),
        wait_window=wait_window,
        _build_generation_fact_card_dialog_state=MainWindow._build_generation_fact_card_dialog_state,
    )


def _writing_plan_snapshot(node=None, text=None, *, fingerprint="snapshot"):
    items = ()
    if node is not None and text is not None:
        items = (WritingPlanItem(node=node, writing_plan=text),)
    return WritingPlanSnapshot(items, fingerprint)


def test_generation_params_start_button_saves_fact_card_references(monkeypatch):
    buttons, _dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    saved_calls = []
    heading = SimpleNamespace(title="质量控制", full_path="项目 > 质量控制")

    def wait_window(_dialog):
        buttons["开始扩写"].command()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            save_callback=lambda chapter_path, selections, **kwargs: saved_calls.append(
                (chapter_path, selections, kwargs)
            ),
        ),
        [heading],
        initial_requirements="补充资质",
    )

    assert result == ("补充资质", 1200, 0, False, ["card-a"])
    assert saved_calls == [
        ("项目 > 质量控制", ["card-a"], {"should_reference_fact_cards": False})
    ]


def test_save_fact_card_references_keeps_generation_params_dialog_open(monkeypatch):
    buttons, dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    saved_calls = []
    heading = SimpleNamespace(title="质量控制", full_path="项目 > 质量控制")

    def wait_window(_dialog):
        buttons["保存事实卡片引用关系"].command()
        assert dialogs[0].destroy_calls == 0

    window = _fake_generation_window(wait_window)
    window.bid_writer.save_chapter_default_fact_cards = (
        lambda chapter_path, selections, **kwargs: saved_calls.append((chapter_path, selections, kwargs))
    )

    result = MainWindow._get_generation_params(window, [heading])

    assert result is None
    assert saved_calls == [
        ("项目 > 质量控制", ["card-a"], {"should_reference_fact_cards": False})
    ]


def test_batch_generation_uses_readonly_summary_without_saving_defaults(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    saved_calls = []
    headings = [
        SimpleNamespace(title="质量控制", full_path="项目 > 质量控制"),
        SimpleNamespace(title="进度保障", full_path="项目 > 进度保障"),
    ]

    def wait_window(_dialog):
        buttons["开始扩写"].command()

    window = _fake_generation_window(wait_window)
    window.bid_writer.save_chapter_default_fact_cards = (
        lambda chapter_path, selections, **kwargs: saved_calls.append((chapter_path, selections, kwargs))
    )

    result = MainWindow._get_generation_params(window, headings)

    assert result == ("", 1200, 0, True, None)
    assert saved_calls == []
    assert _FakeFactCardSelectionPanel.instances == []
    assert "统一应用到所选章节…" in buttons
    assert "保存事实卡片引用关系" not in buttons
    assert all(
        widget.kwargs.get("text") != "批量生成启用事实卡片模式"
        for widget in widgets
    )
    ignore_widget = next(
        widget
        for widget in widgets
        if widget.kwargs.get("text") == "本次批量忽略全部事实卡片"
    )
    assert ignore_widget.kwargs["variable"].get() is False
    summary_vars = [widget.kwargs.get("textvariable") for widget in widgets]
    assert any(
        value is not None
        and "人员配置：1/2 个章节引用（混合状态）" in str(value.get())
        for value in summary_vars
    )


def test_batch_generation_can_ignore_fact_cards_for_this_run_without_saving(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    applied = []
    headings = [
        SimpleNamespace(title="质量控制", full_path="项目 > 质量控制"),
        SimpleNamespace(title="进度保障", full_path="项目 > 进度保障"),
    ]

    def wait_window(_dialog):
        ignore_widget = next(
            widget
            for widget in widgets
            if widget.kwargs.get("text") == "本次批量忽略全部事实卡片"
        )
        ignore_widget.kwargs["variable"].set(True)
        buttons["开始扩写"].command()

    window = _fake_generation_window(wait_window)
    window.bid_writer.apply_batch_chapter_default_fact_cards = (
        lambda *_args, **_kwargs: applied.append(True)
    )

    result = MainWindow._get_generation_params(window, headings)

    assert result == ("", 1200, 0, False, None)
    assert applied == []


def test_batch_generation_explicit_uniform_apply_refreshes_summary(monkeypatch):
    buttons, _dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    headings = [
        SimpleNamespace(title="质量控制", full_path="项目 > 质量控制"),
        SimpleNamespace(title="进度保障", full_path="项目 > 进度保障"),
    ]
    applied = []
    summarized = []

    def show_dialog(_master, *, summary, apply_callback):
        assert summary.reference_enabled_chapters == 1
        apply_callback(True, {"personnel": False})
        return fact_card_dialogs.BatchFactCardDialogResult(True, {"personnel": False})

    monkeypatch.setattr(fact_card_dialogs.BatchFactCardConfigDialog, "show", show_dialog)

    def wait_window(_dialog):
        buttons["统一应用到所选章节…"].command()

    window = _fake_generation_window(wait_window)
    original_summary = window.bid_writer.summarize_chapter_default_fact_cards
    window.bid_writer.summarize_chapter_default_fact_cards = lambda headings_arg: (
        summarized.append(list(headings_arg)) or original_summary(headings_arg)
    )
    window.bid_writer.apply_batch_chapter_default_fact_cards = (
        lambda headings_arg, **kwargs: applied.append((list(headings_arg), kwargs))
    )

    result = MainWindow._get_generation_params(window, headings)

    assert result is None
    assert applied == [
        (
            headings,
            {
                "should_reference_fact_cards": True,
                "card_references": {"personnel": False},
            },
        )
    ]
    assert summarized == [headings, headings]


def test_writing_plan_single_prefills_saved_text_and_shows_node_number(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    snapshot = _writing_plan_snapshot("1.4.2", "第一行\n第二行")

    def wait_window(_dialog):
        buttons["关闭"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: snapshot,
        ),
        [heading],
    )

    assert result is None
    assert _FakeText.instances[0].content == "第一行\n第二行"
    assert "保存撰写计划" in buttons
    assert "重新加载撰写计划" in buttons
    displayed_values = [
        widget.kwargs["textvariable"].get()
        for widget in widgets
        if widget.kwargs.get("textvariable") is not None
    ]
    assert any("节点编号：1.4.2" in str(value) for value in displayed_values)


def test_writing_plan_single_edit_marks_dirty_and_explicit_save_keeps_new_snapshot(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    original = _writing_plan_snapshot("1.4.2", "旧计划", fingerprint="old")
    saved = _writing_plan_snapshot("1.4.2", "第一行\n第二行", fingerprint="new")
    save_calls = []

    def save_plan(node, text, snapshot):
        save_calls.append((node, text, snapshot))
        return saved

    def wait_window(_dialog):
        _FakeText.instances[0].simulate_user_edit("第一行\n第二行")
        displayed_values = [
            widget.kwargs["textvariable"].get()
            for widget in widgets
            if widget.kwargs.get("textvariable") is not None
        ]
        assert any("未保存" in str(value) for value in displayed_values)
        buttons["保存撰写计划"].invoke()
        assert any(
            "已保存" in str(widget.kwargs["textvariable"].get())
            for widget in widgets
            if widget.kwargs.get("textvariable") is not None
        )
        buttons["关闭"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: original,
            save_writing_plan=save_plan,
        ),
        [heading],
    )

    assert result is None
    assert save_calls == [("1.4.2", "第一行\n第二行", original)]


def test_writing_plan_single_start_save_error_keeps_dialog_open(monkeypatch):
    buttons, dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    errors = []
    save_calls = []
    monkeypatch.setattr(
        gui.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message, kwargs)),
    )

    def save_plan(node, text, snapshot):
        save_calls.append((node, text, snapshot))
        raise WritingPlanStoreError("保存失败")

    def wait_window(_dialog):
        _FakeText.instances[0].simulate_user_edit("保留这段输入")
        buttons["开始扩写"].invoke()
        assert dialogs[0].destroy_calls == 0

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: _writing_plan_snapshot(),
            save_writing_plan=save_plan,
        ),
        [heading],
    )

    assert result is None
    assert save_calls and save_calls[0][:2] == ("1.4.2", "保留这段输入")
    assert errors and "保存失败" in errors[0][1]
    assert _FakeText.instances[0].content == "保留这段输入"


def test_writing_plan_single_whitespace_save_deletes_node_with_raw_text(monkeypatch):
    buttons, _dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    original = _writing_plan_snapshot("1.4.2", "旧计划")
    save_calls = []

    def wait_window(_dialog):
        _FakeText.instances[0].simulate_user_edit("  \n ")
        buttons["保存撰写计划"].invoke()
        buttons["关闭"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: original,
            save_writing_plan=lambda node, text, snapshot: (
                save_calls.append((node, text, snapshot))
                or _writing_plan_snapshot(fingerprint="deleted")
            ),
        ),
        [heading],
    )

    assert result is None
    assert save_calls == [("1.4.2", "  \n ", original)]


def test_writing_plan_single_unnumbered_title_is_transient_only(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="进场核验", full_path="项目 > 进场核验")
    save_calls = []

    def wait_window(_dialog):
        _FakeText.instances[0].simulate_user_edit("仅本次生成")
        assert buttons["保存撰写计划"].kwargs.get("state") == "disabled"
        buttons["开始扩写"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: _writing_plan_snapshot(),
            save_writing_plan=lambda *args: save_calls.append(args),
        ),
        [heading],
    )

    assert result == ("仅本次生成", 1200, 0, False, ["card-a"])
    assert save_calls == []
    displayed_values = [
        widget.kwargs["textvariable"].get()
        for widget in widgets
        if widget.kwargs.get("textvariable") is not None
    ]
    assert any("当前节点无可用编号" in str(value) for value in displayed_values)


@pytest.mark.parametrize(
    ("answer", "expected_destroy_calls", "expected_save_calls"),
    [(True, 1, 1), (False, 1, 0), (None, 0, 0)],
)
def test_writing_plan_single_dirty_close_supports_save_discard_cancel(
    monkeypatch, answer, expected_destroy_calls, expected_save_calls
):
    _buttons, dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    save_calls = []
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *_args, **_kwargs: answer)

    def wait_window(dialog):
        _FakeText.instances[0].simulate_user_edit("未保存计划")
        dialog.protocols["WM_DELETE_WINDOW"]()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=lambda: _writing_plan_snapshot(),
            save_writing_plan=lambda node, text, snapshot: (
                save_calls.append((node, text, snapshot))
                or _writing_plan_snapshot(node, text, fingerprint="saved")
            ),
        ),
        [heading],
    )

    assert result is None
    assert dialogs[0].destroy_calls == expected_destroy_calls
    assert len(save_calls) == expected_save_calls


def test_writing_plan_single_malformed_library_blocks_persistence_and_start(monkeypatch):
    buttons, dialogs, _widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    save_calls = []
    errors = []
    monkeypatch.setattr(
        gui.messagebox,
        "showerror",
        lambda title, message, **kwargs: errors.append((title, message, kwargs)),
    )

    def load_broken():
        raise WritingPlanValidationError("撰写计划文件格式错误")

    def wait_window(_dialog):
        assert buttons["保存撰写计划"].kwargs.get("state") == "disabled"
        assert buttons["开始扩写"].kwargs.get("state") == "disabled"
        buttons["开始扩写"].invoke()
        assert dialogs[0].destroy_calls == 0

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=load_broken,
            save_writing_plan=lambda *args: save_calls.append(args),
        ),
        [heading],
    )

    assert result is None
    assert save_calls == []
    assert errors and "格式错误" in errors[0][1]


def test_writing_plan_single_conflict_preserves_text_then_reload_replaces_it(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    heading = SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验")
    original = _writing_plan_snapshot("1.4.2", "原计划", fingerprint="old")
    external = _writing_plan_snapshot("1.4.2", "外部新计划", fingerprint="external")
    snapshots = iter((original, external))
    load_calls = []
    discard_prompts = []
    monkeypatch.setattr(
        gui.messagebox,
        "askyesno",
        lambda *args, **kwargs: discard_prompts.append((args, kwargs)) or True,
    )

    def load_snapshot():
        load_calls.append(True)
        return next(snapshots)

    def save_conflict(_node, _text, _snapshot):
        raise WritingPlanExternalModificationError("撰写计划文件已被外部修改")

    def wait_window(_dialog):
        text = _FakeText.instances[0]
        text.simulate_user_edit("本地未保存计划")
        buttons["保存撰写计划"].invoke()
        assert text.content == "本地未保存计划"
        assert any(
            "未保存" in str(widget.kwargs["textvariable"].get())
            for widget in widgets
            if widget.kwargs.get("textvariable") is not None
        )
        buttons["重新加载撰写计划"].invoke()
        assert text.content == "外部新计划"
        buttons["关闭"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            load_writing_plan_snapshot=load_snapshot,
            save_writing_plan=save_conflict,
        ),
        [heading],
    )

    assert result is None
    assert len(load_calls) == 2
    assert len(discard_prompts) == 1


def test_writing_plan_batch_shows_readonly_coverage_without_plan_editor(monkeypatch):
    buttons, _dialogs, widgets = _install_generation_dialog_fakes(monkeypatch)
    headings = [
        SimpleNamespace(title="1.4.1 总体安排", full_path="项目 > 1.4.1 总体安排"),
        SimpleNamespace(title="1.4.2 进场核验", full_path="项目 > 1.4.2 进场核验"),
        SimpleNamespace(title="进场说明", full_path="项目 > 进场说明"),
    ]
    snapshot = _writing_plan_snapshot("1.4.2", "只写启动准备阶段")
    save_calls = []

    def wait_window(_dialog):
        buttons["开始扩写"].invoke()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            writing_plan_store=object(),
            save_writing_plan=lambda *args: save_calls.append(args),
            summarize_writing_plans=lambda headings_arg, snapshot_arg: (
                assert_snapshot_and_return_coverage(headings_arg, snapshot_arg, headings, snapshot)
            ),
        ),
        headings,
        writing_plan_snapshot=snapshot,
    )

    assert result == ("", 1200, 0, True, None)
    assert save_calls == []
    assert _FakeText.instances == []
    assert "保存撰写计划" not in buttons
    assert "重新加载撰写计划" not in buttons
    assert any(
        widget.kwargs.get("text") == "节点撰写计划：1/3 个所选节点已配置；其中 1 个无可用编号"
        for widget in widgets
    )


def assert_snapshot_and_return_coverage(headings_arg, snapshot_arg, expected_headings, expected_snapshot):
    assert headings_arg == expected_headings
    assert snapshot_arg is expected_snapshot
    return WritingPlanCoverage(
        total_headings=3,
        numbered_headings=2,
        planned_headings=1,
    )
