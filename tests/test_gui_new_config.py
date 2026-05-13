from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import pytest

from bid_writer import config_editor_dialog
from bid_writer.gui import MainWindow, _ensure_env_local_file


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


def test_startup_build_prompts_when_only_discovered_configs_exist(monkeypatch, tmp_path):
    from bid_writer import gui

    calls: list[dict[str, object]] = []

    def fake_candidates(config_path=None, *, base_dir=None, include_discovered_configs=True):
        calls.append(
            {
                "config_path": config_path,
                "base_dir": base_dir,
                "include_discovered_configs": include_discovered_configs,
            }
        )
        return []

    monkeypatch.setattr(gui, "get_startup_config_candidates", fake_candidates)

    with pytest.raises(FileNotFoundError):
        gui._build_startup_bid_writer(None, base_dir=tmp_path)

    assert calls == [
        {
            "config_path": None,
            "base_dir": tmp_path,
            "include_discovered_configs": False,
        }
    ]


def test_startup_recovery_defers_new_config_outline_prepare_to_workbench(monkeypatch, tmp_path):
    from bid_writer import gui

    selected_path = tmp_path / "config_新项目.yaml"
    recovered = (object(), False)
    build_calls: list[dict[str, object]] = []

    class FakeRoot:
        def withdraw(self):
            pass

        def destroy(self):
            pass

    monkeypatch.setattr(gui.tk, "Tk", FakeRoot)
    monkeypatch.setattr(gui, "setup_gui_theme", lambda _root: None)
    monkeypatch.setattr(gui, "set_window_brand_icon", lambda _root: None)
    monkeypatch.setattr(gui, "choose_config_file", lambda **_kwargs: gui.NEW_CONFIG_REQUEST)
    monkeypatch.setattr(gui, "_open_new_config_wizard_for_startup", lambda _parent, _base_dir: str(selected_path))

    def fake_build(config_path=None, *, base_dir=None, prepare_parent=None):
        build_calls.append(
            {
                "config_path": config_path,
                "base_dir": base_dir,
                "prepare_parent": prepare_parent,
            }
        )
        return recovered

    monkeypatch.setattr(gui, "_build_startup_bid_writer", fake_build)

    result = gui._recover_startup_bid_writer(
        None,
        base_dir=tmp_path,
        startup_error=FileNotFoundError("missing"),
    )

    assert result == recovered
    assert build_calls == [
        {
            "config_path": str(selected_path),
            "base_dir": tmp_path,
            "prepare_parent": None,
        }
    ]


def test_setup_gui_theme_rebinds_ttkbootstrap_after_destroyed_root(monkeypatch):
    from bid_writer import gui

    class DeadMaster:
        def winfo_exists(self):
            raise tk.TclError("application has been destroyed")

    class FakeRoot:
        def __init__(self):
            self.option_calls: list[tuple[object, ...]] = []

        def _root(self):
            return self

        def option_add(self, *args):
            self.option_calls.append(args)

    root = FakeRoot()

    class FakeBootstrapStyle:
        instance = SimpleNamespace(master=DeadMaster())

        def __new__(cls, theme=None):
            if cls.instance is not None:
                return cls.instance
            return super().__new__(cls)

        def __init__(self, theme=None):
            if getattr(self, "_initialized", False):
                return
            self.theme = theme
            self.master = root
            self._initialized = True
            FakeBootstrapStyle.instance = self

    class FakeTtkStyle:
        def __init__(self, master):
            self.master = master
            self.configure_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.map_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def configure(self, *args, **kwargs):
            self.configure_calls.append((args, kwargs))

        def map(self, *args, **kwargs):
            self.map_calls.append((args, kwargs))

        def theme_names(self):
            return []

        def theme_use(self, _theme):
            pass

    scale_profile = SimpleNamespace(
        button_padding=(1, 1),
        field_padding=(1, 1),
        tree_rowheight=24,
        compact_font_size=10,
        default_font_size=11,
        heading_font_size=12,
        text_padding=(1, 1),
    )
    palette = SimpleNamespace(
        surface_background="#f0f0f0",
        input_background="#ffffff",
        input_foreground="#111111",
        border_color="#cccccc",
        accent_color="#3b82f6",
    )

    monkeypatch.setattr(gui, "_TTKBOOTSTRAP_MODULE", SimpleNamespace(Style=FakeBootstrapStyle))
    monkeypatch.setattr(gui, "_TTKBOOTSTRAP_READY", True)
    monkeypatch.setattr(gui, "_get_gui_scale_profile", lambda _root: scale_profile)
    monkeypatch.setattr(gui, "_configure_named_fonts", lambda _profile: None)
    monkeypatch.setattr(gui, "_build_gui_color_palette", lambda _style: palette)
    monkeypatch.setattr(gui.ttk, "Style", FakeTtkStyle)

    style = gui.setup_gui_theme(root)

    assert FakeBootstrapStyle.instance.master is root
    assert root._bid_writer_bootstrap_style.master is root
    assert root._bid_writer_style is style
    assert root._bid_writer_gui_color_palette is palette


