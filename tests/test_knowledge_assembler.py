import json
from pathlib import Path

from bid_writer.chapter_fact_extractor import ChapterFactExtractor
from bid_writer.chapter_fact_store import ChapterFactStore, ExtractedFact
from bid_writer.config import Config
from bid_writer.file_saver import FileSaver
from bid_writer.knowledge_assembler import KnowledgeAssembler
from bid_writer.outline_parser import parse_outline


def _build_config(tmp_path: Path, body: str) -> Config:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(body.strip(), encoding="utf-8")
    return Config(str(config_path))


def test_knowledge_assembler_prefers_declared_files_then_directory_scan_and_dedupes(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    knowledge_dir = project_root / "knowledge"
    knowledge_dir.mkdir()
    (project_root / "公司简介.md").write_text("- 公司名称：测试投标主体\n", encoding="utf-8")
    (knowledge_dir / "团队.md").write_text("- 项目经理：张三\n", encoding="utf-8")
    (knowledge_dir / "服务承诺.md").write_text("- 驻场人员：不少于 5 人\n", encoding="utf-8")

    config = _build_config(
        tmp_path,
        """
project:
  root_dir: "./project"
  inputs:
    knowledge_files:
      - "./公司简介.md"
      - "./knowledge/团队.md"
    knowledge_directory: "./knowledge"
processing:
  knowledge:
    enabled: true
    max_chars: 800
""",
    )

    assembler = KnowledgeAssembler(config)
    documents = assembler.load_documents()

    assert [document.title for document in documents] == ["公司简介", "团队", "服务承诺"]


def test_knowledge_assembler_respects_budget_at_block_boundary(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "公司简介.md").write_text("- 公司名称：测试投标主体\n", encoding="utf-8")
    (project_root / "团队.md").write_text("- 项目经理：张三\n- 驻场人员：不少于 5 人\n", encoding="utf-8")

    config = _build_config(
        tmp_path,
        """
project:
  root_dir: "./project"
  inputs:
    knowledge_files:
      - "./公司简介.md"
      - "./团队.md"
processing:
  knowledge:
    enabled: true
    max_chars: 60
""",
    )

    section = KnowledgeAssembler(config).build_prompt_section()

    assert "## 投标方知识库" in section
    assert "### 公司简介" in section
    assert "### 团队" not in section


def test_knowledge_assembler_ignores_legacy_dependency_facts(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "outline.md").write_text(
        "\n".join(
            [
                "# 项目",
                "## 实施方案",
                "### 人员配置方案",
                "### 质量保障措施",
                "### 进度计划安排",
                "### 其他章节",
            ]
        ),
        encoding="utf-8",
    )

    config = _build_config(
        tmp_path,
        """
project:
  root_dir: "./project"
  inputs:
    outline_file: "./outline.md"
processing:
  knowledge:
    enabled: true
    max_chars: 800
""",
    )

    parser = parse_outline(config.get_outline_content())
    target = parser.find_heading_by_title("质量保障措施")
    dep_a = parser.find_heading_by_title("人员配置方案")
    dep_b = parser.find_heading_by_title("进度计划安排")
    dep_c = parser.find_heading_by_title("其他章节")
    assert target is not None and dep_a is not None and dep_b is not None and dep_c is not None

    dependency_path = project_root / ".bid_writer" / "chapter_dependencies.json"
    dependency_path.parent.mkdir(parents=True)
    dependency_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    target.full_path: {
                        "title": target.title,
                        "dependencies": [dep_a.full_path, dep_b.full_path],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    file_saver = FileSaver(config.output_directory, config.output_prefix)
    file_saver.save(dep_a, "人员配置正文")
    file_saver.save(dep_b, "进度计划正文")
    file_saver.save(dep_c, "其他章节正文")

    fact_store = ChapterFactStore(config)
    fact_store.save(
        heading=dep_a,
        source_hash=ChapterFactExtractor._hash_source("人员配置正文"),
        facts=[
            ExtractedFact(scope="global", category="项目经理", value="张三"),
            ExtractedFact(scope="local", category="质量巡检", value="每周一次"),
        ],
    )
    fact_store.save(
        heading=dep_b,
        source_hash=ChapterFactExtractor._hash_source("进度计划正文"),
        facts=[
            ExtractedFact(scope="global", category="项目经理", value="张三"),
            ExtractedFact(scope="local", category="阶段划分", value="调研、开发、测试"),
        ],
    )
    fact_store.save(
        heading=dep_c,
        source_hash=ChapterFactExtractor._hash_source("其他章节正文"),
        facts=[ExtractedFact(scope="global", category="无关事实", value="不应注入")],
    )

    section = KnowledgeAssembler(config).build_prompt_section(
        heading=target,
        focus_terms=["质量"],
    )

    assert section == ""
    assert dependency_path.exists()
    assert "项目经理" not in section
    assert "质量巡检" not in section
    assert "阶段划分" not in section
    assert "无关事实" not in section


def test_knowledge_assembler_keeps_manual_knowledge_as_only_runtime_source(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "公司简介.md").write_text("- 公司名称：测试投标主体\n", encoding="utf-8")

    config = _build_config(
        tmp_path,
        """
project:
  root_dir: "./project"
  inputs:
    knowledge_files:
      - "./公司简介.md"
processing:
  knowledge:
    enabled: true
    max_chars: 800
""",
    )

    section = KnowledgeAssembler(config).build_prompt_section()

    assert "## 投标方知识库" in section
    assert "### 公司简介" in section
