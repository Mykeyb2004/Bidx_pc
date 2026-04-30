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
        bid_writer=SimpleNamespace(config=SimpleNamespace(config_path=config_path, outline_locked=True)),
        open_new_config_editor=lambda: None,
        select_and_switch_config=lambda: None,
        open_config_editor=lambda: None,
        unlock_and_prepare_outline=lambda: None,
        reload_outline=lambda: None,
        refresh_status=lambda: None,
        open_output_dir=lambda: None,
        quit=lambda: None,
    )


def test_project_menu_starts_with_new_config_entry(tmp_path):
    fake_window = _fake_window(tmp_path / "config.yaml")
    menu = _FakeMenu()

    MainWindow._populate_project_menu(fake_window, menu)

    assert menu.labels[:4] == ["新建配置...", "切换配置...", "编辑当前配置...", "解锁/重新准备大纲..."]
    assert menu.items[0]["command"] is fake_window.open_new_config_editor


def test_update_action_states_configures_project_menu_commands_only(tmp_path):
    fake_window = _fake_window(tmp_path / "config.yaml")
    fake_window.bid_writer.parser = object()
    fake_window.is_generating = True
    fake_window.is_modal_workflow_active = False
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
        ("解锁/重新准备大纲...", tk.DISABLED),
        ("重载大纲", tk.DISABLED),
        ("扫描输出状态", tk.DISABLED),
        ("打开输出目录", tk.DISABLED),
    ]


def test_update_action_states_disables_old_project_during_modal_workflow(tmp_path):
    fake_window = _fake_window(tmp_path / "config.yaml")
    fake_window.bid_writer.parser = object()
    fake_window.is_generating = False
    fake_window.is_modal_workflow_active = True
    fake_window.visible_leaf_count = 3
    fake_window.generated_leaf_count = 2
    fake_window.selection_text = _FakeVar()
    fake_window.btn_generate = _FakeWidget()
    fake_window.btn_merge = _FakeWidget()
    fake_window.btn_selection_menu = _FakeWidget()
    fake_window.btn_stop_generation = _FakeWidget()
    fake_window.selection_tools_menu = _FakeSelectionToolsMenu()
    fake_window.search_entry = _FakeWidget()
    fake_window.status_filter_combo = _FakeWidget()
    fake_window._get_selected_leaf_headings = lambda: [object()]
    fake_window.schedule_responsive_layout = lambda: None

    project_menu = _FakeMenu()
    MainWindow._populate_project_menu(fake_window, project_menu)
    fake_window.project_menu = project_menu

    MainWindow.update_action_states(fake_window)

    assert fake_window.btn_generate.config_calls[-1]["state"] == tk.DISABLED
    assert fake_window.btn_merge.config_calls[-1]["state"] == tk.DISABLED
    assert fake_window.search_entry.config_calls[-1]["state"] == tk.DISABLED
    assert fake_window.status_filter_combo.config_calls[-1]["state"] == "disabled"
    assert all(state == tk.DISABLED for _label, state in project_menu.configured_entries)