def test_prepare_startup_outline_loads_outline_after_confirmation(tmp_path):
    config = SimpleNamespace(outline_locked=False)
    writer = SimpleNamespace(config=config)
    prepared = []
    loaded = []

    fake_window = SimpleNamespace(
        bid_writer=writer,
        _prepare_unlocked_outline=lambda active_writer: prepared.append(active_writer) or setattr(config, "outline_locked", True) or True,
        load_outline=lambda preserve_tree_view=True, reset_tree_view=False: loaded.append(
            (preserve_tree_view, reset_tree_view)
        ) or True,
    )

    MainWindow._prepare_startup_outline_if_needed(fake_window)

    assert prepared == [writer]
    assert loaded == [(False, True)]


def test_prepare_startup_outline_cancel_keeps_workbench_open(tmp_path):
    config = SimpleNamespace(outline_locked=False)
    writer = SimpleNamespace(config=config)
    state_updates = []
    loaded = []
    fake_window = SimpleNamespace(
        bid_writer=writer,
        status_text=_FakeVar(),
        update_action_states=lambda: state_updates.append(True),
        _prepare_unlocked_outline=lambda _writer: False,
        load_outline=lambda **_kwargs: loaded.append(True),
    )

    MainWindow._prepare_startup_outline_if_needed(fake_window)

    assert loaded == []
    assert state_updates == [True]
    assert fake_window.status_text.value == "大纲准备已取消，可从“项目 -> 继续准备大纲...”继续"


def test_ensure_env_local_file_copies_example_next_to_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    example = tmp_path / ".env.example"
    example.write_text("BID_WRITER_API_KEY=\n", encoding="utf-8")

    env_path = _ensure_env_local_file(config_path)

    assert env_path == tmp_path / ".env.local"
    assert env_path.read_text(encoding="utf-8") == "BID_WRITER_API_KEY=\n"


def test_missing_env_local_prompt_creates_and_opens_file(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    (tmp_path / ".env.example").write_text("BID_WRITER_API_KEY=\n", encoding="utf-8")
    opened: list[Path] = []

    fake_window = SimpleNamespace(
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(config_path=config_path, api_key="")
        ),
        _env_local_prompted_dirs=set(),
        status_text=_FakeVar(),
    )
    monkeypatch.setattr("bid_writer.gui.messagebox.askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("bid_writer.gui._open_file_for_edit", lambda path: opened.append(Path(path)))

    MainWindow._maybe_prompt_missing_env_local(fake_window)

    assert (tmp_path / ".env.local").exists()
    assert opened == [tmp_path / ".env.local"]
    assert fake_window.status_text.value == ".env.local 已打开，填写保存后请重启软件"


def test_missing_env_local_prompt_skips_when_api_key_already_configured(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    asked = []
    fake_window = SimpleNamespace(
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(config_path=config_path, api_key="external-key")
        ),
        _env_local_prompted_dirs=set(),
        status_text=_FakeVar(),
    )
    monkeypatch.setattr("bid_writer.gui.messagebox.askyesno", lambda *_args, **_kwargs: asked.append(True))

    MainWindow._maybe_prompt_missing_env_local(fake_window)

    assert asked == []
    assert not (tmp_path / ".env.local").exists()


def test_batch_generate_prompts_for_env_local_before_params(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    (tmp_path / ".env.example").write_text("BID_WRITER_API_KEY=\n", encoding="utf-8")
    opened: list[Path] = []
    params_requested = []
    prompts: list[str] = []

    fake_window = SimpleNamespace(
        bid_writer=SimpleNamespace(
            config=SimpleNamespace(config_path=config_path, api_key=""),
            reload_config=lambda: None,
        ),
        status_text=_FakeVar(),
        _get_selected_leaf_headings=lambda: [SimpleNamespace(title="服务方案")],
        _get_generation_params=lambda _headings: params_requested.append(True),
    )
    fake_window._reload_config_before_env_check = (
        lambda: MainWindow._reload_config_before_env_check(fake_window)
    )
    fake_window._ensure_chapter_generation_model_configured = (
        lambda: MainWindow._ensure_chapter_generation_model_configured(fake_window)
    )
    monkeypatch.setattr(
        "bid_writer.gui.messagebox.askyesno",
        lambda _title, message, **_kwargs: prompts.append(message) or True,
    )
    monkeypatch.setattr("bid_writer.gui._open_file_for_edit", lambda path: opened.append(Path(path)))

    MainWindow.batch_generate(fake_window)

    assert params_requested == []
    assert (tmp_path / ".env.local").exists()
    assert opened == [tmp_path / ".env.local"]
    assert "扩写章节前需要先配置模型连接" in prompts[0]
    assert "BID_WRITER_API_KEY=你的 API Key" in prompts[0]
    assert fake_window.status_text.value == ".env.local 已打开，保存后请重新载入当前配置再扩写"


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
