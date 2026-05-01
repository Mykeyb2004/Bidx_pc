# Tender Chapter Boundary Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand tender section extraction so a matched “项目采购需求” or “评分标准” line widens to the smallest correct chapter span using external boundary rules in `roles/`, while keeping the current manual confirmation flow and falling back safely when chapter markers are weak.

**Architecture:** Add a tiny boundary-rule loader for `roles/tender_section_boundaries.yaml`, a boundary detector/resolver that works on converted blocks, and a thin integration layer inside `tender_section_extractor.py`. The resolver should prefer major chapter markers such as `第x章` and `第x部分`, fall back to subsection markers when needed, and downgrade to smaller spans when both target sections would otherwise collapse into the same major chapter.

**Tech Stack:** Python 3.10+, PyYAML, pytest, uv, existing tender conversion/extraction models.

---

## File Structure

- Create `roles/tender_section_boundaries.yaml`
  - Stores all chapter marker patterns and normalization flags as data.
- Create `bid_writer/tender_section_boundary_config.py`
  - Loads the YAML file, normalizes text for matching, and compiles regex rules.
- Create `bid_writer/tender_section_boundary_detector.py`
  - Detects boundary matches on converted blocks and resolves extraction spans.
- Modify `bid_writer/tender_section_extractor.py`
  - Uses the boundary resolver before building `TenderExtractionResult`.
- Create `tests/test_tender_section_boundary_config.py`
  - Covers config loading, normalization, and bad-rule handling.
- Create `tests/test_tender_section_boundary_detector.py`
  - Covers major/fallback boundary matching and span resolution.
- Modify `tests/test_tender_section_extractor.py`
  - Covers whole-chapter defaulting and same-chapter fallback behavior.

---

### Task 1: Add Boundary Config Loader

**Files:**
- Create: `roles/tender_section_boundaries.yaml`
- Create: `bid_writer/tender_section_boundary_config.py`
- Create: `tests/test_tender_section_boundary_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tender_section_boundary_config.py`:

```python
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
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
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
    pattern: "(?P<ordinal>"
    priority: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_boundary_config(boundary_file)

    assert config.major_markers == ()
    assert any("broken" in warning for warning in config.warnings)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_config.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_section_boundary_config'`.

- [ ] **Step 3: Implement the loader and config file**

Create `bid_writer/tender_section_boundary_config.py`:

```python
"""招标文件章节边界规则加载。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal

import yaml


DEFAULT_BOUNDARY_CONFIG_PATH = Path(__file__).resolve().parents[1] / "roles" / "tender_section_boundaries.yaml"


@dataclass(frozen=True)
class TenderSectionBoundaryRule:
    name: str
    kind: Literal["major", "fallback"]
    priority: int
    pattern: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class TenderSectionBoundaryMatch:
    block_id: str
    block_index: int
    kind: Literal["major", "fallback"]
    rule_name: str
    priority: int
    marker_text: str
    ordinal: str
    title: str
    normalized_text: str


@dataclass(frozen=True)
class TenderSectionBoundaryConfig:
    normalization: dict[str, bool] = field(default_factory=dict)
    major_markers: tuple[TenderSectionBoundaryRule, ...] = ()
    fallback_markers: tuple[TenderSectionBoundaryRule, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_boundary_text(
    text: str,
    *,
    strip_invisible: bool = True,
    collapse_space: bool = True,
) -> str:
    text = text.replace("\ufeff", "")
    if strip_invisible:
        text = re.sub(r"[\u200b-\u200f\u2060]", "", text)
    text = text.replace("\u3000", " ")
    if collapse_space:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_boundary_config(path: str | Path | None = None) -> TenderSectionBoundaryConfig:
    boundary_path = Path(path or DEFAULT_BOUNDARY_CONFIG_PATH).expanduser()
    if not boundary_path.exists():
        return TenderSectionBoundaryConfig(warnings=(f"章节边界配置不存在：{boundary_path}",))

    payload = yaml.safe_load(boundary_path.read_text(encoding="utf-8")) or {}
    warnings: list[str] = []
    major_markers = _load_rules(payload.get("major_markers", []), kind="major", warnings=warnings)
    fallback_markers = _load_rules(payload.get("fallback_markers", []), kind="fallback", warnings=warnings)
    normalization = dict(payload.get("normalization", {}) or {})
    return TenderSectionBoundaryConfig(
        normalization=normalization,
        major_markers=tuple(major_markers),
        fallback_markers=tuple(fallback_markers),
        warnings=tuple(warnings),
    )


def _load_rules(items: list[dict[str, object]], *, kind: Literal["major", "fallback"], warnings: list[str]) -> list[TenderSectionBoundaryRule]:
    rules: list[TenderSectionBoundaryRule] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        pattern = str(item.get("pattern", "")).strip()
        priority = int(item.get("priority", 0) or 0)
        if not name or not pattern:
            warnings.append(f"章节边界规则缺少 name 或 pattern：{item!r}")
            continue
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            warnings.append(f"章节边界规则 {name} 编译失败：{exc}")
            continue
        rules.append(
            TenderSectionBoundaryRule(
                name=name,
                kind=kind,
                priority=priority,
                pattern=pattern,
                regex=regex,
            )
        )
    return rules
```

