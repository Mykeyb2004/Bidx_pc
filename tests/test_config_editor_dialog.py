from types import SimpleNamespace

import tkinter as tk

from bid_writer.config_editor_dialog import ScrollableSection


def test_scrollable_section_mousewheel_ignores_destroyed_widget():
    section = ScrollableSection.__new__(ScrollableSection)
    calls: list[str] = []

    section._mousewheel_bound = True
    section._unbind_mousewheel = lambda _event=None: calls.append("unbind")
    section.winfo_exists = lambda: False
    section.winfo_ismapped = lambda: True
    section.canvas = SimpleNamespace(yview_scroll=lambda *_args, **_kwargs: calls.append("scroll"))

    section._on_mousewheel(SimpleNamespace(delta=120))

    assert calls == ["unbind"]


def test_scrollable_section_mousewheel_catches_tclerror():
    section = ScrollableSection.__new__(ScrollableSection)
    calls: list[str] = []

    section._mousewheel_bound = True
    section._unbind_mousewheel = lambda _event=None: calls.append("unbind")
    section.winfo_exists = lambda: True

    def raise_tclerror():
        raise tk.TclError("widget destroyed")

    section.winfo_ismapped = raise_tclerror
    section.canvas = SimpleNamespace(yview_scroll=lambda *_args, **_kwargs: calls.append("scroll"))

    section._on_mousewheel(SimpleNamespace(delta=120))

    assert calls == ["unbind"]
