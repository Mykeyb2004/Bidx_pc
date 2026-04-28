# H2 Project Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend-first H2-scoped project background pipeline for `processing.path: auto`, with evidence-backed cache generation, prompt injection, trace visibility, and batch precompute.

**Architecture:** Keep global `ProjectBackgroundGenerator` for `full_context` and compatibility. Add `bid_writer/h2_project_background.py` for H2 discovery, evidence retrieval, summary cache, fallback, and trace payloads; wire it through `AIWriter` and `BidWriter` so auto chapters read H2 summaries while full-context chapters keep global summaries.

**Tech Stack:** Python 3.13, uv, pytest, existing `SourceUnitParser`, `HybridRetriever`, `EmbeddingStore`, `LLMVerifier`, OpenAI-compatible pruning/generation clients.

---

## Scope

This plan implements the core backend slice only:

- Config schema and defaults for `processing.project_background.scope` and `processing.project_background.h2`.
- H2 result/report data classes and JSON cache.
- H2 evidence retrieval and summary generation.
- Auto prompt injection of H2 background, with global fallback.
- Batch precompute entry point on `BidWriter`.
- Trace/context summary metadata.
- Docs and example config updates.

The GUI management window, background task queue, stop/retry UI, and H2 status badges are intentionally left for a later UI-specific plan.

## Files

- Create: `bid_writer/h2_project_background.py`
- Create: `tests/test_h2_project_background.py`
- Modify: `bid_writer/config.py`
- Modify: `bid_writer/ai_writer.py`
- Modify: `bid_writer/generation_trace.py`
- Modify: `bid_writer/main.py`
- Modify: `tests/test_config_schema.py`
- Modify: `tests/test_prompt_contract.py`
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `docs/generation_trace.md`
- Modify: `docs/extraction_modes_and_config.md`
- Modify: `config.example.yaml`
- Modify: `config_公共服务满意度_auto.yaml`

---

### Task 1: Config Surface

**Files:**
- Modify: `bid_writer/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing config tests**

Append these tests to `tests/test_config_schema.py`:

```python
def test_h2_project_background_config_defaults_to_global_for_old_shape(tmp_path: Path):
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

    assert config.project_background_scope == "global"
    assert config.h2_project_background_enabled is False
    assert config.h2_project_background_precompute_on_batch is True
    assert config.h2_project_background_generate_missing_on_single is True
    assert config.h2_project_background_max_evidence_blocks == 6
    assert config.h2_project_background_max_evidence_chars == 2400
    assert config.h2_project_background_include_evidence_in_prompt is False
    assert config.h2_project_background_min_evidence_blocks == 2
    assert config.h2_project_background_fallback == "global"
    assert config.h2_project_background_cache_dir == str(tmp_path / "caches" / "project_background_h2")


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
      include_evidence_in_prompt: true
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
    assert config.h2_project_background_include_evidence_in_prompt is True
    assert config.h2_project_background_min_evidence_blocks == 1
    assert config.h2_project_background_fallback == "raw_evidence"
    assert config.h2_project_background_cache_dir == str(project_root / "cache" / "h2-bg")
```

- [ ] **Step 2: Run config tests and verify RED**

Run:

```bash
uv run pytest tests/test_config_schema.py::test_h2_project_background_config_defaults_to_global_for_old_shape tests/test_config_schema.py::test_h2_project_background_config_reads_new_h2_auto_scope -q
```

Expected: FAIL because `Config` does not yet expose the new H2 project background properties.

- [ ] **Step 3: Implement config properties**

In `bid_writer/config.py`, near the existing project background properties, add:

```python
    @property
    def project_background_scope(self) -> str:
        """项目背景作用域：global 或 h2_auto。"""
        value = self._get_first_defined(
            ('processing', 'project_background', 'scope'),
            default='global',
        )
        normalized = str(value).strip().lower() if value is not None else 'global'
        return normalized if normalized in {'global', 'h2_auto'} else 'global'

    @property
    def h2_project_background_enabled(self) -> bool:
        """auto 模式下是否启用 H2 级项目背景。"""
        return bool(
            self.project_background_enabled
            and self.processing_path == 'auto'
            and self.project_background_scope == 'h2_auto'
        )

    @property
    def h2_project_background_precompute_on_batch(self) -> bool:
        return self._get_bool(
            ('processing', 'project_background', 'h2', 'precompute_on_batch'),
            default=True,
        )

    @property
    def h2_project_background_generate_missing_on_single(self) -> bool:
        return self._get_bool(
            ('processing', 'project_background', 'h2', 'generate_missing_on_single'),
            default=True,
        )

    @property
    def h2_project_background_max_evidence_blocks(self) -> int:
        return self._get_int(
            ('processing', 'project_background', 'h2', 'max_evidence_blocks'),
            default=6,
        )

    @property
    def h2_project_background_max_evidence_chars(self) -> int:
        return self._get_int(
            ('processing', 'project_background', 'h2', 'max_evidence_chars'),
            default=2400,
        )

    @property
    def h2_project_background_include_evidence_in_prompt(self) -> bool:
        return self._get_bool(
            ('processing', 'project_background', 'h2', 'include_evidence_in_prompt'),
            default=False,
        )

    @property
    def h2_project_background_min_evidence_blocks(self) -> int:
        return self._get_int(
            ('processing', 'project_background', 'h2', 'min_evidence_blocks'),
            default=2,
        )

    @property
    def h2_project_background_fallback(self) -> str:
        value = self._get_first_defined(
            ('processing', 'project_background', 'h2', 'fallback'),
            default='global',
        )
        normalized = str(value).strip().lower() if value is not None else 'global'
        return normalized if normalized in {'global', 'raw_evidence', 'empty'} else 'global'

    @property
    def h2_project_background_cache_dir(self) -> str:
        value = self._get_value('processing', 'project_background', 'h2', 'cache_dir', default=self._MISSING)
        if value is not self._MISSING:
            return self._resolve_declared_path(
                value,
                resolver=self._resolve_project_path,
                default=str(self._resolve_project_path('./caches/project_background_h2')),
            )
        return str(self._resolve_project_path('./caches/project_background_h2'))
