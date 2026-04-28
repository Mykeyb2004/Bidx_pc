from pathlib import PureWindowsPath
from types import SimpleNamespace

import tkinter as tk

from bid_writer import config_editor_dialog
from bid_writer.config_editor import create_new_config_editor_document
from bid_writer.config_editor_dialog import ConfigEditorDialog, ScrollableSection, _label_wraplength_for_width


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def trace_add(self, *_args, **_kwargs):
        return None

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


def test_scrollable_section_canvas_leaves_gutter_before_scrollbar():
    section = ScrollableSection.__new__(ScrollableSection)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    section.window_id = "content-window"
    section.canvas = SimpleNamespace(itemconfigure=lambda *args, **kwargs: calls.append((args, kwargs)))

    section._on_canvas_configure(SimpleNamespace(width=240))

    assert calls == [(("content-window",), {"width": 212})]


def test_label_wraplength_tracks_available_container_width():
    assert _label_wraplength_for_width(560, horizontal_padding=48) == 512


def test_label_wraplength_never_exceeds_narrow_container_width():
    assert _label_wraplength_for_width(32, horizontal_padding=48) == 1


def test_config_editor_path_browse_button_keeps_right_gutter(monkeypatch):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    parent = SimpleNamespace(columnconfigure=lambda *_args, **_kwargs: None)
    created_buttons = []

    class FakeButton:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.grid_kwargs = None
            created_buttons.append(self)

        def grid(self, **kwargs):
            self.grid_kwargs = kwargs

    monkeypatch.setattr(config_editor_dialog.ttk, "Button", FakeButton)
    monkeypatch.setattr(ConfigEditorDialog, "_add_entry_row", lambda *_args, **_kwargs: None)
    dialog._register_tooltip = lambda *_args, **_kwargs: None

    dialog._add_path_row(parent, 3, "H2 缓存目录", "processing.project_background.h2.cache_dir", browse_kind="dir", relative_to="project")

    assert created_buttons[0].grid_kwargs["padx"] == (8, 12)


def test_config_editor_widgets_do_not_create_side_assessment_panel(monkeypatch):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.SECTION_LABELS = [("project", "项目")]
    dialog.section_var = StubVar("project")
    dialog.current_file_var = StubVar("当前文件：config.yaml")
    dialog.status_var = StubVar("配置已同步")
    dialog._tooltips = []
    dialog.section_pages = {}
    calls: list[str] = []

    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def grid(self, **_kwargs):
            return None

        def pack(self, **_kwargs):
            return None

        def columnconfigure(self, *_args, **_kwargs):
            return None

        def rowconfigure(self, *_args, **_kwargs):
            return None

    class FakeButton(FakeWidget):
        pass

    class FakeRadio(FakeWidget):
        pass

    def fail_create_right_panel():
        raise AssertionError("right assessment panel should not be created")

    dialog.columnconfigure = lambda *_args, **_kwargs: None
    dialog.rowconfigure = lambda *_args, **_kwargs: None
    dialog._register_tooltip = lambda *_args, **_kwargs: None
    dialog._create_right_panel = fail_create_right_panel
    dialog._build_project_section = lambda: calls.append("project")
    dialog._build_writing_section = lambda: calls.append("writing")
    dialog._build_processing_section = lambda: calls.append("processing")
    dialog._build_runtime_section = lambda: calls.append("runtime")
    dialog._show_current_section = lambda: calls.append("show")
    dialog._reload_from_disk = lambda: None
    dialog._save_as = lambda: None
    dialog._save_current = lambda: None
    dialog._on_close = lambda: None

    monkeypatch.setattr(config_editor_dialog.ttk, "Frame", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Label", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Button", FakeButton)
    monkeypatch.setattr(config_editor_dialog.ttk, "Radiobutton", FakeRadio)

    dialog._create_widgets()

    assert not hasattr(dialog, "right_panel")
    assert calls == ["project", "writing", "processing", "runtime", "show"]


