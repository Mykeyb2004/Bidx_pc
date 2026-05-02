from pathlib import Path
import queue

from bid_writer.config import Config
from bid_writer.outline_prepare_dialog import OutlinePrepareDialog


class FakeText:
    def __init__(self):
        self.value = ""
        self.seen: list[str] = []

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value += value

    def get(self, *_args):
        return self.value

    def see(self, index):
        self.seen.append(index)


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeButton:
    def __init__(self):
        self.states: list[str] = []

    def configure(self, **kwargs):
        self.states.append(kwargs["state"])


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
    dialog.confirm_button = FakeButton()
    dialog.destroy = lambda: None
    dialog.after = lambda _delay, callback=None: callback() if callback is not None else None
    dialog._generation_queue = queue.Queue()
    dialog._generation_in_progress = False
    return dialog


def test_load_existing_outline_sets_text(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    OutlinePrepareDialog._load_existing_outline(dialog)

    assert dialog.outline_text.get("1.0", "end").startswith("# 项目")
    assert "已读取已有大纲" in dialog.status_var.get()


def test_load_missing_outline_shows_neutral_prompt_without_error(tmp_path: Path):
    config_path = _write_config(tmp_path)
    (tmp_path / "outline.md").unlink()
    config = Config(str(config_path))
    dialog = _dialog(config)

    OutlinePrepareDialog._load_existing_outline(dialog)

    assert dialog.outline_text.get("1.0", "end") == ""
    assert "尚未准备大纲" in dialog.status_var.get()
    assert "错误" not in dialog.validation_var.get()
    assert "Markdown 标题" not in dialog.validation_var.get()
    assert dialog.confirm_button.states[-1] == "disabled"


def test_validate_current_text_reports_h4_error(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 项目\n## 章\n### 节\n")

    ok = OutlinePrepareDialog._validate_current_text(dialog)

    assert ok is False
    assert "至少包含 1 个 H4" in dialog.validation_var.get()
    assert dialog.confirm_button.states[-1] == "disabled"


def test_validate_current_text_enables_confirm_for_valid_h4_outline(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 项目\n## 章\n### 节\n#### 单元\n")

    ok = OutlinePrepareDialog._validate_current_text(dialog)

    assert ok is True
    assert dialog.confirm_button.states[-1] == "normal"


def test_format_current_text_rewrites_numbering_and_validates(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert(
        "1.0",
        "# 项目\n## 7. 实施方案\n### 7.5 服务流程\n#### 7.5.4 响应机制\n",
    )

    OutlinePrepareDialog._format_current_text(dialog)

    assert dialog.outline_text.get("1.0", "end") == (
        "# 项目\n## 1. 实施方案\n### 1.1 服务流程\n#### 1.1.1 响应机制\n"
    )
    assert "已格式化大纲编号" in dialog.status_var.get()
    assert dialog.confirm_button.states[-1] == "normal"


def test_confirm_writes_outline_and_marks_result(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)
    dialog.outline_text.insert("1.0", "# 新项目\n## 9. 项目理解\n### 9.3 需求分析\n#### 9.3.2 采购需求响应\n")

    OutlinePrepareDialog._confirm(dialog)

    assert dialog.result["confirmed"] is True
    assert (tmp_path / "outline.md").read_text(encoding="utf-8") == (
        "# 新项目\n## 1. 项目理解\n### 1.1 需求分析\n#### 1.1.1 采购需求响应\n"
    )


def test_run_generate_outline_updates_status_before_text_arrives(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    class FakeGenerator:
        def generate(self, **kwargs):
            status_callback = kwargs["status_callback"]
            status_callback("准备大纲请求", "正在准备大纲生成请求...")
            status_callback("等待首批输出", "正在请求模型并等待首批内容...")
            return type("Result", (), {"outline_text": "# 项目\n## 章\n### 节\n#### 单元\n", "warnings": []})()

    dialog._generator_factory = lambda: FakeGenerator()

    OutlinePrepareDialog._run_generate_outline(dialog)
    OutlinePrepareDialog._drain_generation_queue(dialog, stop_before_done=True)
    assert "等待首批输出" in dialog.status_var.get()

    OutlinePrepareDialog._drain_generation_queue(dialog)
    assert dialog.outline_text.get("1.0", "end").startswith("# 项目")
    assert dialog.confirm_button.states[-1] == "normal"


def test_run_generate_outline_streams_text_into_editor_before_final_replace(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    dialog = _dialog(config)

    class FakeGenerator:
        def generate(self, **kwargs):
            status_callback = kwargs["status_callback"]
            chunk_callback = kwargs["chunk_callback"]
            status_callback("等待首批输出", "正在请求模型并等待首批内容...")
            chunk_callback("# 项目\n")
            chunk_callback("## 章\n")
            chunk_callback("### 节\n")
            return type("Result", (), {"outline_text": "# 项目\n## 章\n### 节\n#### 单元\n", "warnings": []})()

    dialog._generator_factory = lambda: FakeGenerator()

    OutlinePrepareDialog._run_generate_outline(dialog)

    OutlinePrepareDialog._drain_generation_queue(dialog, stop_before_done=True)
    assert dialog.outline_text.get("1.0", "end") == "# 项目\n## 章\n### 节\n"

    OutlinePrepareDialog._drain_generation_queue(dialog)
    assert dialog.outline_text.get("1.0", "end") == "# 项目\n## 章\n### 节\n#### 单元\n"
    assert dialog.confirm_button.states[-1] == "normal"
