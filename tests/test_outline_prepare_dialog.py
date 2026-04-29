from pathlib import Path

from bid_writer.config import Config
from bid_writer.outline_prepare_dialog import OutlinePrepareDialog


class FakeText:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value

    def get(self, *_args):
        return self.value


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _write_config(tmp_path: Path) -> Path:
    (tmp_path / "outline.md").write_text("# 项目\n## 章\n### 节\n#### 单元\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text("采购需求", encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  outline_locked: false
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _dialog(config: Config) -> OutlinePrepareDialog:
    dialog = OutlinePrepareDialog.__new__(OutlinePrepareDialog)
    dialog.config = config
    dialog.result = {"confirmed": False}
    dialog.outline_text = FakeText()
    dialog.status_var = FakeVar()
    dialog.validation_var = FakeVar()
    dialog.destroy = lambda: None
    return dialog


def test_load_existing_outline_sets_text(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    OutlinePrepareDialog._load_existing_outline(dialog)

    assert dialog.outline_text.get("1.0", "end").startswith("# 项目")
    assert "已读取已有大纲" in dialog.status_var.get()


def test_validate_current_text_reports_h4_error(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 项目\n## 章\n### 节\n")

    ok = OutlinePrepareDialog._validate_current_text(dialog)

    assert ok is False
    assert "至少包含 1 个 H4" in dialog.validation_var.get()


def test_confirm_writes_outline_and_marks_result(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 新项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n")

    OutlinePrepareDialog._confirm(dialog)

    assert dialog.result["confirmed"] is True
    assert (tmp_path / "outline.md").read_text(encoding="utf-8").startswith("# 新项目")
