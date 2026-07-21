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
