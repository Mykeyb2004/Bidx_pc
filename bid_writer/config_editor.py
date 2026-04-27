"""
配置编辑器的数据模型、校验与 YAML 导出。
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_MISSING = object()
_SUPPORTED_PROCESSING_PATHS = {"auto", "full_context"}
_KNOWN_PROCESSING_PATHS = _SUPPORTED_PROCESSING_PATHS | {"legacy_rule", "hybrid_extract", "mixed"}


@dataclass(frozen=True)
class ValidationMessage:
    level: str
    text: str


@dataclass(frozen=True)
class ConnectionStatus:
    configured: bool
    source: str = ""


@dataclass
class ConfigEditorDocument:
    config_path: Path
    raw_config: dict[str, Any]
    model: dict[str, Any]
    preserved_extra: dict[str, Any] = field(default_factory=dict)
    env_status: dict[str, ConnectionStatus] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    require_project_identity: bool = False

    def render_yaml(self, model: dict[str, Any] | None = None) -> str:
        payload = merge_with_preserved(
            build_canonical_config(model or self.model),
            self.preserved_extra,
        )
        return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip() + "\n"

    def validate(self, model: dict[str, Any] | None = None) -> list[ValidationMessage]:
        return validate_editor_model(
            model or self.model,
            self.config_path,
            self.env_status,
            self.raw_config,
            require_project_identity=self.require_project_identity,
        )

    def save(
        self,
        model: dict[str, Any] | None = None,
        *,
        target_path: str | Path | None = None,
        create_backup: bool = True,
    ) -> Path:
        output_path = Path(target_path or self.config_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_text = self.render_yaml(model)
        if create_backup and output_path.exists():
            backup_path = output_path.with_suffix(output_path.suffix + ".bak")
            backup_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")

        output_path.write_text(yaml_text, encoding="utf-8")
        self.config_path = output_path.resolve()
        self.raw_config = yaml.safe_load(yaml_text) or {}
        self.preserved_extra = extract_preserved_extra(self.raw_config)
        self.model = normalize_raw_config_to_editor_model(self.raw_config)
        self.env_status = detect_connection_status(self.config_path, self.raw_config)
        self.notes = build_editor_notes(self.model, self.raw_config)
        return output_path


def load_config_editor_document(config_path: str | Path) -> ConfigEditorDocument:
    path = Path(config_path).expanduser().resolve()
    raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    model = normalize_raw_config_to_editor_model(raw_config)
    return ConfigEditorDocument(
        config_path=path,
        raw_config=raw_config,
        model=model,
        preserved_extra=extract_preserved_extra(raw_config),
        env_status=detect_connection_status(path, raw_config),
        notes=build_editor_notes(model, raw_config),
    )


def build_default_editor_model() -> dict[str, Any]:
    return {
        "project": {
            "root_dir": ".",
            "bidder_name": "",
            "outline_file": "./outline.md",
            "bid_requirements_mode": "file",
            "bid_requirements_file": "./项目要求/项目采购需求.md",
            "bid_requirements_text": "",
            "scoring_criteria_mode": "file",
            "scoring_criteria_file": "./项目要求/评分标准.md",
            "scoring_criteria_text": "",
            "output_dir": "./output",
        },
        "writing": {
            "role_mode": "file",
            "role_file": "./roles/example_role.md",
            "role_text": "",
            "target_words_default": 3000,
            "target_words_min": 100,
            "target_words_max": 15000,
            "target_words_step": 100,
            "target_words_upper_ratio": 1.15,
            "output_format": "纯正文",
            "first_line_template": "",
            "allow_markdown_headings": False,
            "allow_english_terms": False,
            "max_tables_per_section": 2,
            "max_mermaid_flowcharts_per_section": 0,
            "summary_title": "",
            "hard_constraints": [],
            "extra_rules": [
                "内容要专业、严谨，符合标书撰写规范",
                "请根据以上任务卡，结合采购需求、评分标准撰写投标正文。",
            ],
        },
        "processing": {
            "path": "auto",
            "context_view": {
                "include_ancestors": True,
                "include_siblings": True,
                "max_siblings": 8,
            },
            "project_background": {
                "enabled": True,
                "max_chars": 800,
            },
            "auto": {
                "requirements_top_k": 8,
                "scoring_parse_mode": "auto",
                "scoring_max_rows": 4,
                "retrieval": {
                    "lexical_enabled": True,
                    "vector_enabled": False,
                    "top_k_lexical": 20,
                    "top_k_fused": 30,
                    "top_k_final": 8,
                    "min_fused_score": 0.0,
                },
            },
            "full_context": {
                "chapter_writing_plan": {
                    "enabled": False,
                    "max_chars": 320,
                },
            },
        },
        "models": {
            "generation": {
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 8000,
                "timeout_seconds": 120,
                "max_retries": 3,
                "top_p": "",
                "seed": "",
            },
            "pruning": {
                "model": "gpt-4o-mini",
                "temperature": 0.2,
                "max_tokens": 1200,
                "timeout_seconds": 60,
                "max_retries": 2,
                "top_p": "",
                "seed": "",
            },
            "embedding": {
                "model": "text-embedding-3-small",
                "batch_size": 64,
                "cache_dir": "./output/_embedding_cache",
                "rebuild_on_source_change": True,
                "query_prefix": "",
                "document_prefix": "",
            },
        },
        "runtime": {
            "stream": {
                "enabled": True,
                "idle_timeout_seconds": 12,
            },
            "trace": {
                "enabled": False,
                "directory": "./log/generation_traces",
                "mode": "full",
                "write_prompt": True,
                "write_output": True,
                "write_context": True,
                "write_summary": True,
                "redact_sensitive": True,
            },
            "debug": {
                "context_pruning_dump": False,
            },
            "output": {
                "prefix": "",
                "include_title_header": True,
                "overwrite_existing": True,
                "filename_max_length": 100,
                "empty_filename_fallback": "untitled",
            },
            "merge": {
                "normalize_soft_line_breaks": False,
            },
        },
    }


def create_new_config_editor_document(config_path: str | Path | None = None) -> ConfigEditorDocument:
    path = Path(config_path or "config_新项目.yaml").expanduser().resolve()
    model = build_default_editor_model()
    raw_config = merge_with_preserved(
        build_canonical_config(model),
        {
            "fact_cards": {
                "enabled": True,
                "cards": [],
                "chapter_defaults": {},
            }
        },
    )
    return ConfigEditorDocument(
        config_path=path,
        raw_config=raw_config,
        model=copy.deepcopy(model),
        preserved_extra=extract_preserved_extra(raw_config),
        env_status=detect_connection_status(path, raw_config),
        notes=build_editor_notes(model, raw_config),
        require_project_identity=True,
    )


def build_editor_notes(model: dict[str, Any], raw_config: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    processing_path = model["processing"]["path"]
    if processing_path not in _SUPPORTED_PROCESSING_PATHS:
        notes.append(
            "当前配置使用的 processing.path 暂不支持完整可视化编辑；"
            "编辑器当前仅支持 auto / full_context，若直接保存将按 auto 模式导出。"
        )
    elif processing_path == "full_context":
        notes.append("full_context 模式会把采购需求和评分标准全文直接拼入提示词，不做章节级摘录。")

    if "context_pruning" in raw_config or "prompt" in raw_config or "api" in raw_config:
        notes.append("当前文件包含旧 schema 字段，保存后会按 canonical schema 标准化。")

    if model["project"]["bid_requirements_mode"] == "inline":
        notes.append("采购需求当前以内嵌文本保存，推荐后续迁移为独立文件。")

    if model["project"]["scoring_criteria_mode"] == "inline":
        notes.append("评分标准当前以内嵌文本保存，推荐后续迁移为独立文件。")

    if model["writing"]["role_mode"] == "inline":
        notes.append("角色设定当前以内嵌文本保存，如需复用，建议迁移到 role_file。")

    return notes


def normalize_raw_config_to_editor_model(raw_config: dict[str, Any]) -> dict[str, Any]:
    project_root = _coerce_str(_first_defined(raw_config, ("project", "root_dir"), default=".")).strip() or "."
    bid_requirements_mode, bid_requirements_file, bid_requirements_text = _normalize_text_source(
        inline_value=_first_defined(
            raw_config,
            ("project", "inputs", "bid_requirements"),
            ("inputs", "bid_requirements"),
            "bid_requirements",
            default="",
        ),
        file_value=_first_defined(
            raw_config,
            ("project", "inputs", "bid_requirements_file"),
            ("inputs", "bid_requirements_file"),
            "bid_requirements_file",
            default="",
        ),
        default_file="./bid_requirements.md",
    )
    scoring_mode, scoring_file, scoring_text = _normalize_text_source(
        inline_value=_first_defined(
            raw_config,
            ("project", "inputs", "scoring_criteria"),
            ("inputs", "scoring_criteria"),
            "scoring_criteria",
            default="",
        ),
        file_value=_first_defined(
            raw_config,
            ("project", "inputs", "scoring_criteria_file"),
            ("inputs", "scoring_criteria_file"),
            "scoring_criteria_file",
            default="",
        ),
        default_file="./scoring_criteria.md",
    )
    role_mode, role_file, role_text = _normalize_text_source(
        inline_value=_first_defined(raw_config, ("writing", "role"), "role", default=""),
        file_value=_first_defined(raw_config, ("writing", "role_file"), "role_file", default=""),
        default_file="./roles/example_role.md",
    )

    processing_path = _derive_processing_path(raw_config)
    return {
        "project": {
            "root_dir": project_root,
            "bidder_name": _coerce_str(
                _first_defined(
                    raw_config,
                    ("project", "bidder_name"),
                    ("writing", "bidder_name"),
                    ("prompt", "bidder_name"),
                    default="",
                )
            ),
            "outline_file": _coerce_str(
                _first_defined(
                    raw_config,
                    ("project", "inputs", "outline_file"),
                    ("inputs", "outline_file"),
                    "outline_file",
                    default="./outline.md",
                )
            ),
            "bid_requirements_mode": bid_requirements_mode,
            "bid_requirements_file": bid_requirements_file,
            "bid_requirements_text": bid_requirements_text,
            "scoring_criteria_mode": scoring_mode,
            "scoring_criteria_file": scoring_file,
            "scoring_criteria_text": scoring_text,
            "output_dir": _coerce_str(
                _first_defined(
                    raw_config,
                    ("project", "output_dir"),
                    ("runtime", "output", "directory"),
                    ("output", "directory"),
                    default="./output",
                )
            ),
        },
        "writing": {
            "role_mode": role_mode,
            "role_file": role_file,
            "role_text": role_text,
            "target_words_default": _coerce_int(
                _first_defined(
                    raw_config,
                    ("writing", "target_words", "default"),
                    ("writing", "min_words", "default"),
                    ("generation", "default_min_words"),
                    "default_min_words",
                    default=500,
                ),
                default=500,
            ),
            "target_words_min": _coerce_int(
                _first_defined(
                    raw_config,
                    ("writing", "target_words", "min"),
                    ("writing", "min_words", "min"),
                    ("generation", "min_words_min"),
                    default=100,
                ),
                default=100,
            ),
            "target_words_max": _coerce_int(
                _first_defined(
                    raw_config,
                    ("writing", "target_words", "max"),
                    ("writing", "min_words", "max"),
                    ("generation", "min_words_max"),
                    default=15000,
                ),
                default=15000,
            ),
            "target_words_step": _coerce_int(
                _first_defined(
                    raw_config,
                    ("writing", "target_words", "step"),
                    ("writing", "min_words", "step"),
                    ("generation", "min_words_step"),
                    default=100,
                ),
                default=100,
            ),
            "target_words_upper_ratio": _coerce_float(
                _first_defined(raw_config, ("writing", "target_words", "upper_ratio"), default=1.15),
                default=1.15,
            ),
            "output_format": _coerce_str(
                _first_defined(raw_config, ("writing", "output_format"), ("prompt", "output_format"), default="Markdown格式")
            ),
            "first_line_template": _coerce_str(
                _first_defined(raw_config, ("writing", "first_line_template"), ("prompt", "first_line_template"), default="")
            ),
            "allow_markdown_headings": _coerce_bool(
                _first_defined(raw_config, ("writing", "allow_markdown_headings"), ("prompt", "allow_markdown_headings"), default=False),
                default=False,
            ),
            "allow_english_terms": _coerce_bool(
                _first_defined(raw_config, ("writing", "allow_english_terms"), ("prompt", "allow_english_terms"), default=False),
                default=False,
            ),
            "max_tables_per_section": _coerce_int(
                _first_defined(raw_config, ("writing", "max_tables_per_section"), ("prompt", "max_tables_per_section"), default=4),
                default=4,
            ),
            "max_mermaid_flowcharts_per_section": _coerce_int(
                _first_defined(
                    raw_config,
                    ("writing", "max_mermaid_flowcharts_per_section"),
                    ("prompt", "max_mermaid_flowcharts_per_section"),
                    default=0,
                ),
                default=0,
            ),
            "summary_title": _coerce_str(
                _first_defined(raw_config, ("writing", "summary_title"), ("prompt", "summary_title"), default="章节小结")
            ),
            "hard_constraints": _coerce_string_list(
                _first_defined(raw_config, ("writing", "hard_constraints"), ("prompt", "hard_constraints"), default=[]),
            ),
            "extra_rules": _coerce_string_list(
                _first_defined(raw_config, ("writing", "extra_rules"), ("prompt", "extra_rules"), default=[]),
            ),
        },
        "processing": {
            "path": processing_path,
            "context_view": {
                "include_ancestors": _coerce_bool(
                    _first_defined(raw_config, ("processing", "context_view", "include_ancestors"), ("context_pruning", "local_outline", "include_ancestors"), default=True),
                    default=True,
                ),
                "include_siblings": _coerce_bool(
                    _first_defined(raw_config, ("processing", "context_view", "include_siblings"), ("context_pruning", "local_outline", "include_siblings"), default=True),
                    default=True,
                ),
                "max_siblings": _coerce_int(
                    _first_defined(raw_config, ("processing", "context_view", "max_siblings"), ("context_pruning", "local_outline", "max_siblings"), default=8),
                    default=8,
                ),
            },
            "project_background": {
                "enabled": _coerce_bool(
                    _first_defined(raw_config, ("processing", "project_background", "enabled"), default=True),
                    default=True,
                ),
                "max_chars": _coerce_int(
                    _first_defined(raw_config, ("processing", "project_background", "max_chars"), default=800),
                    default=800,
                ),
            },
            "auto": {
                "requirements_top_k": _coerce_int(
                    _first_defined(raw_config, ("processing", "auto", "requirements_top_k"), default=8),
                    default=8,
                ),
                "scoring_parse_mode": _coerce_str(
                    _first_defined(raw_config, ("processing", "hybrid_extract", "scoring_parse_mode"), default="auto")
                ),
                "scoring_max_rows": _coerce_int(
                    _first_defined(raw_config, ("processing", "hybrid_extract", "scoring_max_rows"), ("context_pruning", "scoring", "max_rows"), default=20),
                    default=20,
                ),
                "retrieval": {
                    "lexical_enabled": _coerce_bool(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "lexical_enabled"), ("context_pruning", "retrieval", "lexical_enabled"), default=True),
                        default=True,
                    ),
                    "vector_enabled": _coerce_bool(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "vector_enabled"), ("context_pruning", "retrieval", "vector_enabled"), default=False),
                        default=False,
                    ),
                    "top_k_lexical": _coerce_int(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "top_k_lexical"), ("context_pruning", "retrieval", "top_k_lexical"), default=20),
                        default=20,
                    ),
                    "top_k_fused": _coerce_int(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "top_k_fused"), ("context_pruning", "retrieval", "top_k_fused"), default=30),
                        default=30,
                    ),
                    "top_k_final": _coerce_int(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "top_k_final"), ("context_pruning", "retrieval", "top_k_final"), default=8),
                        default=8,
                    ),
                    "min_fused_score": _coerce_float(
                        _first_defined(raw_config, ("processing", "hybrid_extract", "retrieval", "min_fused_score"), ("context_pruning", "retrieval", "min_fused_score"), default=0.0),
                        default=0.0,
                    ),
                },
            },
            "full_context": {
                "chapter_writing_plan": {
                    "enabled": _coerce_bool(
                        _first_defined(raw_config, ("processing", "full_context", "chapter_writing_plan", "enabled"), default=False),
                        default=False,
                    ),
                    "max_chars": _coerce_int(
                        _first_defined(raw_config, ("processing", "full_context", "chapter_writing_plan", "max_chars"), default=320),
                        default=320,
                    ),
                },
            },
        },
        "models": {
            "generation": {
                "model": _coerce_str(_first_defined(raw_config, ("models", "generation", "model"), ("api", "model"), default="gpt-4")),
                "temperature": _coerce_float(_first_defined(raw_config, ("models", "generation", "temperature"), ("api", "temperature"), default=0.7), default=0.7),
                "max_tokens": _coerce_int(_first_defined(raw_config, ("models", "generation", "max_tokens"), ("api", "max_tokens"), default=8000), default=8000),
                "timeout_seconds": _coerce_int(_first_defined(raw_config, ("models", "generation", "timeout_seconds"), ("api", "timeout_seconds"), default=120), default=120),
                "max_retries": _coerce_int(_first_defined(raw_config, ("models", "generation", "max_retries"), ("api", "max_retries"), default=3), default=3),
                "top_p": _coerce_optional(_first_defined(raw_config, ("models", "generation", "top_p"), ("api", "top_p"), default="")),
                "seed": _coerce_optional(_first_defined(raw_config, ("models", "generation", "seed"), ("api", "seed"), default="")),
            },
            "pruning": {
                "model": _coerce_str(_first_defined(raw_config, ("models", "pruning", "model"), ("context_pruning", "api", "model"), default="")),
                "temperature": _coerce_float(_first_defined(raw_config, ("models", "pruning", "temperature"), ("context_pruning", "api", "temperature"), default=0.2), default=0.2),
                "max_tokens": _coerce_int(_first_defined(raw_config, ("models", "pruning", "max_tokens"), ("context_pruning", "api", "max_tokens"), default=1200), default=1200),
                "timeout_seconds": _coerce_int(_first_defined(raw_config, ("models", "pruning", "timeout_seconds"), ("context_pruning", "api", "timeout_seconds"), default=60), default=60),
                "max_retries": _coerce_int(_first_defined(raw_config, ("models", "pruning", "max_retries"), ("context_pruning", "api", "max_retries"), default=2), default=2),
                "top_p": _coerce_optional(_first_defined(raw_config, ("models", "pruning", "top_p"), ("context_pruning", "api", "top_p"), default="")),
                "seed": _coerce_optional(_first_defined(raw_config, ("models", "pruning", "seed"), ("context_pruning", "api", "seed"), default="")),
            },
            "embedding": {
                "model": _coerce_str(_first_defined(raw_config, ("models", "embedding", "model"), ("context_pruning", "retrieval", "embedding", "model"), default="text-embedding-3-small")),
                "batch_size": _coerce_int(_first_defined(raw_config, ("models", "embedding", "batch_size"), ("context_pruning", "retrieval", "embedding", "batch_size"), default=64), default=64),
                "cache_dir": _coerce_str(_first_defined(raw_config, ("models", "embedding", "cache_dir"), ("context_pruning", "retrieval", "embedding", "cache_dir"), default="./output/_embedding_cache")),
                "rebuild_on_source_change": _coerce_bool(
                    _first_defined(raw_config, ("models", "embedding", "rebuild_on_source_change"), ("context_pruning", "retrieval", "embedding", "rebuild_on_source_change"), default=True),
                    default=True,
                ),
                "query_prefix": _coerce_str(_first_defined(raw_config, ("models", "embedding", "query_prefix"), ("context_pruning", "retrieval", "embedding", "query_prefix"), default="")),
                "document_prefix": _coerce_str(_first_defined(raw_config, ("models", "embedding", "document_prefix"), ("context_pruning", "retrieval", "embedding", "document_prefix"), default="")),
            },
        },
        "runtime": {
            "stream": {
                "enabled": _coerce_bool(_first_defined(raw_config, ("runtime", "stream", "enabled"), ("generation", "stream"), default=True), default=True),
                "idle_timeout_seconds": _coerce_int(
                    _first_defined(raw_config, ("runtime", "stream", "idle_timeout_seconds"), ("generation", "stream_idle_timeout_seconds"), default=12),
                    default=12,
                ),
            },
            "trace": {
                "enabled": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "enabled"), ("generation_trace", "enabled"), default=False), default=False),
                "directory": _coerce_str(_first_defined(raw_config, ("runtime", "trace", "directory"), ("generation_trace", "directory"), default="./log/generation_traces")),
                "mode": _coerce_str(_first_defined(raw_config, ("runtime", "trace", "mode"), ("generation_trace", "mode"), default="full")),
                "write_prompt": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "write_prompt"), ("generation_trace", "write_prompt"), default=True), default=True),
                "write_output": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "write_output"), ("generation_trace", "write_output"), default=True), default=True),
                "write_context": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "write_context"), ("generation_trace", "write_context"), default=True), default=True),
                "write_summary": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "write_summary"), ("generation_trace", "write_summary"), default=True), default=True),
                "redact_sensitive": _coerce_bool(_first_defined(raw_config, ("runtime", "trace", "redact_sensitive"), ("generation_trace", "redact_sensitive"), default=True), default=True),
            },
            "debug": {
                "context_pruning_dump": _coerce_bool(
                    _first_defined(raw_config, ("runtime", "debug", "context_pruning_dump"), ("context_pruning", "debug_dump"), default=False),
                    default=False,
                ),
            },
            "output": {
                "prefix": _coerce_str(_first_defined(raw_config, ("runtime", "output", "prefix"), ("output", "prefix"), default="")),
                "include_title_header": _coerce_bool(
                    _first_defined(raw_config, ("runtime", "output", "include_title_header"), ("output", "include_title_header"), default=True),
                    default=True,
                ),
                "overwrite_existing": _coerce_bool(
                    _first_defined(raw_config, ("runtime", "output", "overwrite_existing"), ("output", "overwrite_existing"), ("generation", "overwrite_existing"), default=True),
                    default=True,
                ),
                "filename_max_length": _coerce_int(_first_defined(raw_config, ("runtime", "output", "filename_max_length"), ("output", "filename_max_length"), default=100), default=100),
                "empty_filename_fallback": _coerce_str(_first_defined(raw_config, ("runtime", "output", "empty_filename_fallback"), ("output", "empty_filename_fallback"), default="untitled")),
            },
            "merge": {
                "normalize_soft_line_breaks": _coerce_bool(
                    _first_defined(raw_config, ("runtime", "merge", "normalize_soft_line_breaks"), ("output", "normalize_soft_line_breaks_on_merge"), default=False),
                    default=False,
                ),
            },
        },
    }


def build_canonical_config(model: dict[str, Any]) -> dict[str, Any]:
    processing_path = model["processing"]["path"] if model["processing"]["path"] in _SUPPORTED_PROCESSING_PATHS else "auto"
    project_inputs: dict[str, Any] = {
        "outline_file": model["project"]["outline_file"].strip() or "./outline.md",
    }
    if model["project"]["bid_requirements_mode"] == "inline":
        project_inputs["bid_requirements"] = model["project"]["bid_requirements_text"]
    else:
        project_inputs["bid_requirements_file"] = model["project"]["bid_requirements_file"].strip() or "./bid_requirements.md"

    if model["project"]["scoring_criteria_mode"] == "inline":
        project_inputs["scoring_criteria"] = model["project"]["scoring_criteria_text"]
    else:
        project_inputs["scoring_criteria_file"] = model["project"]["scoring_criteria_file"].strip() or "./scoring_criteria.md"

    writing_payload: dict[str, Any] = {
        "target_words": {
            "default": int(model["writing"]["target_words_default"]),
            "min": int(model["writing"]["target_words_min"]),
            "max": int(model["writing"]["target_words_max"]),
            "step": int(model["writing"]["target_words_step"]),
            "upper_ratio": float(model["writing"]["target_words_upper_ratio"]),
        },
        "output_format": model["writing"]["output_format"],
        "first_line_template": model["writing"]["first_line_template"],
        "allow_markdown_headings": bool(model["writing"]["allow_markdown_headings"]),
        "allow_english_terms": bool(model["writing"]["allow_english_terms"]),
        "max_tables_per_section": int(model["writing"]["max_tables_per_section"]),
        "max_mermaid_flowcharts_per_section": int(model["writing"]["max_mermaid_flowcharts_per_section"]),
        "summary_title": model["writing"]["summary_title"],
        "hard_constraints": list(model["writing"]["hard_constraints"]),
        "extra_rules": list(model["writing"]["extra_rules"]),
    }
    if model["writing"]["role_mode"] == "inline":
        writing_payload["role"] = model["writing"]["role_text"]
    else:
        writing_payload["role_file"] = model["writing"]["role_file"].strip() or "./roles/example_role.md"

    generation_payload = _strip_none_values(
        {
            "model": model["models"]["generation"]["model"],
            "temperature": float(model["models"]["generation"]["temperature"]),
            "max_tokens": int(model["models"]["generation"]["max_tokens"]),
            "timeout_seconds": int(model["models"]["generation"]["timeout_seconds"]),
            "max_retries": int(model["models"]["generation"]["max_retries"]),
            "top_p": _maybe_float(model["models"]["generation"]["top_p"]),
            "seed": _maybe_int(model["models"]["generation"]["seed"]),
        }
    )
    pruning_payload = _strip_none_values(
        {
            "model": model["models"]["pruning"]["model"],
            "temperature": float(model["models"]["pruning"]["temperature"]),
            "max_tokens": int(model["models"]["pruning"]["max_tokens"]),
            "timeout_seconds": int(model["models"]["pruning"]["timeout_seconds"]),
            "max_retries": int(model["models"]["pruning"]["max_retries"]),
            "top_p": _maybe_float(model["models"]["pruning"]["top_p"]),
            "seed": _maybe_int(model["models"]["pruning"]["seed"]),
        }
    )
    embedding_payload = {
        "model": model["models"]["embedding"]["model"],
        "batch_size": int(model["models"]["embedding"]["batch_size"]),
        "cache_dir": model["models"]["embedding"]["cache_dir"],
        "rebuild_on_source_change": bool(model["models"]["embedding"]["rebuild_on_source_change"]),
        "query_prefix": model["models"]["embedding"]["query_prefix"],
        "document_prefix": model["models"]["embedding"]["document_prefix"],
    }

    return {
        "project": {
            "root_dir": model["project"]["root_dir"].strip() or ".",
            "bidder_name": model["project"]["bidder_name"],
            "inputs": project_inputs,
            "output_dir": model["project"]["output_dir"].strip() or "./output",
        },
        "writing": writing_payload,
        "processing": {
            "path": processing_path,
            "context_view": {
                "include_ancestors": bool(model["processing"]["context_view"]["include_ancestors"]),
                "include_siblings": bool(model["processing"]["context_view"]["include_siblings"]),
                "max_siblings": int(model["processing"]["context_view"]["max_siblings"]),
            },
            "project_background": {
                "enabled": bool(model["processing"]["project_background"]["enabled"]),
                "max_chars": int(model["processing"]["project_background"]["max_chars"]),
            },
            "auto": {
                "requirements_top_k": int(model["processing"]["auto"]["requirements_top_k"]),
            },
            "full_context": {
                "chapter_writing_plan": {
                    "enabled": bool(model["processing"]["full_context"]["chapter_writing_plan"]["enabled"]),
                    "max_chars": int(model["processing"]["full_context"]["chapter_writing_plan"]["max_chars"]),
                },
            },
            "hybrid_extract": {
                "unavailable_policy": "fail_fast",
                "scoring_parse_mode": model["processing"]["auto"]["scoring_parse_mode"],
                "scoring_max_rows": int(model["processing"]["auto"]["scoring_max_rows"]),
                "retrieval": {
                    "lexical_enabled": bool(model["processing"]["auto"]["retrieval"]["lexical_enabled"]),
                    "vector_enabled": bool(model["processing"]["auto"]["retrieval"]["vector_enabled"]),
                    "verify_enabled": False,
                    "top_k_lexical": int(model["processing"]["auto"]["retrieval"]["top_k_lexical"]),
                    "top_k_vector": 20,
                    "top_k_fused": int(model["processing"]["auto"]["retrieval"]["top_k_fused"]),
                    "top_k_final": int(model["processing"]["auto"]["retrieval"]["top_k_final"]),
                    "min_fused_score": float(model["processing"]["auto"]["retrieval"]["min_fused_score"]),
                },
                "quote_only": True,
                "return_ids_only": True,
                "verify_max_candidates": 8,
            },
        },
        "models": {
            "generation": generation_payload,
            "pruning": pruning_payload,
            "embedding": embedding_payload,
        },
        "runtime": {
            "stream": {
                "enabled": bool(model["runtime"]["stream"]["enabled"]),
                "idle_timeout_seconds": int(model["runtime"]["stream"]["idle_timeout_seconds"]),
            },
            "trace": {
                "enabled": bool(model["runtime"]["trace"]["enabled"]),
                "directory": model["runtime"]["trace"]["directory"],
                "mode": model["runtime"]["trace"]["mode"],
                "write_prompt": bool(model["runtime"]["trace"]["write_prompt"]),
                "write_output": bool(model["runtime"]["trace"]["write_output"]),
                "write_context": bool(model["runtime"]["trace"]["write_context"]),
                "write_summary": bool(model["runtime"]["trace"]["write_summary"]),
                "redact_sensitive": bool(model["runtime"]["trace"]["redact_sensitive"]),
            },
            "debug": {
                "context_pruning_dump": bool(model["runtime"]["debug"]["context_pruning_dump"]),
            },
            "output": {
                "prefix": model["runtime"]["output"]["prefix"],
                "include_title_header": bool(model["runtime"]["output"]["include_title_header"]),
                "overwrite_existing": bool(model["runtime"]["output"]["overwrite_existing"]),
                "filename_max_length": int(model["runtime"]["output"]["filename_max_length"]),
                "empty_filename_fallback": model["runtime"]["output"]["empty_filename_fallback"],
            },
            "merge": {
                "normalize_soft_line_breaks": bool(model["runtime"]["merge"]["normalize_soft_line_breaks"]),
            },
        },
    }


def validate_editor_model(
    model: dict[str, Any],
    config_path: Path,
    env_status: dict[str, ConnectionStatus],
    raw_config: dict[str, Any] | None = None,
    *,
    require_project_identity: bool = False,
) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []
    processing_path = model["processing"]["path"]
    if processing_path not in _SUPPORTED_PROCESSING_PATHS:
        messages.append(ValidationMessage("error", "processing.path 当前仅支持 auto / full_context 两种模式。"))

    root_dir = _resolve_path(model["project"]["root_dir"] or ".", config_path.parent)
    if not root_dir.exists():
        messages.append(ValidationMessage("error", f"project.root_dir 不存在：{root_dir}"))

    if require_project_identity and not _coerce_str(model["project"]["bidder_name"]).strip():
        messages.append(ValidationMessage("error", "投标主体名称不能为空。"))

    outline_path = _resolve_path(model["project"]["outline_file"] or "./outline.md", root_dir)
    if not outline_path.exists():
        messages.append(ValidationMessage("error", f"大纲文件不存在：{outline_path}"))

    for source_key, label in (("bid_requirements", "采购需求"), ("scoring_criteria", "评分标准")):
        mode = model["project"][f"{source_key}_mode"]
        if mode == "inline":
            if not _coerce_str(model["project"][f"{source_key}_text"]).strip():
                messages.append(ValidationMessage("error", f"{label} 当前为内嵌文本模式，但内容为空。"))
            else:
                messages.append(ValidationMessage("warning", f"{label} 当前以内嵌文本保存，推荐迁移为独立文件。"))
            continue

        file_value = _coerce_str(model["project"][f"{source_key}_file"]).strip()
        file_path = _resolve_path(file_value or f"./{source_key}.md", root_dir)
        if not file_path.exists():
            messages.append(ValidationMessage("error", f"{label}文件不存在：{file_path}"))

    role_mode = model["writing"]["role_mode"]
    if role_mode == "inline":
        if not _coerce_str(model["writing"]["role_text"]).strip():
            messages.append(ValidationMessage("error", "写作角色当前为内嵌文本模式，但内容为空。"))
    else:
        role_path = _resolve_path(model["writing"]["role_file"] or "./roles/example_role.md", config_path.parent)
        if not role_path.exists():
            messages.append(ValidationMessage("warning", f"role_file 当前不存在：{role_path}"))

    min_value = _coerce_int(model["writing"]["target_words_min"], default=100)
    default_value = _coerce_int(model["writing"]["target_words_default"], default=500)
    max_value = _coerce_int(model["writing"]["target_words_max"], default=15000)
    step_value = _coerce_int(model["writing"]["target_words_step"], default=100)
    upper_ratio_value = _coerce_float(model["writing"]["target_words_upper_ratio"], default=1.15)
    if not (min_value <= default_value <= max_value):
        messages.append(ValidationMessage("error", "target_words 配置需要满足 min <= default <= max。"))
    if step_value <= 0:
        messages.append(ValidationMessage("error", "target_words.step 必须大于 0。"))
    if upper_ratio_value < 1.0:
        messages.append(ValidationMessage("error", "target_words.upper_ratio 不能小于 1.0。"))
    if _coerce_int(model["writing"]["max_mermaid_flowcharts_per_section"], default=0) < 0:
        messages.append(ValidationMessage("error", "max_mermaid_flowcharts_per_section 不能小于 0。"))

    trace_dir = _resolve_path(model["runtime"]["trace"]["directory"] or "./log/generation_traces", config_path.parent)
    if trace_dir.exists() and not trace_dir.is_dir():
        messages.append(ValidationMessage("error", f"trace.directory 不是目录：{trace_dir}"))

    embedding_cache_dir = _resolve_path(model["models"]["embedding"]["cache_dir"] or "./output/_embedding_cache", config_path.parent)
    if embedding_cache_dir.exists() and not embedding_cache_dir.is_dir():
        messages.append(ValidationMessage("error", f"embedding.cache_dir 不是目录：{embedding_cache_dir}"))

    if processing_path in {"auto", "hybrid_extract"}:
        retrieval = model["processing"]["auto"]["retrieval"]
        if processing_path == "auto" and not env_status["pruning"].configured:
            messages.append(ValidationMessage("error", "auto 模式需要配置辅助模型（models.pruning），请在 .env.local 中设置 BID_WRITER_PRUNING_* 环境变量。"))
        if not retrieval["lexical_enabled"]:
            messages.append(ValidationMessage("error", f"{processing_path} 模式要求 lexical_enabled=true。"))
        if retrieval["vector_enabled"] and not env_status["embedding"].configured:
            messages.append(ValidationMessage("error", "启用 vector_enabled 时，必须先在 .env.local 中配置 embedding 连接信息。"))
    elif processing_path == "full_context":
        plan_max_chars = _coerce_int(
            model["processing"]["full_context"]["chapter_writing_plan"]["max_chars"],
            default=320,
        )
        if plan_max_chars <= 0:
            messages.append(ValidationMessage("error", "full_context.chapter_writing_plan.max_chars 必须大于 0。"))

    if not env_status["generation"].configured:
        messages.append(ValidationMessage("warning", "当前未检测到 generation 连接配置，保存后可能无法直接运行生成。"))

    messages.extend(
        ValidationMessage("info", note)
        for note in build_editor_notes(model, raw_config or {})
    )
    return messages


def summarize_model(model: dict[str, Any], env_status: dict[str, ConnectionStatus]) -> list[str]:
    lines = [
        f"processing.path = {model['processing']['path']}",
        (
            "章节写作计划 = "
            + ("开启" if model["processing"]["full_context"]["chapter_writing_plan"]["enabled"] else "关闭")
            if model["processing"]["path"] == "full_context"
            else "章节写作计划 = 不适用"
        ),
        f"投标主体 = {model['project']['bidder_name'] or '（未填写）'}",
        f"角色模式 = {'内嵌文本' if model['writing']['role_mode'] == 'inline' else 'role_file'}",
        f"流式输出 = {'开启' if model['runtime']['stream']['enabled'] else '关闭'}",
        f"trace = {'开启' if model['runtime']['trace']['enabled'] else '关闭'}",
        f"generation 连接 = {'已配置' if env_status['generation'].configured else '未配置'}",
        f"pruning 连接 = {'已配置' if env_status['pruning'].configured else '未配置'}",
        f"embedding 连接 = {'已配置' if env_status['embedding'].configured else '未配置'}",
    ]
    return lines


def detect_connection_status(config_path: Path, raw_config: dict[str, Any]) -> dict[str, ConnectionStatus]:
    file_env = _read_env_files(config_path.parent)

    def detect(keys: list[tuple[str, ...]], env_keys: list[str]) -> ConnectionStatus:
        has_raw = any(bool(_coerce_str(_get_value(raw_config, *path, default="")).strip()) for path in keys)
        if has_raw:
            return ConnectionStatus(True, "YAML")
        if any(bool(os.environ.get(key, "").strip()) for key in env_keys):
            return ConnectionStatus(True, "环境变量")
        if any(bool(file_env.get(key, "").strip()) for key in env_keys):
            return ConnectionStatus(True, ".env.local")
        return ConnectionStatus(False, "")

    return {
        "generation": detect(
            keys=[("models", "generation", "base_url"), ("models", "generation", "api_key"), ("api", "base_url"), ("api", "api_key")],
            env_keys=["BID_WRITER_API_BASE_URL", "BID_WRITER_API_KEY"],
        ),
        "pruning": detect(
            keys=[("models", "pruning", "base_url"), ("models", "pruning", "api_key"), ("context_pruning", "api", "base_url"), ("context_pruning", "api", "api_key")],
            env_keys=["BID_WRITER_PRUNING_API_BASE_URL", "BID_WRITER_PRUNING_API_KEY"],
        ),
        "embedding": detect(
            keys=[("models", "embedding", "base_url"), ("models", "embedding", "api_key"), ("context_pruning", "retrieval", "embedding", "base_url"), ("context_pruning", "retrieval", "embedding", "api_key")],
            env_keys=["BID_WRITER_EMBEDDING_API_BASE_URL", "BID_WRITER_EMBEDDING_API_KEY"],
        ),
    }


def extract_preserved_extra(raw_config: dict[str, Any]) -> dict[str, Any]:
    preserved = _extract_unmanaged(raw_config, _ROOT_MANAGED_SCHEMA)
    _merge_nested_extra(
        preserved,
        ("models", "generation"),
        _extract_unmanaged(_get_dict(raw_config, "api"), _LEGACY_API_MANAGED_SCHEMA),
    )
    _merge_nested_extra(
        preserved,
        ("models", "pruning"),
        _extract_unmanaged(_get_dict(raw_config, "context_pruning", "api"), _LEGACY_PRUNING_API_MANAGED_SCHEMA),
    )
    _merge_nested_extra(
        preserved,
        ("models", "embedding"),
        _extract_unmanaged(_get_dict(raw_config, "context_pruning", "retrieval", "embedding"), _LEGACY_EMBEDDING_MANAGED_SCHEMA),
    )
    _merge_nested_extra(
        preserved,
        ("runtime", "trace"),
        _extract_unmanaged(_get_dict(raw_config, "generation_trace"), _LEGACY_GENERATION_TRACE_MANAGED_SCHEMA),
    )
    return preserved


def merge_with_preserved(canonical: dict[str, Any], preserved: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(canonical)
    for key, value in preserved.items():
        if key not in merged:
            merged[key] = copy.deepcopy(value)
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_with_preserved(merged[key], value)
    return merged


def _extract_unmanaged(raw: Any, schema: Any) -> Any:
    if not isinstance(raw, dict):
        return {}
    if schema is True:
        return {}
    if not isinstance(schema, dict):
        return copy.deepcopy(raw)

    preserved: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in schema:
            preserved[key] = copy.deepcopy(value)
            continue
        child_schema = schema[key]
        if isinstance(value, dict) and isinstance(child_schema, dict):
            child_preserved = _extract_unmanaged(value, child_schema)
            if child_preserved:
                preserved[key] = child_preserved
    return preserved


def _derive_processing_path(raw_config: dict[str, Any]) -> str:
    configured = _get_value(raw_config, "processing", "path", default=_MISSING)
    if configured is not _MISSING:
        normalized = _coerce_str(configured).strip().lower()
        return normalized if normalized in _KNOWN_PROCESSING_PATHS else "full_context"

    enabled = _coerce_bool(_get_value(raw_config, "context_pruning", "enabled", default=False), default=False)
    if not enabled:
        return "full_context"

    base_mode = _normalize_mode(_get_value(raw_config, "context_pruning", "mode", default="legacy_rule"))
    scoring_mode = _normalize_mode(
        _get_value(raw_config, "context_pruning", "scoring", "mode", default=base_mode),
        default=base_mode,
    )
    requirements_mode = _normalize_mode(
        _get_value(raw_config, "context_pruning", "requirements", "mode", default=base_mode),
        default=base_mode,
    )
    if scoring_mode == requirements_mode:
        return scoring_mode
    return "mixed"


def _normalize_mode(value: Any, default: str = "legacy_rule") -> str:
    normalized = _coerce_str(value).strip().lower() if value is not None else default
    return normalized if normalized in {"legacy_rule", "hybrid_extract"} else default


def _normalize_text_source(
    *,
    inline_value: Any,
    file_value: Any,
    default_file: str,
    default_text: str = "",
) -> tuple[str, str, str]:
    file_path = _coerce_str(file_value).strip()
    if file_path:
        return "file", file_path, ""

    if inline_value in (None, ""):
        if default_text:
            return "inline", "", default_text
        return "file", default_file, ""

    inline_text = _coerce_str(inline_value)
    candidate = _extract_inline_path_candidate(inline_text)
    if candidate:
        return "file", candidate, ""
    return "inline", "", inline_text


def _extract_inline_path_candidate(inline_value: str) -> str | None:
    candidates: list[str] = []
    for raw_line in inline_value.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
            stripped = stripped[1:-1].strip()
        if stripped:
            candidates.append(stripped)
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    return candidate if _looks_like_path(candidate) else None


def _looks_like_path(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    if normalized.startswith(("~", "/", "./", "../")):
        return True
    if "/" in normalized or "\\" in normalized:
        return True
    if len(normalized) >= 2 and normalized[1] == ":":
        return True
    return bool(Path(normalized).suffix)


def _resolve_path(path_value: str, base_dir: Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _read_env_files(base_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in (".env", ".env.local"):
        env_path = base_dir / name
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_dotenv_line(line)
            if parsed is None:
                continue
            key, value = parsed
            result[key] = value
    return result


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export "):].strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _get_dict(data: dict[str, Any], *path: str) -> dict[str, Any]:
    value = _get_value(data, *path, default={})
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _get_value(data: dict[str, Any], *path: str, default: Any = _MISSING) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _first_defined(data: dict[str, Any], *paths: tuple[str, ...] | str, default: Any = None) -> Any:
    for path in paths:
        normalized = (path,) if isinstance(path, str) else path
        value = _get_value(data, *normalized, default=_MISSING)
        if value is not _MISSING:
            return value
    return default


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _maybe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_none_values(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _merge_nested_extra(target: dict[str, Any], path: tuple[str, ...], extra: dict[str, Any]) -> None:
    if not extra:
        return
    current = target
    for key in path[:-1]:
        current = current.setdefault(key, {})
    existing = current.setdefault(path[-1], {})
    if isinstance(existing, dict):
        current[path[-1]] = merge_with_preserved(existing, extra)


_ROOT_MANAGED_SCHEMA: dict[str, Any] = {
    "project": {
        "root_dir": True,
        "bidder_name": True,
        "inputs": {
            "outline_file": True,
            "bid_requirements": True,
            "bid_requirements_file": True,
            "scoring_criteria": True,
            "scoring_criteria_file": True,
        },
        "output_dir": True,
    },
    "writing": {
        "role": True,
        "role_file": True,
        "target_words": {
            "default": True,
            "min": True,
            "max": True,
            "step": True,
            "upper_ratio": True,
        },
        "output_format": True,
        "first_line_template": True,
        "allow_markdown_headings": True,
        "allow_english_terms": True,
        "max_tables_per_section": True,
        "max_mermaid_flowcharts_per_section": True,
        "summary_title": True,
        "hard_constraints": True,
        "extra_rules": True,
    },
    "processing": {
        "path": True,
        "context_view": {
            "include_ancestors": True,
            "include_siblings": True,
            "max_siblings": True,
        },
        "project_background": {
            "enabled": True,
            "max_chars": True,
            "cache_dir": True,
        },
        "auto": {
            "requirements_top_k": True,
        },
        "full_context": {
            "chapter_writing_plan": {
                "enabled": True,
                "max_chars": True,
                "cache_dir": True,
            },
        },
        "legacy_rule": {
            "scoring_max_rows": True,
            "requirements_max_quotes": True,
            "requirements_max_quote_chars": True,
            "requirement_brief_enabled": True,
            "requirement_brief_fallback": True,
        },
        "hybrid_extract": {
            "unavailable_policy": True,
            "scoring_parse_mode": True,
            "scoring_max_rows": True,
            "requirements_max_quotes": True,
            "requirements_max_quote_chars": True,
            "requirement_brief_enabled": True,
            "requirement_brief_fallback": True,
            "retrieval": {
                "lexical_enabled": True,
                "vector_enabled": True,
                "verify_enabled": True,
                "top_k_lexical": True,
                "top_k_vector": True,
                "top_k_fused": True,
                "top_k_final": True,
                "min_fused_score": True,
            },
            "quote_only": True,
            "return_ids_only": True,
            "verify_max_candidates": True,
        },
    },
    "models": {
        "generation": {
            "model": True,
            "temperature": True,
            "max_tokens": True,
            "timeout_seconds": True,
            "max_retries": True,
            "top_p": True,
            "seed": True,
        },
        "pruning": {
            "model": True,
            "temperature": True,
            "max_tokens": True,
            "timeout_seconds": True,
            "max_retries": True,
            "top_p": True,
            "seed": True,
        },
        "embedding": {
            "model": True,
            "batch_size": True,
            "cache_dir": True,
            "rebuild_on_source_change": True,
            "query_prefix": True,
            "document_prefix": True,
        },
    },
    "runtime": {
        "stream": {
            "enabled": True,
            "idle_timeout_seconds": True,
        },
        "trace": {
            "enabled": True,
            "directory": True,
            "mode": True,
            "write_prompt": True,
            "write_output": True,
            "write_context": True,
            "write_summary": True,
            "redact_sensitive": True,
        },
        "debug": {
            "context_pruning_dump": True,
        },
        "output": {
            "prefix": True,
            "include_title_header": True,
            "overwrite_existing": True,
            "filename_max_length": True,
            "empty_filename_fallback": True,
            "directory": True,
        },
        "merge": {
            "normalize_soft_line_breaks": True,
        },
    },
    "inputs": True,
    "output": True,
    "generation": True,
    "prompt": True,
    "context_pruning": True,
    "generation_trace": True,
    "api": True,
    "role": True,
    "role_file": True,
    "outline_file": True,
    "bid_requirements": True,
    "bid_requirements_file": True,
    "scoring_criteria": True,
    "scoring_criteria_file": True,
    "default_min_words": True,
    "min_words": True,
}

_LEGACY_API_MANAGED_SCHEMA: dict[str, Any] = {
    "model": True,
    "temperature": True,
    "max_tokens": True,
    "timeout_seconds": True,
    "max_retries": True,
    "top_p": True,
    "seed": True,
}

_LEGACY_PRUNING_API_MANAGED_SCHEMA: dict[str, Any] = {
    "model": True,
    "temperature": True,
    "max_tokens": True,
    "timeout_seconds": True,
    "max_retries": True,
    "top_p": True,
    "seed": True,
}

_LEGACY_EMBEDDING_MANAGED_SCHEMA: dict[str, Any] = {
    "model": True,
    "batch_size": True,
    "cache_dir": True,
    "rebuild_on_source_change": True,
    "query_prefix": True,
    "document_prefix": True,
}

_LEGACY_GENERATION_TRACE_MANAGED_SCHEMA: dict[str, Any] = {
    "enabled": True,
    "directory": True,
    "mode": True,
    "write_prompt": True,
    "write_output": True,
    "write_context": True,
    "write_summary": True,
    "redact_sensitive": True,
}
