# Manual Tender Section Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require human confirmation after tender document extraction so “项目采购需求” and “评分标准” are written only after the user reviews or adjusts the selected Markdown.

**Architecture:** Keep the conversion and automatic extraction pipeline, but insert a UI-free confirmation contract before target-file writes. Add a pure selection model for block-to-Markdown range mapping, then build a Tk confirmation dialog on top of it and wire the wizard to call that dialog every time “开始抽取” runs.

**Tech Stack:** Python 3.10+, Tkinter/ttk, existing tender import models/converter/extractor, pytest, `uv run`.

---

## File Structure

- Modify `bid_writer/tender_import_models.py`
  - Add `ManualTenderSectionSelection` and `ManualTenderConfirmationResult`.
  - Extend extraction report serialization to include optional manual confirmation metadata.

- Create `bid_writer/tender_selection_model.py`
  - Pure, Tk-free selection model.
  - Builds full converted Markdown text from `ConvertedBlock` objects.
  - Maps block ids to character ranges.
  - Creates default selections from `TenderExtractionResult`.
  - Expands selections to adjacent blocks and extracts selected Markdown.
  - Runs lightweight validation warnings for requirement/scoring selections.

- Modify `bid_writer/tender_import_service.py`
  - Replace `confirm_low_confidence` with mandatory `confirm_sections`.
  - Always call `confirm_sections` after conversion/extraction/report generation.
  - Allow incomplete automatic extraction to proceed to manual confirmation.
  - Write only the Markdown returned by the manual confirmation result.
  - Preserve overwrite confirmation and `.bak` backup behavior.

- Modify `bid_writer/tender_import_dialog.py`
  - Keep `build_low_confidence_preview()` temporarily so existing preview tests still pass, but stop using it in the wizard.
  - Add `ManualTenderSectionConfirmDialog`.
  - Add `confirm_tender_sections(parent, *, conversion, extraction, **kwargs)`.
  - Use a three-column layout: control panel, rendered Markdown block view, source Markdown text.
  - Support default selection, block click selection, source text dragging, expand previous/next, and save buttons.

- Modify `bid_writer/new_config_wizard.py`
  - Import and call `confirm_tender_sections`.
  - Pass it to `TenderImportService.import_document(confirm_sections=...)`.
  - Update cancellation status text for manual confirmation cancellation.
  - Remove the low-confidence-only confirmation path from the wizard.

- Modify `tests/test_tender_import_service.py`
  - Update existing service tests to provide `confirm_sections`.
  - Add tests proving target files are not written without manual confirmation and incomplete extraction can be manually completed.

- Create `tests/test_tender_selection_model.py`
  - Cover default selection mapping, missing defaults, adjacent expansion, selected Markdown extraction, and warning logic.

- Modify `tests/test_tender_import_dialog.py`
  - Add tests for pure dialog helper functions and lightweight dialog model behavior that can run without a display.

- Modify `tests/test_new_config_wizard.py`
  - Update `_run_import()` test to assert the wizard passes mandatory manual confirmation into the service.

---

## Task 1: Manual Confirmation Models

**Files:**
- Modify: `bid_writer/tender_import_models.py`
- Modify: `tests/test_tender_import_service.py`
- Modify: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Write failing model assertions**

Append these imports and assertions to existing tests where they are closest to current coverage.

In `tests/test_tender_import_service.py`, add:

```python
from bid_writer.tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
)
```

Add this test:

```python
def test_manual_confirmation_result_carries_final_markdown():
    confirmation = ManualTenderConfirmationResult(
        requirements=ManualTenderSectionSelection(
            section_key="bid_requirements",
            markdown="# 项目采购需求\n\n人工确认需求",
            start_block_id="r1",
            end_block_id="r2",
            manually_adjusted=True,
        ),
        scoring=ManualTenderSectionSelection(
            section_key="scoring_criteria",
            markdown="# 评分标准\n\n人工确认评分",
            start_block_id="s1",
            end_block_id="s2",
            manually_adjusted=False,
        ),
    )

    assert confirmation.requirements.markdown.endswith("人工确认需求")
    assert confirmation.requirements.manually_adjusted is True
    assert confirmation.scoring.manually_adjusted is False
    assert confirmation.cancelled is False
```

In `tests/test_tender_import_dialog.py`, add:

```python
from bid_writer.tender_import_models import ManualTenderSectionSelection
```

Add this test:

```python
def test_manual_selection_dataclass_keeps_block_range():
    selection = ManualTenderSectionSelection(
        section_key="bid_requirements",
        markdown="需求",
        start_block_id="b1",
        end_block_id="b3",
        manually_adjusted=True,
    )

    assert selection.section_key == "bid_requirements"
    assert selection.start_block_id == "b1"
    assert selection.end_block_id == "b3"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_manual_confirmation_result_carries_final_markdown tests/test_tender_import_dialog.py::test_manual_selection_dataclass_keeps_block_range -q
```

