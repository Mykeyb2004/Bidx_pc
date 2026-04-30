# Tender Document Import Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new-config-only import flow that converts one Word/PDF/Excel tender document to Markdown, extracts the original “项目采购需求” and “评分标准” sections, writes them to project Markdown files, and fills the new configuration form paths.

**Architecture:** Keep import work upstream of the existing generation pipeline. Add focused modules for import dataclasses, Markdown conversion, section extraction, service orchestration, and a small confirmation dialog; wire the service into `ConfigEditorDialog` only when `new_config=True`.

**Tech Stack:** Python 3.10+, Tkinter/ttk, PyYAML, PyMuPDF/PyMuPDF4LLM, python-docx, openpyxl, pandas/tabulate, RapidFuzz, optional python-calamine and LibreOffice, pytest, uv.

---

## File Structure

- Create `bid_writer/tender_import_models.py`
  - Defines conversion, extraction, write, and report dataclasses.
  - Owns JSON serialization helpers for `conversion_map.json` and `extraction_report.json`.

- Create `bid_writer/tender_section_extractor.py`
  - Consumes `TenderConversionResult`.
  - Finds section boundaries for `bid_requirements` and `scoring_criteria`.
  - Produces extract results, confidence scores, warnings, and candidate reports.

- Create `bid_writer/tender_markdown_converter.py`
  - Converts exactly one source file to `ConvertedBlock` objects and `converted.md`.
  - Supports `.pdf`, `.docx`, `.xlsx`, `.doc`, `.xls`.
  - Rejects `.wps` and `.et`.
  - Does not perform OCR.

- Create `bid_writer/tender_import_service.py`
  - Orchestrates conversion, extraction, target file backup/write, and report output.
  - Keeps UI-free behavior testable.

- Create `bid_writer/tender_import_dialog.py`
  - Provides a small confirmation dialog for low-confidence extracts.
  - Exposes a pure helper for preview text so most behavior can be unit tested without Tk.

- Modify `bid_writer/config_editor_dialog.py`
  - Adds a new-config-only “从招标文件导入...” button in the project input section.
  - Calls `TenderImportService`.
  - Updates form variables after import succeeds.
  - Uses file-open dialog with single selection only.

- Modify `bid_writer/config_editor_tooltips.py`
  - Adds tooltip text for the import button/status.

- Modify `pyproject.toml` and `uv.lock`
  - Adds runtime dependencies.

- Modify `README.md`
  - Documents the new import flow and supported formats.

- Modify `docs/config_schema.md`
  - Documents that import writes existing `project.inputs.*` files and does not add schema fields.

- Create `tests/test_tender_import_models.py`
- Create `tests/test_tender_section_extractor.py`
- Create `tests/test_tender_markdown_converter.py`
- Create `tests/test_tender_import_service.py`
- Create `tests/test_config_editor_tender_import.py`
- Modify `tests/test_config_editor_dialog.py`

---

### Task 1: Add Runtime Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add dependencies with uv**

Run:

```bash
uv add pymupdf pymupdf4llm python-docx openpyxl pandas tabulate rapidfuzz python-calamine
```

Expected: `pyproject.toml` and `uv.lock` update successfully. If `python-calamine` is unavailable for the current platform, rerun without it and keep `.xls` support via LibreOffice fallback:

```bash
uv add pymupdf pymupdf4llm python-docx openpyxl pandas tabulate rapidfuzz
```

- [ ] **Step 2: Verify importable packages**

Run:

```bash
uv run python -c "import fitz, pymupdf4llm, docx, openpyxl, pandas, rapidfuzz; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit dependency update**

Run:

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add tender import dependencies"
```

Expected: commit succeeds.

---

### Task 2: Add Tender Import Data Models

**Files:**
- Create: `bid_writer/tender_import_models.py`
- Test: `tests/test_tender_import_models.py`

- [ ] **Step 1: Write failing tests for JSON serialization and report shape**

Create `tests/test_tender_import_models.py`:

```python
from pathlib import Path

from bid_writer.tender_import_models import (
    ConvertedBlock,
    SectionCandidate,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
    dump_conversion_map,
    dump_extraction_report,
)


def test_dump_conversion_map_serializes_blocks(tmp_path: Path):
    result = TenderConversionResult(
        source_path=tmp_path / "tender.docx",
        output_dir=tmp_path / ".bid_writer" / "imports" / "import-1",
        converted_markdown_path=tmp_path / ".bid_writer" / "imports" / "import-1" / "converted.md",
        conversion_map_path=tmp_path / ".bid_writer" / "imports" / "import-1" / "conversion_map.json",
        blocks=[
            ConvertedBlock(
                block_id="docx:p0001",
                source_file="tender.docx",
                source_type="docx",
                block_type="heading",
                markdown="## 项目采购需求",
                text="项目采购需求",
                order_index=1,
                heading_level=2,
                heading_title="项目采购需求",
                paragraph_index=1,
            )
        ],
        warnings=("converted",),
    )

    payload = dump_conversion_map(result)

    assert payload["source_path"].endswith("tender.docx")
    assert payload["warnings"] == ["converted"]
    assert payload["blocks"][0]["block_id"] == "docx:p0001"
    assert payload["blocks"][0]["heading_level"] == 2


def test_dump_extraction_report_serializes_results_and_candidates(tmp_path: Path):
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult(
            section_key="bid_requirements",
            title="项目采购需求",
            markdown="# 项目采购需求\n\n正文",
            start_block_id="b1",
            end_block_id="b3",
            confidence=0.91,
        ),
        scoring=TenderExtractionResult(
            section_key="scoring_criteria",
            title="评分标准",
            markdown="# 评分标准\n\n表格",
            start_block_id="b4",
            end_block_id="b7",
            confidence=0.87,
            warnings=("命中评分表",),
        ),
        candidates=[
            SectionCandidate(
                section_key="scoring_criteria",
                block_id="b4",
                title="评分标准",
                score=120.0,
                reason="exact_alias",
            )
        ],
        warnings=("ok",),
    )

    payload = dump_extraction_report(extraction)

    assert payload["requirements"]["confidence"] == 0.91
    assert payload["scoring"]["warnings"] == ["命中评分表"]
    assert payload["candidates"][0]["reason"] == "exact_alias"
    assert payload["warnings"] == ["ok"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_import_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_import_models'`.

- [ ] **Step 3: Implement dataclasses and dump helpers**

Create `bid_writer/tender_import_models.py`:

