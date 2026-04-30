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