Create `roles/tender_section_boundaries.yaml`:

```yaml
normalization:
  strip_invisible: true
  collapse_space: true
major_markers:
  - name: chapter
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
  - name: part
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*部分\\s*(?P<title>.*)"
    priority: 100
  - name: volume_or_book
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*[篇卷册]\\s*(?P<title>.*)"
    priority: 95
  - name: section
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*节\\s*(?P<title>.*)"
    priority: 85
  - name: appendix
    pattern: "附件\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９A-Za-zＡ-Ｚａ-ｚ]+)?\\s*[:：、.．]?\\s*(?P<title>.*)"
    priority: 85
  - name: appendix_table
    pattern: "附表\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９A-Za-zＡ-Ｚａ-ｚ]+)?\\s*[:：、.．]?\\s*(?P<title>.*)"
    priority: 85
  - name: package
    pattern: "(?:第\\s*)?(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*(?:包|标包|采购包)\\s*(?P<title>.*)"
    priority: 80
fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
    priority: 60
  - name: parenthesized
    pattern: "[（(]\\s*(?P<ordinal>[一二三四五六七八九十百千万0-9０-９]+)\\s*[）)]\\s*(?P<title>.+)"
    priority: 50
  - name: numeric
    pattern: "(?P<ordinal>[0-9０-９]+(?:\\s*[.．]\\s*[0-9０-９]+)*)\\s*[.．、]?\\s*(?P<title>.+)"
    priority: 45
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the config loader**

Run:

```bash
git add roles/tender_section_boundaries.yaml bid_writer/tender_section_boundary_config.py tests/test_tender_section_boundary_config.py
git commit -m "feat: add tender section boundary config"
```

Expected: commit succeeds.

---

### Task 2: Add Boundary Detector and Span Resolver

**Files:**
- Create: `bid_writer/tender_section_boundary_detector.py`
- Create: `tests/test_tender_section_boundary_detector.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tender_section_boundary_detector.py`:

```python
from pathlib import Path

from bid_writer.tender_import_models import ConvertedBlock
from bid_writer.tender_section_boundary_config import load_boundary_config
from bid_writer.tender_section_boundary_detector import detect_boundary_matches, resolve_extraction_spans


def _block(block_id: str, text: str, order: int, *, block_type: str = "paragraph", heading_level: int | None = None) -> ConvertedBlock:
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type=block_type,
        markdown=text,
        text=text,
        order_index=order,
        heading_level=heading_level,
        heading_title=text if heading_level else "",
    )


def test_detects_major_marker_from_noisy_text(tmp_path: Path):
    boundary_file = tmp_path / "tender_section_boundaries.yaml"
    boundary_file.write_text(
        """
major_markers:
  - name: chapter
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
    priority: 60
""".strip(),
        encoding="utf-8",
    )
    config = load_boundary_config(boundary_file)
    blocks = [_block("c5", "第\u200b五　章   项目采购需求", 1, heading_level=None)]

    matches = detect_boundary_matches(blocks, config)

    assert matches[0].kind == "major"
    assert matches[0].rule_name == "chapter"
    assert matches[0].ordinal == "五"
    assert "项目采购需求" in matches[0].title


