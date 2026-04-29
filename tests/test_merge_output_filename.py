from pathlib import Path

from bid_writer.main import BidWriter


def _write_project(tmp_path: Path, outline: str) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "outline.md").write_text(outline.strip(), encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project"
  inputs:
    outline_file: "./outline.md"
  output_dir: "./output"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_merge_generated_sections_defaults_filename_to_outline_h1(tmp_path: Path):
    config_path = _write_project(
        tmp_path,
        """
# 儿童关爱服务项目投标文件
## 服务方案
### 入户走访安排
""",
    )
    writer = BidWriter(str(config_path))
    assert writer.load_outline()
    assert writer.parser is not None
    heading = writer.parser.find_heading_by_title("入户走访安排")
    assert heading is not None
    writer.file_saver.save(heading, "入户走访正文")

    result = writer.merge_generated_sections()

    assert result.filepath.name == "儿童关爱服务项目投标文件.md"
    assert "入户走访正文" in result.filepath.read_text(encoding="utf-8")


def test_merge_generated_sections_sanitizes_default_outline_h1_filename(tmp_path: Path):
    config_path = _write_project(
        tmp_path,
        """
# 项目:儿童/关爱*服务?投标<文件>|初稿
## 服务方案
### 入户走访安排
""",
    )
    writer = BidWriter(str(config_path))
    assert writer.load_outline()
    assert writer.parser is not None
    heading = writer.parser.find_heading_by_title("入户走访安排")
    assert heading is not None
    writer.file_saver.save(heading, "入户走访正文")

    result = writer.merge_generated_sections()

    assert result.filepath.name == "项目_儿童_关爱_服务_投标_文件_初稿.md"