Expected: FAIL with `ImportError` because `ManualTenderConfirmationResult` and `ManualTenderSectionSelection` do not exist.

- [ ] **Step 3: Implement the model classes**

In `bid_writer/tender_import_models.py`, add after `TenderSectionExtraction`:

```python
@dataclass(frozen=True)
class ManualTenderSectionSelection:
    section_key: str
    markdown: str
    start_block_id: str | None = None
    end_block_id: str | None = None
    manually_adjusted: bool = False


@dataclass(frozen=True)
class ManualTenderConfirmationResult:
    requirements: ManualTenderSectionSelection | None = None
    scoring: ManualTenderSectionSelection | None = None
    cancelled: bool = False
```

Add helper serialization below `_result_to_dict()`:

```python
def _manual_selection_to_dict(selection: ManualTenderSectionSelection | None) -> dict[str, Any] | None:
    if selection is None:
        return None
    return asdict(selection)
```

Change `dump_extraction_report()` signature and return payload:

```python
def dump_extraction_report(
    extraction: TenderSectionExtraction,
    manual_confirmation: ManualTenderConfirmationResult | None = None,
) -> dict[str, Any]:
    payload = {
        "requirements": _result_to_dict(extraction.requirements),
        "scoring": _result_to_dict(extraction.scoring),
        "candidates": [asdict(candidate) for candidate in extraction.candidates],
        "warnings": list(extraction.warnings),
        "complete": extraction.is_complete,
        "needs_confirmation": extraction.needs_confirmation,
    }
    if manual_confirmation is not None:
        payload["manual_confirmation"] = {
            "requirements": _manual_selection_to_dict(manual_confirmation.requirements),
            "scoring": _manual_selection_to_dict(manual_confirmation.scoring),
            "cancelled": manual_confirmation.cancelled,
        }
    return payload
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_manual_confirmation_result_carries_final_markdown tests/test_tender_import_dialog.py::test_manual_selection_dataclass_keeps_block_range tests/test_tender_import_models.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/tender_import_models.py tests/test_tender_import_service.py tests/test_tender_import_dialog.py
git commit -m "feat: add manual tender confirmation models"
```

Expected: commit succeeds.

---

## Task 2: Pure Markdown Selection Model

**Files:**
- Create: `bid_writer/tender_selection_model.py`
- Create: `tests/test_tender_selection_model.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tender_selection_model.py`:

```python
from bid_writer.tender_import_models import ConvertedBlock, TenderExtractionResult
from bid_writer.tender_selection_model import (
    TenderSelectionDocument,
    build_default_selection,
    expand_selection_to_next_block,
    expand_selection_to_previous_block,
    selection_to_markdown,
    validate_selection_markdown,
)


def _block(block_id: str, markdown: str, order: int, block_type: str = "paragraph", heading_level=None):
    return ConvertedBlock(
        block_id=block_id,
        source_file="tender.md",
        source_type="md",
        block_type=block_type,
        markdown=markdown,
        text=markdown.replace("#", "").strip(),
        order_index=order,
        heading_level=heading_level,
        heading_title=markdown.replace("#", "").strip() if heading_level else "",
    )


def _document():
    return TenderSelectionDocument.from_blocks(
        [
            _block("h1", "## 项目采购需求", 1, "heading", 2),
            _block("r1", "服务内容包括调查、成果提交和验收。", 2),
            _block("r2", "技术要求应满足采购范围。", 3),
            _block("h2", "## 评分标准", 4, "heading", 2),
            _block("s1", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", 5, "table"),
        ]
    )


def test_document_joins_blocks_and_records_ranges():
    document = _document()

    assert document.markdown.startswith("## 项目采购需求")
    assert document.block_ranges["h1"].start == 0
    assert document.block_ranges["r1"].start > document.block_ranges["h1"].end
    assert document.ordered_block_ids == ["h1", "r1", "r2", "h2", "s1"]


def test_build_default_selection_maps_extraction_block_ids():
    document = _document()
    extraction = TenderExtractionResult(
        section_key="bid_requirements",
        title="项目采购需求",
        markdown="",
        start_block_id="h1",
        end_block_id="r2",
        confidence=0.9,
    )

    selection = build_default_selection(document, extraction)

    assert selection is not None
    assert selection.start_block_id == "h1"
    assert selection.end_block_id == "r2"
    assert "项目采购需求" in selection_to_markdown(document, selection)
    assert "评分标准" not in selection_to_markdown(document, selection)


def test_build_default_selection_returns_none_for_missing_extraction_or_blocks():
    document = _document()
    missing = TenderExtractionResult("bid_requirements", "需求", "", "missing", "r2", 0.1)

    assert build_default_selection(document, None) is None
    assert build_default_selection(document, missing) is None


def test_expand_selection_to_adjacent_blocks():
    document = _document()
    selection = build_default_selection(
        document,
        TenderExtractionResult("bid_requirements", "项目采购需求", "", "r1", "r1", 0.9),
    )

    previous = expand_selection_to_previous_block(document, selection)
    expanded = expand_selection_to_next_block(document, previous)

    assert previous.start_block_id == "h1"
    assert previous.end_block_id == "r1"
    assert expanded.start_block_id == "h1"
    assert expanded.end_block_id == "r2"


def test_selection_to_markdown_uses_character_range():
    document = _document()
    selection = build_default_selection(
        document,
        TenderExtractionResult("scoring_criteria", "评分标准", "", "h2", "s1", 0.9),
    )

    markdown = selection_to_markdown(document, selection)

    assert markdown.startswith("## 评分标准")
    assert "10分" in markdown
    assert "项目采购需求" not in markdown


def test_validate_selection_markdown_warns_for_empty_short_and_suspicious_content():
    assert "不能为空" in validate_selection_markdown("bid_requirements", "")[0]
    assert "内容较短" in validate_selection_markdown("bid_requirements", "短")[0]
    assert any("可能不是项目采购需求" in item for item in validate_selection_markdown("bid_requirements", "只有一句普通说明但没有关键词" * 3))
    assert any("可能不是评分标准" in item for item in validate_selection_markdown("scoring_criteria", "普通说明文字" * 10))
    assert validate_selection_markdown("scoring_criteria", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |") == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_tender_selection_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.tender_selection_model'`.

