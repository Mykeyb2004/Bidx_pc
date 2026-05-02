from pathlib import Path
import queue
import threading
import tkinter as tk
from types import SimpleNamespace

import pytest

from bid_writer.gui import ensure_tk_runtime
from bid_writer.new_config_wizard import NewConfigWizardDialog, WIZARD_STEPS
from bid_writer.tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
)


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class StubButton:
    def __init__(self):
        self.config_calls = []
        self.options = {}

    def configure(self, **kwargs):
        self.config_calls.append(kwargs)
        self.options.update(kwargs)


class StubFrame:
    def __init__(self):
        self.raised = False

    def tkraise(self):
        self.raised = True


def _dialog(tmp_path: Path) -> NewConfigWizardDialog:
    dialog = NewConfigWizardDialog.__new__(NewConfigWizardDialog)
    dialog.current_step_index = 0
    dialog.max_completed_step_index = 0
    dialog.result = {"saved_path": None, "apply_path": None}
    dialog.vars = {
        "source_path": StubVar(""),
        "project_root": StubVar(str(tmp_path)),
        "config_path": StubVar(str(tmp_path / "config.yaml")),
        "requirements_path": StubVar(str(tmp_path / "项目要求" / "项目采购需求.md")),
        "scoring_path": StubVar(str(tmp_path / "项目要求" / "评分标准.md")),
        "outline_path": StubVar(str(tmp_path / "投标大纲.md")),
        "output_dir": StubVar(str(tmp_path / "output")),
        "bidder_name": StubVar(""),
    }
    dialog.status_var = StubVar("")
    dialog.config_summary_var = StubVar("")
    dialog.source_hint_var = StubVar("")
    dialog.import_status_var = StubVar("")
    dialog.review_summary_var = StubVar("")
    dialog.back_button = StubButton()
    dialog.next_button = StubButton()
    dialog.step_buttons = []
    dialog.step_frames = {key: StubFrame() for key in [step.key for step in WIZARD_STEPS]}
    dialog.state = SimpleNamespace(
        source_path=None,
        project_root=tmp_path,
        config_path=tmp_path / "config.yaml",
        import_dir=None,
        should_copy_source=False,
        source_copy_path=None,
        copied_source_path=None,
        requirements_path=None,
        scoring_path=None,
        outline_path=tmp_path / "投标大纲.md",
        output_dir=tmp_path / "output",
        bidder_name="",
        created_paths=[],
        manual_inputs=True,
    )
    return dialog


def _run_import_job_inline(dialog: NewConfigWizardDialog, job) -> None:
    NewConfigWizardDialog._run_import_worker(dialog, job)
    outcome = dialog._import_result_queue.get_nowait()
    NewConfigWizardDialog._finish_import(dialog, outcome)


def test_wizard_defines_five_steps():
    assert [step.key for step in WIZARD_STEPS] == [
        "source",
        "location",
        "materials",
        "basics",
        "review",
    ]


def test_constructor_builds_initial_wizard_shell(tmp_path: Path):
    ensure_tk_runtime()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available: {exc}")

    dialog = None
    try:
        root.withdraw()
        config_path = tmp_path / "config_test.yaml"

        dialog = NewConfigWizardDialog(root, config_path=config_path)

        assert dialog.result == {"saved_path": None, "apply_path": None}
        assert dialog.current_step_index == 0
        assert dialog.max_completed_step_index == 0
        assert dialog.state.config_path == config_path.resolve()
        assert set(dialog.step_frames) == {step.key for step in WIZARD_STEPS}
    finally:
        if dialog is not None:
            dialog.destroy()
        root.destroy()


def test_go_next_advances_when_current_step_valid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: True

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 1
    assert dialog.max_completed_step_index == 1


