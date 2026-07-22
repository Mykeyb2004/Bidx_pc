from types import SimpleNamespace

import bid_writer.gui as gui
from bid_writer.gui import MainWindow


class _FakeMenu:
    def __init__(self, *args, **kwargs):
        self.entries: list[dict[str, object]] = []
        self.configured: list[tuple[int, dict[str, object]]] = []
        self.posted_at: tuple[int, int] | None = None
        self.grab_released = False

    def add_command(self, **kwargs):
        self.entries.append(kwargs)

    def entryconfigure(self, index, **kwargs):
        self.configured.append((index, kwargs))

    def tk_popup(self, x, y):
        self.posted_at = (x, y)

    def grab_release(self):
        self.grab_released = True


class _FakeTree:
    def __init__(self, *, clicked_item: str, selected_items=()):
        self.clicked_item = clicked_item
        self.selected_items = tuple(selected_items)
        self.selection_set_calls: list[str] = []
        self.focus_calls: list[str] = []

    def identify_row(self, _y):
        return self.clicked_item

    def selection(self):
        return self.selected_items

    def selection_set(self, item_id):
        self.selection_set_calls.append(item_id)
        self.selected_items = (item_id,)

    def focus(self, item_id):
        self.focus_calls.append(item_id)


class _FakeVar:
    def __init__(self):
        self.values: list[str] = []

    def set(self, value):
        self.values.append(value)


class _FakeProgressBar:
    def __init__(self):
        self.config_calls: list[dict[str, object]] = []

    def configure(self, **kwargs):
        self.config_calls.append(kwargs)


class _FakeAdapter:
    def __init__(self, status="未开始", progress=(0, 0)):
        self.status = status
        self.progress = progress

    def get_status_text(self, _heading):
        return self.status

    def get_progress(self, _heading):
        return self.progress


def _heading(title: str, *, children=None):
    return SimpleNamespace(title=title, full_path=f"根 > {title}", children=children or [])


def test_outline_context_menu_includes_generate_selected(monkeypatch):
    monkeypatch.setattr(gui.tk, "Menu", _FakeMenu)
    window = SimpleNamespace(
        generate_context_menu_selection=lambda: None,
        extract_context_menu_facts=lambda: None,
    )

    MainWindow.create_outline_context_menu(window)

    assert [entry["label"] for entry in window.outline_context_menu.entries] == [
        "生成所选",
        "提炼事实卡片",
    ]


def test_tree_context_menu_preserves_multi_selection_when_clicking_selected_leaf():
    clicked_heading = _heading("实施安排")
    another_heading = _heading("服务保障")
    tree = _FakeTree(clicked_item="item-a", selected_items=("item-a", "item-b"))
    menu = _FakeMenu()
    window = SimpleNamespace(
        is_generating=False,
        outline_tree=tree,
        tree_node_map={"item-a": clicked_heading, "item-b": another_heading},
        outline_context_menu=menu,
    )
    window._fact_card_menu_label_for_heading = lambda heading: f"提炼 {heading.title}"
    event = SimpleNamespace(y=12, x_root=100, y_root=220)

    result = MainWindow.on_tree_context_menu(window, event)

    assert result == "break"
    assert tree.selection_set_calls == []
    assert tree.selection() == ("item-a", "item-b")
    assert tree.focus_calls == ["item-a"]
    assert menu.configured[0] == (0, {"label": "生成所选 2"})
    assert menu.configured[1] == (
        1,
        {"label": "提炼事实卡片（仅单选）", "state": gui.tk.DISABLED},
    )
    assert menu.posted_at == (100, 220)