def test_resolve_extraction_spans_prefers_whole_major_chapter_when_targets_are_in_separate_chapters(tmp_path: Path):
    boundary_file = tmp_path / "tender_section_boundaries.yaml"
    boundary_file.write_text(
        """
major_markers:
  - name: chapter
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
    priority: 60
""".strip(),
        encoding="utf-8",
    )
    config = load_boundary_config(boundary_file)
    blocks = [
        _block("chapter5", "第五章 采购需求", 1, heading_level=2),
        _block("req", "本项目服务内容包括调查、分析、成果提交和验收。", 2),
        _block("chapter6", "第六章 评分标准", 3, heading_level=2),
        _block("score", "| 评分项 | 分值 |\\n| --- | --- |\\n| 服务 | 10分 |", 4, block_type="table"),
        _block("chapter7", "第七章 合同条款", 5, heading_level=2),
    ]

    matches = detect_boundary_matches(blocks, config)
    requirements_span, scoring_span, warnings = resolve_extraction_spans(
        blocks=blocks,
        matches=matches,
        requirements_candidate_index=1,
        scoring_candidate_index=3,
    )

    assert requirements_span is not None
    assert requirements_span.start_block_id == "chapter5"
    assert requirements_span.end_block_id == "req"
    assert scoring_span is not None
    assert scoring_span.start_block_id == "chapter6"
    assert scoring_span.end_block_id == "score"
    assert warnings == ()


def test_resolve_extraction_spans_falls_back_to_minor_sections_when_both_targets_share_one_major_chapter(tmp_path: Path):
    boundary_file = tmp_path / "tender_section_boundaries.yaml"
    boundary_file.write_text(
        """
major_markers:
  - name: chapter
    pattern: "第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)"
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: "(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)"
    priority: 60
""".strip(),
        encoding="utf-8",
    )
    config = load_boundary_config(boundary_file)
    blocks = [
        _block("chapter5", "第五章 招标要求", 1, heading_level=2),
        _block("req_title", "一、项目采购需求", 2, heading_level=None),
        _block("req_body", "采购需求正文。", 3),
        _block("score_title", "二、评分标准", 4, heading_level=None),
        _block("score_body", "| 评分项 | 分值 |\\n| --- | --- |\\n| 服务 | 10分 |", 5, block_type="table"),
        _block("chapter6", "第六章 其他条款", 6, heading_level=2),
    ]

    matches = detect_boundary_matches(blocks, config)
    requirements_span, scoring_span, warnings = resolve_extraction_spans(
        blocks=blocks,
        matches=matches,
        requirements_candidate_index=2,
        scoring_candidate_index=4,
    )

    assert requirements_span is not None
    assert requirements_span.start_block_id == "req_title"
    assert requirements_span.end_block_id == "req_body"
    assert scoring_span is not None
    assert scoring_span.start_block_id == "score_title"
    assert scoring_span.end_block_id == "score_body"
    assert any("同一大章节" in warning for warning in warnings)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_detector.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_section_boundary_detector'`.

- [ ] **Step 3: Implement the detector and resolver**

Create `bid_writer/tender_section_boundary_detector.py`:

```python
"""招标文件章节边界检测与章节范围解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .tender_import_models import ConvertedBlock
from .tender_section_boundary_config import (
    TenderSectionBoundaryConfig,
    TenderSectionBoundaryMatch,
    normalize_boundary_text,
)


@dataclass(frozen=True)
class TenderSectionBoundarySpan:
    section_key: str
    kind: Literal["major", "fallback"]
    start_index: int
    end_index: int
    start_block_id: str
    end_block_id: str
    rule_name: str
    boundary_block_id: str


def detect_boundary_matches(blocks: list[ConvertedBlock], config: TenderSectionBoundaryConfig) -> list[TenderSectionBoundaryMatch]:
    ...


def resolve_extraction_spans(
    *,
    blocks: list[ConvertedBlock],
    matches: list[TenderSectionBoundaryMatch],
    requirements_candidate_index: int | None,
    scoring_candidate_index: int | None,
) -> tuple[TenderSectionBoundarySpan | None, TenderSectionBoundarySpan | None, tuple[str, ...]]:
    ...
```

Implementation requirements:

- Match on a normalized shadow string only.
- Keep original block markdown untouched.
- Prefer `major` markers before `fallback` markers.
- When both target sections resolve to the same major chapter, downgrade both to their fallback spans if those spans exist; otherwise keep the best available span and emit a warning.
- Keep span boundaries inclusive in `start_block_id` / `end_block_id` and exclusive in `start_index` / `end_index` so the extractor can slice blocks directly.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_detector.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the detector**

