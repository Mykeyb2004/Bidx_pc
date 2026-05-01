"""招标文件导入服务：转换、抽取、写入项目资料文件。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tender_import_models import (
    ManualTenderConfirmationResult,
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
    created_paths: tuple[Path, ...] = ()


ConfirmSectionsCallback = Callable[..., ManualTenderConfirmationResult]


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
        confirm_sections: ConfirmSectionsCallback,
        import_dir: Path | None = None,
    ) -> TenderImportResult:
        project_root = Path(project_root).expanduser().resolve()
        import_dir = (
            Path(import_dir).expanduser().resolve()
            if import_dir is not None
            else project_root / ".bid_writer" / "imports" / self.import_id_factory()
        )
        import_dir.mkdir(parents=True, exist_ok=True)
        try:
            conversion = self.converter(Path(source_path), import_dir)
            extraction = self.extractor(conversion)
        except TenderImportError:
            raise
        except Exception as exc:
            raise TenderImportError(str(exc)) from exc
        report_path = import_dir / "extraction_report.json"
        report_path.write_text(
            json.dumps(dump_extraction_report(extraction), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        return TenderImportResult(
            requirements_path=requirements_path,
            scoring_path=scoring_path,
            relative_requirements_path="./项目要求/项目采购需求.md",
            relative_scoring_path="./项目要求/评分标准.md",
            import_dir=import_dir,
            extraction_report_path=report_path,
            extraction=extraction,
            created_paths=(
                *self._conversion_created_paths(conversion, import_dir),
                report_path,
                requirements_path,
                scoring_path,
            ),
        )

    def _conversion_created_paths(self, conversion, import_dir: Path) -> tuple[Path, ...]:
        paths = [
            getattr(conversion, "converted_markdown_path", import_dir / "converted.md"),
            getattr(conversion, "conversion_map_path", import_dir / "conversion_map.json"),
        ]
        created_paths: list[Path] = []
        for path in paths:
            if path is None:
                continue
            normalized = Path(path)
            if normalized not in created_paths:
                created_paths.append(normalized)
        return tuple(created_paths)

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