def test_tree_context_menu_enables_fact_card_when_clicking_unselected_leaf_as_single_selection():
    clicked_heading = _heading("质量控制")
    previous_heading = _heading("服务保障")
    tree = _FakeTree(clicked_item="item-a", selected_items=("item-b",))
    menu = _FakeMenu()
    window = SimpleNamespace(
        is_generating=False,
        outline_tree=tree,
        tree_node_map={"item-a": clicked_heading, "item-b": previous_heading},
        outline_context_menu=menu,
    )
    window._fact_card_menu_label_for_heading = lambda heading: f"提炼 {heading.title}"
    event = SimpleNamespace(y=12, x_root=100, y_root=220)

    result = MainWindow.on_tree_context_menu(window, event)

    assert result == "break"
    assert tree.selection_set_calls == ["item-a"]
    assert tree.selection() == ("item-a",)
    assert menu.configured[0] == (0, {"label": "生成所选 1"})
    assert menu.configured[1] == (
        1,
        {"label": "提炼 质量控制", "state": gui.tk.NORMAL},
    )


def test_context_menu_generate_uses_context_heading_when_selection_is_empty():
    heading = _heading("质量控制")
    selected_after_generate: list[str] = []
    window = SimpleNamespace(is_generating=False)
    window._get_selected_leaf_headings = lambda: []
    window._get_context_menu_heading = lambda: heading
    window._set_single_heading_selection = lambda selected: selected_after_generate.append(selected.full_path)
    window.batch_generate = lambda: selected_after_generate.append("batch_generate")

    result = MainWindow.generate_context_menu_selection(window)

    assert result == "break"
    assert selected_after_generate == [heading.full_path, "batch_generate"]


def test_batch_generate_starts_without_secondary_confirmation(monkeypatch):
    heading = _heading("质量控制")
    generate_calls = []

    def fail_if_confirmed(*_args, **_kwargs):
        raise AssertionError("batch_generate should start directly after generation params are accepted")

    monkeypatch.setattr(gui.messagebox, "askyesno", fail_if_confirmed)

    window = SimpleNamespace(
        _get_selected_leaf_headings=lambda: [heading],
        _ensure_chapter_generation_model_configured=lambda: True,
        _get_generation_params=lambda _headings: ("补充资质", 1200, 0, True, ["card-a"]),
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(
                chapter_facts_enabled=False,
                chapter_facts_auto_extract_on_batch=False,
                build_target_word_range=lambda _target_words: SimpleNamespace(display_text="1000-1400"),
            )
        ),
        _do_batch_generate=lambda *args, **kwargs: generate_calls.append((args, kwargs)),
    )

    MainWindow.batch_generate(window)

    assert generate_calls == [
        (
            ([heading], "补充资质", 1200, 0),
            {
                "fact_card_mode": True,
                "manual_fact_card_selections": ["card-a"],
                "auto_extract_facts": False,
            },
        )
    ]


def test_do_batch_generate_refreshes_completed_status_before_next_heading():
    first = _heading("质量控制")
    second = _heading("服务保障")
    generated_titles: list[str] = []
    events: list[tuple[str, object]] = []

    def generate_into_workspace(heading, *_args, **_kwargs):
        events.append(("generate", heading.title))
        generated_titles.append(heading.title)
        return "success"

    def refresh_status():
        events.append(("refresh", tuple(generated_titles)))

    window = SimpleNamespace(
        progress_bar=_FakeProgressBar(),
        batch_progress_text=_FakeVar(),
        task_text=_FakeVar(),
        status_text=_FakeVar(),
        update_action_states=lambda: None,
        update_idletasks=lambda: None,
        _generate_into_workspace=generate_into_workspace,
        refresh_status=refresh_status,
    )

    MainWindow._do_batch_generate(window, [first, second], "", 1200, 0)

    assert events[:3] == [
        ("generate", "质量控制"),
        ("refresh", ("质量控制",)),
        ("generate", "服务保障"),
    ]


def test_refresh_workspace_updates_single_selection_while_generating():
    heading = _heading("服务保障")
    previews: list[str] = []
    summaries: list[int] = []
    idle_calls: list[bool] = []
    window = SimpleNamespace(
        is_generating=True,
        _get_selected_leaf_headings=lambda: [heading],
        _show_heading_preview_in_workspace=lambda selected: previews.append(selected.full_path),
        _show_workspace_selection_summary=lambda count: summaries.append(count),
        _show_workspace_idle=lambda: idle_calls.append(True),
    )

    MainWindow._refresh_workspace_from_selection(window)

    assert previews == [heading.full_path]
    assert summaries == []
    assert idle_calls == []
    assert window._workspace_view_heading_path == heading.full_path


