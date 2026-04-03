from pathlib import Path

from bid_writer.config import Config


def test_new_schema_resolves_project_relative_paths(tmp_path: Path):
    project_root = tmp_path / "project-data"
    project_root.mkdir()
    (project_root / "outline.md").write_text("# 项目\n## 章节\n### 质量保障措施\n", encoding="utf-8")
    (project_root / "bid_requirements.md").write_text("项目采购需求正文", encoding="utf-8")
    (project_root / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project-data"
  bidder_name: "测试投标主体"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
  output_dir: "./output"

writing:
  role: |
    你是一位专业的标书撰写专家。
  min_words:
    default: 1500
    min: 100
    max: 5000
    step: 100
  output_format: "纯正文"
  allow_markdown_headings: false

processing:
  path: "legacy_rule"
  context_view:
    include_ancestors: true
    include_siblings: true
    max_siblings: 6
  legacy_rule:
    scoring_max_rows: 3
    requirements_max_quotes: 2
    requirements_max_quote_chars: 180
    requirement_brief_enabled: true
  hybrid_extract:
    retrieval:
      lexical_enabled: true
      vector_enabled: false
      verify_enabled: false

models:
  generation:
    model: "test-model"
  pruning:
    model: "test-pruning-model"
  embedding:
    model: "test-embedding-model"
    cache_dir: "./embed-cache"

runtime:
  stream:
    enabled: false
    idle_timeout_seconds: 15
  trace:
    enabled: true
    directory: "./trace-output"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_path == "legacy_rule"
    assert config.context_pruning_enabled is True
    assert config.context_pruning_scoring_mode == "legacy_rule"
    assert config.context_pruning_requirements_mode == "legacy_rule"
    assert config.context_pruning_scoring_max_rows == 3
    assert config.context_pruning_requirements_max_quotes == 2
    assert config.context_pruning_requirements_max_quote_chars == 180
    assert config.context_pruning_requirements_brief_enabled is True
    assert config.output_directory == str(project_root / "output")
    assert config.generation_trace_directory == str(tmp_path / "trace-output")
    assert config.embedding_cache_dir == str(tmp_path / "embed-cache")
    assert config.bid_requirements == "项目采购需求正文"
    assert config.scoring_criteria == "评分标准正文"
    assert config.prompt_bidder_name == "测试投标主体"
    assert config.generation_stream is False
    assert config.generation_stream_idle_timeout_seconds == 15


def test_legacy_schema_still_derives_full_context_and_reads_inputs(tmp_path: Path):
    (tmp_path / "outline.md").write_text("# 项目\n## 章节\n### 质量保障措施\n", encoding="utf-8")
    (tmp_path / "bid_requirements.md").write_text("旧配置采购需求", encoding="utf-8")
    (tmp_path / "scoring_criteria.md").write_text("旧配置评分标准", encoding="utf-8")

    config_path = tmp_path / "legacy.yaml"
    config_path.write_text(
        """
role: |
  你是一位专业的标书撰写专家。

outline_file: "./outline.md"
bid_requirements_file: "./bid_requirements.md"
scoring_criteria_file: "./scoring_criteria.md"

context_pruning:
  enabled: false

output:
  directory: "./output"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_path == "full_context"
    assert config.context_pruning_enabled is False
    assert config.bid_requirements == "旧配置采购需求"
    assert config.scoring_criteria == "旧配置评分标准"
    assert config.output_directory == str(tmp_path / "output")


def test_mixed_legacy_modes_remain_compatible(tmp_path: Path):
    config_path = tmp_path / "mixed.yaml"
    config_path.write_text(
        """
context_pruning:
  enabled: true
  mode: "legacy_rule"
  scoring:
    mode: "legacy_rule"
  requirements:
    mode: "hybrid_extract"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_path == "mixed"
    assert config.context_pruning_enabled is True
    assert config.context_pruning_scoring_mode == "legacy_rule"
    assert config.context_pruning_requirements_mode == "hybrid_extract"
