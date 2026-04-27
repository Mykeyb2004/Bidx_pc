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
    assert menu.posted_at == (100, 220)


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