def test_generation_queue_does_not_overwrite_workspace_when_viewing_other_heading():
    heading = _heading("质量控制")
    workspace_updates: list[tuple[tuple[object, ...], dict[str, object]]] = []
    start_calls: list[str] = []
    parent = SimpleNamespace(
        _show_generation_start_in_workspace=lambda selected: start_calls.append(selected.full_path),
        _should_show_generation_updates=lambda selected: False,
        _set_workspace_text=lambda *args, **kwargs: workspace_updates.append((args, kwargs)),
        _workspace_generation_buffers={},
        workspace_meta_var=_FakeVar(),
        status_text=_FakeVar(),
    )

    session = MainWindow.GenerationSession(parent, heading)
    session.is_generating = True
    session.text_queue.put(("text", "流式正文"))
    session.text_queue.put(("replace", "修复后正文"))
    session.text_queue.put(("status", "正在接收模型输出..."))
    session.text_queue.put(("done", ("修复后正文", 6, None)))

    session._check_queue()

    assert start_calls == [heading.full_path]
    assert workspace_updates == []
    assert parent._workspace_generation_buffers == {heading.full_path: "修复后正文"}
    assert parent.workspace_meta_var.values == []
    assert parent.status_text.values == [f"{heading.title}：正在接收模型输出..."]


def test_generation_start_does_not_overwrite_workspace_when_viewing_other_heading():
    generating_heading = _heading("质量控制")
    viewed_heading = _heading("服务保障")
    messages: list[tuple[str, str, str]] = []
    window = SimpleNamespace(
        _workspace_view_heading_path=viewed_heading.full_path,
        _show_workspace_message=lambda heading_text, meta_text, body_text, **_kwargs: messages.append(
            (heading_text, meta_text, body_text)
        ),
    )

    MainWindow._show_generation_start_in_workspace(window, generating_heading)

    assert messages == []


def test_heading_tree_status_marks_current_generating_leaf():
    heading = _heading("质量控制")
    window = SimpleNamespace(
        adapter=_FakeAdapter(status="未开始"),
        _current_generation_heading_path=heading.full_path,
        _status_to_row_tag=MainWindow._status_to_row_tag,
    )

    status, progress_info, row_tag = MainWindow._get_heading_tree_row_values(window, heading)

    assert status == "正在生成"
    assert progress_info == "-"
    assert row_tag == "generating"


def test_status_filter_uses_current_generating_status_override():
    heading = _heading("质量控制")
    window = SimpleNamespace(
        adapter=_FakeAdapter(status="未开始"),
        _current_generation_heading_path=heading.full_path,
    )

    assert MainWindow._heading_matches_status_filter(window, heading, "正在生成")
    assert not MainWindow._heading_matches_status_filter(window, heading, "未开始")


def test_heading_preview_uses_live_buffer_for_current_generating_heading():
    heading = _heading("质量控制")
    messages: list[tuple[str, str, str, dict[str, object]]] = []
    window = SimpleNamespace(
        _current_generation_heading_path=heading.full_path,
        _workspace_generation_buffers={heading.full_path: "已收到的正文片段"},
        bid_writer=SimpleNamespace(
            file_saver=SimpleNamespace(find_existing_filepath=lambda _heading: None)
        ),
        _show_workspace_message=lambda heading_text, meta_text, body_text, **kwargs: messages.append(
            (heading_text, meta_text, body_text, kwargs)
        ),
    )

    MainWindow._show_heading_preview_in_workspace(window, heading)

    assert messages == [
        (
            f"当前章节：{heading.full_path}",
            "正在生成正文",
            "已收到的正文片段",
            {"generated_char_count": gui._count_text_characters("已收到的正文片段")},
        )
    ]