```python
"""招标文件导入、转换和章节抽取的数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConvertedBlock:
    block_id: str
    source_file: str
    source_type: str
    block_type: str
    markdown: str
    text: str
    order_index: int
    heading_level: int | None = None
    heading_title: str = ""
    page_number: int | None = None
    sheet_name: str = ""
    cell_range: str = ""
    paragraph_index: int | None = None
    table_index: int | None = None


@dataclass(frozen=True)
class TenderConversionResult:
    source_path: Path
    output_dir: Path
    converted_markdown_path: Path
    conversion_map_path: Path
    blocks: list[ConvertedBlock]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionCandidate:
    section_key: str
    block_id: str
    title: str
    score: float
    reason: str
    order_index: int = 0


@dataclass(frozen=True)
class TenderExtractionResult:
    section_key: str
    title: str
    markdown: str
    start_block_id: str
    end_block_id: str
    confidence: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TenderSectionExtraction:
    requirements: TenderExtractionResult | None = None
    scoring: TenderExtractionResult | None = None
    candidates: list[SectionCandidate] = field(default_factory=list)
    warnings: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.requirements is not None and self.scoring is not None

    @property
    def needs_confirmation(self) -> bool:
        results = [item for item in (self.requirements, self.scoring) if item is not None]
        return any(item.confidence < 0.80 for item in results)


def _json_path(path: Path) -> str:
    return path.as_posix()


def _block_to_dict(block: ConvertedBlock) -> dict[str, Any]:
    return asdict(block)


def _result_to_dict(result: TenderExtractionResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    payload = asdict(result)
    payload["warnings"] = list(result.warnings)
    return payload


def dump_conversion_map(result: TenderConversionResult) -> dict[str, Any]:
    return {
        "source_path": _json_path(result.source_path),
        "output_dir": _json_path(result.output_dir),
        "converted_markdown_path": _json_path(result.converted_markdown_path),
        "conversion_map_path": _json_path(result.conversion_map_path),
        "warnings": list(result.warnings),
        "blocks": [_block_to_dict(block) for block in result.blocks],
    }


def dump_extraction_report(extraction: TenderSectionExtraction) -> dict[str, Any]:
    return {
        "requirements": _result_to_dict(extraction.requirements),
        "scoring": _result_to_dict(extraction.scoring),
        "candidates": [asdict(candidate) for candidate in extraction.candidates],
        "warnings": list(extraction.warnings),
        "complete": extraction.is_complete,
        "needs_confirmation": extraction.needs_confirmation,
    }
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/test_tender_import_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit models**

Run:

```bash
git add bid_writer/tender_import_models.py tests/test_tender_import_models.py
git commit -m "feat: add tender import models"
```

Expected: commit succeeds.

---

### Task 3: Implement Section Extraction From Converted Blocks

**Files:**
- Create: `bid_writer/tender_section_extractor.py`
- Test: `tests/test_tender_section_extractor.py`

- [ ] **Step 1: Write failing extractor tests**

Create `tests/test_tender_section_extractor.py`:

```python
from pathlib import Path

from bid_writer.tender_import_models import ConvertedBlock, TenderConversionResult
from bid_writer.tender_section_extractor import extract_tender_sections


def _conversion(blocks: list[ConvertedBlock]) -> TenderConversionResult:
    return TenderConversionResult(
        source_path=Path("tender.md"),
        output_dir=Path(".bid_writer/imports/import-1"),
        converted_markdown_path=Path(".bid_writer/imports/import-1/converted.md"),
        conversion_map_path=Path(".bid_writer/imports/import-1/conversion_map.json"),
        blocks=blocks,
    )


def _heading(block_id: str, title: str, order: int, level: int = 2) -> ConvertedBlock:
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type="heading",
        markdown=f"{'#' * level} {title}",
        text=title,
        order_index=order,
        heading_level=level,
        heading_title=title,
    )


def _paragraph(block_id: str, text: str, order: int) -> ConvertedBlock:
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type="paragraph",
        markdown=text,
        text=text,
        order_index=order,
    )


def _table(block_id: str, markdown: str, order: int) -> ConvertedBlock:
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type="table",
        markdown=markdown,
        text=markdown,
        order_index=order,
    )