```

- [ ] **Step 4: Run config tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_config_schema.py::test_h2_project_background_config_defaults_to_global_for_old_shape tests/test_config_schema.py::test_h2_project_background_config_reads_new_h2_auto_scope -q
```

Expected: PASS.

---

### Task 2: H2 Result Models, H2 Discovery, Cache Key, and Cache IO

**Files:**
- Create: `bid_writer/h2_project_background.py`
- Create: `tests/test_h2_project_background.py`

- [ ] **Step 1: Write failing model/cache tests**

Create `tests/test_h2_project_background.py` with:

```python
import json
from pathlib import Path

from bid_writer.config import Config
from bid_writer.h2_project_background import H2ProjectBackgroundGenerator
from bid_writer.outline_parser import parse_outline


def _write_config(tmp_path: Path, *, requirements: str = "项目需求") -> Config:
    (tmp_path / "outline.md").write_text("# 项目\n## 项目理解\n### 现状分析\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text(requirements, encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
  output_dir: "./output"

processing:
  path: "auto"
  project_background:
    enabled: true
    scope: "h2_auto"
    max_chars: 500
    h2:
      cache_dir: "./cache/h2-bg"
      max_evidence_blocks: 3
      max_evidence_chars: 1200
      min_evidence_blocks: 1
""".strip(),
        encoding="utf-8",
    )
    return Config(str(config_path))


def test_h2_generator_finds_h2_ancestor_and_collects_h2_nodes(tmp_path: Path):
    config = _write_config(tmp_path)
    parser = parse_outline(
        "# 项目\n"
        "## 项目理解\n"
        "### 现状分析\n"
        "#### 政策背景\n"
        "## 服务方案\n"
        "### 工作流程\n"
    )
    generator = H2ProjectBackgroundGenerator(config)
    leaf = parser.find_heading_by_title("政策背景")
    assert leaf is not None

    h2 = generator.find_h2_ancestor(leaf)
    h2_nodes = generator.collect_h2_nodes(parser)

    assert h2.title == "项目理解"
    assert [node.full_path for node in h2_nodes] == ["项目 > 项目理解", "项目 > 服务方案"]


def test_h2_generator_cache_key_changes_when_subtree_changes(tmp_path: Path):
    config = _write_config(tmp_path)
    generator = H2ProjectBackgroundGenerator(config)
    parser_a = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    parser_b = parse_outline("# 项目\n## 项目理解\n### 现状分析\n### 服务边界\n")
    h2_a = parser_a.find_heading_by_title("项目理解")
    h2_b = parser_b.find_heading_by_title("项目理解")
    assert h2_a is not None and h2_b is not None

    key_a = generator.cache_key_for_h2(h2_a)
    key_b = generator.cache_key_for_h2(h2_b)

    assert key_a != key_b


def test_h2_generator_writes_and_reads_json_cache(tmp_path: Path):
    config = _write_config(tmp_path)
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    h2 = parser.find_heading_by_title("项目理解")
    assert h2 is not None
    generator = H2ProjectBackgroundGenerator(config)
    result = generator.build_result(
        h2=h2,
        summary="围绕项目理解形成背景。",
        evidence_unit_ids=["requirements_0"],
        evidence_blocks=["项目需求原文"],
        cache_status="miss",
    )

    generator.write_cache(result)
    cached = generator.read_cache(h2)
    cache_files = list((tmp_path / "cache" / "h2-bg").glob("h2_*.json"))

    assert cached is not None
    assert cached.cache_status == "hit"
    assert cached.summary == "围绕项目理解形成背景。"
    assert cached.evidence_unit_ids == ["requirements_0"]
    assert cached.evidence_blocks == ["项目需求原文"]
    assert cached.h2_full_path == "项目 > 项目理解"
    assert len(cache_files) == 1
    payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["h2_full_path"] == "项目 > 项目理解"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_h2_project_background.py::test_h2_generator_finds_h2_ancestor_and_collects_h2_nodes tests/test_h2_project_background.py::test_h2_generator_cache_key_changes_when_subtree_changes tests/test_h2_project_background.py::test_h2_generator_writes_and_reads_json_cache -q
```

Expected: FAIL because `bid_writer.h2_project_background` does not exist.

- [ ] **Step 3: Implement data classes, discovery, hashing, and cache IO**

Create `bid_writer/h2_project_background.py` with:

