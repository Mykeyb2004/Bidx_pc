"""招标文件导入服务：转换、抽取、写入项目资料文件。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tender_import_models import TenderSectionExtraction, dump_extraction_report
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
