from pathlib import Path

from bid_writer.chapter_fact_store import ChapterFactStore, ExtractedFact
from bid_writer.config import Config
from bid_writer.outline_parser import parse_outline


def _build_config(tmp_path: Path) -> Config:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "outline.md").write_text("# 项目\n## 章节\n### 质量保障措施\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project"
  inputs:
    outline_file: "./outline.md"
""".strip(),
        encoding="utf-8",
    )
    return Config(str(config_path))


def _select_heading(config: Config):
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title("质量保障措施")
    assert heading is not None
    return heading


def test_chapter_fact_store_round_trip(tmp_path: Path):
    config = _build_config(tmp_path)
    store = ChapterFactStore(config)
    heading = _select_heading(config)

    record = store.save(
        heading=heading,
        source_hash="output:abc123",
        facts=[
            ExtractedFact(scope="global", category="项目经理", value="张三"),
            ExtractedFact(scope="local", category="阶段划分", value="调研、开发、测试"),
        ],
    )
    loaded = store.get(heading)

    assert loaded is not None
    assert loaded.source_hash == "output:abc123"
    assert loaded.extracted_at == record.extracted_at
    assert [(fact.scope, fact.category, fact.value) for fact in loaded.facts] == [
        ("global", "项目经理", "张三"),
        ("local", "阶段划分", "调研、开发、测试"),
    ]


def test_chapter_fact_store_returns_empty_fact_list_when_saved_as_none(tmp_path: Path):
    config = _build_config(tmp_path)
    store = ChapterFactStore(config)
    heading = _select_heading(config)

    store.save(
        heading=heading,
        source_hash="output:def456",
        facts=[],
    )
    loaded = store.get(heading)

    assert loaded is not None
    assert loaded.source_hash == "output:def456"
    assert loaded.facts == []