```python
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from .config import Config
from .embedding_store import EmbeddingStore
from .hybrid_retriever import HybridRetriever
from .llm_verifier import LLMVerifier
from .outline_parser import HeadingNode, OutlineParser
from .retrieval_models import RetrievedUnit
from .source_unit_parser import SourceUnitParser


PROMPT_VERSION = "h2-project-background-v1"


@dataclass
class H2ProjectBackgroundResult:
    h2_title: str
    h2_full_path: str
    summary: str
    evidence_unit_ids: list[str]
    evidence_blocks: list[str]
    source_hash: str
    subtree_hash: str
    cache_status: str
    fallback_reason: str = ""
    model: str = ""
    created_at: str = ""
    prompt_version: str = PROMPT_VERSION
    precomputed: bool = False

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "scope": "h2",
            "h2_title": self.h2_title,
            "h2_full_path": self.h2_full_path,
            "summary_chars": len(self.summary),
            "evidence_unit_ids": list(self.evidence_unit_ids),
            "evidence_blocks": list(self.evidence_blocks),
            "evidence_count": len(self.evidence_blocks),
            "cache_status": self.cache_status,
            "fallback_reason": self.fallback_reason,
            "precomputed": self.precomputed,
        }


@dataclass
class H2ProjectBackgroundPrecomputeReport:
    total_h2: int
    generated: int = 0
    cache_hits: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[H2ProjectBackgroundResult] = field(default_factory=list)


class H2ProjectBackgroundGenerator:
    """生成并缓存 auto 模式 H2 级项目背景。"""

    def __init__(self, config: Config):
        self.config = config
        self.source_unit_parser = SourceUnitParser()
        self.hybrid_retriever = HybridRetriever()
        self.embedding_store = EmbeddingStore(config) if config.embedding_is_configured else None
        self.llm_verifier = LLMVerifier(config) if config.pruning_api_is_configured else None
        self._lock = threading.Lock()

    @staticmethod
    def find_h2_ancestor(heading: HeadingNode) -> HeadingNode:
        current: Optional[HeadingNode] = heading
        while current is not None:
            if current.level == 2:
                return current
            current = current.parent
        return heading.parent if heading.parent is not None else heading

    @staticmethod
    def collect_h2_nodes(outline: OutlineParser | HeadingNode | list[HeadingNode]) -> list[HeadingNode]:
        if isinstance(outline, OutlineParser):
            nodes = outline.get_all_headings()
        elif isinstance(outline, HeadingNode):
            nodes = []

            def visit(node: HeadingNode) -> None:
                nodes.append(node)
                for child in node.children:
                    visit(child)

            visit(outline)
        else:
            nodes = list(outline)
        return [node for node in nodes if node.level == 2]

    @staticmethod
    def _sha1(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def source_hash(self) -> str:
        return self._sha1(self.config.bid_requirements.strip())

    def subtree_hash(self, h2: HeadingNode) -> str:
        lines: list[str] = []

        def visit(node: HeadingNode) -> None:
            lines.append(f"{node.level}:{node.full_path}")
            for child in node.children:
                visit(child)

        visit(h2)
        return self._sha1("\n".join(lines))

    def retrieval_fingerprint(self) -> str:
        parts = [
            f"top_k_lexical={self.config.context_pruning_retrieval_top_k_lexical}",
            f"top_k_vector={self.config.context_pruning_retrieval_top_k_vector}",
            f"top_k_fused={self.config.context_pruning_retrieval_top_k_fused}",
            f"min_fused_score={self.config.context_pruning_retrieval_min_fused_score}",
            f"vector={self.config.context_pruning_retrieval_vector_enabled}",
            f"verify={self.config.context_pruning_rerank_or_verify_enabled}",
        ]
        return self._sha1("|".join(parts))[:16]

    def cache_key_for_h2(self, h2: HeadingNode) -> str:
        model = self._model_name()
        key_input = "|".join(
            [
                self.source_hash(),
                h2.full_path,
                self.subtree_hash(h2),
                str(self.config.project_background_max_chars),
                str(self.config.h2_project_background_max_evidence_blocks),
                str(self.config.h2_project_background_max_evidence_chars),
                self.retrieval_fingerprint(),
                PROMPT_VERSION,
                model,
            ]
        )
        return self._sha1(key_input)[:20]

    def cache_path_for_h2(self, h2: HeadingNode) -> Path:
        return Path(self.config.h2_project_background_cache_dir) / f"h2_{self.cache_key_for_h2(h2)}.json"

    def build_result(
        self,
        *,
        h2: HeadingNode,
        summary: str,
        evidence_unit_ids: list[str],
        evidence_blocks: list[str],
        cache_status: str,
        fallback_reason: str = "",
        precomputed: bool = False,
    ) -> H2ProjectBackgroundResult:
        return H2ProjectBackgroundResult(
            h2_title=h2.title,
            h2_full_path=h2.full_path,
            summary=summary.strip(),
            evidence_unit_ids=list(evidence_unit_ids),
            evidence_blocks=list(evidence_blocks),
            source_hash=self.source_hash(),
            subtree_hash=self.subtree_hash(h2),
            cache_status=cache_status,
            fallback_reason=fallback_reason,
            model=self._model_name(),
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            precomputed=precomputed,
        )

    def read_cache(self, h2: HeadingNode) -> Optional[H2ProjectBackgroundResult]:
        cache_path = self.cache_path_for_h2(h2)
        try:
            if not cache_path.exists():
                return None
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            result = H2ProjectBackgroundResult(
                h2_title=str(data.get("h2_title") or h2.title),
                h2_full_path=str(data.get("h2_full_path") or h2.full_path),
                summary=str(data.get("summary") or "").strip(),
                evidence_unit_ids=[str(item) for item in data.get("evidence_unit_ids") or []],
                evidence_blocks=[str(item) for item in data.get("evidence_blocks") or []],
                source_hash=str(data.get("source_hash") or ""),
                subtree_hash=str(data.get("subtree_hash") or ""),
                cache_status="hit",
                fallback_reason=str(data.get("fallback_reason") or ""),
                model=str(data.get("model") or ""),
                created_at=str(data.get("created_at") or ""),
                prompt_version=str(data.get("prompt_version") or PROMPT_VERSION),
                precomputed=bool(data.get("precomputed", False)),
            )
            if not result.summary:
                return None
            return result
        except Exception:
            return None

    def write_cache(self, result: H2ProjectBackgroundResult) -> None:
        cache_path = self.cache_path_for_result(result)
        payload = asdict(result)
        payload["version"] = 1
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(cache_path)
        except OSError:
            pass

    def cache_path_for_result(self, result: H2ProjectBackgroundResult) -> Path:
        key_input = "|".join(
            [
                result.source_hash,
                result.h2_full_path,
                result.subtree_hash,
                str(self.config.project_background_max_chars),
                str(self.config.h2_project_background_max_evidence_blocks),
                str(self.config.h2_project_background_max_evidence_chars),
                self.retrieval_fingerprint(),
                result.prompt_version,
                result.model,
            ]
        )
        return Path(self.config.h2_project_background_cache_dir) / f"h2_{self._sha1(key_input)[:20]}.json"

    def _model_name(self) -> str:
        if self.config.pruning_api_is_configured:
            return self.config.pruning_model
        return self.config.model
```