def test_open_new_config_editor_uses_default_path_next_to_current_config(monkeypatch, tmp_path):
    current_path = tmp_path / "config.yaml"
    expected_path = tmp_path / "config_新项目.yaml"
    created: list[dict[str, object]] = []
    switches: list[dict[str, object]] = []
    waited: list[object] = []

    class FakeNewConfigWizardDialog:
        def __init__(self, parent, config_path):
            created.append(
                {"parent": parent, "config_path": config_path}
            )
            self.result = {"apply_path": expected_path}

    fake_window = _fake_window(current_path)
    fake_window.status_text = _FakeVar()
    fake_window.is_modal_workflow_active = False
    state_updates: list[bool] = []
    fake_window.update_action_states = lambda: state_updates.append(fake_window.is_modal_workflow_active)
    fake_window._set_modal_workflow_active = lambda active, status_text=None: MainWindow._set_modal_workflow_active(
        fake_window,
        active,
        status_text,
    )
    fake_window.wait_window = lambda dialog: waited.append(dialog)
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr("bid_writer.new_config_wizard.NewConfigWizardDialog", FakeNewConfigWizardDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert created == [
        {"parent": fake_window, "config_path": expected_path}
    ]
    assert len(waited) == 1
    assert switches == [{"path": expected_path, "force_reload": False}]
    assert state_updates == [True, False]


def test_open_new_config_editor_forces_reload_when_applying_current_path(monkeypatch, tmp_path):
    current_path = tmp_path / "config_新项目.yaml"
    switches: list[dict[str, object]] = []

    class FakeNewConfigWizardDialog:
        def __init__(self, _parent, _config_path):
            self.result = {"apply_path": current_path}

    fake_window = _fake_window(current_path)
    fake_window.status_text = _FakeVar()
    fake_window.is_modal_workflow_active = False
    state_updates: list[bool] = []
    fake_window.update_action_states = lambda: state_updates.append(fake_window.is_modal_workflow_active)
    fake_window._set_modal_workflow_active = lambda active, status_text=None: MainWindow._set_modal_workflow_active(
        fake_window,
        active,
        status_text,
    )
    fake_window.wait_window = lambda _dialog: None
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr("bid_writer.new_config_wizard.NewConfigWizardDialog", FakeNewConfigWizardDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert switches == [{"path": current_path, "force_reload": True}]


def test_open_new_config_editor_ignores_cancelled_dialog(monkeypatch, tmp_path):
    current_path = tmp_path / "config.yaml"
    switches: list[dict[str, object]] = []

    class FakeNewConfigWizardDialog:
        def __init__(self, _parent, _config_path):
            self.result = {"apply_path": None}

    fake_window = _fake_window(current_path)
    fake_window.status_text = _FakeVar()
    fake_window.is_modal_workflow_active = False
    state_updates: list[bool] = []
    fake_window.update_action_states = lambda: state_updates.append(fake_window.is_modal_workflow_active)
    fake_window._set_modal_workflow_active = lambda active, status_text=None: MainWindow._set_modal_workflow_active(
        fake_window,
        active,
        status_text,
    )
    fake_window.wait_window = lambda _dialog: None
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: switches.append(
        {"path": path, "force_reload": force_reload}
    )
    monkeypatch.setattr("bid_writer.new_config_wizard.NewConfigWizardDialog", FakeNewConfigWizardDialog)

    MainWindow.open_new_config_editor(fake_window)

    assert switches == []
    assert state_updates == [True, False]
    assert fake_window.status_text.value == "已取消新建配置，仍在使用：config.yaml"


def test_switch_to_config_prepares_unlocked_outline_before_applying(monkeypatch, tmp_path):
    selected_path = tmp_path / "config_new.yaml"
    current_path = tmp_path / "config.yaml"
    prepared = []
    loaded = []
    synced = []

    class FakeConfig:
        def __init__(self):
            self.config_path = selected_path
            self.outline_locked = False

    class FakeBidWriter:
        def __init__(self, config_path):
            assert Path(config_path) == selected_path
            self.config = FakeConfig()
            self.parser = object()

        def reload_config(self):
            self.config.outline_locked = True

        def load_outline(self):
            loaded.append(True)
            return True

    fake_window = _fake_window(current_path)
    fake_window.status_text = _FakeVar()
    fake_window.update_idletasks = lambda: None
    fake_window._sync_loaded_outline = lambda reset_tree_view=False: synced.append(reset_tree_view)
    monkeypatch.setattr("bid_writer.gui.BidWriter", FakeBidWriter)
    monkeypatch.setattr("bid_writer.gui.GUIAdapter", lambda writer: SimpleNamespace(writer=writer))
    fake_window._prepare_unlocked_outline = lambda writer: prepared.append(writer) or True

    result = MainWindow._switch_to_config_path(fake_window, selected_path)

    assert result is True
    assert len(prepared) == 1
    assert loaded == [True]
    assert synced == [True]
    assert fake_window.bid_writer.config.config_path == selected_path


def test_switch_to_config_cancelled_outline_prepare_keeps_current_config(monkeypatch, tmp_path):
    selected_path = tmp_path / "config_new.yaml"
    current_path = tmp_path / "config.yaml"
    original_writer = SimpleNamespace(config=SimpleNamespace(config_path=current_path))

    class FakeConfig:
        config_path = selected_path
        outline_locked = False

    class FakeBidWriter:
        def __init__(self, _config_path):
            self.config = FakeConfig()

        def load_outline(self):
            raise AssertionError("load_outline should not run when preparation is cancelled")

    fake_window = _fake_window(current_path)
    fake_window.bid_writer = original_writer
    fake_window.status_text = _FakeVar()
    fake_window.update_idletasks = lambda: None
    fake_window._prepare_unlocked_outline = lambda _writer: False
    monkeypatch.setattr("bid_writer.gui.BidWriter", FakeBidWriter)

    result = MainWindow._switch_to_config_path(fake_window, selected_path)

    assert result is False
    assert fake_window.bid_writer is original_writer
    assert fake_window.status_text.value == "大纲准备已取消，仍在使用：config.yaml"


def test_unlock_and_prepare_outline_sets_lock_false_then_reopens_dialog(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    calls = []
    fake_window = _fake_window(config_path)
    fake_window.is_generating = False
    fake_window.bid_writer.config.outline_locked = True
    fake_window.status_text = _FakeVar()
    fake_window._switch_to_config_path = lambda path, *, force_reload=False: calls.append((path, force_reload))
    monkeypatch.setattr("bid_writer.gui.messagebox.askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("bid_writer.gui.set_outline_locked", lambda path, locked: calls.append((Path(path), locked)))

    MainWindow.unlock_and_prepare_outline(fake_window)

    assert calls == [(config_path, False), (config_path, True)]