- [ ] **Step 3: Implement the selection model**

Create `bid_writer/tender_selection_model.py`:

```python
"""Pure selection helpers for manual tender section confirmation."""

from __future__ import annotations

from dataclasses import dataclass

from .tender_import_models import ConvertedBlock, ManualTenderSectionSelection, TenderExtractionResult


REQUIREMENT_TERMS = ("服务", "技术", "要求", "内容", "范围", "参数", "成果", "验收", "采购")
SCORING_TERMS = ("评分", "评审", "分值", "满分", "权重", "得分")


@dataclass(frozen=True)
class TextRange:
    start: int
    end: int


@dataclass(frozen=True)
class TenderSelectionDocument:
    markdown: str
    blocks: list[ConvertedBlock]
    block_ranges: dict[str, TextRange]
    ordered_block_ids: list[str]

    @classmethod
    def from_blocks(cls, blocks: list[ConvertedBlock]) -> "TenderSelectionDocument":
        ordered = sorted(blocks, key=lambda item: item.order_index)
        parts: list[str] = []
        ranges: dict[str, TextRange] = {}
        cursor = 0
        for block in ordered:
            if parts:
                parts.append("\n\n")
                cursor += 2
            markdown = block.markdown.strip()
            start = cursor
            parts.append(markdown)
            cursor += len(markdown)
            ranges[block.block_id] = TextRange(start=start, end=cursor)
        return cls(
            markdown="".join(parts),
            blocks=ordered,
            block_ranges=ranges,
            ordered_block_ids=[block.block_id for block in ordered],
        )


def build_default_selection(
    document: TenderSelectionDocument,
    extraction: TenderExtractionResult | None,
) -> ManualTenderSectionSelection | None:
    if extraction is None:
        return None
    if extraction.start_block_id not in document.block_ranges or extraction.end_block_id not in document.block_ranges:
        return None
    markdown = selection_to_markdown(
        document,
        ManualTenderSectionSelection(
            section_key=extraction.section_key,
            markdown="",
            start_block_id=extraction.start_block_id,
            end_block_id=extraction.end_block_id,
            manually_adjusted=False,
        ),
    )
    return ManualTenderSectionSelection(
        section_key=extraction.section_key,
        markdown=markdown,
        start_block_id=extraction.start_block_id,
        end_block_id=extraction.end_block_id,
        manually_adjusted=False,
    )


def selection_to_markdown(document: TenderSelectionDocument, selection: ManualTenderSectionSelection) -> str:
    if selection.start_block_id is None or selection.end_block_id is None:
        return selection.markdown.strip()
    start_range = document.block_ranges.get(selection.start_block_id)
    end_range = document.block_ranges.get(selection.end_block_id)
    if start_range is None or end_range is None:
        return selection.markdown.strip()
    start = min(start_range.start, end_range.start)
    end = max(start_range.end, end_range.end)
    return document.markdown[start:end].strip()


def expand_selection_to_previous_block(
    document: TenderSelectionDocument,
    selection: ManualTenderSectionSelection,
) -> ManualTenderSectionSelection:
    if selection.start_block_id not in document.ordered_block_ids:
        return selection
    index = document.ordered_block_ids.index(selection.start_block_id)
    if index <= 0:
        return selection
    return _replace_block_range(
        document,
        selection,
        start_block_id=document.ordered_block_ids[index - 1],
        end_block_id=selection.end_block_id,
    )


def expand_selection_to_next_block(
    document: TenderSelectionDocument,
    selection: ManualTenderSectionSelection,
) -> ManualTenderSectionSelection:
    if selection.end_block_id not in document.ordered_block_ids:
        return selection
    index = document.ordered_block_ids.index(selection.end_block_id)
    if index >= len(document.ordered_block_ids) - 1:
        return selection
    return _replace_block_range(
        document,
        selection,
        start_block_id=selection.start_block_id,
        end_block_id=document.ordered_block_ids[index + 1],
    )


def _replace_block_range(
    document: TenderSelectionDocument,
    selection: ManualTenderSectionSelection,
    *,
    start_block_id: str | None,
    end_block_id: str | None,
) -> ManualTenderSectionSelection:
    updated = ManualTenderSectionSelection(
        section_key=selection.section_key,
        markdown="",
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        manually_adjusted=True,
    )
    return ManualTenderSectionSelection(
        section_key=selection.section_key,
        markdown=selection_to_markdown(document, updated),
        start_block_id=start_block_id,
        end_block_id=end_block_id,
        manually_adjusted=True,
    )


def validate_selection_markdown(section_key: str, markdown: str) -> list[str]:
    text = markdown.strip()
    if not text:
        return ["选区不能为空。"]
    warnings: list[str] = []
    if len(text) < 20:
        warnings.append("选区内容较短，请确认是否完整。")
    if section_key == "bid_requirements":
        hits = sum(1 for term in REQUIREMENT_TERMS if term in text)
        if hits < 2:
            warnings.append("当前内容可能不是项目采购需求，请确认。")
    elif section_key == "scoring_criteria":
        has_table = "|" in text and "---" in text
        hits = sum(1 for term in SCORING_TERMS if term in text)
        if hits < 2 and not has_table:
            warnings.append("当前内容可能不是评分标准，请确认。")
    return warnings
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_tender_selection_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/tender_selection_model.py tests/test_tender_selection_model.py
git commit -m "feat: add tender markdown selection model"
```