Leave retrieval/generation methods for the next task.

- [ ] **Step 4: Run model/cache tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_h2_project_background.py::test_h2_generator_finds_h2_ancestor_and_collects_h2_nodes tests/test_h2_project_background.py::test_h2_generator_cache_key_changes_when_subtree_changes tests/test_h2_project_background.py::test_h2_generator_writes_and_reads_json_cache -q
```

Expected: PASS.

---

### Task 3: Evidence Retrieval, Summary Generation, Fallback, and Precompute

**Files:**
- Modify: `bid_writer/h2_project_background.py`
- Modify: `tests/test_h2_project_background.py`

- [ ] **Step 1: Write failing retrieval/precompute tests**

Append:

```python
def test_h2_background_uses_requirement_evidence_only_and_precomputes_all_h2(tmp_path: Path, monkeypatch):
    requirements = (
        "# 采购需求\n"
        "项目理解要求说明政策背景、建设目标和现状问题。\n\n"
        "项目理解还应覆盖需求边界、服务对象和项目痛点。\n\n"
        "服务方案要求说明实施流程、质量检查和交付安排。\n"
    )
    config = _write_config(tmp_path, requirements=requirements)
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 1
    config._config["processing"]["project_background"]["h2"]["max_evidence_blocks"] = 2
    parser = parse_outline(
        "# 项目\n"
        "## 项目理解\n"
        "### 现状分析\n"
        "## 服务方案\n"
        "### 实施流程\n"
    )
    generator = H2ProjectBackgroundGenerator(config)
    prompts: list[str] = []

    def fake_compute(h2, evidence_blocks):
        prompts.append("\n".join(evidence_blocks))
        return f"{h2.title}摘要：{evidence_blocks[0][:12]}"

    monkeypatch.setattr(generator, "_compute_summary", fake_compute)

    report = generator.precompute_all(parser)

    assert report.total_h2 == 2
    assert report.generated == 2
    assert report.cache_hits == 0
    assert report.failed == 0
    assert [result.h2_title for result in report.results] == ["项目理解", "服务方案"]
    assert all(result.evidence_blocks for result in report.results)
    assert any("项目理解要求" in prompt for prompt in prompts)
    assert any("服务方案要求" in prompt for prompt in prompts)


def test_h2_background_falls_back_when_evidence_is_insufficient(tmp_path: Path, monkeypatch):
    config = _write_config(tmp_path, requirements="完全无关的采购需求。")
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 2
    config._config["processing"]["project_background"]["h2"]["fallback"] = "raw_evidence"
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    h2 = parser.find_heading_by_title("项目理解")
    assert h2 is not None
    generator = H2ProjectBackgroundGenerator(config)
    monkeypatch.setattr(generator, "_compute_summary", lambda h2, evidence_blocks: "不应调用")

    result = generator.get_or_generate(h2)

    assert result.cache_status == "fallback"
    assert "证据片段不足" in result.fallback_reason
    assert result.summary == "完全无关的采购需求。"
    assert result.evidence_blocks == ["完全无关的采购需求。"]


def test_h2_background_generate_missing_false_returns_empty_fallback(tmp_path: Path):
    config = _write_config(tmp_path, requirements="项目理解要求说明政策背景。")
    config._config["processing"]["project_background"]["h2"]["generate_missing_on_single"] = False
    config._config["processing"]["project_background"]["h2"]["fallback"] = "empty"
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    heading = parser.find_heading_by_title("现状分析")
    assert heading is not None
    generator = H2ProjectBackgroundGenerator(config)

    result = generator.get_for_heading(heading)

    assert result.cache_status == "fallback"
    assert result.summary == ""
    assert "缓存缺失" in result.fallback_reason
