from pathlib import Path
from types import SimpleNamespace

from bid_writer import config_editor_dialog
from bid_writer.config_editor_dialog import ConfigEditorDialog


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _dialog(tmp_path: Path, *, new_config: bool = True):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.is_new_config = new_config
    dialog.vars = {
        "project.root_dir": StubVar("."),
        "project.bid_requirements_mode": StubVar("file"),
        "project.bid_requirements_file": StubVar(""),
        "project.scoring_criteria_mode": StubVar("file"),
        "project.scoring_criteria_file": StubVar(""),
    }
    dialog.active_config_path = tmp_path / "config_新项目.yaml"
    dialog.document = SimpleNamespace(config_path=tmp_path / "config_新项目.yaml")
    dialog.tender_import_status_var = StubVar("")
    dialog._current_project_root = lambda: tmp_path
    dialog._schedule_refresh = lambda: None
    return dialog


def test_apply_tender_import_result_updates_file_modes_and_paths(tmp_path: Path):
    dialog = _dialog(tmp_path)
    result = SimpleNamespace(
        relative_requirements_path="./项目要求/项目采购需求.md",
        relative_scoring_path="./项目要求/评分标准.md",
        import_dir=tmp_path / ".bid_writer" / "imports" / "abc",
        extraction_report_path=tmp_path / ".bid_writer" / "imports" / "abc" / "extraction_report.json",
        cancelled=False,
    )

    ConfigEditorDialog._apply_tender_import_result(dialog, result)

    assert dialog.vars["project.bid_requirements_mode"].get() == "file"
    assert dialog.vars["project.scoring_criteria_mode"].get() == "file"
    assert dialog.vars["project.bid_requirements_file"].get() == "./项目要求/项目采购需求.md"
    assert dialog.vars["project.scoring_criteria_file"].get() == "./项目要求/评分标准.md"
    assert "导入完成" in dialog.tender_import_status_var.get()


def test_import_tender_document_uses_single_file_dialog(monkeypatch, tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    dialog = _dialog(tmp_path)
    calls = {}

    class FakeService:
        def import_document(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                relative_requirements_path="./项目要求/项目采购需求.md",
                relative_scoring_path="./项目要求/评分标准.md",
                import_dir=tmp_path / ".bid_writer" / "imports" / "abc",
                extraction_report_path=tmp_path / ".bid_writer" / "imports" / "abc" / "extraction_report.json",
                cancelled=False,
            )

    monkeypatch.setattr(config_editor_dialog.filedialog, "askopenfilename", lambda **_kwargs: str(source))
    monkeypatch.setattr(config_editor_dialog, "TenderImportService", lambda: FakeService())
    monkeypatch.setattr(config_editor_dialog.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(config_editor_dialog, "confirm_low_confidence", lambda _parent, _extraction: True)
    dialog._apply_tender_import_result = lambda result: calls.setdefault("applied", result)

    ConfigEditorDialog._import_tender_document(dialog)

    assert calls["source_path"] == source
    assert calls["project_root"] == tmp_path
    assert "applied" in calls


def test_import_tender_document_is_disabled_outside_new_config(tmp_path: Path):
    dialog = _dialog(tmp_path, new_config=False)

    assert ConfigEditorDialog._can_import_tender_document(dialog) is False
