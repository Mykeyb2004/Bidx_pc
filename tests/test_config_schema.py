import sys
from pathlib import Path

import pytest

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
  target_words:
    default: 1500
    min: 100
    max: 5000
    step: 100
    upper_ratio: 1.15
  max_mermaid_flowcharts_per_section: 3

processing:
  path: "legacy_rule"
  legacy_rule:
    scoring_max_rows: 3
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
    assert config.context_pruning_scoring_max_rows == 3
    assert config.output_directory == str(project_root / "output")
    assert config.generation_trace_directory == str(tmp_path / "trace-output")
    assert config.embedding_cache_dir == str(Path(sys.argv[0]).resolve().parent / "embedding_cache")
    assert config.bid_requirements == "项目采购需求正文"
    assert config.scoring_criteria == "评分标准正文"
    assert config.prompt_bidder_name == "测试投标主体"
    assert config.prompt_max_mermaid_flowcharts_per_section == 3
    assert config.generation_stream is False
    assert config.generation_stream_idle_timeout_seconds == 15
    assert config.generation_default_target_words == 1500
    assert config.build_target_word_range(1500).to_dict() == {"baseline": 1500, "lower": 1500, "upper": 1800}


def test_processing_scoring_enabled_defaults_to_true(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_scoring_enabled is True
    assert config.context_pruning_scoring_enabled is True


def test_processing_scoring_enabled_can_disable_auto_scoring(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
  scoring:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_scoring_enabled is False
    assert config.context_pruning_scoring_enabled is False


def test_processing_scoring_enabled_uses_legacy_fallback(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
context_pruning:
  enabled: true
  scoring:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_scoring_enabled is False
    assert config.context_pruning_scoring_enabled is False


def test_model_settings_are_loaded_from_env_local_and_not_yaml(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_API_BASE_URL",
        "BID_WRITER_API_KEY",
        "BID_WRITER_MODEL",
        "BID_WRITER_TEMPERATURE",
        "BID_WRITER_MAX_TOKENS",
        "BID_WRITER_TIMEOUT_SECONDS",
        "BID_WRITER_MAX_RETRIES",
        "BID_WRITER_TOP_P",
        "BID_WRITER_SEED",
        "BID_WRITER_PRUNING_API_BASE_URL",
        "BID_WRITER_PRUNING_API_KEY",
        "BID_WRITER_PRUNING_MODEL",
        "BID_WRITER_PRUNING_TEMPERATURE",
        "BID_WRITER_PRUNING_MAX_TOKENS",
        "BID_WRITER_PRUNING_TIMEOUT_SECONDS",
        "BID_WRITER_PRUNING_MAX_RETRIES",
        "BID_WRITER_PRUNING_TOP_P",
        "BID_WRITER_PRUNING_SEED",
        "BID_WRITER_EMBEDDING_API_BASE_URL",
        "BID_WRITER_EMBEDDING_API_KEY",
        "BID_WRITER_EMBEDDING_MODEL",
        "BID_WRITER_EMBEDDING_BATCH_SIZE",
        "BID_WRITER_EMBEDDING_REBUILD_ON_SOURCE_CHANGE",
        "BID_WRITER_EMBEDDING_QUERY_PREFIX",
        "BID_WRITER_EMBEDDING_DOCUMENT_PREFIX",
    ):
        monkeypatch.delenv(key, raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  generation:
    base_url: "https://yaml.invalid/v1"
    api_key: "yaml-key"
    model: "yaml-generation"
    temperature: 1.1
    max_tokens: 111
    timeout_seconds: 11
    max_retries: 1
    top_p: 0.11
    seed: 11
  pruning:
    base_url: "https://yaml-pruning.invalid/v1"
    api_key: "yaml-pruning-key"
    model: "yaml-pruning"
    temperature: 1.2
    max_tokens: 222
    timeout_seconds: 22
    max_retries: 2
    top_p: 0.22
    seed: 22
  embedding:
    base_url: "https://yaml-embedding.invalid/v1"
    api_key: "yaml-embedding-key"
    model: "yaml-embedding"
    batch_size: 22
    rebuild_on_source_change: false
    query_prefix: "yaml-query:"
    document_prefix: "yaml-document:"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        """
BID_WRITER_API_BASE_URL=https://env.example/v1
BID_WRITER_API_KEY=env-key
BID_WRITER_MODEL=env-generation
BID_WRITER_TEMPERATURE=0.3
BID_WRITER_MAX_TOKENS=333
BID_WRITER_TIMEOUT_SECONDS=33
BID_WRITER_MAX_RETRIES=4
BID_WRITER_TOP_P=0.93
BID_WRITER_SEED=333
BID_WRITER_PRUNING_API_BASE_URL=https://env-pruning.example/v1
BID_WRITER_PRUNING_API_KEY=env-pruning-key
BID_WRITER_PRUNING_MODEL=env-pruning
BID_WRITER_PRUNING_TEMPERATURE=0.2
BID_WRITER_PRUNING_MAX_TOKENS=444
BID_WRITER_PRUNING_TIMEOUT_SECONDS=44
BID_WRITER_PRUNING_MAX_RETRIES=5
BID_WRITER_PRUNING_TOP_P=0.82
BID_WRITER_PRUNING_SEED=444
BID_WRITER_EMBEDDING_API_BASE_URL=https://env-embedding.example/v1
BID_WRITER_EMBEDDING_API_KEY=env-embedding-key
BID_WRITER_EMBEDDING_MODEL=env-embedding
BID_WRITER_EMBEDDING_BATCH_SIZE=32
BID_WRITER_EMBEDDING_REBUILD_ON_SOURCE_CHANGE=false
BID_WRITER_EMBEDDING_QUERY_PREFIX=query:
BID_WRITER_EMBEDDING_DOCUMENT_PREFIX=document:
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.api_base_url == "https://env.example/v1"
    assert config.api_key == "env-key"
    assert config.model == "env-generation"
    assert config.temperature == 0.3
    assert config.max_tokens == 333
    assert config.api_timeout_seconds == 33
    assert config.api_max_retries == 4
    assert config.api_top_p == 0.93
    assert config.api_seed == 333
    assert config.pruning_api_base_url == "https://env-pruning.example/v1"
    assert config.pruning_api_key == "env-pruning-key"
    assert config.pruning_model == "env-pruning"
    assert config.pruning_temperature == 0.2
    assert config.pruning_max_tokens == 444
    assert config.pruning_timeout_seconds == 44
    assert config.pruning_max_retries == 5
    assert config.pruning_top_p == 0.82
    assert config.pruning_seed == 444
    assert config.embedding_api_base_url == "https://env-embedding.example/v1"
    assert config.embedding_api_key == "env-embedding-key"
    assert config.embedding_model == "env-embedding"
    assert config.embedding_batch_size == 32
    assert config.embedding_rebuild_on_source_change is False
    assert config.embedding_query_prefix == "query:"
    assert config.embedding_document_prefix == "document:"


def test_model_settings_ignore_yaml_when_env_local_is_absent(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_API_BASE_URL",
        "BID_WRITER_API_KEY",
        "BID_WRITER_MODEL",
        "BID_WRITER_TEMPERATURE",
        "BID_WRITER_MAX_TOKENS",
        "BID_WRITER_TIMEOUT_SECONDS",
        "BID_WRITER_MAX_RETRIES",
        "BID_WRITER_TOP_P",
        "BID_WRITER_SEED",
        "BID_WRITER_PRUNING_API_BASE_URL",
        "BID_WRITER_PRUNING_API_KEY",
        "BID_WRITER_PRUNING_MODEL",
        "BID_WRITER_EMBEDDING_API_BASE_URL",
        "BID_WRITER_EMBEDDING_API_KEY",
        "BID_WRITER_EMBEDDING_MODEL",
        "BID_WRITER_EMBEDDING_BATCH_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  generation:
    base_url: "https://yaml.invalid/v1"
    api_key: "yaml-key"
    model: "yaml-generation"
    temperature: 1.1
    max_tokens: 111
    timeout_seconds: 11
    max_retries: 1
  pruning:
    base_url: "https://yaml-pruning.invalid/v1"
    api_key: "yaml-pruning-key"
    model: "yaml-pruning"
  embedding:
    base_url: "https://yaml-embedding.invalid/v1"
    api_key: "yaml-embedding-key"
    model: "yaml-embedding"
    batch_size: 22
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.api_base_url == "https://api.openai.com/v1"
    assert config.api_key == ""
    assert config.model == "gpt-5.4"
    assert config.temperature == 0.7
    assert config.max_tokens == 10000
    assert config.api_timeout_seconds == 120
    assert config.api_max_retries == 3
    assert config.pruning_api_base_url == ""
    assert config.pruning_api_key == ""
    assert config.pruning_model == "gpt-5.4"
    assert config.embedding_api_base_url == ""
    assert config.embedding_api_key == ""
    assert config.embedding_model == "text-embedding-3-large"
    assert config.embedding_batch_size == 64


def test_env_local_values_refresh_between_config_directories(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_API_KEY",
        "BID_WRITER_MODEL",
        "BID_WRITER_EMBEDDING_API_KEY",
        "BID_WRITER_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "config.yaml").write_text("project: {}\n", encoding="utf-8")
    (project_b / "config.yaml").write_text("project: {}\n", encoding="utf-8")
    (project_a / ".env.local").write_text(
        "BID_WRITER_API_KEY=key-a\nBID_WRITER_MODEL=model-a\n"
        "BID_WRITER_EMBEDDING_API_KEY=embedding-key-a\nBID_WRITER_EMBEDDING_MODEL=embedding-a\n",
        encoding="utf-8",
    )
    (project_b / ".env.local").write_text(
        "BID_WRITER_API_KEY=key-b\nBID_WRITER_MODEL=model-b\n"
        "BID_WRITER_EMBEDDING_API_KEY=embedding-key-b\nBID_WRITER_EMBEDDING_MODEL=embedding-b\n",
        encoding="utf-8",
    )

    config_a = Config(str(project_a / "config.yaml"))
    config_b = Config(str(project_b / "config.yaml"))

    assert config_a.api_key == "key-a"
    assert config_a.model == "model-a"
    assert config_a.embedding_api_key == "embedding-key-a"
    assert config_a.embedding_model == "embedding-a"
    assert config_b.api_key == "key-b"
    assert config_b.model == "model-b"
    assert config_b.embedding_api_key == "embedding-key-b"
    assert config_b.embedding_model == "embedding-b"


def test_auto_retrieval_settings_are_loaded_from_env_local(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_AUTO_RETRIEVAL_LEXICAL_ENABLED",
        "BID_WRITER_AUTO_RETRIEVAL_VECTOR_ENABLED",
        "BID_WRITER_AUTO_RETRIEVAL_TOP_K_LEXICAL",
        "BID_WRITER_AUTO_RETRIEVAL_TOP_K_VECTOR",
        "BID_WRITER_AUTO_RETRIEVAL_TOP_K_FUSED",
        "BID_WRITER_AUTO_RETRIEVAL_TOP_K_FINAL",
        "BID_WRITER_AUTO_RETRIEVAL_MIN_FUSED_SCORE",
    ):
        monkeypatch.delenv(key, raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
  hybrid_extract:
    retrieval:
      lexical_enabled: false
      vector_enabled: false
      top_k_lexical: 4
      top_k_vector: 5
      top_k_fused: 6
      top_k_final: 7
      min_fused_score: 0.2
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        """
BID_WRITER_AUTO_RETRIEVAL_LEXICAL_ENABLED=true
BID_WRITER_AUTO_RETRIEVAL_VECTOR_ENABLED=true
BID_WRITER_AUTO_RETRIEVAL_TOP_K_LEXICAL=21
BID_WRITER_AUTO_RETRIEVAL_TOP_K_VECTOR=22
BID_WRITER_AUTO_RETRIEVAL_TOP_K_FUSED=31
BID_WRITER_AUTO_RETRIEVAL_TOP_K_FINAL=12
BID_WRITER_AUTO_RETRIEVAL_MIN_FUSED_SCORE=0.35
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.context_pruning_retrieval_lexical_enabled is True
    assert config.context_pruning_retrieval_vector_enabled is True
    assert config.context_pruning_retrieval_top_k_lexical == 21
    assert config.context_pruning_retrieval_top_k_vector == 22
    assert config.context_pruning_retrieval_top_k_fused == 31
    assert config.context_pruning_retrieval_top_k_final == 12
    assert config.context_pruning_retrieval_min_fused_score == 0.35


def test_embedding_cache_defaults_next_to_execution_file(monkeypatch, tmp_path: Path):
    execution_dir = tmp_path / "runner"
    execution_dir.mkdir()
    fake_runner = execution_dir / "run.py"
    fake_runner.write_text("", encoding="utf-8")
    config_path = tmp_path / "project" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text("project: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(fake_runner)])

    config = Config(str(config_path))

    assert config.embedding_cache_dir == str(execution_dir / "embedding_cache")


def test_full_context_chapter_writing_plan_config_is_read(tmp_path: Path):
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
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

processing:
  path: "full_context"
  full_context:
    chapter_writing_plan:
      enabled: true
      max_chars: 280
      cache_dir: "./plan-cache"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.processing_path == "full_context"
    assert config.chapter_writing_plan_enabled is True
    assert config.chapter_writing_plan_max_chars == 280
    assert config.chapter_writing_plan_cache_dir == str(project_root / "plan-cache")


def test_new_schema_reads_knowledge_paths_and_budget(tmp_path: Path):
    project_root = tmp_path / "project-data"
    project_root.mkdir()
    knowledge_dir = project_root / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "团队.md").write_text("- 项目经理：张三\n", encoding="utf-8")
    (project_root / "公司简介.md").write_text("- 公司名称：测试投标主体\n", encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project-data"
  inputs:
    knowledge_files:
      - "./公司简介.md"
    knowledge_directory: "./knowledge"

processing:
  knowledge:
    enabled: true
    max_chars: 360
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.knowledge_files == [str(project_root / "公司简介.md")]
    assert config.knowledge_directory == str(project_root / "knowledge")
    assert config.knowledge_enabled is True
    assert config.knowledge_max_chars == 360


def test_new_schema_reads_chapter_fact_settings(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  chapter_facts:
    enabled: true
    auto_extract_on_batch: false
    max_facts_per_chapter: 9
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.chapter_facts_enabled is True
    assert config.chapter_facts_auto_extract_on_batch is False
    assert config.chapter_facts_max_facts_per_chapter == 9


def test_h2_project_background_config_defaults_to_h2_raw_evidence_for_old_shape(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  output_dir: "./output"

processing:
  path: "auto"
  project_background:
    enabled: true
    max_chars: 640
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.project_background_scope == "h2_auto"
    assert config.h2_project_background_enabled is True
    assert config.h2_project_background_precompute_on_batch is True
    assert config.h2_project_background_generate_missing_on_single is True
    assert config.h2_project_background_max_evidence_blocks == 6
    assert config.h2_project_background_max_evidence_chars == 2400
    assert config.h2_project_background_include_evidence_in_prompt is False
    assert config.h2_project_background_content_mode == "excerpts"
    assert config.h2_project_background_min_evidence_blocks == 1
    assert config.h2_project_background_fallback == "raw_evidence"
    assert config.h2_project_background_cache_dir == str(tmp_path / "caches" / "project_background_h2")


def test_project_background_global_scope_is_rejected(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
  project_background:
    enabled: true
    scope: "global"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    with pytest.raises(ValueError, match="project_background.scope"):
        _ = config.project_background_scope


def test_h2_project_background_global_fallback_is_rejected(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
  project_background:
    enabled: true
    h2:
      fallback: "global"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    with pytest.raises(ValueError, match="project_background.h2.fallback"):
        _ = config.h2_project_background_fallback


def test_h2_project_background_config_reads_new_h2_auto_scope(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project"

processing:
  path: "auto"
  project_background:
    enabled: true
    scope: "h2_auto"
    max_chars: 720
    h2:
      precompute_on_batch: false
      generate_missing_on_single: false
      max_evidence_blocks: 4
      max_evidence_chars: 1800
      content_mode: "summary"
      min_evidence_blocks: 1
      fallback: "raw_evidence"
      cache_dir: "./cache/h2-bg"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.project_background_scope == "h2_auto"
    assert config.h2_project_background_enabled is True
    assert config.project_background_max_chars == 720
    assert config.h2_project_background_precompute_on_batch is False
    assert config.h2_project_background_generate_missing_on_single is False
    assert config.h2_project_background_max_evidence_blocks == 4
    assert config.h2_project_background_max_evidence_chars == 1800
    assert config.h2_project_background_content_mode == "summary"
    assert config.h2_project_background_min_evidence_blocks == 1
    assert config.h2_project_background_fallback == "raw_evidence"
    assert config.h2_project_background_cache_dir == str(project_root / "cache" / "h2-bg")


def test_h2_project_background_invalid_content_mode_is_rejected(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
processing:
  path: "auto"
  project_background:
    enabled: true
    h2:
      content_mode: "model"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    with pytest.raises(ValueError, match="project_background.h2.content_mode"):
        _ = config.h2_project_background_content_mode


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


def test_legacy_requirements_mode_is_ignored(tmp_path: Path):
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

    assert config.processing_path == "legacy_rule"
    assert config.context_pruning_enabled is True
    assert config.context_pruning_scoring_mode == "legacy_rule"


def test_outline_lock_defaults_true_for_existing_configs(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}\n", encoding="utf-8")

    config = Config(str(config_path))

    assert config.outline_locked is True


def test_outline_lock_can_be_disabled_for_new_project_flow(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  outline_locked: false
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_locked is False


def test_outline_generation_role_file_resolves_from_config_dir(tmp_path: Path):
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    role_file = roles_dir / "标书架构师.md"
    role_file.write_text("架构师角色", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  outline_generation:
    role_file: "./roles/标书架构师.md"
""".strip(),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_generation_role_file == str(role_file)


def test_outline_model_settings_prefer_outline_env_and_fallback_to_generation(monkeypatch, tmp_path: Path):
    for key in (
        "BID_WRITER_API_BASE_URL",
        "BID_WRITER_API_KEY",
        "BID_WRITER_MODEL",
        "BID_WRITER_TEMPERATURE",
        "BID_WRITER_MAX_TOKENS",
        "BID_WRITER_TIMEOUT_SECONDS",
        "BID_WRITER_MAX_RETRIES",
        "BID_WRITER_TOP_P",
        "BID_WRITER_SEED",
        "BID_WRITER_OUTLINE_API_BASE_URL",
        "BID_WRITER_OUTLINE_API_KEY",
        "BID_WRITER_OUTLINE_MODEL",
        "BID_WRITER_OUTLINE_TEMPERATURE",
        "BID_WRITER_OUTLINE_MAX_TOKENS",
        "BID_WRITER_OUTLINE_TIMEOUT_SECONDS",
        "BID_WRITER_OUTLINE_MAX_RETRIES",
        "BID_WRITER_OUTLINE_TOP_P",
        "BID_WRITER_OUTLINE_SEED",
    ):
        monkeypatch.delenv(key, raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "BID_WRITER_API_BASE_URL=https://generation.example/v1",
                "BID_WRITER_API_KEY=generation-key",
                "BID_WRITER_MODEL=generation-model",
                "BID_WRITER_TEMPERATURE=0.7",
                "BID_WRITER_MAX_TOKENS=10000",
                "BID_WRITER_TIMEOUT_SECONDS=120",
                "BID_WRITER_MAX_RETRIES=3",
                "BID_WRITER_TOP_P=0.9",
                "BID_WRITER_SEED=100",
                "BID_WRITER_OUTLINE_MODEL=outline-model",
                "BID_WRITER_OUTLINE_TEMPERATURE=0.25",
                "BID_WRITER_OUTLINE_MAX_TOKENS=4321",
            ]
        ),
        encoding="utf-8",
    )

    config = Config(str(config_path))

    assert config.outline_api_base_url == "https://generation.example/v1"
    assert config.outline_api_key == "generation-key"
    assert config.outline_model == "outline-model"
    assert config.outline_temperature == 0.25
    assert config.outline_max_tokens == 4321
    assert config.outline_timeout_seconds == 120
    assert config.outline_max_retries == 3
    assert config.outline_top_p == 0.9
    assert config.outline_seed == 100