```

- [ ] **Step 2: Run retrieval/precompute tests and verify RED**

Run:

```bash
uv run pytest tests/test_h2_project_background.py -q
```

Expected: FAIL because `precompute_all`, `get_for_heading`, `get_or_generate`, and retrieval/generation methods are not implemented.

- [ ] **Step 3: Implement retrieval, generation, fallback, and precompute**

Add these methods to `H2ProjectBackgroundGenerator`:

```python
    def precompute_all(self, outline: OutlineParser | HeadingNode | list[HeadingNode]) -> H2ProjectBackgroundPrecomputeReport:
        h2_nodes = self.collect_h2_nodes(outline)
        report = H2ProjectBackgroundPrecomputeReport(total_h2=len(h2_nodes))
        for h2 in h2_nodes:
            result = self.get_or_generate(h2, precomputed=True)
            report.results.append(result)
            if result.cache_status == "hit":
                report.cache_hits += 1
            elif result.cache_status == "generated":
                report.generated += 1
            elif result.cache_status in {"failed", "fallback"}:
                report.failed += 1 if not result.summary else 0
        return report

    def get_for_heading(self, heading: HeadingNode) -> H2ProjectBackgroundResult:
        h2 = self.find_h2_ancestor(heading)
        cached = self.read_cache(h2)
        if cached is not None:
            return cached
        if not self.config.h2_project_background_generate_missing_on_single:
            return self._fallback_result(h2, "缓存缺失且未启用单章节补生成")
        return self.get_or_generate(h2)

    def get_or_generate(self, h2: HeadingNode, *, precomputed: bool = False) -> H2ProjectBackgroundResult:
        cached = self.read_cache(h2)
        if cached is not None:
            cached.precomputed = precomputed or cached.precomputed
            return cached

        with self._lock:
            cached = self.read_cache(h2)
            if cached is not None:
                cached.precomputed = precomputed or cached.precomputed
                return cached
            try:
                evidence_hits = self.retrieve_evidence(h2)
                evidence_unit_ids = [hit.unit.unit_id for hit in evidence_hits]
                evidence_blocks = self._trim_evidence_blocks(
                    [hit.unit.source_text_exact or hit.unit.source_text for hit in evidence_hits]
                )
                if len(evidence_blocks) < self.config.h2_project_background_min_evidence_blocks:
                    return self._fallback_result(
                        h2,
                        f"证据片段不足：{len(evidence_blocks)} < {self.config.h2_project_background_min_evidence_blocks}",
                        evidence_unit_ids=evidence_unit_ids,
                        evidence_blocks=evidence_blocks,
                    )
                summary = self._compute_summary(h2, evidence_blocks)
                if not summary.strip():
                    return self._fallback_result(
                        h2,
                        "摘要生成为空",
                        evidence_unit_ids=evidence_unit_ids,
                        evidence_blocks=evidence_blocks,
                    )
                result = self.build_result(
                    h2=h2,
                    summary=summary,
                    evidence_unit_ids=evidence_unit_ids,
                    evidence_blocks=evidence_blocks,
                    cache_status="generated",
                    precomputed=precomputed,
                )
                self.write_cache(result)
                return result
            except Exception as exc:
                return self._fallback_result(h2, f"{type(exc).__name__}: {exc}")

    def retrieve_evidence(self, h2: HeadingNode) -> list[RetrievedUnit]:
        text = self.config.bid_requirements.strip()
        if not text:
            return []
        units = self.source_unit_parser.parse_requirements(text)
        if not units:
            return []
        query_text = self.build_h2_query(h2)
        focus_terms = self._collect_h2_titles(h2)
        hits = self.hybrid_retriever.retrieve(
            query_text,
            units,
            response_labels=[h2.title],
            keywords=focus_terms,
            focus_terms=focus_terms,
            top_k_lexical=self.config.context_pruning_retrieval_top_k_lexical,
            top_k_vector=self.config.context_pruning_retrieval_top_k_vector,
            top_k_fused=self.config.context_pruning_retrieval_top_k_fused,
            embedding_store=self.embedding_store if self.config.context_pruning_retrieval_vector_enabled else None,
        )
        selected_hits = self.hybrid_retriever.select_final(
            hits,
            top_k_final=self.config.h2_project_background_max_evidence_blocks,
            min_score=self.config.context_pruning_retrieval_min_fused_score,
        )
        if not selected_hits and units:
            selected_hits = [RetrievedUnit(unit=unit, lexical_score=0.0, fused_score=0.0) for unit in units[:1]]
        return selected_hits

    def build_h2_query(self, h2: HeadingNode) -> str:
        child_titles = self._collect_h2_titles(h2, include_self=False)
        parts = [
            f"H2 标题：{h2.title}",
            f"H2 路径：{h2.full_path}",
            f"H2 子树标题：{'；'.join(child_titles)}",
            f"重点词：{'；'.join(self._collect_h2_titles(h2))}",
        ]
        return "\n".join(part for part in parts if part.strip())

    def _collect_h2_titles(self, h2: HeadingNode, *, include_self: bool = True, limit: int = 20) -> list[str]:
        titles: list[str] = []

        def add(title: str) -> None:
            normalized = title.strip()
            if normalized and normalized not in titles:
                titles.append(normalized)

        def visit(node: HeadingNode) -> None:
            if len(titles) >= limit:
                return
            if include_self or node is not h2:
                add(node.title)
            for child in node.children:
                visit(child)

        visit(h2)
        return titles[:limit]

    def _trim_evidence_blocks(self, blocks: list[str]) -> list[str]:
        max_total = max(self.config.h2_project_background_max_evidence_chars, 0)
        trimmed: list[str] = []
        used = 0
        for block in blocks[: self.config.h2_project_background_max_evidence_blocks]:
            text = block.strip()
            if not text:
                continue
            remaining = max_total - used if max_total else len(text)
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining].rstrip()
            trimmed.append(text)
            used += len(text)
        return trimmed

    def _fallback_result(
        self,
        h2: HeadingNode,
        reason: str,
        *,
        evidence_unit_ids: Optional[list[str]] = None,
        evidence_blocks: Optional[list[str]] = None,
    ) -> H2ProjectBackgroundResult:
        fallback = self.config.h2_project_background_fallback
        blocks = evidence_blocks or []
        summary = ""
        if fallback == "raw_evidence" and blocks:
            summary = "\n\n".join(blocks[:3])
        elif fallback == "raw_evidence" and self.config.bid_requirements.strip():
            summary = self.config.bid_requirements.strip()[: self.config.project_background_max_chars]
            blocks = [summary]
        return self.build_result(
            h2=h2,
            summary=summary,
            evidence_unit_ids=evidence_unit_ids or [],
            evidence_blocks=blocks,
            cache_status="fallback",
            fallback_reason=reason,
        )

    def _compute_summary(self, h2: HeadingNode, evidence_blocks: list[str]) -> str:
        prompt = self._build_summary_prompt(h2, evidence_blocks)
        client, model = self._get_client_and_model()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=self.config.project_background_max_chars * 2,
            messages=[
                {
                    "role": "system",
                    "content": "你是招标文件分析助手，只能依据给定原文片段提炼背景。",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        if self.config.pruning_api_is_configured:
            client = OpenAI(
                base_url=self.config.pruning_api_base_url,
                api_key=self.config.pruning_api_key,
                timeout=self.config.pruning_timeout_seconds,
                max_retries=self.config.pruning_max_retries,
            )
            return client, self.config.pruning_model
        client = OpenAI(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        return client, self.config.model

    def _build_summary_prompt(self, h2: HeadingNode, evidence_blocks: list[str]) -> str:
        evidence_text = "\n\n".join(f"[证据{i + 1}]\n{block}" for i, block in enumerate(evidence_blocks))
        return (
            "请仅基于给定采购需求原文片段，提炼当前 H2 章节的项目背景。\n\n"
            f"H2 标题：{h2.title}\n"
            f"H2 路径：{h2.full_path}\n"
            f"H2 子树标题：{'；'.join(self._collect_h2_titles(h2, include_self=False))}\n"
            f"输出长度：约 {self.config.project_background_max_chars} 字以内\n\n"
            "必须覆盖：\n"
            "1. 与本 H2 相关的项目目标或问题来源\n"
            "2. 与本 H2 相关的任务范围\n"
            "3. 与本 H2 相关的主要交付物或成果\n"
            "4. 与本 H2 相关的质量、合规、时限或验收要求\n"
            "5. 本 H2 下章节扩写时不可遗漏的关键信息\n\n"
            "限制：\n"
            "- 不得引入原文没有的信息。\n"
            "- 不要写成评分响应清单。\n"
            "- 不要覆盖其他 H2 的职责范围。\n"
            "- 如果证据片段不足以支持某项内容，省略该项，不要编造。\n"
            "- 直接输出摘要正文，不要输出引导语。\n\n"
            "采购需求原文片段：\n"
            f"{evidence_text}"
        )
```

- [ ] **Step 4: Run H2 generator tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_h2_project_background.py -q
```

Expected: PASS.

---

### Task 4: Prompt Injection and Global Compatibility

**Files:**
- Modify: `bid_writer/ai_writer.py`
- Modify: `tests/test_prompt_contract.py`

- [ ] **Step 1: Write failing prompt tests**

Append to `tests/test_prompt_contract.py`:

```python
def test_auto_prompt_uses_h2_project_background(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "auto"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    monkeypatch.setattr(
        writer.context_pruner,
        "build_context",
        lambda _: ChapterContext(
            chapter_focus_terms=["质量保障措施"],
            requirement_seed="质量保障应建立过程检查机制。",
            retrieval_mode="path=auto;vector=off;classify=off",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    class DummyH2BackgroundGenerator:
        @staticmethod
        def get_for_heading(_heading):
            from bid_writer.h2_project_background import H2ProjectBackgroundResult

            return H2ProjectBackgroundResult(
                h2_title="项目实施方案",
                h2_full_path="综合服务项目投标方案 > 项目实施方案",
                summary="H2专属背景摘要。",
                evidence_unit_ids=["requirements_0"],
                evidence_blocks=["采购需求证据片段"],
                source_hash="source",
                subtree_hash="tree",
                cache_status="hit",
                precomputed=True,
            )

    writer.h2_project_background_generator = DummyH2BackgroundGenerator()
    writer.project_background_generator = type(
        "DummyGlobalBackground",
        (),
        {"get_or_generate": staticmethod(lambda: "全局背景不应进入 auto h2 prompt。")},
    )()

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "## 项目背景" in result.prompt
    assert "H2专属背景摘要。" in result.prompt
    assert "全局背景不应进入 auto h2 prompt。" not in result.prompt
    block = next(block for block in result.prompt_contract_blocks if block["id"] == "project_background")
    assert "H2ProjectBackgroundGenerator.get_for_heading" in block["source_context"]
    assert result.project_background_trace["h2_title"] == "项目实施方案"
    assert result.project_background_trace["cache_status"] == "hit"


def test_full_context_prompt_keeps_global_project_background_when_h2_scope_configured(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "full_context"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)
    writer.project_background_generator = type(
        "DummyGlobalBackground",
        (),
        {"get_or_generate": staticmethod(lambda: "全局项目背景摘要。")},
    )()
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "全局项目背景摘要。" in result.prompt
    block = next(block for block in result.prompt_contract_blocks if block["id"] == "project_background")
    assert "ProjectBackgroundGenerator.get_or_generate" in block["source_context"]
    assert result.project_background_trace["scope"] == "global"
```

- [ ] **Step 2: Run prompt tests and verify RED**

Run:

```bash
uv run pytest tests/test_prompt_contract.py::test_auto_prompt_uses_h2_project_background tests/test_prompt_contract.py::test_full_context_prompt_keeps_global_project_background_when_h2_scope_configured -q
```

Expected: FAIL because `AIWriter` does not create/use H2 generator and `PromptBuildResult` has no `project_background_trace`.

- [ ] **Step 3: Wire H2 background into `AIWriter`**

In `bid_writer/ai_writer.py`:

1. Import:

```python
from .h2_project_background import H2ProjectBackgroundGenerator
```

2. Add `project_background_trace` to `PromptBuildResult`:

```python
    project_background_trace: dict[str, Any] = field(default_factory=dict)
```

3. In `AIWriter.__init__`, add:

```python
        self.h2_project_background_generator = (
            H2ProjectBackgroundGenerator(config)
            if config.h2_project_background_enabled
            else None
        )
```

4. Replace current background retrieval in `build_prompt_result()` with a mode-aware flow:

```python
        background = ""
        project_background_trace: dict[str, Any] = {}
        try:
            if pruned_context is not None and self.h2_project_background_generator is not None:
                if status_callback is not None:
                    status_callback("整理H2项目背景", "正在整理当前H2项目背景...")
                h2_background = self.h2_project_background_generator.get_for_heading(heading)
                background = h2_background.summary
                project_background_trace = h2_background.to_trace_payload()
                if (
                    not background
                    and self.project_background_generator is not None
                    and self.config.h2_project_background_fallback == "global"
                ):
                    background = self.project_background_generator.get_or_generate()
                    project_background_trace = {
                        "scope": "global",
                        "cache_status": "fallback",
                        "fallback_reason": h2_background.fallback_reason,
                        "summary_chars": len(background),
                    }
            elif self.project_background_generator is not None:
                if status_callback is not None:
                    status_callback("整理项目背景", "正在整理项目背景...")
                background = self.project_background_generator.get_or_generate()
                if background:
                    project_background_trace = {
                        "scope": "global",
                        "summary_chars": len(background),
                        "cache_status": "unknown",
                    }
        except Exception:
            background = ""
            project_background_trace = {}
```

5. Update `_build_prompt_contract_blocks()` signature to accept `project_background_trace`.

6. In the project background block source context, use:

```python
                    (
                        "H2ProjectBackgroundGenerator.get_for_heading"
                        if project_background_trace.get("scope") == "h2"
                        else "ProjectBackgroundGenerator.get_or_generate"
                    )
                    if "project_background" in section_map else "",
```

7. Pass `project_background_trace` into `_build_prompt_contract_blocks()` and the returned `PromptBuildResult`.

- [ ] **Step 4: Run prompt tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_prompt_contract.py::test_auto_prompt_uses_h2_project_background tests/test_prompt_contract.py::test_full_context_prompt_keeps_global_project_background_when_h2_scope_configured -q
```

Expected: PASS.

---

### Task 5: Trace Payload and Summary

**Files:**
- Modify: `bid_writer/generation_trace.py`
- Modify: `bid_writer/ai_writer.py`
- Modify: `tests/test_prompt_contract.py`

- [ ] **Step 1: Write failing trace test**

Append:

```python
def test_trace_records_h2_project_background_evidence(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "auto"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    monkeypatch.setattr(
        writer.context_pruner,
        "build_context",
        lambda _: ChapterContext(
            chapter_focus_terms=["质量保障措施"],
            requirement_seed="质量保障应建立过程检查机制。",
            requirement_blocks=[],
            retrieval_mode="path=auto;vector=off;classify=off",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    class DummyH2BackgroundGenerator:
        @staticmethod
        def get_for_heading(_heading):
            from bid_writer.h2_project_background import H2ProjectBackgroundResult

            return H2ProjectBackgroundResult(
                h2_title="项目实施方案",
                h2_full_path="综合服务项目投标方案 > 项目实施方案",
                summary="H2专属背景摘要。",
                evidence_unit_ids=["requirements_7"],
                evidence_blocks=["采购需求证据片段"],
                source_hash="source",
                subtree_hash="tree",
                cache_status="hit",
                precomputed=True,
            )

    writer.h2_project_background_generator = DummyH2BackgroundGenerator()

    prepared = writer.prepare_generation(heading, target_words=1200, stream=False)
    assert prepared.trace_session is not None
    prepared.trace_session.finalize("测试正文")

    context_payload = json.loads(
        prepared.trace_session.artifact_paths["context_assembly"].read_text(encoding="utf-8")
    )
    summary = prepared.trace_session.artifact_paths["summary"].read_text(encoding="utf-8")

    assert context_payload["project_background"]["scope"] == "h2"
    assert context_payload["project_background"]["h2_title"] == "项目实施方案"
    assert context_payload["project_background"]["evidence_unit_ids"] == ["requirements_7"]
    assert context_payload["project_background"]["evidence_blocks"] == ["采购需求证据片段"]
    assert "- project_background_scope: h2" in summary
    assert "- project_background_h2: 项目实施方案" in summary
    assert "- project_background_evidence_blocks: 1" in summary
    assert "- project_background_cache_status: hit" in summary
```

- [ ] **Step 2: Run trace test and verify RED**

Run:

```bash
uv run pytest tests/test_prompt_contract.py::test_trace_records_h2_project_background_evidence -q
```

Expected: FAIL because `GenerationTraceSession` does not accept or serialize project background trace metadata.

- [ ] **Step 3: Pass project background trace through trace logger**

In `bid_writer/generation_trace.py`:

1. Add `project_background_trace: dict[str, Any]` to `GenerationTraceSession.__init__` and assign it.
2. Add `project_background_trace` to `GenerationTraceLogger.start_session()` and pass it into the session.
3. In `_build_context_payload()`, add:

```python
        if self.project_background_trace:
            payload["project_background"] = self.project_background_trace
```

4. In `_build_summary()`, add:

```python
        if self.project_background_trace:
            lines.extend(
                [
                    f"- project_background_scope: {self.project_background_trace.get('scope', '（无）')}",
                    f"- project_background_h2: {self.project_background_trace.get('h2_title', '（无）')}",
                    f"- project_background_chars: {self.project_background_trace.get('summary_chars', 0)}",
                    f"- project_background_evidence_blocks: {self.project_background_trace.get('evidence_count', 0)}",
                    f"- project_background_cache_status: {self.project_background_trace.get('cache_status', '（无）')}",
                ]
            )
```

In `bid_writer/ai_writer.py`, pass `prompt_result.project_background_trace` into `start_session()`.

- [ ] **Step 4: Run trace test and verify GREEN**

Run:

```bash
uv run pytest tests/test_prompt_contract.py::test_trace_records_h2_project_background_evidence -q
```

Expected: PASS.

---

### Task 6: BidWriter Batch Precompute Entry Point

**Files:**
- Modify: `bid_writer/main.py`
- Modify: `tests/test_h2_project_background.py`

- [ ] **Step 1: Write failing precompute service test**

Append:

```python
def test_bid_writer_precompute_h2_project_backgrounds_uses_loaded_outline(tmp_path: Path, monkeypatch):
    requirements = (
        "项目理解要求说明政策背景和现状问题。\n\n"
        "服务方案要求说明实施流程和交付安排。\n"
    )
    config = _write_config(tmp_path, requirements=requirements)
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 1
    from bid_writer.main import BidWriter

    writer = BidWriter(str(config.config_path))
    assert writer.load_outline() is True
    monkeypatch.setattr(
        writer.ai_writer.h2_project_background_generator,
        "_compute_summary",
        lambda h2, evidence_blocks: f"{h2.title}摘要",
    )

    report = writer.precompute_h2_project_backgrounds()

    assert report.total_h2 == 1
    assert report.generated == 1
    assert report.results[0].h2_title == "项目理解"
```

- [ ] **Step 2: Run service test and verify RED**

Run:

```bash
uv run pytest tests/test_h2_project_background.py::test_bid_writer_precompute_h2_project_backgrounds_uses_loaded_outline -q
```

Expected: FAIL because `BidWriter.precompute_h2_project_backgrounds()` is not implemented.

- [ ] **Step 3: Implement `BidWriter.precompute_h2_project_backgrounds()`**

In `bid_writer/main.py` import:

```python
from .h2_project_background import H2ProjectBackgroundPrecomputeReport
```

Add to `BidWriter`:

```python
    def precompute_h2_project_backgrounds(self) -> H2ProjectBackgroundPrecomputeReport:
        """批量生成前预计算 auto 模式 H2 项目背景。"""
        generator = self.ai_writer.h2_project_background_generator
        if (
            generator is None
            or not self.config.h2_project_background_enabled
            or not self.config.h2_project_background_precompute_on_batch
        ):
            return H2ProjectBackgroundPrecomputeReport(total_h2=0, skipped=0)
        if self.parser is None:
            if not self.load_outline():
                raise RuntimeError(self.last_error_message or "请先加载大纲")
        assert self.parser is not None
        return generator.precompute_all(self.parser)
```

- [ ] **Step 4: Run service test and verify GREEN**

Run:

```bash
uv run pytest tests/test_h2_project_background.py::test_bid_writer_precompute_h2_project_backgrounds_uses_loaded_outline -q
```

Expected: PASS.

---

### Task 7: Docs and Example Configs

**Files:**
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `docs/generation_trace.md`
- Modify: `docs/extraction_modes_and_config.md`
- Modify: `config.example.yaml`
- Modify: `config_公共服务满意度_auto.yaml`

- [ ] **Step 1: Update example configs**

In both YAML files, under `processing.project_background`, include:

```yaml
    enabled: true
    scope: "h2_auto"
    max_chars: 800
    h2:
      precompute_on_batch: true
      generate_missing_on_single: true
      max_evidence_blocks: 6
      max_evidence_chars: 2400
      include_evidence_in_prompt: false
      min_evidence_blocks: 2
      fallback: "global"
      cache_dir: "./caches/project_background_h2"
```

If an example is intended for `full_context`, keep `scope: "global"` and omit or comment the H2 block.

- [ ] **Step 2: Update config schema docs**

Document:

- `processing.project_background.scope`: `global` or `h2_auto`; default `global` for old configs.
- `processing.project_background.h2.precompute_on_batch`.
- `generate_missing_on_single`.
- `max_evidence_blocks`.
- `max_evidence_chars`.
- `include_evidence_in_prompt`.
- `min_evidence_blocks`.
- `fallback`: `global`, `raw_evidence`, `empty`.
- `cache_dir`.

- [ ] **Step 3: Update prompt contract and trace docs**

In `docs/prompt_contract.md`, describe that `project_background` may come from `ProjectBackgroundGenerator.get_or_generate` or `H2ProjectBackgroundGenerator.get_for_heading`.

In `docs/generation_trace.md`, document the new `project_background` payload and `07_summary.md` fields.

In `docs/extraction_modes_and_config.md`, document `auto` mode H2 background behavior and that full-context remains global.

- [ ] **Step 4: Run docs/config related tests**

Run:

```bash
uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -q
```

Expected: PASS.

---

### Task 8: Final Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run targeted suites**

Run:

```bash
uv run pytest tests/test_h2_project_background.py tests/test_config_schema.py tests/test_prompt_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run regression suites from the optimization plan**

Run:

```bash
uv run pytest tests/test_chapter_fact_store.py tests/test_fact_card_prompt.py -q
uv run python -m compileall bid_writer run.py tests
```

Expected: PASS and compileall exits 0.

- [ ] **Step 3: Run full suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Review working tree**

Run:

```bash
git status --short
```

Expected: only planned files changed.

---

## Self-Review

- Spec coverage: This plan covers backend H2 summary generation, caching, fallback, prompt injection, trace metadata, batch precompute, docs, and config examples. UI management window and threaded progress are intentionally deferred.
- Placeholder scan: No `TBD`, `TODO`, or vague "add tests" steps remain; tests and commands are explicit.
- Type consistency: `H2ProjectBackgroundResult`, `H2ProjectBackgroundPrecomputeReport`, `project_background_trace`, and config property names are consistent across tasks.