Run:

```bash
git add bid_writer/tender_section_boundary_detector.py tests/test_tender_section_boundary_detector.py
git commit -m "feat: detect tender section boundary spans"
```

Expected: commit succeeds.

---

### Task 3: Wire Boundary Spans into Tender Extraction

**Files:**
- Modify: `bid_writer/tender_section_extractor.py`
- Modify: `tests/test_tender_section_extractor.py`

- [ ] **Step 1: Write the failing extractor tests**

Add these tests to `tests/test_tender_section_extractor.py`:

```python
def test_extracts_whole_major_chapter_for_requirements_and_scoring():
    conversion = _conversion(
        [
            _heading("chapter5", "第五章 项目采购需求", 1),
            _paragraph("req_body", "本项目服务内容包括调查、分析、成果提交和验收。", 2),
            _heading("chapter6", "第六章 评分标准", 3),
            _table("score_body", "| 评分项 | 分值 |\\n| --- | --- |\\n| 服务 | 10分 |", 4),
            _heading("chapter7", "第七章 合同条款", 5),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.start_block_id == "chapter5"
    assert result.requirements.end_block_id == "req_body"
    assert result.scoring is not None
    assert result.scoring.start_block_id == "chapter6"
    assert result.scoring.end_block_id == "score_body"


def test_extracts_minor_sections_when_both_targets_share_one_major_chapter():
    conversion = _conversion(
        [
            _heading("chapter5", "第五章 招标要求", 1),
            _paragraph("req_title", "一、项目采购需求", 2),
            _paragraph("req_body", "采购需求正文。", 3),
            _paragraph("score_title", "二、评分标准", 4),
            _table("score_body", "| 评分项 | 分值 |\\n| --- | --- |\\n| 服务 | 10分 |", 5),
            _heading("chapter6", "第六章 其他条款", 6),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.start_block_id == "req_title"
    assert result.requirements.end_block_id == "req_body"
    assert result.scoring is not None
    assert result.scoring.start_block_id == "score_title"
    assert result.scoring.end_block_id == "score_body"
    assert any("同一大章节" in warning for warning in result.warnings)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_section_extractor.py -q
```

Expected: FAIL because the extractor still only uses the current heading/stop-word logic and cannot expand by external boundary config.

- [ ] **Step 3: Integrate the boundary loader and resolver**

Update `bid_writer/tender_section_extractor.py` so `extract_tender_sections()`:

```python
boundary_config = load_boundary_config()
candidates = _collect_candidates(blocks)
boundary_matches = detect_boundary_matches(blocks, boundary_config)
requirements_span, scoring_span, boundary_warnings = resolve_extraction_spans(
    blocks=blocks,
    matches=boundary_matches,
    requirements_candidate_index=_candidate_index_for("bid_requirements", candidates, blocks),
    scoring_candidate_index=_candidate_index_for("scoring_criteria", candidates, blocks),
)
```

Then build each `TenderExtractionResult` from the returned span instead of the current `_adjust_start_index()` / `_find_end_index()` path.

Keep the existing candidate scoring, alias matching, confidence calculation, and TOC filtering intact. Only replace the section span resolution.

- [ ] **Step 4: Run focused tests and the full suite**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_config.py tests/test_tender_section_boundary_detector.py tests/test_tender_section_extractor.py -q
```

Expected: PASS.

Then run:

```bash
uv run pytest -q
```

Expected: PASS with the full project suite still green.

- [ ] **Step 5: Commit the extractor integration**

Run:

```bash
git add bid_writer/tender_section_extractor.py tests/test_tender_section_extractor.py
git commit -m "feat: widen tender extraction by chapter boundaries"
```

Expected: commit succeeds.

---

### Task 4: Final Verification

**Files:**
- None new; verify the committed changes only.

- [ ] **Step 1: Run the chapter-boundary focused suite again**

Run:

```bash
uv run pytest tests/test_tender_section_boundary_config.py tests/test_tender_section_boundary_detector.py tests/test_tender_section_extractor.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Review the diff**

Run:

```bash
git diff --stat
git status --short
```

Expected: only the new boundary config file, two new boundary modules, extractor updates, and the new/updated tests are present.