Expected: commit succeeds.

---

## Task 3: Mandatory Confirmation In Import Service

**Files:**
- Modify: `bid_writer/tender_import_service.py`
- Modify: `tests/test_tender_import_service.py`

- [ ] **Step 1: Update service tests to the new contract**

In `tests/test_tender_import_service.py`, update imports:

```python
from bid_writer.tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderExtractionResult,
    TenderSectionExtraction,
)
```

Add helper:

```python
def _confirmation(requirements="# 项目采购需求\n\n人工需求\n", scoring="# 评分标准\n\n人工评分\n"):
    return ManualTenderConfirmationResult(
        requirements=ManualTenderSectionSelection(
            "bid_requirements",
            requirements,
            "r1",
            "r2",
            manually_adjusted=False,
        ),
        scoring=ManualTenderSectionSelection(
            "scoring_criteria",
            scoring,
            "s1",
            "s2",
            manually_adjusted=False,
        ),
    )
```

In existing `service.import_document(...)` calls, replace:

```python
confirm_low_confidence=lambda _extraction: True,
```

with:

```python
confirm_sections=lambda **_kwargs: _confirmation(),
```

For the existing cancellation test, rename it to `test_import_service_stops_when_manual_confirmation_cancelled` and use:

```python
confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(cancelled=True),
```

Update expected output assertions in `test_import_service_writes_outputs_and_report` to expect `人工需求` and `人工评分`, proving the service writes manual content rather than algorithm content:

```python
assert result.requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n人工需求\n"
assert result.scoring_path.read_text(encoding="utf-8") == "# 评分标准\n\n人工评分\n"
```

Add this test:

```python
def test_import_service_allows_manual_completion_when_extractor_misses_sections(tmp_path: Path):
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
    extraction = TenderSectionExtraction(requirements=None, scoring=None, warnings=("未定位到章节",))
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_sections=lambda **_kwargs: _confirmation(),
    )

    assert result.cancelled is False
    assert result.requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n人工需求\n"
    assert result.scoring_path.read_text(encoding="utf-8") == "# 评分标准\n\n人工评分\n"
```

Add this test:

```python
def test_import_service_does_not_write_when_confirmation_returns_incomplete_result(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction()
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(
            requirements=ManualTenderSectionSelection("bid_requirements", "需求", None, None, True),
            scoring=None,
            cancelled=True,
        ),
    )

    assert result.cancelled is True
    assert not (tmp_path / "项目要求" / "项目采购需求.md").exists()
    assert not (tmp_path / "项目要求" / "评分标准.md").exists()
```

