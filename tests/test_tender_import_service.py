from pathlib import Path

from bid_writer.tender_import_models import TenderExtractionResult, TenderSectionExtraction
from bid_writer.tender_import_service import TenderImportError, TenderImportService


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


def test_import_service_accepts_explicit_import_dir_and_reports_created_paths(tmp_path: Path):
    source = tmp_path / "source" / "tender.docx"
    source.parent.mkdir()
    source.write_text("fake", encoding="utf-8")
    explicit_import_dir = tmp_path / "项目" / ".bid_writer" / "imports" / "fixed-id"
    conversion = type("Conversion", (), {"output_dir": explicit_import_dir})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "ignored-id",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path / "项目",
        import_dir=explicit_import_dir,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: True,
    )

    assert service.converter.calls[0] == (source, explicit_import_dir)
    assert result.import_dir == explicit_import_dir
    assert result.created_paths == (
        result.extraction_report_path,
        result.requirements_path,
        result.scoring_path,
    )


def test_import_service_cancelled_low_confidence_reports_only_report_path(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "fixed-id"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.50),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "fixed-id",
    )

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_low_confidence=lambda _extraction: False,
    )

    assert result.cancelled is True
    assert result.created_paths == (result.extraction_report_path,)


def test_import_service_wraps_converter_errors_for_ui(tmp_path: Path):
    source = tmp_path / "tender.wps"
    source.write_text("fake", encoding="utf-8")

    def broken_converter(_path, _output_dir):
        raise RuntimeError("暂不支持 WPS 原生格式")

    service = TenderImportService(
        converter=broken_converter,
        extractor=FakeExtractor(TenderSectionExtraction()),
        import_id_factory=lambda: "import-test",
    )

    try:
        service.import_document(
            source_path=source,
            project_root=tmp_path,
            confirm_overwrite=lambda _path: True,
            confirm_low_confidence=lambda _extraction: True,
        )
    except TenderImportError as exc:
        assert str(exc) == "暂不支持 WPS 原生格式"
    else:
        raise AssertionError("TenderImportError was not raised")
