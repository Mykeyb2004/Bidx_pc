from types import SimpleNamespace

import bid_writer.gui as gui
from bid_writer import fact_card_dialogs
from bid_writer.gui import MainWindow


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

    def pack(self, *_args, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)


class _FakeText(_FakeWidget):
    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.content = ""

    def insert(self, _index, value):
        self.content += value

    def get(self, *_args):
        return self.content


class _FakeDialog(_FakeWidget):
    def __init__(self, *_args, **_kwargs):
        super().__init__()
        self.destroy_calls = 0

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


class _FakeFactCardSelectionPanel(_FakeWidget):
    def __init__(self, *_args, **_kwargs):
        super().__init__()

    def get_selections(self):
        return ["card-a"]


def _install_generation_dialog_fakes(monkeypatch):
    buttons = {}
    dialogs = []

    class _FakeButton(_FakeWidget):
        def __init__(self, *_args, text="", command=None, **_kwargs):
            super().__init__()
            self.text = text
            self.command = command
            buttons[text] = self

    def _new_dialog(*args, **kwargs):
        dialog = _FakeDialog(*args, **kwargs)
        dialogs.append(dialog)
        return dialog

    monkeypatch.setattr(gui.tk, "Toplevel", _new_dialog)
    monkeypatch.setattr(gui.tk, "Text", _FakeText)
    monkeypatch.setattr(gui.tk, "IntVar", _FakeVar)
    monkeypatch.setattr(gui.tk, "BooleanVar", _FakeVar)
    monkeypatch.setattr(gui.tk, "StringVar", _FakeVar)
    monkeypatch.setattr(gui.ttk, "Frame", _FakeWidget)
    monkeypatch.setattr(gui.ttk, "Label", _FakeWidget)
    monkeypatch.setattr(gui.ttk, "Checkbutton", _FakeWidget)
    monkeypatch.setattr(gui.ttk, "Spinbox", _FakeWidget)
    monkeypatch.setattr(gui.ttk, "Button", _FakeButton)
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

    return buttons, dialogs


def _fake_generation_window(wait_window, save_callback=None):
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
            save_chapter_default_fact_cards=save_callback or (lambda *_args: None),
        ),
        status_text=SimpleNamespace(set=lambda _value: None),
        wait_window=wait_window,
        _build_generation_fact_card_dialog_state=MainWindow._build_generation_fact_card_dialog_state,
    )


def test_generation_params_start_button_saves_fact_card_references(monkeypatch):
    buttons, _dialogs = _install_generation_dialog_fakes(monkeypatch)
    saved_calls = []
    heading = SimpleNamespace(title="质量控制", full_path="项目 > 质量控制")

    def wait_window(_dialog):
        buttons["开始扩写"].command()

    result = MainWindow._get_generation_params(
        _fake_generation_window(
            wait_window,
            save_callback=lambda chapter_path, selections: saved_calls.append((chapter_path, selections)),
        ),
        [heading],
        initial_requirements="补充资质",
    )

    assert result == ("补充资质", 1200, 0, False, ["card-a"])
    assert saved_calls == [("项目 > 质量控制", ["card-a"])]


def test_save_fact_card_references_keeps_generation_params_dialog_open(monkeypatch):
    buttons, dialogs = _install_generation_dialog_fakes(monkeypatch)
    saved_calls = []
    heading = SimpleNamespace(title="质量控制", full_path="项目 > 质量控制")

    def wait_window(_dialog):
        buttons["保存事实卡片引用关系"].command()
        assert dialogs[0].destroy_calls == 0

    window = _fake_generation_window(wait_window)
    window.bid_writer.save_chapter_default_fact_cards = (
        lambda chapter_path, selections: saved_calls.append((chapter_path, selections))
    )

    result = MainWindow._get_generation_params(window, [heading])

    assert result is None
    assert saved_calls == [("项目 > 质量控制", ["card-a"])]
