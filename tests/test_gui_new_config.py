from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

from bid_writer import config_editor_dialog
from bid_writer.gui import MainWindow


class _FakeMenu:
    def __init__(self):
        self.items: list[dict[str, object]] = []
        self.configured_entries: list[tuple[str, object]] = []

    def add_command(self, *, label, command):
        self.items.append({"label": label, "command": command})

    def add_separator(self):
        self.items.append({"label": "---", "command": None})

    def entryconfigure(self, index, **kwargs):
        item = self.items[index]
        if item["command"] is None:
            raise AssertionError(f"separator entry configured at index {index}")
        item.update(kwargs)
        self.configured_entries.append((str(item["label"]), kwargs.get("state")))

    @property
    def labels(self) -> list[str]:
        return [str(item["label"]) for item in self.items]


class _FakeWidget:
    def __init__(self):
        self.config_calls: list[dict[str, object]] = []

    def config(self, **kwargs):
        self.config_calls.append(kwargs)


class _FakeVar:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _FakeSelectionToolsMenu:
    def __init__(self):
        self.configured_entries: list[tuple[str, object]] = []

    def entryconfigure(self, label, **kwargs):
        self.configured_entries.append((label, kwargs.get("state")))


def _fake_window(config_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        bid_writer=SimpleNamespace(config=SimpleNamespace(config_path=config_path)),
        open_new_config_editor=lambda: None,
        select_and_switch_config=lambda: None,
        open_config_editor=lambda: None,
        reload_outline=lambda: None,
        refresh_status=lambda: None,
        open_output_dir=lambda: None,
        quit=lambda: None,
    )


def test_project_menu_starts_with_new_config_entry(tmp_path):
    fake_window = _fake_window(tmp_path / "config.yaml")
    menu = _FakeMenu()

    MainWindow._populate_project_menu(fake_window, menu)

    assert menu.labels[:3] == ["新建配置...", "切换配置...", "编辑当前配置..."]
    assert menu.items[0]["command"] is fake_window.open_new_config_editor


def test_update_action_states_configures_project_menu_commands_only(tmp_path):
    fake_window = _fake_window(tmp_path / "config.yaml")
    fake_window.bid_writer.parser = object()
    fake_window.is_generating = True
    fake_window.visible_leaf_count = 0
    fake_window.generated_leaf_count = 0
    fake_window.selection_text = _FakeVar()
    fake_window.btn_generate = _FakeWidget()
    fake_window.btn_merge = _FakeWidget()
    fake_window.btn_selection_menu = _FakeWidget()
    fake_window.btn_stop_generation = _FakeWidget()
    fake_window.selection_tools_menu = _FakeSelectionToolsMenu()
    fake_window.search_entry = _FakeWidget()
    fake_window.status_filter_combo = _FakeWidget()
    fake_window._get_selected_leaf_headings = lambda: []
    fake_window.schedule_responsive_layout = lambda: None

    project_menu = _FakeMenu()
    MainWindow._populate_project_menu(fake_window, project_menu)
    fake_window.project_menu = project_menu

    MainWindow.update_action_states(fake_window)

    assert project_menu.configured_entries == [
        ("新建配置...", tk.DISABLED),
        ("切换配置...", tk.DISABLED),
        ("编辑当前配置...", tk.DISABLED),
        ("重载大纲", tk.DISABLED),
        ("扫描输出状态", tk.DISABLED),
        ("打开输出目录", tk.DISABLED),
    ]


def test_open_new_config_editor_uses_default_path_next_to_current_config(monkeypatch, tmp_path):
    current_path = tmp_path / "config.yaml"
    expected_path = tmp_path / "config_新项目.yaml"
    created: list[dict[str, object]] = []
    switches: list[dict[str, object]] = []
    waited: list[object] = []

    class FakeConfigEditorDialog:
        def __init__(self, parent, config_path, *, new_config):
            created.append(
                {"parent": parent, "config_path": config_path, "new_config": new_config}
            )
            self.result = {"apply_path": expected_path}

    fake_window = _fake_window(current_path)
    fake_window.wait_window = lambda dialog: waited.append(dialog)
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr(config_editor_dialog, "ConfigEditorDialog", FakeConfigEditorDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert created == [
        {"parent": fake_window, "config_path": expected_path, "new_config": True}
    ]
    assert len(waited) == 1
    assert switches == [{"path": expected_path, "force_reload": False}]


def test_open_new_config_editor_forces_reload_when_applying_current_path(monkeypatch, tmp_path):
    current_path = tmp_path / "config_新项目.yaml"
    switches: list[dict[str, object]] = []

    class FakeConfigEditorDialog:
        def __init__(self, _parent, _config_path, *, new_config):
            assert new_config is True
            self.result = {"apply_path": current_path}

    fake_window = _fake_window(current_path)
    fake_window.wait_window = lambda _dialog: None
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr(config_editor_dialog, "ConfigEditorDialog", FakeConfigEditorDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert switches == [{"path": current_path, "force_reload": True}]


def test_open_new_config_editor_ignores_cancelled_dialog(monkeypatch, tmp_path):
    current_path = tmp_path / "config.yaml"
    switches: list[dict[str, object]] = []

    class FakeConfigEditorDialog:
        def __init__(self, _parent, _config_path, *, new_config):
            assert new_config is True
            self.result = {"apply_path": None}

    fake_window = _fake_window(current_path)
    fake_window.wait_window = lambda _dialog: None
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr(config_editor_dialog, "ConfigEditorDialog", FakeConfigEditorDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert switches == []