- [ ] **Step 2: Run service tests to verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_service.py -q
```

Expected: FAIL with `TypeError` because `import_document()` does not accept `confirm_sections`.

- [ ] **Step 3: Update `TenderImportService.import_document()`**

In `bid_writer/tender_import_service.py`, update imports:

```python
from .tender_import_models import (
    ManualTenderConfirmationResult,
    TenderConversionResult,
    TenderSectionExtraction,
    dump_extraction_report,
)
```

Add a type alias near the dataclass:

```python
ConfirmSectionsCallback = Callable[..., ManualTenderConfirmationResult]
```

Change `import_document()` signature:

```python
def import_document(
    self,
    *,
    source_path: Path,
    project_root: Path,
    confirm_overwrite: Callable[[Path], bool],
    confirm_sections: ConfirmSectionsCallback,
    import_dir: Path | None = None,
) -> TenderImportResult:
```

Replace the old incomplete/low-confidence block with:

```python
target_dir = project_root / "项目要求"
requirements_path = target_dir / "项目采购需求.md"
scoring_path = target_dir / "评分标准.md"
confirmation = confirm_sections(
    conversion=conversion,
    extraction=extraction,
    requirements_path=requirements_path,
    scoring_path=scoring_path,
)
report_path.write_text(
    json.dumps(dump_extraction_report(extraction, confirmation), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if confirmation.cancelled or confirmation.requirements is None or confirmation.scoring is None:
    return TenderImportResult(
        requirements_path=None,
        scoring_path=None,
        relative_requirements_path="./项目要求/项目采购需求.md",
        relative_scoring_path="./项目要求/评分标准.md",
        import_dir=import_dir,
        extraction_report_path=report_path,
        extraction=extraction,
        cancelled=True,
        created_paths=(*self._conversion_created_paths(conversion, import_dir), report_path),
    )

target_dir.mkdir(parents=True, exist_ok=True)
self._write_target(requirements_path, confirmation.requirements.markdown, confirm_overwrite)
self._write_target(scoring_path, confirmation.scoring.markdown, confirm_overwrite)
```

Keep the final `TenderImportResult` structure, but ensure target files are added to `created_paths` only after writes.

- [ ] **Step 4: Remove stale low-confidence behavior from service tests**

Search:

```bash
rg -n "confirm_low_confidence|needs_confirmation|未能同时抽取" tests/test_tender_import_service.py bid_writer/tender_import_service.py
```

Expected after edits:

- `confirm_low_confidence` has no matches in `tender_import_service.py` or service tests.
- `needs_confirmation` may still exist in models and reports.
- `未能同时抽取` has no match in `tender_import_service.py`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py tests/test_tender_import_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/tender_import_service.py tests/test_tender_import_service.py tests/test_tender_import_models.py
git commit -m "feat: require manual confirmation before tender import writes"
```

Expected: commit succeeds.

---

## Task 4: Manual Confirmation Dialog Helpers And Tk Window

**Files:**
- Modify: `bid_writer/tender_import_dialog.py`
- Modify: `tests/test_tender_import_dialog.py`

- [ ] **Step 1: Write tests for dialog helper behavior**

In `tests/test_tender_import_dialog.py`, add imports:

```python
from pathlib import Path

from bid_writer.tender_import_dialog import (
    SECTION_LABELS,
    build_confirmation_status,
    build_initial_section_selection,
)
from bid_writer.tender_import_models import ConvertedBlock, TenderConversionResult
```

Add helper:

```python
def _conversion() -> TenderConversionResult:
    blocks = [
        ConvertedBlock("r0", "tender.md", "md", "heading", "## 项目采购需求", "项目采购需求", 1, heading_level=2, heading_title="项目采购需求"),
        ConvertedBlock("r1", "tender.md", "md", "paragraph", "服务内容包括成果提交和验收。", "服务内容包括成果提交和验收。", 2),
        ConvertedBlock("s0", "tender.md", "md", "heading", "## 评分标准", "评分标准", 3, heading_level=2, heading_title="评分标准"),
        ConvertedBlock("s1", "tender.md", "md", "table", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", "| 评分项 | 分值 |", 4),
    ]
    return TenderConversionResult(
        source_path=Path("tender.md"),
        output_dir=Path(".bid_writer/imports/test"),
        converted_markdown_path=Path(".bid_writer/imports/test/converted.md"),
        conversion_map_path=Path(".bid_writer/imports/test/conversion_map.json"),
        blocks=blocks,
    )
```

Add tests:

```python
def test_section_labels_match_required_flow():
    assert SECTION_LABELS["bid_requirements"] == "项目采购需求"
    assert SECTION_LABELS["scoring_criteria"] == "评分标准"


def test_build_initial_section_selection_uses_extraction_default():
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "", "r0", "r1", 0.91),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "", "s0", "s1", 0.92),
    )
    document, requirements, scoring = build_initial_section_selection(_conversion(), extraction)

    assert requirements is not None
    assert scoring is not None
    assert "服务内容" in requirements.markdown
    assert "10分" in scoring.markdown
    assert document.markdown.startswith("## 项目采购需求")


def test_build_initial_section_selection_handles_missing_extraction():
    document, requirements, scoring = build_initial_section_selection(_conversion(), TenderSectionExtraction())

    assert requirements is None
    assert scoring is None
    assert "评分标准" in document.markdown


def test_build_confirmation_status_mentions_missing_auto_location():
    status = build_confirmation_status("bid_requirements", None, [])

    assert "未自动定位" in status
    assert "项目采购需求" in status


def test_build_confirmation_status_includes_warnings():
    selection = ManualTenderSectionSelection("scoring_criteria", "普通文字" * 20, None, None, True)
    status = build_confirmation_status("scoring_criteria", selection, ["当前内容可能不是评分标准，请确认。"])

    assert "评分标准" in status
    assert "可能不是评分标准" in status
```

- [ ] **Step 2: Run helper tests to verify failure**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py -q
```

Expected: FAIL because the new helpers do not exist.

- [ ] **Step 3: Add pure dialog helpers**

In `bid_writer/tender_import_dialog.py`, add imports:

```python
import tkinter as tk
from tkinter import ttk

from .tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderConversionResult,
)
from .tender_selection_model import (
    TenderSelectionDocument,
    build_default_selection,
    expand_selection_to_next_block,
    expand_selection_to_previous_block,
    validate_selection_markdown,
)
```

Add constants and helpers:

```python
SECTION_LABELS = {
    "bid_requirements": "项目采购需求",
    "scoring_criteria": "评分标准",
}


def build_initial_section_selection(
    conversion: TenderConversionResult,
    extraction: TenderSectionExtraction,
) -> tuple[TenderSelectionDocument, ManualTenderSectionSelection | None, ManualTenderSectionSelection | None]:
    document = TenderSelectionDocument.from_blocks(conversion.blocks)
    requirements = build_default_selection(document, extraction.requirements)
    scoring = build_default_selection(document, extraction.scoring)
    return document, requirements, scoring


def build_confirmation_status(
    section_key: str,
    selection: ManualTenderSectionSelection | None,
    warnings: list[str],
) -> str:
    label = SECTION_LABELS[section_key]
    parts = [label]
    if selection is None:
        parts.append("未自动定位，请手动选择。")
    elif selection.manually_adjusted:
        parts.append("已手动调整选区。")
    else:
        parts.append("已根据自动定位默认选中。")
    parts.extend(warnings)
    return "\n".join(parts)
```

- [ ] **Step 4: Implement `ManualTenderSectionConfirmDialog`**

In the same file, add a dialog class with these public behaviors:

```python
class ManualTenderSectionConfirmDialog(tk.Toplevel):
    section_order = ("bid_requirements", "scoring_criteria")

    def __init__(self, parent, conversion: TenderConversionResult, extraction: TenderSectionExtraction):
        super().__init__(parent)
        self.title("招标文件资料确认")
        self.transient(parent)
        self.grab_set()
        self.document, requirements, scoring = build_initial_section_selection(conversion, extraction)
        self.selections = {
            "bid_requirements": requirements,
            "scoring_criteria": scoring,
        }
        self.confirmed: dict[str, ManualTenderSectionSelection] = {}
        self.current_index = 0
        self.result = ManualTenderConfirmationResult(cancelled=True)
        self.status_var = tk.StringVar(value="")
        self._create_widgets()
        self._load_current_section()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
```

Implement `_create_widgets()` with a `ttk.PanedWindow` or grid. The rendered Markdown block view is a Tk `Text` widget with simple tags; it must not add a Markdown/WebView dependency:

- Left `ttk.Frame`: labels, status text, previous/next expand buttons, save button, cancel button.
- Middle `tk.Text`: rendered-ish view. Insert each block with simple tags:
  - headings: larger/bold tag where supported by `tkinter.font`.
  - tables: monospace tag.
  - selected block range: yellow background tag.
- Right `tk.Text`: source Markdown full text with native text selection.

Implement these methods:

```python
def _load_current_section(self) -> None:
    section_key = self.section_order[self.current_index]
    self.source_text.delete("1.0", tk.END)
    self.source_text.insert("1.0", self.document.markdown)
    self._render_blocks()
    selection = self.selections.get(section_key)
    if selection is not None:
        self._apply_source_selection(selection)
    self._sync_status()

def _apply_source_selection(self, selection: ManualTenderSectionSelection) -> None:
    markdown = selection.markdown.strip()
    if not markdown:
        return
    start = self.document.markdown.find(markdown)
    if start < 0:
        return
    end = start + len(markdown)
    self.source_text.tag_remove(tk.SEL, "1.0", tk.END)
    self.source_text.tag_add(tk.SEL, f"1.0+{start}c", f"1.0+{end}c")
    self.source_text.see(f"1.0+{start}c")

def _current_source_markdown(self) -> str:
    try:
        return self.source_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
    except tk.TclError:
        section_key = self.section_order[self.current_index]
        selection = self.selections.get(section_key)
        return "" if selection is None else selection.markdown.strip()
```

Implement save behavior:

```python
def _save_current_section(self) -> None:
    section_key = self.section_order[self.current_index]
    markdown = self._current_source_markdown()
    warnings = validate_selection_markdown(section_key, markdown)
    blocking = [item for item in warnings if "不能为空" in item]
    if blocking:
        messagebox.showwarning("选区无效", "\n".join(blocking), parent=self)
        return
    if warnings and not messagebox.askyesno("确认存入", "\n".join(warnings) + "\n是否继续存入？", parent=self):
        return
    previous = self.selections.get(section_key)
    selection = ManualTenderSectionSelection(
        section_key=section_key,
        markdown=markdown,
        start_block_id=None if previous is None else previous.start_block_id,
        end_block_id=None if previous is None else previous.end_block_id,
        manually_adjusted=True if previous is None else previous.manually_adjusted,
    )
    self.confirmed[section_key] = selection
    if self.current_index == 0:
        self.current_index = 1
        self._load_current_section()
        return
    self.result = ManualTenderConfirmationResult(
        requirements=self.confirmed.get("bid_requirements"),
        scoring=self.confirmed.get("scoring_criteria"),
        cancelled=False,
    )
    self.destroy()
```

Implement `_expand_previous()` and `_expand_next()` using `expand_selection_to_previous_block()` and `expand_selection_to_next_block()` when there is an existing block-based selection.

Implement `_cancel()`:

```python
def _cancel(self) -> None:
    self.result = ManualTenderConfirmationResult(
        requirements=self.confirmed.get("bid_requirements"),
        scoring=self.confirmed.get("scoring_criteria"),
        cancelled=True,
    )
    self.destroy()
```

Add public function:

```python
def confirm_tender_sections(parent, *, conversion: TenderConversionResult, extraction: TenderSectionExtraction, **_kwargs) -> ManualTenderConfirmationResult:
    dialog = ManualTenderSectionConfirmDialog(parent, conversion, extraction)
    parent.wait_window(dialog)
    return dialog.result
```

- [ ] **Step 5: Run dialog tests**

Run:

```bash
uv run pytest tests/test_tender_import_dialog.py tests/test_tender_selection_model.py -q
```

Expected: PASS. If headless Tk prevents constructing the full dialog in tests, keep tests focused on pure helpers and rely on manual GUI smoke testing in Task 7.

- [ ] **Step 6: Commit**

Run:

```bash
git add bid_writer/tender_import_dialog.py tests/test_tender_import_dialog.py
git commit -m "feat: add manual tender confirmation dialog"
```

Expected: commit succeeds.

---

## Task 5: Wire The New Config Wizard To Mandatory Confirmation

**Files:**
- Modify: `bid_writer/new_config_wizard.py`
- Modify: `tests/test_new_config_wizard.py`

- [ ] **Step 1: Update wizard test for new callback**

In `tests/test_new_config_wizard.py`, in `test_run_import_updates_material_paths_and_records_only_new_paths`, replace the fake service method with:

```python
class FakeService:
    def import_document(self, **kwargs):
        assert "confirm_sections" in kwargs
        assert "confirm_low_confidence" not in kwargs
        confirmation = kwargs["confirm_sections"](
            conversion=SimpleNamespace(blocks=[]),
            extraction=SimpleNamespace(),
            requirements_path=existing_requirements,
            scoring_path=scoring,
        )
        assert confirmation.cancelled is False
        report.parent.mkdir(parents=True)
        report.write_text("{}", encoding="utf-8")
        converted.write_text("converted", encoding="utf-8")
        conversion_map.write_text("{}", encoding="utf-8")
        scoring.write_text("score", encoding="utf-8")
        return FakeResult()
```

Replace the monkeypatch:

```python
monkeypatch.setattr("bid_writer.new_config_wizard.confirm_low_confidence", lambda _parent, _extraction: True)
```

with:

```python
from bid_writer.tender_import_models import ManualTenderConfirmationResult, ManualTenderSectionSelection

monkeypatch.setattr(
    "bid_writer.new_config_wizard.confirm_tender_sections",
    lambda _parent, **_kwargs: ManualTenderConfirmationResult(
        requirements=ManualTenderSectionSelection("bid_requirements", "需求", None, None, True),
        scoring=ManualTenderSectionSelection("scoring_criteria", "评分", None, None, True),
    ),
)
```

Add cancellation test:

```python
def test_run_import_reports_manual_confirmation_cancelled(monkeypatch, tmp_path: Path):
    dialog = _dialog(tmp_path)
    source = tmp_path / "招标文件.pdf"
    source.write_text("fake", encoding="utf-8")
    dialog.state.source_path = source
    dialog.vars["source_path"].set(str(source))

    class FakeResult:
        cancelled = True
        requirements_path = None
        scoring_path = None
        import_dir = tmp_path / ".bid_writer" / "imports" / "pending"
        created_paths = ()

    class FakeService:
        def import_document(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr("bid_writer.new_config_wizard.copy_source_file_if_needed", lambda _state: None)
    monkeypatch.setattr("bid_writer.new_config_wizard.TenderImportService", lambda: FakeService())

    NewConfigWizardDialog._run_import(dialog)

    assert "已取消确认" in dialog.import_status_var.get()
    assert dialog.state.requirements_path is None
    assert dialog.state.scoring_path is None
```

- [ ] **Step 2: Run wizard tests to verify failure**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py::test_run_import_updates_material_paths_and_records_only_new_paths tests/test_new_config_wizard.py::test_run_import_reports_manual_confirmation_cancelled -q
```

Expected: FAIL because `confirm_tender_sections` is not imported or `_run_import()` still passes `confirm_low_confidence`.

- [ ] **Step 3: Update wizard imports and `_run_import()`**

In `bid_writer/new_config_wizard.py`, replace:

```python
from bid_writer.tender_import_dialog import confirm_low_confidence
```

with:

```python
from bid_writer.tender_import_dialog import confirm_tender_sections
```

In `_run_import()`, replace the service call argument:

```python
confirm_low_confidence=lambda extraction: confirm_low_confidence(self, extraction),
```

with:

```python
confirm_sections=lambda **kwargs: confirm_tender_sections(self, **kwargs),
```

Change cancelled status:

```python
if result.cancelled:
    self.import_status_var.set("已取消确认，未完成资料写入。")
    return
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_new_config_wizard.py tests/test_tender_import_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/new_config_wizard.py tests/test_new_config_wizard.py
git commit -m "feat: require manual confirmation in new config wizard"
```

Expected: commit succeeds.

---

## Task 6: Preserve And Extend Import Reports

**Files:**
- Modify: `tests/test_tender_import_service.py`
- Modify: `bid_writer/tender_import_service.py`
- Modify: `bid_writer/tender_import_models.py`

- [ ] **Step 1: Add report assertion for manual confirmation**

In `tests/test_tender_import_service.py`, in `test_import_service_writes_outputs_and_report`, after `assert result.extraction_report_path.exists()`, add:

```python
import json

report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
assert report["manual_confirmation"]["requirements"]["markdown"] == "# 项目采购需求\n\n人工需求\n"
assert report["manual_confirmation"]["scoring"]["markdown"] == "# 评分标准\n\n人工评分\n"
assert report["manual_confirmation"]["cancelled"] is False
```

Add a cancellation report assertion to the cancellation test:

```python
report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
assert report["manual_confirmation"]["cancelled"] is True
```

- [ ] **Step 2: Run report tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py::test_import_service_writes_outputs_and_report tests/test_tender_import_service.py::test_import_service_stops_when_manual_confirmation_cancelled -q
```

Expected: FAIL if the service still writes the report before confirmation or omits manual metadata.

- [ ] **Step 3: Ensure service rewrites report after confirmation**

In `bid_writer/tender_import_service.py`, keep the first report write only if needed for debugging, but always rewrite after confirmation:

```python
def _write_report(self, path: Path, extraction: TenderSectionExtraction, confirmation: ManualTenderConfirmationResult | None = None) -> None:
    path.write_text(
        json.dumps(dump_extraction_report(extraction, confirmation), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

Use it before confirmation with `confirmation=None`, then immediately after `confirm_sections(...)` with the returned confirmation. This preserves a report if the dialog crashes after extraction and records final manual data on normal return.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_tender_import_service.py tests/test_tender_import_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add bid_writer/tender_import_service.py bid_writer/tender_import_models.py tests/test_tender_import_service.py
git commit -m "feat: record manual tender confirmation in reports"
```

Expected: commit succeeds.

---

## Task 7: Full Regression And Manual GUI Smoke Test

**Files:**
- No required code changes unless tests reveal issues.
- Manual smoke may create local project artifacts; keep throwaway outputs out of commits.

- [ ] **Step 1: Run focused import test suite**

Run:

```bash
uv run pytest tests/test_tender_import_models.py tests/test_tender_selection_model.py tests/test_tender_import_dialog.py tests/test_tender_import_service.py tests/test_new_config_wizard.py tests/test_gui_new_config.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run the desktop app for manual smoke**

Run:

```bash
uv run python run.py
```

Manual checks:

- Open “项目 -> 新建配置...” and choose a supported tender file.
- Advance to “项目材料”.
- Click “开始抽取”.
- Confirm that “招标文件资料确认” appears even when automatic extraction has high confidence.
- Confirm step 1 shows 项目采购需求 and can save it.
- Confirm step 2 shows 评分标准 and can save it.
- Confirm the wizard path fields update after both saves.
- Confirm cancelling the confirmation window leaves the wizard on 项目材料 and shows “已取消确认，未完成资料写入。”

Stop the app after the smoke test.

- [ ] **Step 4: Check final git status**

Run:

```bash
git status --short
```

Expected: no uncommitted code/test changes. If manual smoke created local project files, either delete them if they are throwaway outputs or leave them untracked only if they are user-created test material outside the repo.

---

## Implementation Notes

- Use `uv run` for every Python command.
- Do not add new runtime dependencies for Markdown rendering. The first implementation should use Tk `Text` tags for a readable approximation of rendered Markdown.
- Keep service-level confirmation UI-free. The service receives a callback; only `new_config_wizard.py` knows that the callback opens a Tk dialog.
- Do not remove `TenderSectionExtraction.needs_confirmation`; it remains useful in reports and tests even though the wizard now always requires confirmation.
- Avoid changing the automatic extraction algorithm in `tender_section_extractor.py` during this feature. Candidate quality improvements can be a later task.