def test_extracts_requirements_and_scoring_by_heading_boundaries():
    conversion = _conversion(
        [
            _heading("h1", "目录", 1),
            _paragraph("toc1", "项目采购需求 ........ 12", 2),
            _paragraph("toc2", "评分标准 ........ 26", 3),
            _heading("h2", "第一章 项目采购需求", 4),
            _paragraph("r1", "本项目服务内容包括调查、分析、成果提交和验收。", 5),
            _paragraph("r2", "技术要求应满足采购人对范围、参数和质量的要求。", 6),
            _heading("h3", "第二章 评分标准", 7),
            _table("s1", "| 评审因素 | 评分标准 | 分值 |\n| --- | --- | --- |\n| 服务方案 | 完整得5分 | 5分 |", 8),
            _heading("h4", "第三章 合同条款", 9),
            _paragraph("c1", "合同正文", 10),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert "本项目服务内容" in result.requirements.markdown
    assert "合同正文" not in result.requirements.markdown
    assert result.scoring is not None
    assert "评审因素" in result.scoring.markdown
    assert result.requirements.confidence >= 0.80
    assert result.scoring.confidence >= 0.80


def test_excludes_toc_candidates_from_start_boundary():
    conversion = _conversion(
        [
            _heading("toc", "目录", 1),
            _paragraph("toc_req", "项目采购需求 ........ 3", 2),
            _heading("real_req", "采购需求", 3),
            _paragraph("r1", "服务范围、技术要求、验收标准详见下列内容。", 4),
            _heading("real_score", "评审办法", 5),
            _table("s1", "| 评分项 | 评审内容 | 分值 |\n| --- | --- | --- |\n| 团队 | 人员配置得10分 | 10分 |", 6),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.start_block_id == "real_req"
    assert "........" not in result.requirements.markdown
    assert result.scoring is not None
    assert result.scoring.start_block_id == "real_score"


def test_scoring_can_be_detected_from_excel_sheet_table_without_heading_alias():
    conversion = _conversion(
        [
            ConvertedBlock(
                block_id="sheet1",
                source_file="score.xlsx",
                source_type="xlsx",
                block_type="heading",
                markdown="## 工作表：技术商务评分表",
                text="工作表：技术商务评分表",
                order_index=1,
                heading_level=2,
                heading_title="工作表：技术商务评分表",
                sheet_name="技术商务评分表",
            ),
            _table("t1", "| 子项 | 评审内容 | 分值 |\n| --- | --- | --- |\n| 技术方案 | 优得20分 | 20分 |", 2),
            _heading("req", "采购内容及要求", 3),
            _paragraph("r1", "采购服务内容包括技术支持、成果提交和验收。", 4),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.scoring is not None
    assert result.scoring.start_block_id == "sheet1"
    assert "优得20分" in result.scoring.markdown
    assert result.requirements is not None


def test_low_confidence_when_requirements_content_is_too_short():
    conversion = _conversion(
        [
            _heading("req", "项目需求", 1),
            _paragraph("r1", "详见附件。", 2),
            _heading("score", "评分标准", 3),
            _table("s1", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 5分 |", 4),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.confidence < 0.80
    assert result.needs_confirmation is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_section_extractor.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_section_extractor'`.

- [ ] **Step 3: Implement extractor**

Create `bid_writer/tender_section_extractor.py`:

```python
"""从转换后的招标文件 Markdown block 中抽取采购需求和评分标准。"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .tender_import_models import (
    ConvertedBlock,
    SectionCandidate,
    TenderConversionResult,
    TenderExtractionResult,
    TenderSectionExtraction,
)


REQUIREMENT_ALIASES = (
    "项目采购需求",
    "采购需求",
    "项目需求",
    "服务需求",
    "技术需求",
    "技术和服务要求",
    "采购内容及要求",
    "项目内容及要求",
    "服务内容及要求",
    "技术参数及要求",
    "用户需求书",
    "商务技术要求",
)

SCORING_ALIASES = (
    "评分标准",
    "评审标准",
    "评审办法",
    "评审方法",
    "评分办法",
    "评分细则",
    "综合评分法",
    "详细评审",
    "评审因素",
    "技术商务评分表",
    "综合评分表",
    "评标办法",
)

REQUIREMENT_TERMS = ("服务", "技术", "要求", "内容", "范围", "参数", "成果", "验收", "采购")
SCORING_TERMS = ("评分", "评审", "分值", "满分", "权重", "得分", "得", "分")
SCORING_TABLE_TERMS = ("评审因素", "评分项", "评分标准", "评审内容", "分值", "权重", "得分")
STRONG_STOP_TITLES = ("合同条款", "投标人须知", "响应文件格式", "开标评标定标")
TOC_DOTTED_RE = re.compile(r"\.{3,}|…{2,}|[.．·]{2,}\s*\d+\s*$")


def extract_tender_sections(conversion: TenderConversionResult) -> TenderSectionExtraction:
    blocks = sorted(conversion.blocks, key=lambda item: item.order_index)
    candidates = _collect_candidates(blocks)
    requirements = _build_result("bid_requirements", blocks, candidates)
    scoring = _build_result("scoring_criteria", blocks, candidates)

    warnings: list[str] = []
    if requirements is None:
        warnings.append("未定位到项目采购需求章节。")
    if scoring is None:
        warnings.append("未定位到评分标准章节。")

    return TenderSectionExtraction(
        requirements=requirements,
        scoring=scoring,
        candidates=candidates,
        warnings=tuple(warnings),
    )


def _collect_candidates(blocks: list[ConvertedBlock]) -> list[SectionCandidate]:
    candidates: list[SectionCandidate] = []
    for block in blocks:
        if _is_toc_like(block):
            continue
        title = _candidate_title(block)
        if not title and block.block_type != "table":
            continue
        req_score, req_reason = _alias_score(title, REQUIREMENT_ALIASES)
        if req_score > 0:
            candidates.append(
                SectionCandidate(
                    section_key="bid_requirements",
                    block_id=block.block_id,
                    title=title,
                    score=req_score,
                    reason=req_reason,
                    order_index=block.order_index,
                )
            )

        score, reason = _alias_score(title, SCORING_ALIASES)
        table_bonus = _scoring_table_bonus(block)
        if score > 0 or table_bonus > 0:
            candidates.append(
                SectionCandidate(
                    section_key="scoring_criteria",
                    block_id=block.block_id,
                    title=title or block.text[:40],
                    score=max(score, 45.0) + table_bonus,
                    reason=reason if score > 0 else "scoring_table_terms",
                    order_index=block.order_index,
                )
            )
    candidates.sort(key=lambda item: (-item.score, item.order_index))
    return candidates


def _candidate_title(block: ConvertedBlock) -> str:
    if block.heading_title:
        return block.heading_title.strip()
    if block.block_type == "heading":
        return block.text.strip()
    if block.block_type in {"paragraph", "table"} and len(block.text.strip()) <= 40:
        return block.text.strip()
    return ""


def _alias_score(title: str, aliases: tuple[str, ...]) -> tuple[float, str]:
    normalized = _normalize_title(title)
    if not normalized:
        return 0.0, ""
    best = 0.0
    best_alias = ""
    for alias in aliases:
        alias_norm = _normalize_title(alias)
        if alias_norm == normalized or alias_norm in normalized:
            return 120.0, "exact_alias"
        ratio = float(fuzz.partial_ratio(alias_norm, normalized))
        if ratio > best:
            best = ratio
            best_alias = alias
    if best >= 82:
        return 85.0, f"fuzzy_alias:{best_alias}"
    if best >= 68:
        return 55.0, f"weak_alias:{best_alias}"
    return 0.0, ""


def _normalize_title(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text.strip())
    text = re.sub(r"^[第]?[一二三四五六七八九十百千万\d]+[章节条、.．\s]+", "", text)
    text = re.sub(r"[\s　:：|（）()\[\]【】《》<>/\\-]+", "", text)
    return text.lower()


def _scoring_table_bonus(block: ConvertedBlock) -> float:
    text = block.text
    hits = sum(1 for term in SCORING_TABLE_TERMS if term in text)
    if block.block_type == "table" and hits >= 2:
        return 55.0 + hits * 8.0
    if hits >= 3:
        return 35.0
    return 0.0


def _is_toc_like(block: ConvertedBlock) -> bool:
    text = block.text.strip()
    if block.heading_title.strip() == "目录":
        return True
    return bool(TOC_DOTTED_RE.search(text)) and len(text) <= 80


def _build_result(
    section_key: str,
    blocks: list[ConvertedBlock],
    candidates: list[SectionCandidate],
) -> TenderExtractionResult | None:
    candidate = next((item for item in candidates if item.section_key == section_key), None)
    if candidate is None:
        return None
    index_by_id = {block.block_id: idx for idx, block in enumerate(blocks)}
    start_index = index_by_id[candidate.block_id]
    end_index = _find_end_index(blocks, start_index)
    selected = blocks[start_index:end_index]
    markdown = _join_markdown(selected)
    confidence, warnings = _confidence(section_key, candidate.score, markdown, selected)
    return TenderExtractionResult(
        section_key=section_key,
        title=candidate.title,
        markdown=markdown,
        start_block_id=selected[0].block_id,
        end_block_id=selected[-1].block_id,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def _find_end_index(blocks: list[ConvertedBlock], start_index: int) -> int:
    start_block = blocks[start_index]
    start_level = start_block.heading_level or 2
    for index in range(start_index + 1, len(blocks)):
        block = blocks[index]
        title = block.heading_title or block.text
        if block.heading_level is not None and block.heading_level <= start_level:
            return index
        if block.block_type == "heading" and any(term in title for term in STRONG_STOP_TITLES):
            return index
    return len(blocks)


def _join_markdown(blocks: list[ConvertedBlock]) -> str:
    return "\n\n".join(block.markdown.strip() for block in blocks if block.markdown.strip()).strip() + "\n"


def _confidence(
    section_key: str,
    candidate_score: float,
    markdown: str,
    blocks: list[ConvertedBlock],
) -> tuple[float, list[str]]:
    warnings: list[str] = []
    score = min(candidate_score / 120.0, 1.0)
    text = "\n".join(block.text for block in blocks)
    if section_key == "bid_requirements":
        hits = sum(1 for term in REQUIREMENT_TERMS if term in text)
        if len(text.strip()) < 40:
            score -= 0.30
            warnings.append("采购需求摘录内容较短。")
        if hits < 3:
            score -= 0.20
            warnings.append("采购需求关键词命中较少。")
    else:
        hits = sum(1 for term in SCORING_TERMS if term in text)
        has_table = any(block.block_type == "table" for block in blocks)
        if hits < 2 and not has_table:
            score -= 0.25
            warnings.append("评分标准关键词命中较少。")
        if has_table:
            score += 0.10
    return max(0.0, min(score, 1.0)), warnings
```

- [ ] **Step 4: Run extractor tests**

Run:

```bash
uv run pytest tests/test_tender_section_extractor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit extractor**

Run:

```bash
git add bid_writer/tender_section_extractor.py tests/test_tender_section_extractor.py
git commit -m "feat: extract tender requirement and scoring sections"
```

Expected: commit succeeds.

---

### Task 4: Implement DOCX and XLSX Markdown Conversion

**Files:**
- Create: `bid_writer/tender_markdown_converter.py`
- Test: `tests/test_tender_markdown_converter.py`

- [ ] **Step 1: Write failing tests for DOCX/XLSX conversion and unsupported WPS formats**

Create `tests/test_tender_markdown_converter.py`:

```python
from pathlib import Path

import openpyxl
import pytest
from docx import Document

from bid_writer.tender_markdown_converter import TenderConversionError, convert_tender_document


def test_converts_docx_headings_paragraphs_and_tables(tmp_path: Path):
    doc_path = tmp_path / "tender.docx"
    document = Document()
    document.add_heading("项目采购需求", level=1)
    document.add_paragraph("服务内容包括调查、分析、成果提交和验收。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "要求"
    table.cell(1, 0).text = "服务范围"
    table.cell(1, 1).text = "覆盖采购人指定区域"
    document.add_heading("评分标准", level=1)
    document.add_paragraph("评分总分为100分。")
    document.save(doc_path)

    result = convert_tender_document(doc_path, tmp_path / "out")

    markdown = result.converted_markdown_path.read_text(encoding="utf-8")
    assert "# 项目采购需求" in markdown
    assert "服务内容包括调查" in markdown
    assert "| 项目 | 要求 |" in markdown
    assert "# 评分标准" in markdown
    assert result.conversion_map_path.exists()
    assert any(block.block_type == "table" for block in result.blocks)


def test_converts_xlsx_sheets_to_markdown_tables(tmp_path: Path):
    workbook_path = tmp_path / "score.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "技术商务评分表"
    sheet["A1"] = "评分项"
    sheet["B1"] = "评分标准"
    sheet["C1"] = "分值"
    sheet["A2"] = "服务方案"
    sheet["B2"] = "完整得20分"
    sheet["C2"] = "20分"
    workbook.save(workbook_path)

    result = convert_tender_document(workbook_path, tmp_path / "out")

    markdown = result.converted_markdown_path.read_text(encoding="utf-8")
    assert "## 工作表：技术商务评分表" in markdown
    assert "| 评分项 | 评分标准 | 分值 |" in markdown
    assert any(block.sheet_name == "技术商务评分表" for block in result.blocks)


def test_rejects_wps_and_et_formats(tmp_path: Path):
    wps_path = tmp_path / "tender.wps"
    wps_path.write_text("fake", encoding="utf-8")

    with pytest.raises(TenderConversionError) as exc:
        convert_tender_document(wps_path, tmp_path / "out")

    assert "暂不支持 WPS 原生格式" in str(exc.value)
```

- [ ] **Step 2: Run conversion tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_markdown_converter.py -q
```

Expected: FAIL because `bid_writer.tender_markdown_converter` does not exist.

- [ ] **Step 3: Implement DOCX/XLSX conversion and JSON writing**

Create `bid_writer/tender_markdown_converter.py`:

```python
"""招标文件到 Markdown block 的转换器。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import openpyxl
from docx import Document

from .tender_import_models import ConvertedBlock, TenderConversionResult, dump_conversion_map


class TenderConversionError(RuntimeError):
    """招标文件转换失败。"""


UNSUPPORTED_WPS_SUFFIXES = {".wps", ".et"}
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".doc", ".xls"} | UNSUPPORTED_WPS_SUFFIXES


def convert_tender_document(path: Path, output_dir: Path) -> TenderConversionResult:
    source_path = Path(path).expanduser().resolve()
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise TenderConversionError(f"暂不支持该文件格式：{suffix or '无扩展名'}")
    if suffix in UNSUPPORTED_WPS_SUFFIXES:
        raise TenderConversionError("暂不支持 WPS 原生格式，请另存为 .docx、.xlsx 或可复制文字 PDF 后再导入。")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_for_conversion = source_path
    warnings: list[str] = []

    if suffix == ".doc":
        source_for_conversion = _convert_with_libreoffice(source_path, output_dir, "docx")
        suffix = ".docx"
        warnings.append("已通过 LibreOffice 将 .doc 预转换为 .docx。")
    elif suffix == ".xls":
        source_for_conversion = _convert_with_libreoffice(source_path, output_dir, "xlsx")
        suffix = ".xlsx"
        warnings.append("已通过 LibreOffice 将 .xls 预转换为 .xlsx。")

    if suffix == ".docx":
        blocks = _convert_docx(source_for_conversion, source_path.name)
    elif suffix == ".xlsx":
        blocks = _convert_xlsx(source_for_conversion, source_path.name)
    elif suffix == ".pdf":
        blocks = _convert_pdf(source_for_conversion, source_path.name)
    else:
        raise TenderConversionError(f"暂不支持该文件格式：{suffix}")

    if not blocks:
        raise TenderConversionError("未从文件中解析到可用文本。")

    converted_path = output_dir / "converted.md"
    map_path = output_dir / "conversion_map.json"
    converted_path.write_text(_join_blocks(blocks), encoding="utf-8")
    result = TenderConversionResult(
        source_path=source_path,
        output_dir=output_dir,
        converted_markdown_path=converted_path,
        conversion_map_path=map_path,
        blocks=blocks,
        warnings=tuple(warnings),
    )
    map_path.write_text(
        json.dumps(dump_conversion_map(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def _convert_docx(path: Path, source_name: str) -> list[ConvertedBlock]:
    document = Document(path)
    blocks: list[ConvertedBlock] = []
    order = 0
    paragraph_index = 0
    table_index = 0

    for child in document.element.body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = document.paragraphs[paragraph_index]
            paragraph_index += 1
            text = paragraph.text.strip()
            if not text:
                continue
            order += 1
            level = _docx_heading_level(paragraph.style.name if paragraph.style else "")
            markdown = f"{'#' * level} {text}" if level else text
            blocks.append(
                ConvertedBlock(
                    block_id=f"docx:p{paragraph_index:04d}",
                    source_file=source_name,
                    source_type="docx",
                    block_type="heading" if level else "paragraph",
                    markdown=markdown,
                    text=text,
                    order_index=order,
                    heading_level=level,
                    heading_title=text if level else "",
                    paragraph_index=paragraph_index,
                )
            )
        elif tag == "tbl":
            table = document.tables[table_index]
            table_index += 1
            markdown = _markdown_table([[cell.text.strip() for cell in row.cells] for row in table.rows])
            if not markdown.strip():
                continue
            order += 1
            blocks.append(
                ConvertedBlock(
                    block_id=f"docx:t{table_index:04d}",
                    source_file=source_name,
                    source_type="docx",
                    block_type="table",
                    markdown=markdown,
                    text=markdown,
                    order_index=order,
                    table_index=table_index,
                )
            )
    return blocks


def _docx_heading_level(style_name: str) -> int | None:
    match = re.search(r"(?:Heading|标题)\s*([1-6一二三四五六])", style_name, re.I)
    if not match:
        return None
    raw = match.group(1)
    chinese = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    return chinese.get(raw, int(raw) if raw.isdigit() else 1)


def _convert_xlsx(path: Path, source_name: str) -> list[ConvertedBlock]:
    workbook = openpyxl.load_workbook(path, data_only=True)
    blocks: list[ConvertedBlock] = []
    order = 0
    for sheet in workbook.worksheets:
        order += 1
        sheet_heading = f"工作表：{sheet.title}"
        blocks.append(
            ConvertedBlock(
                block_id=f"xlsx:{sheet.title}:heading",
                source_file=source_name,
                source_type="xlsx",
                block_type="heading",
                markdown=f"## {sheet_heading}",
                text=sheet_heading,
                order_index=order,
                heading_level=2,
                heading_title=sheet_heading,
                sheet_name=sheet.title,
            )
        )
        rows = _sheet_rows(sheet)
        if rows:
            order += 1
            cell_range = f"A1:{sheet.cell(row=sheet.max_row, column=sheet.max_column).coordinate}"
            markdown = _markdown_table(rows)
            blocks.append(
                ConvertedBlock(
                    block_id=f"xlsx:{sheet.title}:table1",
                    source_file=source_name,
                    source_type="xlsx",
                    block_type="table",
                    markdown=markdown,
                    text=markdown,
                    order_index=order,
                    sheet_name=sheet.title,
                    cell_range=cell_range,
                    table_index=1,
                )
            )
    return blocks


def _sheet_rows(sheet) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in sheet.iter_rows():
        values = ["" if cell.value is None else str(cell.value).strip() for cell in row]
        while values and not values[-1]:
            values.pop()
        if any(values):
            rows.append(values)
    if not rows:
        return []
    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def _convert_pdf(path: Path, source_name: str) -> list[ConvertedBlock]:
    try:
        import fitz
        import pymupdf4llm
    except ImportError as exc:
        raise TenderConversionError(f"PDF 转换依赖未安装：{exc}") from exc

    doc = fitz.open(path)
    extracted_text = "\n".join(page.get_text("text") for page in doc)
    if _visible_text_length(extracted_text) < max(80, len(doc) * 20):
        raise TenderConversionError("该 PDF 可能没有可复制文本层；当前版本暂不支持 OCR。")
    markdown = pymupdf4llm.to_markdown(str(path))
    blocks: list[ConvertedBlock] = []
    order = 0
    for chunk in _split_markdown_blocks(markdown):
        order += 1
        heading_level, heading_title = _markdown_heading(chunk)
        blocks.append(
            ConvertedBlock(
                block_id=f"pdf:b{order:04d}",
                source_file=source_name,
                source_type="pdf",
                block_type="heading" if heading_level else ("table" if "|" in chunk else "paragraph"),
                markdown=chunk,
                text=re.sub(r"^#+\s*", "", chunk).strip(),
                order_index=order,
                heading_level=heading_level,
                heading_title=heading_title,
            )
        )
    return blocks


def _split_markdown_blocks(markdown: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]


def _markdown_heading(markdown: str) -> tuple[int | None, str]:
    first_line = markdown.splitlines()[0].strip()
    match = re.match(r"^(#{1,6})\s+(.+)$", first_line)
    if not match:
        return None, ""
    return len(match.group(1)), match.group(2).strip()


def _visible_text_length(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def _markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    separator = ["---"] * width
    body = normalized[1:]
    lines = [
        "| " + " | ".join(_escape_cell(cell) for cell in header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(_escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: str) -> str:
    return str(value).replace("\n", "<br>").replace("|", "\\|")


def _join_blocks(blocks: list[ConvertedBlock]) -> str:
    return "\n\n".join(block.markdown.strip() for block in blocks if block.markdown.strip()).strip() + "\n"


def _convert_with_libreoffice(path: Path, output_dir: Path, target_ext: str) -> Path:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        raise TenderConversionError("未检测到 LibreOffice，无法转换旧 Office 格式；请另存为 .docx 或 .xlsx 后再导入。")
    command = [
        executable,
        "--headless",
        "--convert-to",
        target_ext,
        "--outdir",
        str(output_dir),
        str(path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise TenderConversionError(f"LibreOffice 转换失败：{completed.stderr.strip() or completed.stdout.strip()}")
    converted = output_dir / f"{path.stem}.{target_ext}"
    if not converted.exists():
        raise TenderConversionError("LibreOffice 转换完成但未找到输出文件。")
    return converted
```

- [ ] **Step 4: Run DOCX/XLSX conversion tests**

Run:

```bash
uv run pytest tests/test_tender_markdown_converter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit conversion foundation**

Run:

```bash
git add bid_writer/tender_markdown_converter.py tests/test_tender_markdown_converter.py
git commit -m "feat: convert tender word and excel files"
```

Expected: commit succeeds.

---

### Task 5: Add PDF and Legacy Format Converter Coverage

**Files:**
- Modify: `tests/test_tender_markdown_converter.py`
- Modify: `bid_writer/tender_markdown_converter.py`

- [ ] **Step 1: Add tests for PDF no-text error and LibreOffice command boundaries**

Append to `tests/test_tender_markdown_converter.py`:

```python
from types import SimpleNamespace


def test_pdf_without_text_layer_raises_clear_error(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class FakePage:
        def get_text(self, _kind):
            return ""

    class FakeDoc(list):
        def __init__(self):
            super().__init__([FakePage(), FakePage()])

    monkeypatch.setitem(__import__("sys").modules, "fitz", SimpleNamespace(open=lambda _path: FakeDoc()))
    monkeypatch.setitem(__import__("sys").modules, "pymupdf4llm", SimpleNamespace(to_markdown=lambda _path: ""))

    with pytest.raises(TenderConversionError) as exc:
        convert_tender_document(pdf_path, tmp_path / "out")

    assert "暂不支持 OCR" in str(exc.value)


def test_doc_requires_libreoffice_when_no_converter_available(monkeypatch, tmp_path: Path):
    doc_path = tmp_path / "old.doc"
    doc_path.write_text("fake", encoding="utf-8")

    monkeypatch.setattr("bid_writer.tender_markdown_converter.shutil.which", lambda _name: None)

    with pytest.raises(TenderConversionError) as exc:
        convert_tender_document(doc_path, tmp_path / "out")

    assert "未检测到 LibreOffice" in str(exc.value)
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
uv run pytest tests/test_tender_markdown_converter.py::test_pdf_without_text_layer_raises_clear_error tests/test_tender_markdown_converter.py::test_doc_requires_libreoffice_when_no_converter_available -q
```

Expected: PASS. If the PDF monkeypatch fails because imports occur before monkeypatching, update `_convert_pdf()` to import `fitz` and `pymupdf4llm` inside the function exactly as shown in Task 4.

- [ ] **Step 3: Add optional python-calamine `.xls` path**

Modify `.xls` handling in `convert_tender_document()` so it tries calamine first:

```python
    elif suffix == ".xls":
        calamine_blocks = _try_convert_xls_with_calamine(source_path, source_path.name)
        if calamine_blocks is not None:
            blocks = calamine_blocks
            converted_path = output_dir / "converted.md"
            map_path = output_dir / "conversion_map.json"
            converted_path.write_text(_join_blocks(blocks), encoding="utf-8")
            result = TenderConversionResult(
                source_path=source_path,
                output_dir=output_dir,
                converted_markdown_path=converted_path,
                conversion_map_path=map_path,
                blocks=blocks,
                warnings=("已通过 python-calamine 读取 .xls。",),
            )
            map_path.write_text(
                json.dumps(dump_conversion_map(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return result
        source_for_conversion = _convert_with_libreoffice(source_path, output_dir, "xlsx")
        suffix = ".xlsx"
        warnings.append("已通过 LibreOffice 将 .xls 预转换为 .xlsx。")
```

Add this helper near `_convert_xlsx()`:

```python
def _try_convert_xls_with_calamine(path: Path, source_name: str) -> list[ConvertedBlock] | None:
    try:
        from python_calamine import CalamineWorkbook
    except ImportError:
        return None
    try:
        workbook = CalamineWorkbook.from_path(str(path))
    except Exception:
        return None
    blocks: list[ConvertedBlock] = []
    order = 0
    for sheet_name in workbook.sheet_names:
        sheet = workbook.get_sheet_by_name(sheet_name)
        rows = [[str(cell).strip() if cell is not None else "" for cell in row] for row in sheet.to_python()]
        rows = [row for row in rows if any(row)]
        order += 1
        heading = f"工作表：{sheet_name}"
        blocks.append(
            ConvertedBlock(
                block_id=f"xls:{sheet_name}:heading",
                source_file=source_name,
                source_type="xls",
                block_type="heading",
                markdown=f"## {heading}",
                text=heading,
                order_index=order,
                heading_level=2,
                heading_title=heading,
                sheet_name=sheet_name,
            )
        )
        if rows:
            order += 1
            markdown = _markdown_table(rows)
            blocks.append(
                ConvertedBlock(
                    block_id=f"xls:{sheet_name}:table1",
                    source_file=source_name,
                    source_type="xls",
                    block_type="table",
                    markdown=markdown,
                    text=markdown,
                    order_index=order,
                    sheet_name=sheet_name,
                    table_index=1,
                )
            )
    return blocks
```

- [ ] **Step 4: Run all converter tests**

Run:

```bash
uv run pytest tests/test_tender_markdown_converter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit converter coverage**

Run:

```bash
git add bid_writer/tender_markdown_converter.py tests/test_tender_markdown_converter.py
git commit -m "feat: handle tender pdf and legacy format boundaries"
```

Expected: commit succeeds.

---

### Task 6: Add Import Service Orchestration

**Files:**
- Create: `bid_writer/tender_import_service.py`
- Test: `tests/test_tender_import_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_tender_import_service.py`:

```python
from pathlib import Path

from bid_writer.tender_import_models import (
    TenderExtractionResult,
    TenderSectionExtraction,
)
from bid_writer.tender_import_service import TenderImportService


class FakeConverter:
    def __init__(self, conversion):
        self.conversion = conversion
        self.calls = []

    def __call__(self, path, output_dir):
        self.calls.append((path, output_dir))
        return self.conversion


class FakeExtractor:
    def __init__(self, extraction):
        self.extraction = extraction
        self.calls = []

    def __call__(self, conversion):
        self.calls.append(conversion)
        return self.extraction


def test_import_service_writes_outputs_and_report(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type(
        "Conversion",
        (),
        {
            "source_path": source,
            "output_dir": tmp_path / ".bid_writer" / "imports" / "import-test",
            "converted_markdown_path": tmp_path / ".bid_writer" / "imports" / "import-test" / "converted.md",
            "conversion_map_path": tmp_path / ".bid_writer" / "imports" / "import-test" / "conversion_map.json",
            "blocks": [],
            "warnings": (),
        },
    )()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult(
            section_key="bid_requirements",
            title="项目采购需求",
            markdown="# 项目采购需求\n\n需求正文\n",
            start_block_id="r1",
            end_block_id="r2",
            confidence=0.92,
        ),
        scoring=TenderExtractionResult(
            section_key="scoring_criteria",
            title="评分标准",
            markdown="# 评分标准\n\n评分正文\n",
            start_block_id="s1",
            end_block_id="s2",
            confidence=0.90,
        ),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: True,
    )

    assert result.requirements_path == tmp_path / "项目要求" / "项目采购需求.md"
    assert result.scoring_path == tmp_path / "项目要求" / "评分标准.md"
    assert result.requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n需求正文\n"
    assert result.scoring_path.read_text(encoding="utf-8") == "# 评分标准\n\n评分正文\n"
    assert result.extraction_report_path.exists()
    assert result.relative_requirements_path == "./项目要求/项目采购需求.md"
    assert result.relative_scoring_path == "./项目要求/评分标准.md"


def test_import_service_backs_up_existing_nonempty_files(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    target_dir = tmp_path / "项目要求"
    target_dir.mkdir()
    existing = target_dir / "项目采购需求.md"
    existing.write_text("旧需求", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "# 项目采购需求\n\n新需求\n", "r1", "r1", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "# 评分标准\n\n新评分\n", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda path: path.name == "项目采购需求.md",
        confirm_low_confidence=lambda _extraction: True,
    )

    assert (target_dir / "项目采购需求.md.bak").read_text(encoding="utf-8") == "旧需求"
    assert existing.read_text(encoding="utf-8") == "# 项目采购需求\n\n新需求\n"


def test_import_service_stops_when_low_confidence_not_confirmed(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "# 项目采购需求\n\n短\n", "r1", "r1", 0.50),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "# 评分标准\n\n评分\n", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: False,
    )

    assert result.cancelled is True
    assert not (tmp_path / "项目要求" / "项目采购需求.md").exists()
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_import_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_import_service'`.

- [ ] **Step 3: Implement service**

Create `bid_writer/tender_import_service.py`:

```python
"""招标文件导入服务：转换、抽取、写入项目资料文件。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tender_import_models import (
    TenderSectionExtraction,
    dump_extraction_report,
)
from .tender_markdown_converter import convert_tender_document
from .tender_section_extractor import extract_tender_sections


@dataclass(frozen=True)
class TenderImportResult:
    requirements_path: Path | None
    scoring_path: Path | None
    relative_requirements_path: str
    relative_scoring_path: str
    import_dir: Path
    extraction_report_path: Path
    extraction: TenderSectionExtraction
    cancelled: bool = False


class TenderImportError(RuntimeError):
    """招标文件导入失败。"""


class TenderImportService:
    def __init__(
        self,
        *,
        converter=convert_tender_document,
        extractor=extract_tender_sections,
        import_id_factory: Callable[[], str] | None = None,
    ):
        self.converter = converter
        self.extractor = extractor
        self.import_id_factory = import_id_factory or (lambda: uuid.uuid4().hex[:12])

    def import_document(
        self,
        *,
        source_path: Path,
        project_root: Path,
        confirm_overwrite: Callable[[Path], bool],
        confirm_low_confidence: Callable[[TenderSectionExtraction], bool],
    ) -> TenderImportResult:
        project_root = Path(project_root).expanduser().resolve()
        import_dir = project_root / ".bid_writer" / "imports" / self.import_id_factory()
        import_dir.mkdir(parents=True, exist_ok=True)
        conversion = self.converter(Path(source_path), import_dir)
        extraction = self.extractor(conversion)
        report_path = import_dir / "extraction_report.json"
        report_path.write_text(
            json.dumps(dump_extraction_report(extraction), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if not extraction.is_complete:
            raise TenderImportError("未能同时抽取项目采购需求和评分标准，请查看转换 Markdown 或手动整理。")
        if extraction.needs_confirmation and not confirm_low_confidence(extraction):
            return TenderImportResult(
                requirements_path=None,
                scoring_path=None,
                relative_requirements_path="./项目要求/项目采购需求.md",
                relative_scoring_path="./项目要求/评分标准.md",
                import_dir=import_dir,
                extraction_report_path=report_path,
                extraction=extraction,
                cancelled=True,
            )

        target_dir = project_root / "项目要求"
        target_dir.mkdir(parents=True, exist_ok=True)
        requirements_path = target_dir / "项目采购需求.md"
        scoring_path = target_dir / "评分标准.md"
        self._write_target(requirements_path, extraction.requirements.markdown, confirm_overwrite)
        self._write_target(scoring_path, extraction.scoring.markdown, confirm_overwrite)
        return TenderImportResult(
            requirements_path=requirements_path,
            scoring_path=scoring_path,
            relative_requirements_path="./项目要求/项目采购需求.md",
            relative_scoring_path="./项目要求/评分标准.md",
            import_dir=import_dir,
            extraction_report_path=report_path,
            extraction=extraction,
        )

    def _write_target(
        self,
        path: Path,
        content: str,
        confirm_overwrite: Callable[[Path], bool],
    ) -> None:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            if not confirm_overwrite(path):
                raise TenderImportError(f"用户取消覆盖：{path}")
            backup = path.with_suffix(path.suffix + ".bak")
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(content.strip() + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run service tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit service**

Run:

```bash
git add bid_writer/tender_import_service.py tests/test_tender_import_service.py
git commit -m "feat: orchestrate tender import writes"
```

Expected: commit succeeds.

---

### Task 7: Add Low-Confidence Preview Helper and Dialog

**Files:**
- Create: `bid_writer/tender_import_dialog.py`
- Test: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Write failing tests for preview text**

Create `tests/test_tender_import_dialog.py`:

```python
from bid_writer.tender_import_dialog import build_low_confidence_preview
from bid_writer.tender_import_models import TenderExtractionResult, TenderSectionExtraction


def test_low_confidence_preview_includes_confidence_and_excerpt():
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult(
            "bid_requirements",
            "项目采购需求",
            "# 项目采购需求\n\n" + "需求正文" * 80,
            "r1",
            "r3",
            0.61,
            ("采购需求摘录内容较短。",),
        ),
        scoring=TenderExtractionResult(
            "scoring_criteria",
            "评分标准",
            "# 评分标准\n\n评分正文",
            "s1",
            "s3",
            0.88,
        ),
    )

    preview = build_low_confidence_preview(extraction)

    assert "项目采购需求：61%" in preview
    assert "采购需求摘录内容较短" in preview
    assert "评分标准：88%" in preview
    assert len(preview) < 1600
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_import_dialog'`.

- [ ] **Step 3: Implement preview helper and messagebox-backed confirmation**

Create `bid_writer/tender_import_dialog.py`:

```python
"""招标文件导入确认 UI 辅助。"""

from __future__ import annotations

from tkinter import messagebox

from .tender_import_models import TenderExtractionResult, TenderSectionExtraction


def build_low_confidence_preview(extraction: TenderSectionExtraction, *, max_chars: int = 420) -> str:
    parts: list[str] = ["抽取结果置信度偏低，请确认是否写入项目资料文件。"]
    for label, result in (
        ("项目采购需求", extraction.requirements),
        ("评分标准", extraction.scoring),
    ):
        if result is None:
            parts.append(f"\n{label}：未抽取到")
            continue
        parts.append(_format_result(label, result, max_chars=max_chars))
    return "\n".join(parts)


def confirm_low_confidence(parent, extraction: TenderSectionExtraction) -> bool:
    return messagebox.askyesno(
        "确认导入",
        build_low_confidence_preview(extraction),
        parent=parent,
    )


def _format_result(label: str, result: TenderExtractionResult, *, max_chars: int) -> str:
    excerpt = result.markdown.strip().replace("\n\n", "\n")
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n..."
    warnings = "；".join(result.warnings) if result.warnings else "无"
    return "\n".join(
        [
            f"\n{label}：{result.confidence:.0%}",
            f"标题：{result.title}",
            f"提示：{warnings}",
            "预览：",
            excerpt,
        ]
    )
```

- [ ] **Step 4: Run dialog tests**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit dialog helper**

Run:

```bash
git add bid_writer/tender_import_dialog.py tests/test_tender_import_dialog.py
git commit -m "feat: preview low confidence tender imports"
```

Expected: commit succeeds.

---

### Task 8: Wire Import Flow Into New Config Editor

**Files:**
- Modify: `bid_writer/config_editor_dialog.py`
- Modify: `bid_writer/config_editor_tooltips.py`
- Create: `tests/test_config_editor_tender_import.py`
- Modify: `tests/test_config_editor_dialog.py`

- [ ] **Step 1: Write failing UI/service integration tests without Tk window**

Create `tests/test_config_editor_tender_import.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from bid_writer import config_editor_dialog
from bid_writer.config_editor_dialog import ConfigEditorDialog


class StubVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _dialog(tmp_path: Path, *, new_config: bool = True):
    dialog = ConfigEditorDialog.__new__(ConfigEditorDialog)
    dialog.is_new_config = new_config
    dialog.vars = {
        "project.root_dir": StubVar("."),
        "project.bid_requirements_mode": StubVar("file"),
        "project.bid_requirements_file": StubVar(""),
        "project.scoring_criteria_mode": StubVar("file"),
        "project.scoring_criteria_file": StubVar(""),
    }
    dialog.active_config_path = tmp_path / "config_新项目.yaml"
    dialog.document = SimpleNamespace(config_path=tmp_path / "config_新项目.yaml")
    dialog.tender_import_status_var = StubVar("")
    dialog._current_project_root = lambda: tmp_path
    dialog._schedule_refresh = lambda: None
    return dialog


def test_apply_tender_import_result_updates_file_modes_and_paths(tmp_path: Path):
    dialog = _dialog(tmp_path)
    result = SimpleNamespace(
        relative_requirements_path="./项目要求/项目采购需求.md",
        relative_scoring_path="./项目要求/评分标准.md",
        import_dir=tmp_path / ".bid_writer" / "imports" / "abc",
        extraction_report_path=tmp_path / ".bid_writer" / "imports" / "abc" / "extraction_report.json",
        cancelled=False,
    )

    ConfigEditorDialog._apply_tender_import_result(dialog, result)

    assert dialog.vars["project.bid_requirements_mode"].get() == "file"
    assert dialog.vars["project.scoring_criteria_mode"].get() == "file"
    assert dialog.vars["project.bid_requirements_file"].get() == "./项目要求/项目采购需求.md"
    assert dialog.vars["project.scoring_criteria_file"].get() == "./项目要求/评分标准.md"
    assert "导入完成" in dialog.tender_import_status_var.get()


def test_import_tender_document_uses_single_file_dialog(monkeypatch, tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    dialog = _dialog(tmp_path)
    calls = {}

    class FakeService:
        def import_document(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                relative_requirements_path="./项目要求/项目采购需求.md",
                relative_scoring_path="./项目要求/评分标准.md",
                import_dir=tmp_path / ".bid_writer" / "imports" / "abc",
                extraction_report_path=tmp_path / ".bid_writer" / "imports" / "abc" / "extraction_report.json",
                cancelled=False,
            )

    monkeypatch.setattr(config_editor_dialog.filedialog, "askopenfilename", lambda **_kwargs: str(source))
    monkeypatch.setattr(config_editor_dialog, "TenderImportService", lambda: FakeService())
    monkeypatch.setattr(config_editor_dialog.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(config_editor_dialog.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(config_editor_dialog, "confirm_low_confidence", lambda _parent, _extraction: True)
    dialog._apply_tender_import_result = lambda result: calls.setdefault("applied", result)

    ConfigEditorDialog._import_tender_document(dialog)

    assert calls["source_path"] == source
    assert calls["project_root"] == tmp_path
    assert "applied" in calls


def test_import_tender_document_is_disabled_outside_new_config(tmp_path: Path):
    dialog = _dialog(tmp_path, new_config=False)

    assert ConfigEditorDialog._can_import_tender_document(dialog) is False
```

- [ ] **Step 2: Run UI integration tests to verify they fail**

Run:

```bash
uv run pytest tests/test_config_editor_tender_import.py -q
```

Expected: FAIL because methods and imports do not exist.

- [ ] **Step 3: Add imports to `bid_writer/config_editor_dialog.py`**

Add near existing imports:

```python
from .tender_import_dialog import confirm_low_confidence
from .tender_import_service import TenderImportError, TenderImportService
```

- [ ] **Step 4: Add variables in `_create_variables()`**

In `ConfigEditorDialog._create_variables()`, after project variables are created, initialize a status variable:

```python
        self.tender_import_status_var = tk.StringVar(value="")
```

If tests instantiate `__new__`, keep methods tolerant of the attribute already being set by tests.

- [ ] **Step 5: Add import button in `_build_project_section()`**

In `ConfigEditorDialog._build_project_section()`, inside `inputs = ttk.LabelFrame(...)` and before the outline row, add:

```python
        if self.is_new_config:
            import_frame = ttk.Frame(inputs)
            import_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
            import_button = ttk.Button(
                import_frame,
                text="从招标文件导入...",
                command=self._import_tender_document,
                **_bootstyle_kwargs("secondary"),
            )
            import_button.pack(side=tk.LEFT)
            self._register_tooltip(import_button, "project.tender_import")
            ttk.Label(
                import_frame,
                textvariable=self.tender_import_status_var,
                style="Muted.TLabel",
            ).pack(side=tk.LEFT, padx=(10, 0))
```

Then shift the existing input rows down by one in new-config mode. Use a local `row_offset = 1 if self.is_new_config else 0` and add it to all rows inside the input section:

```python
        row_offset = 1 if self.is_new_config else 0
        self._add_path_row(inputs, 0 + row_offset, outline_file_label, ...)
        self._add_mode_selector(inputs, 1 + row_offset, ...)
```

Apply this row offset consistently through scoring rows.

- [ ] **Step 6: Add import methods to `ConfigEditorDialog`**

Add methods near `_browse_path()`:

```python
    def _can_import_tender_document(self) -> bool:
        return bool(getattr(self, "is_new_config", False))

    def _import_tender_document(self) -> None:
        if not self._can_import_tender_document():
            messagebox.showwarning("不可用", "招标文件导入仅支持新建配置流程。", parent=self)
            return
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择招标文件",
            filetypes=[
                ("招标文件", "*.pdf *.docx *.doc *.xlsx *.xls"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx *.doc"),
                ("Excel", "*.xlsx *.xls"),
                ("全部文件", "*.*"),
            ],
        )
        if not selected:
            return
        service = TenderImportService()
        try:
            result = service.import_document(
                source_path=Path(selected),
                project_root=self._current_project_root(),
                confirm_overwrite=self._confirm_tender_overwrite,
                confirm_low_confidence=lambda extraction: confirm_low_confidence(self, extraction),
            )
        except TenderImportError as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror("导入失败", f"{type(exc).__name__}: {exc}", parent=self)
            return
        if result.cancelled:
            self.tender_import_status_var.set("已取消写入，未修改配置路径。")
            return
        self._apply_tender_import_result(result)
        messagebox.showinfo("导入完成", "已抽取项目采购需求和评分标准，并填入当前新建配置。", parent=self)

    def _confirm_tender_overwrite(self, path: Path) -> bool:
        return messagebox.askyesno(
            "确认覆盖",
            f"{path.name} 已存在且非空。是否覆盖并生成 .bak 备份？",
            parent=self,
        )

    def _apply_tender_import_result(self, result) -> None:
        self.vars["project.bid_requirements_mode"].set("file")
        self.vars["project.scoring_criteria_mode"].set("file")
        self.vars["project.bid_requirements_file"].set(result.relative_requirements_path)
        self.vars["project.scoring_criteria_file"].set(result.relative_scoring_path)
        if hasattr(self, "_update_mode_visibility"):
            self._update_mode_visibility()
        self.tender_import_status_var.set(f"导入完成：{result.import_dir.name}")
        self._schedule_refresh()
```

- [ ] **Step 7: Add tooltip**

In `bid_writer/config_editor_tooltips.py`, add:

```python
    "project.tender_import": "从单个 Word、Excel 或可复制文字 PDF 招标文件中抽取项目采购需求和评分标准，并写入项目要求 Markdown 文件。暂不支持 OCR、.wps 或 .et。",
```

- [ ] **Step 8: Run UI integration tests**

Run:

```bash
uv run pytest tests/test_config_editor_tender_import.py tests/test_config_editor_dialog.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit UI wiring**

Run:

```bash
git add bid_writer/config_editor_dialog.py bid_writer/config_editor_tooltips.py tests/test_config_editor_tender_import.py tests/test_config_editor_dialog.py
git commit -m "feat: wire tender import into new config dialog"
```

Expected: commit succeeds.

---

### Task 9: Add Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/config_schema.md`
- Test: none

- [ ] **Step 1: Update README usage flow**

In `README.md`, in the “使用流程” section after the existing new-config explanation, add:

```markdown
### 新建配置中导入招标文件

在“项目 -> 新建配置...”窗口中，可以点击“从招标文件导入...”选择一个招标文件。当前支持：

- 可复制文字的 `.pdf`
- `.docx`
- `.xlsx`
- `.doc`（需要本机可用的 LibreOffice 进行预转换）
- `.xls`（优先通过 `python-calamine` 读取，必要时需要 LibreOffice 预转换）

导入时系统会先转换为 Markdown，再定位并原文摘录“项目采购需求”和“评分标准”，写入：

- `项目要求/项目采购需求.md`
- `项目要求/评分标准.md`

然后自动把这两个路径填入新建配置表单。当前版本不做 OCR，不支持扫描件 PDF、`.wps`、`.et`、OFD、图片或压缩包。若目标文件已存在且非空，系统会确认后覆盖并生成 `.bak` 备份；低置信度抽取会要求用户预览确认后再写入。
```

- [ ] **Step 2: Update config schema doc**

In `docs/config_schema.md`, after section `3.1.2 大纲准备与锁定`, add:

```markdown
### 3.1.3 新建配置导入招标文件

新建配置窗口支持从单个招标文件导入采购需求和评分标准。该功能不会新增 YAML schema 字段，而是写入现有输入文件路径：

```yaml
project:
  inputs:
    bid_requirements_file: "./项目要求/项目采购需求.md"
    scoring_criteria_file: "./项目要求/评分标准.md"
```

转换中间产物保存在 `project.root_dir` 下的 `.bid_writer/imports/<import_id>/`，包括完整转换 Markdown、来源映射 JSON 和抽取报告 JSON。正式进入生成链路的仍只有 `project.inputs.bid_requirements_file` 与 `project.inputs.scoring_criteria_file` 指向的 Markdown 文件。

当前导入仅支持单个文件，支持可复制文字 PDF、DOCX、XLSX、DOC、XLS；不支持 OCR、扫描件 PDF、WPS 原生 `.wps` / `.et`、OFD、图片或压缩包。
```

- [ ] **Step 3: Run doc-adjacent smoke tests**

Run:

```bash
uv run pytest tests/test_config_schema.py tests/test_config_editor_tooltips.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add README.md docs/config_schema.md
git commit -m "docs: describe tender document import"
```

Expected: commit succeeds.

---

### Task 10: Run Full Verification

**Files:**
- No file edits expected unless verification reveals failures.

- [ ] **Step 1: Run focused tender import suite**

Run:

```bash
uv run pytest tests/test_tender_import_models.py tests/test_tender_section_extractor.py tests/test_tender_markdown_converter.py tests/test_tender_import_service.py tests/test_tender_import_dialog.py tests/test_config_editor_tender_import.py -q
```

Expected: PASS.

- [ ] **Step 2: Run config editor regression suite**

Run:

```bash
uv run pytest tests/test_config_editor.py tests/test_config_editor_dialog.py tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended files are changed or already committed.

- [ ] **Step 5: Commit any verification fixes**

If Step 1-3 required fixes, commit them:

```bash
git add <fixed-files>
git commit -m "test: stabilize tender import flow"
```

Expected: commit succeeds if fixes were needed; skip this step if no files changed.

---

## Self-Review Checklist

- Spec coverage:
  - Single-file import only: Task 8 file dialog uses `askopenfilename`, not multi-select.
  - No WPS parsing: Task 4 rejects `.wps` / `.et`.
  - Existing target overwrite confirmation and `.bak`: Task 6.
  - Low-confidence confirmation: Task 7 and Task 8.
  - New-config-only UI: Task 8.
  - No OCR: Task 4/5 PDF no-text error.

- Type consistency:
  - `TenderConversionResult`, `TenderSectionExtraction`, and `TenderImportResult` names are used consistently.
  - Service callbacks are `confirm_overwrite(Path) -> bool` and `confirm_low_confidence(TenderSectionExtraction) -> bool`.
  - Config editor paths are written to `project.bid_requirements_file` and `project.scoring_criteria_file` variables.

- Verification:
  - All test commands use `uv run`.
  - Full suite command is included.