def test_config_editor_processing_path_combobox_is_readonly(monkeypatch):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    created_comboboxes = []

    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.grid_kwargs = None
            self.bind_calls = []

        def grid(self, **kwargs):
            self.grid_kwargs = kwargs

        def pack(self, **_kwargs):
            return None

        def pack_forget(self):
            return None

        def columnconfigure(self, *_args, **_kwargs):
            return None

        def bind(self, *args, **kwargs):
            self.bind_calls.append((args, kwargs))

    class FakeCombobox(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_comboboxes.append(self)

    dialog.vars = {
        "processing.path": StubVar("full_context"),
        "processing.project_background.scope": StubVar("global"),
        "processing.project_background.h2.fallback": StubVar("global"),
    }
    dialog._create_section_page = lambda _name: SimpleNamespace(content=FakeWidget())
    dialog._register_tooltip = lambda *_args, **_kwargs: None
    dialog._add_check_row = lambda *_args, **_kwargs: None
    dialog._add_entry_row = lambda *_args, **_kwargs: None
    dialog._add_path_row = lambda *_args, **_kwargs: None
    dialog._update_processing_visibility = lambda: None

    monkeypatch.setattr(config_editor_dialog.ttk, "LabelFrame", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Label", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Combobox", FakeCombobox)

    dialog._build_processing_section()

    assert created_comboboxes[0].kwargs["state"] == "readonly"
    assert dialog.processing_full_context_frame.bind_calls[0][0][0] == "<Configure>"


def test_config_editor_project_background_enums_are_readonly_comboboxes(monkeypatch):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    created_comboboxes = []

    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.grid_kwargs = None
            self.bind_calls = []

        def grid(self, **kwargs):
            self.grid_kwargs = kwargs

        def pack(self, **_kwargs):
            return None

        def pack_forget(self):
            return None

        def columnconfigure(self, *_args, **_kwargs):
            return None

        def bind(self, *args, **kwargs):
            self.bind_calls.append((args, kwargs))

    class FakeCombobox(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created_comboboxes.append(self)

    dialog.vars = {
        "processing.path": StubVar("auto"),
        "processing.project_background.enabled": StubVar(True),
        "processing.project_background.scope": StubVar("h2_auto"),
        "processing.project_background.max_chars": StubVar("800"),
        "processing.project_background.h2.precompute_on_batch": StubVar(True),
        "processing.project_background.h2.generate_missing_on_single": StubVar(True),
        "processing.project_background.h2.max_evidence_blocks": StubVar("6"),
        "processing.project_background.h2.max_evidence_chars": StubVar("2400"),
        "processing.project_background.h2.include_evidence_in_prompt": StubVar(False),
        "processing.project_background.h2.min_evidence_blocks": StubVar("2"),
        "processing.project_background.h2.fallback": StubVar("global"),
        "processing.project_background.h2.cache_dir": StubVar("./caches/project_background_h2"),
    }
    dialog._create_section_page = lambda _name: SimpleNamespace(content=FakeWidget())
    dialog._register_tooltip = lambda *_args, **_kwargs: None
    dialog._add_check_row = lambda *_args, **_kwargs: None
    dialog._add_entry_row = lambda *_args, **_kwargs: FakeWidget()
    dialog._add_path_row = lambda *_args, **_kwargs: None
    dialog._schedule_refresh = lambda: None

    monkeypatch.setattr(config_editor_dialog.ttk, "Frame", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "LabelFrame", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Label", FakeWidget)
    monkeypatch.setattr(config_editor_dialog.ttk, "Combobox", FakeCombobox)

    dialog._build_processing_section()

    scope_box = created_comboboxes[1]
    fallback_box = created_comboboxes[2]
    assert scope_box.kwargs["state"] == "readonly"
    assert scope_box.kwargs["values"] == ("global", "h2_auto")
    assert fallback_box.kwargs["state"] == "readonly"
    assert fallback_box.kwargs["values"] == ("global", "raw_evidence", "empty")


def test_config_editor_full_context_hides_project_background_frame():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {"processing.path": StubVar("full_context")}
    dialog._schedule_refresh = lambda: None

    class FakeFrame:
        def __init__(self, name):
            self.name = name
            self.actions: list[str] = []

        def pack_forget(self):
            self.actions.append("forget")

        def pack(self, **_kwargs):
            self.actions.append("pack")

    dialog.processing_full_context_frame = FakeFrame("full_context")
    dialog.processing_project_background_frame = FakeFrame("project_background")
    dialog.processing_chapter_plan_frame = FakeFrame("chapter_plan")
    dialog.processing_req_frame = FakeFrame("requirements")
    dialog.processing_scoring_frame = FakeFrame("scoring")

    dialog._update_processing_visibility()

    assert dialog.processing_full_context_frame.actions == ["forget", "pack"]
    assert dialog.processing_project_background_frame.actions == ["forget"]
    assert dialog.processing_chapter_plan_frame.actions == ["forget", "pack"]
    assert dialog.processing_req_frame.actions == ["forget"]
    assert dialog.processing_scoring_frame.actions == ["forget"]


def test_config_editor_auto_hides_requirements_retrieval_frame():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {"processing.path": StubVar("auto")}
    dialog._schedule_refresh = lambda: None
    dialog._update_project_background_visibility = lambda: None

    class FakeFrame:
        def __init__(self, name):
            self.name = name
            self.actions: list[str] = []

        def pack_forget(self):
            self.actions.append("forget")

        def pack(self, **_kwargs):
            self.actions.append("pack")

    dialog.processing_full_context_frame = FakeFrame("full_context")
    dialog.processing_project_background_frame = FakeFrame("project_background")
    dialog.processing_chapter_plan_frame = FakeFrame("chapter_plan")
    dialog.processing_req_frame = FakeFrame("requirements")
    dialog.processing_scoring_frame = FakeFrame("scoring")

    dialog._update_processing_visibility()

    assert dialog.processing_project_background_frame.actions == ["forget", "pack"]
    assert dialog.processing_req_frame.actions == ["forget"]
    assert dialog.processing_scoring_frame.actions == ["forget", "pack"]


def test_config_editor_hides_h2_project_background_controls_for_global_scope():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {
        "processing.project_background.enabled": StubVar(True),
        "processing.project_background.scope": StubVar("global"),
    }

    class FakeFrame:
        def __init__(self):
            self.actions: list[str] = []

        def grid(self):
            self.actions.append("grid")

        def grid_remove(self):
            self.actions.append("remove")

    class FakeControl:
        def __init__(self):
            self.states: list[str] = []

        def configure(self, **kwargs):
            self.states.append(kwargs["state"])

    scope_control = FakeControl()
    max_chars_control = FakeControl()
    dialog.processing_project_background_optional_controls = [
        (scope_control, "readonly"),
        (max_chars_control, "normal"),
    ]
    dialog.processing_project_background_h2_frame = FakeFrame()

    dialog._update_project_background_visibility()

    assert scope_control.states == ["readonly"]
    assert max_chars_control.states == ["normal"]
    assert dialog.processing_project_background_h2_frame.actions == ["remove"]


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
        validate=lambda _model, **_kwargs: [],
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


def test_config_editor_save_as_validates_against_selected_target_path(monkeypatch, tmp_path):
    provisional_dir = tmp_path / "empty-template-dir"
    target_dir = tmp_path / "real-project"
    provisional_dir.mkdir()
    target_dir.mkdir()
    (target_dir / "outline.md").write_text("# 项目\n## 章节\n### 内容\n", encoding="utf-8")
    (target_dir / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (target_dir / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")

    target_path = target_dir / "config_新项目.yaml"
    document = create_new_config_editor_document(provisional_dir / "config_新项目.yaml")
    model = document.model
    model["project"]["bidder_name"] = "示例投标单位"
    model["project"]["bid_requirements_file"] = "./bid_requirements.md"
    model["project"]["scoring_criteria_file"] = "./scoring_criteria.md"
    model["processing"]["path"] = "full_context"

    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    loaded_paths = []
    errors = []

    dialog.is_new_config = True
    dialog.document = document
    dialog.active_config_path = provisional_dir / "config_新项目.yaml"
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.current_file_var = StubVar()
    dialog.status_var = StubVar()
    dialog._collect_model = lambda: model
    dialog._load_document = lambda path: loaded_paths.append(path)
    dialog.title = lambda _value: None
    monkeypatch.setattr(
        config_editor_dialog.messagebox,
        "showerror",
        lambda title, message, **_kwargs: errors.append((title, message)),
    )
    monkeypatch.setattr(config_editor_dialog.messagebox, "askyesno", lambda *_args, **_kwargs: False)

    dialog._save(target_path=target_path, ask_switch=True)

    assert errors == []
    assert dialog.result["saved_path"] == target_path
    assert target_path.exists()
    assert loaded_paths == [target_path]


def test_config_editor_dialog_does_not_register_deprecated_context_view_vars(monkeypatch):
    monkeypatch.setattr(config_editor_dialog.tk, "StringVar", StubVar)
    monkeypatch.setattr(config_editor_dialog.tk, "BooleanVar", StubVar)
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.vars = {}
    dialog.section_var = StubVar()
    dialog._schedule_refresh = lambda: None
    dialog._update_processing_visibility = lambda: None

    ConfigEditorDialog._create_variables(dialog)

    assert not any(key.startswith("processing.context_view.") for key in dialog.vars)


def test_config_editor_display_relative_path_uses_posix_separators_for_yaml():
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)

    result = dialog._display_relative_path(
        PureWindowsPath("C:/project/项目要求/采购需求.md"),
        PureWindowsPath("C:/project"),
    )

    assert result == "项目要求/采购需求.md"
