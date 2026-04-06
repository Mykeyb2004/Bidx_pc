from pathlib import Path

import yaml

from bid_writer.config_editor import load_config_editor_document


def _write_project_files(base_dir: Path) -> None:
    (base_dir / "outline.md").write_text("# 项目\n## 章节\n### 内容\n", encoding="utf-8")
    (base_dir / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (base_dir / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")


def test_config_editor_normalizes_legacy_schema_and_preserves_generation_connection_fields(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "legacy.yaml"
    config_path.write_text(
        """
role: |
  你是一位专业的标书撰写专家。

outline_file: "./outline.md"
bid_requirements_file: "./bid_requirements.md"
scoring_criteria_file: "./scoring_criteria.md"

context_pruning:
  enabled: true
  mode: "legacy_rule"

api:
  base_url: "https://example.invalid/v1"
  api_key: "secret-key"
  model: "legacy-model"
  temperature: 0.6

prompt:
  max_mermaid_flowcharts_per_section: 5

output:
  directory: "./output"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    payload = yaml.safe_load(document.render_yaml())

    assert document.model["processing"]["path"] == "legacy_rule"
    assert "api" not in payload
    assert "context_pruning" not in payload
    assert payload["project"]["root_dir"] == "."
    assert payload["project"]["inputs"]["outline_file"] == "./outline.md"
    assert payload["models"]["generation"]["model"] == "legacy-model"
    assert payload["models"]["generation"]["temperature"] == 0.6
    assert payload["models"]["generation"]["base_url"] == "https://example.invalid/v1"
    assert payload["models"]["generation"]["api_key"] == "secret-key"
    assert payload["writing"]["target_words"]["default"] == 500
    assert document.model["writing"]["max_mermaid_flowcharts_per_section"] == 5
    assert payload["writing"]["max_mermaid_flowcharts_per_section"] == 5


def test_config_editor_preserves_full_context_processing_path(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "full-context.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

processing:
  path: "full_context"
  project_background:
    enabled: true
    max_chars: 600
  full_context:
    chapter_writing_plan:
      enabled: true
      max_chars: 280
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    payload = yaml.safe_load(document.render_yaml())

    assert document.model["processing"]["path"] == "full_context"
    assert payload["processing"]["path"] == "full_context"
    assert payload["processing"]["project_background"]["enabled"] is True
    assert payload["processing"]["project_background"]["max_chars"] == 600
    assert payload["processing"]["full_context"]["chapter_writing_plan"]["enabled"] is True
    assert payload["processing"]["full_context"]["chapter_writing_plan"]["max_chars"] == 280


def test_config_editor_validation_full_context_does_not_require_auto_runtime(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "full-context.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

processing:
  path: "full_context"
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate()

    assert not any("processing.path" in message.text for message in messages if message.level == "error")
    assert not any("auto 模式需要配置辅助模型" in message.text for message in messages)


def test_config_editor_validation_requires_explicit_processing_path_for_legacy_mixed_mode(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "mixed.yaml"
    config_path.write_text(
        """
outline_file: "./outline.md"
bid_requirements_file: "./bid_requirements.md"
scoring_criteria_file: "./scoring_criteria.md"

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

    document = load_config_editor_document(config_path)
    messages = document.validate()

    assert document.model["processing"]["path"] == "mixed"
    assert any("processing.path" in message.text for message in messages if message.level == "error")


def test_config_editor_validation_flags_hybrid_vector_without_embedding_connection(tmp_path: Path):
    _write_project_files(tmp_path)
    config_path = tmp_path / "hybrid.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

processing:
  path: "hybrid_extract"
  context_view:
    include_ancestors: true
    include_siblings: true
    max_siblings: 8
  legacy_rule:
    scoring_max_rows: 4
    requirements_max_quotes: 4
    requirements_max_quote_chars: 220
    requirement_brief_enabled: false
    requirement_brief_fallback: "rule_only"
  hybrid_extract:
    unavailable_policy: "fallback_legacy"
    scoring_parse_mode: "auto"
    scoring_max_rows: 4
    requirements_max_quotes: 4
    requirements_max_quote_chars: 220
    requirement_brief_enabled: false
    requirement_brief_fallback: "rule_only"
    retrieval:
      lexical_enabled: true
      vector_enabled: true
      verify_enabled: false
      top_k_lexical: 20
      top_k_vector: 20
      top_k_fused: 30
      top_k_final: 6
      min_fused_score: 0.0
    quote_only: true
    return_ids_only: true
    verify_max_candidates: 8
""".strip(),
        encoding="utf-8",
    )

    document = load_config_editor_document(config_path)
    messages = document.validate()

    assert any("embedding" in message.text for message in messages if message.level == "error")