def test_go_next_stays_when_current_step_invalid(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._validate_current_step = lambda: False

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 0
    assert dialog.max_completed_step_index == 0


def test_go_back_moves_to_previous_step(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2

    NewConfigWizardDialog._go_back(dialog)

    assert dialog.current_step_index == 1


def test_jump_to_step_only_allows_completed_steps(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.max_completed_step_index = 1

    NewConfigWizardDialog._jump_to_step(dialog, 2)
    assert dialog.current_step_index == 0

    NewConfigWizardDialog._jump_to_step(dialog, 1)
    assert dialog.current_step_index == 1


def test_jump_to_previous_step_does_not_validate_current_incomplete_step(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2
    dialog.max_completed_step_index = 2
    dialog._validate_current_step = lambda: False

    NewConfigWizardDialog._jump_to_step(dialog, 1)

    assert dialog.current_step_index == 1


def test_sync_footer_sets_status_and_final_button_text(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = len(WIZARD_STEPS) - 1

    NewConfigWizardDialog._sync_footer(dialog)

    assert dialog.status_var.get() == "第 5 步，共 5 步"
    assert dialog.next_button.config_calls[-1]["text"] == "保存并应用"


def test_import_completion_reenables_next_button(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.current_step_index = 2

    NewConfigWizardDialog._set_import_in_progress(dialog, True)
    NewConfigWizardDialog._set_import_in_progress(dialog, False)

    assert dialog.next_button.options["state"] == tk.NORMAL


def test_sync_fields_updates_header_config_summary(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.state.config_path = tmp_path / "config_推导项目.yaml"

    NewConfigWizardDialog._sync_fields_from_state(dialog)

    assert dialog.config_summary_var.get() == f"目标配置：{tmp_path / 'config_推导项目.yaml'}"


def test_project_root_change_rebases_default_material_paths(tmp_path: Path):
    old_root = tmp_path / "旧项目"
    new_root = tmp_path / "706-15号楼研究"
    dialog = _dialog(old_root)
    dialog.current_step_index = 1
    dialog.state.project_root = old_root
    dialog.state.requirements_path = old_root / "项目要求" / "项目采购需求.md"
    dialog.state.scoring_path = old_root / "项目要求" / "评分标准.md"
    dialog.vars["project_root"].set(str(new_root))
    dialog.vars["requirements_path"].set(str(old_root / "项目要求" / "项目采购需求.md"))
    dialog.vars["scoring_path"].set(str(old_root / "项目要求" / "评分标准.md"))

    NewConfigWizardDialog._go_next(dialog)

    assert dialog.current_step_index == 2
    assert dialog.state.requirements_path == new_root / "项目要求" / "项目采购需求.md"
    assert dialog.state.scoring_path == new_root / "项目要求" / "评分标准.md"
    assert dialog.vars["requirements_path"].get() == str(new_root / "项目要求" / "项目采购需求.md")
    assert dialog.vars["scoring_path"].get() == str(new_root / "项目要求" / "评分标准.md")


def test_project_root_change_preserves_custom_material_paths(tmp_path: Path):
    old_root = tmp_path / "旧项目"
    new_root = tmp_path / "706-15号楼研究"
    custom_requirements = tmp_path / "客户资料" / "采购需求.md"
    custom_scoring = tmp_path / "客户资料" / "评分标准.md"
    dialog = _dialog(old_root)
    dialog.state.project_root = old_root
    dialog.vars["project_root"].set(str(new_root))
    dialog.vars["requirements_path"].set(str(custom_requirements))
    dialog.vars["scoring_path"].set(str(custom_scoring))

    NewConfigWizardDialog._sync_state_from_fields(dialog)

    assert dialog.state.requirements_path == custom_requirements
    assert dialog.state.scoring_path == custom_scoring
    assert dialog.vars["requirements_path"].get() == str(custom_requirements)
    assert dialog.vars["scoring_path"].get() == str(custom_scoring)


def test_save_and_apply_sets_result_from_document(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"].set("测试公司")
    dialog.vars["config_path"].set(str(tmp_path / "config_测试.yaml"))
    saved = tmp_path / "config_测试.yaml"
    destroyed = []

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return []

        def save(self, model=None, *, target_path=None, create_backup=True):
            assert target_path == saved
            assert create_backup is True
            return saved

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    dialog.destroy = lambda: destroyed.append(True)

    NewConfigWizardDialog._save_and_apply(dialog)

    assert dialog.result == {"saved_path": saved, "apply_path": saved}
    assert destroyed == [True]


def test_save_and_apply_shows_validation_errors(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog.vars["bidder_name"].set("")
    shown_errors = []
    destroyed = []

    class FakeMessage:
        level = "error"
        text = "投标主体名称不能为空。"

    class FakeDocument:
        model = {}

        def validate(self, model, *, config_path=None):
            return [FakeMessage()]

        def save(self, model=None, *, target_path=None, create_backup=True):
            raise AssertionError("save should not be called")

    monkeypatch.setattr("bid_writer.new_config_wizard.build_editor_document_from_state", lambda _state: FakeDocument())
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.showerror",
        lambda *args, **kwargs: shown_errors.append(args),
    )
    dialog.destroy = lambda: destroyed.append(True)

    NewConfigWizardDialog._save_and_apply(dialog)

    assert dialog.result == {"saved_path": None, "apply_path": None}
    assert destroyed == []
    assert shown_errors and "投标主体名称不能为空" in shown_errors[0][1]


def test_cancel_with_created_paths_can_cleanup(monkeypatch, tmp_path: Path):
    created = tmp_path / "created.md"
    created.write_text("created", encoding="utf-8")
    dialog = _dialog(tmp_path)
    dialog.state.created_paths = [created]
    calls = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.askyesnocancel",
        lambda *args, **kwargs: calls.append(args) or False,
    )
    dialog.destroy = lambda: calls.append(("destroy",))

    NewConfigWizardDialog._cancel(dialog)

    assert not created.exists()
    assert ("destroy",) in calls


def test_cancel_keeps_created_paths_when_user_chooses_keep(monkeypatch, tmp_path: Path):
    created = tmp_path / "created.md"
    created.write_text("created", encoding="utf-8")
    dialog = _dialog(tmp_path)
    dialog.state.created_paths = [created]
    destroyed = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.messagebox.askyesnocancel",
        lambda *args, **kwargs: True,
    )
    dialog.destroy = lambda: destroyed.append(True)

    NewConfigWizardDialog._cancel(dialog)

    assert created.exists()
    assert destroyed == [True]


def test_select_source_file_rebuilds_state_and_moves_to_location(monkeypatch, tmp_path: Path):
    source = tmp_path / "公共服务满意度项目招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    dialog = _dialog(tmp_path)
    shown = []
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.filedialog.askopenfilename",
        lambda *args, **kwargs: str(source),
    )
    dialog._show_step = lambda: shown.append(dialog.current_step_index)

    NewConfigWizardDialog._select_source_file(dialog)

    assert dialog.state.source_path == source
    assert dialog.vars["source_path"].get() == str(source)
    assert dialog.vars["project_root"].get() == str(tmp_path)
    assert dialog.current_step_index == 1
    assert dialog.max_completed_step_index == 1
    assert shown == [1]


def test_run_import_updates_material_paths_and_records_only_new_paths(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    source = tmp_path / "招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    dialog.state.source_path = source
    dialog.vars["source_path"].set(str(source))
    existing_requirements = tmp_path / "项目要求" / "项目采购需求.md"
    existing_requirements.parent.mkdir()
    existing_requirements.write_text("old", encoding="utf-8")
    existing_backup = existing_requirements.with_suffix(existing_requirements.suffix + ".bak")
    existing_backup.write_text("old backup", encoding="utf-8")
    scoring = existing_requirements.parent / "评分标准.md"
    scoring_backup = scoring.with_suffix(scoring.suffix + ".bak")
    report = tmp_path / ".bid_writer" / "imports" / "pending" / "extraction_report.json"
    converted = report.parent / "converted.md"
    conversion_map = report.parent / "conversion_map.json"
    synced = []

    class FakeResult:
        cancelled = False
        requirements_path = existing_requirements
        scoring_path = scoring
        import_dir = report.parent
        created_paths = (report, converted, conversion_map, existing_requirements, existing_backup, scoring, scoring_backup)

    class FakeService:
        def import_document(self, **kwargs):
            assert "confirm_sections" in kwargs
            assert "confirm_low_confidence" not in kwargs
            confirmation = kwargs["confirm_sections"](
                conversion=SimpleNamespace(blocks=[]),
                extraction=SimpleNamespace(),
                requirements_path=existing_requirements,
                scoring_path=scoring,
            )
            assert confirmation.cancelled is False
            report.parent.mkdir(parents=True)
            report.write_text("{}", encoding="utf-8")
            converted.write_text("converted", encoding="utf-8")
            conversion_map.write_text("{}", encoding="utf-8")
            scoring.write_text("score", encoding="utf-8")
            scoring_backup.write_text("score backup", encoding="utf-8")
            return FakeResult()

    monkeypatch.setattr("bid_writer.new_config_wizard.copy_source_file_if_needed", lambda _state: None)
    monkeypatch.setattr("bid_writer.new_config_wizard.TenderImportService", lambda: FakeService())
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.confirm_tender_sections",
        lambda _parent, **_kwargs: ManualTenderConfirmationResult(
            requirements=ManualTenderSectionSelection("bid_requirements", "需求", None, None, True),
            scoring=ManualTenderSectionSelection("scoring_criteria", "评分", None, None, True),
        ),
    )
    dialog._sync_fields_from_state = lambda: synced.append(True)
    dialog._start_import_worker = lambda job: _run_import_job_inline(dialog, job)

    NewConfigWizardDialog._run_import(dialog)

    assert dialog.state.requirements_path == existing_requirements
    assert dialog.state.scoring_path == scoring
    assert report in dialog.state.created_paths
    assert converted in dialog.state.created_paths
    assert conversion_map in dialog.state.created_paths
    assert scoring in dialog.state.created_paths
    assert existing_requirements not in dialog.state.created_paths
    assert existing_backup not in dialog.state.created_paths
    assert scoring_backup not in dialog.state.created_paths
    assert synced == [True]


def test_run_import_starts_background_worker_without_running_import_inline(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    source = tmp_path / "招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    dialog.state.source_path = source
    dialog.vars["source_path"].set(str(source))
    import_calls = []
    worker_jobs = []

    class FakeService:
        def import_document(self, **kwargs):
            import_calls.append(kwargs)
            return SimpleNamespace(
                cancelled=False,
                requirements_path=tmp_path / "项目要求" / "项目采购需求.md",
                scoring_path=tmp_path / "项目要求" / "评分标准.md",
                import_dir=tmp_path / ".bid_writer" / "imports" / "pending",
                created_paths=(),
            )

    monkeypatch.setattr("bid_writer.new_config_wizard.copy_source_file_if_needed", lambda _state: None)
    monkeypatch.setattr("bid_writer.new_config_wizard.TenderImportService", lambda: FakeService())
    dialog._start_import_worker = lambda job: worker_jobs.append(job)

    NewConfigWizardDialog._run_import(dialog)

    assert worker_jobs
    assert import_calls == []
    assert "正在" in dialog.import_status_var.get()


def test_import_worker_marshals_ui_callbacks_to_main_queue(tmp_path: Path):
    dialog = _dialog(tmp_path)
    dialog._import_ui_requests = queue.Queue()
    result_values = []

    def worker():
        result_values.append(NewConfigWizardDialog._run_on_import_ui(dialog, lambda: "ok"))

    thread = threading.Thread(target=worker)
    thread.start()
    request = dialog._import_ui_requests.get(timeout=1)

    assert result_values == []

    request.result = request.callback()
    request.event.set()
    thread.join(timeout=1)

    assert result_values == ["ok"]


def test_run_import_reports_manual_confirmation_cancelled(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    source = tmp_path / "招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    dialog.state.source_path = source
    dialog.vars["source_path"].set(str(source))
    created_artifact = tmp_path / ".bid_writer" / "imports" / "pending" / "converted.md"
    confirm_calls = []

    class FakeResult:
        cancelled = True
        requirements_path = None
        scoring_path = None
        import_dir = tmp_path / ".bid_writer" / "imports" / "pending"
        created_paths = (created_artifact,)

    class FakeService:
        def import_document(self, **kwargs):
            confirmation = kwargs["confirm_sections"](
                conversion=SimpleNamespace(blocks=[]),
                extraction=SimpleNamespace(),
                requirements_path=tmp_path / "项目要求" / "项目采购需求.md",
                scoring_path=tmp_path / "项目要求" / "评分标准.md",
            )
            assert confirmation.cancelled is True
            created_artifact.parent.mkdir(parents=True)
            created_artifact.write_text("converted", encoding="utf-8")
            return FakeResult()

    monkeypatch.setattr("bid_writer.new_config_wizard.copy_source_file_if_needed", lambda _state: None)
    monkeypatch.setattr("bid_writer.new_config_wizard.TenderImportService", lambda: FakeService())
    monkeypatch.setattr(
        "bid_writer.new_config_wizard.confirm_tender_sections",
        lambda _parent, **_kwargs: confirm_calls.append(_kwargs)
        or ManualTenderConfirmationResult(cancelled=True),
    )
    dialog._start_import_worker = lambda job: _run_import_job_inline(dialog, job)

    NewConfigWizardDialog._run_import(dialog)

    assert confirm_calls
    assert "已取消确认" in dialog.import_status_var.get()
    assert dialog.state.requirements_path is None
    assert dialog.state.scoring_path is None
    assert dialog.vars["requirements_path"].get() == ""
    assert dialog.vars["scoring_path"].get() == ""
    assert created_artifact in dialog.state.created_paths
