from pathlib import Path

from bid_writer.tender_section_boundary_config import load_boundary_config, normalize_boundary_text


def test_loads_major_and_fallback_rules_from_yaml(tmp_path: Path):
    boundary_file = tmp_path / "tender_section_boundaries.yaml"
    boundary_file.write_text(
        """
normalization:
  strip_invisible: true
  collapse_space: true
major_markers:
  - name: chapter
    pattern: '第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)'
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: '(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)'
    priority: 60
""".strip(),
        encoding="utf-8",
    )

    config = load_boundary_config(boundary_file)

    assert len(config.major_markers) == 1
    assert config.major_markers[0].name == "chapter"
    assert config.major_markers[0].kind == "major"
    assert config.major_markers[0].regex.search("第 五 章 项目采购需求")
    assert len(config.fallback_markers) == 1
    assert config.fallback_markers[0].kind == "fallback"


def test_normalize_boundary_text_removes_invisible_characters():
    assert normalize_boundary_text("第\u200b五　章\u2060 项目采购需求") == "第五 章 项目采购需求"


def test_invalid_regex_rules_are_skipped_with_warning(tmp_path: Path):
    boundary_file = tmp_path / "tender_section_boundaries.yaml"
    boundary_file.write_text(
        """
major_markers:
  - name: broken
    pattern: '(?P<ordinal>'
    priority: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_boundary_config(boundary_file)

    assert config.major_markers == ()
    assert any("broken" in warning for warning in config.warnings)
