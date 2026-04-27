from types import SimpleNamespace

import tkinter as tk

from bid_writer import config_editor_dialog
from bid_writer.config_editor_dialog import ConfigEditorDialog, ScrollableSection


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


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


def test_config_editor_new_mode_first_save_uses_save_as_even_when_target_exists(tmp_path):
    target_path = tmp_path / "config_新项目.yaml"
    target_path.write_text("existing: true\n", encoding="utf-8")
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    calls: list[str] = []

    dialog.is_new_config = True
    dialog.active_config_path = target_path
    dialog.document = SimpleNamespace(config_path=target_path)
    dialog._save_as = lambda: calls.append("save_as")
    dialog._save = lambda **_kwargs: calls.append("save")

    dialog._save_current()

    assert calls == ["save_as"]


def test_config_editor_existing_mode_save_current_saves_target_directly(tmp_path):
    target_path = tmp_path / "config.yaml"
    calls: list[dict[str, object]] = []
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)

    dialog.is_new_config = False
    dialog.active_config_path = target_path
    dialog.document = SimpleNamespace(config_path=target_path)
    dialog._save = lambda **kwargs: calls.append(kwargs)

    dialog._save_current()

    assert calls == [{"target_path": target_path, "ask_switch": False}]


def test_config_editor_new_mode_save_as_offers_default_filename(monkeypatch, tmp_path):
    target_path = tmp_path / "custom-name.yaml"
    captured: dict[str, object] = {}
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)

    dialog.is_new_config = True
    dialog.active_config_path = target_path
    dialog.document = SimpleNamespace(config_path=target_path)
    dialog._save = lambda **_kwargs: None

    def fake_asksaveasfilename(**kwargs):
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(config_editor_dialog.filedialog, "asksaveasfilename", fake_asksaveasfilename)

    dialog._save_as()

    assert captured["initialdir"] == str(tmp_path)
    assert captured["initialfile"] == "config_新项目.yaml"


def test_config_editor_load_new_document_uses_unsaved_template(monkeypatch, tmp_path):
    target_path = tmp_path / "config_新项目.yaml"
    document = SimpleNamespace(config_path=target_path, model={"project": {}}, render_yaml=lambda: "rendered\n")
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    calls: list[object] = []

    dialog.active_config_path = target_path
    dialog.current_file_var = StubVar()
    dialog._populate_vars = lambda model: calls.append(("populate", model))
    dialog._update_connection_panel = lambda: calls.append("connection")
    dialog._refresh_side_panel = lambda: calls.append("refresh")
    monkeypatch.setattr(config_editor_dialog, "create_new_config_editor_document", lambda config_path: document)

    dialog._load_new_document()

    assert dialog.document is document
    assert dialog.current_file_var.get() == "当前文件：未保存的新配置"
    assert dialog._saved_yaml == ""
    assert calls == [("populate", document.model), "connection", "refresh"]


def test_config_editor_reload_resets_new_document_template():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    calls: list[str] = []

    dialog.is_new_config = True
    dialog._has_unsaved_changes = lambda: False
    dialog._load_new_document = lambda: calls.append("load_new")
    dialog._load_document = lambda _path: calls.append("load_existing")

    dialog._reload_from_disk()

    assert calls == ["load_new"]


def test_config_editor_successful_save_exits_new_mode(tmp_path):
    target_path = tmp_path / "config_新项目.yaml"
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    titles: list[str] = []
    loaded_paths = []
    saved_paths = []
    document = SimpleNamespace(
        config_path=target_path,
        validate=lambda _model: [],
        save=lambda _model, *, target_path, create_backup: saved_paths.append((target_path, create_backup)) or target_path,
        render_yaml=lambda: "saved\n",
    )

    dialog.is_new_config = True
    dialog.document = document
    dialog.active_config_path = target_path
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.current_file_var = StubVar()
    dialog.status_var = StubVar()
    dialog._collect_model = lambda: {"project": {}}
    dialog._load_document = lambda path: loaded_paths.append(path)
    dialog.title = lambda value: titles.append(value)

    dialog._save(target_path=target_path, ask_switch=False)

    assert saved_paths == [(target_path, True)]
    assert dialog.is_new_config is False
    assert titles == ["配置编辑器"]
    assert dialog.current_file_var.get() == f"当前文件：{target_path}"
    assert dialog.result == {"saved_path": target_path, "apply_path": target_path}
    assert dialog.status_var.get() == "已保存，关闭窗口后会自动重载当前配置"
    assert loaded_paths == [target_path]
