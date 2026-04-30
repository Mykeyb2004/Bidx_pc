from pathlib import Path

import pytest
import yaml

from bid_writer.config import Config
from bid_writer.outline_prepare import (
    OutlinePrepareError,
    confirm_outline_and_lock,
    load_existing_outline,
    set_outline_locked,
)


def _write_project(tmp_path: Path) -> Path:
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


def test_load_existing_outline_returns_empty_when_file_missing(tmp_path: Path):
    config = Config(str(_write_project(tmp_path)))

    assert load_existing_outline(config) == ""


def test_confirm_outline_writes_file_and_locks_config(tmp_path: Path):
    config_path = _write_project(tmp_path)
    config = Config(str(config_path))

    confirm_outline_and_lock(
        config,
        "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n",
    )

    assert (tmp_path / "outline.md").read_text(encoding="utf-8").endswith("#### 1.1.1 采购需求响应\n")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["project"]["outline_locked"] is True


def test_confirm_outline_formats_numbering_before_saving(tmp_path: Path):
    config = Config(str(_write_project(tmp_path)))

    confirm_outline_and_lock(
        config,
        "# 项目\n## 4. 实施方案\n### 4.2 服务流程\n#### 4.2.8 响应机制\n",
    )

    assert (tmp_path / "outline.md").read_text(encoding="utf-8") == (
        "# 项目\n## 1. 实施方案\n### 1.1 服务流程\n#### 1.1.1 响应机制\n"
    )


def test_confirm_outline_blocks_h3_leaf(tmp_path: Path):
    config = Config(str(_write_project(tmp_path)))

    with pytest.raises(OutlinePrepareError, match="叶子节点必须是 H4"):
        confirm_outline_and_lock(config, "# 项目\n## 章节\n### 未细化小节\n")


def test_set_outline_locked_preserves_existing_project_fields(tmp_path: Path):
    config_path = _write_project(tmp_path)

    set_outline_locked(config_path, True)

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["project"]["root_dir"] == "."
    assert payload["project"]["outline_locked"] is True
