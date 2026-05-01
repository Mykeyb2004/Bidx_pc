import json
from pathlib import Path

from bid_writer.tender_import_models import (
    ManualTenderConfirmationResult,
    ManualTenderSectionSelection,
    TenderExtractionResult,
    TenderSectionExtraction,
)
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
        confirm_sections=lambda **_kwargs: _confirmation(),
    )

    assert result.requirements_path == tmp_path / "项目要求" / "项目采购需求.md"
    assert result.scoring_path == tmp_path / "项目要求" / "评分标准.md"
    assert result.requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n人工需求\n"
    assert result.scoring_path.read_text(encoding="utf-8") == "# 评分标准\n\n人工评分\n"
    assert result.extraction_report_path.exists()
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["manual_confirmation"]["requirements"]["markdown"] == "# 项目采购需求\n\n人工需求\n"
    assert report["manual_confirmation"]["scoring"]["markdown"] == "# 评分标准\n\n人工评分\n"
    assert report["manual_confirmation"]["cancelled"] is False
    assert result.relative_requirements_path == "./项目要求/项目采购需求.md"
    assert result.relative_scoring_path == "./项目要求/评分标准.md"


def test_import_service_report_records_edited_manual_confirmation(tmp_path: Path):
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
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "算法需求", "r1", "r2", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "算法评分", "s1", "s2", 0.90),
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
        confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(
            requirements=ManualTenderSectionSelection(
                "bid_requirements",
                "# 项目采购需求\n\n编辑后的需求",
                None,
                None,
                manually_adjusted=True,
            ),
            scoring=ManualTenderSectionSelection(
                "scoring_criteria",
                "# 评分标准\n\n编辑后的评分",
                None,
                None,
                manually_adjusted=True,
            ),
        ),
    )

    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["manual_confirmation"]["requirements"]["markdown"] == "# 项目采购需求\n\n编辑后的需求"
    assert report["manual_confirmation"]["requirements"]["manually_adjusted"] is True
    assert report["manual_confirmation"]["requirements"]["start_block_id"] is None
    assert report["manual_confirmation"]["scoring"]["markdown"] == "# 评分标准\n\n编辑后的评分"
    assert report["manual_confirmation"]["scoring"]["manually_adjusted"] is True


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

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda path: path.name == "项目采购需求.md",
        confirm_sections=lambda **_kwargs: _confirmation("# 项目采购需求\n\n新需求\n", "# 评分标准\n\n新评分\n"),
    )

    assert (target_dir / "项目采购需求.md.bak").read_text(encoding="utf-8") == "旧需求"
    assert existing.read_text(encoding="utf-8") == "# 项目采购需求\n\n新需求\n"
    assert target_dir / "项目采购需求.md.bak" in result.created_paths


def test_import_service_confirms_all_overwrites_before_writing_targets(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    target_dir = tmp_path / "项目要求"
    target_dir.mkdir()
    requirements = target_dir / "项目采购需求.md"
    scoring = target_dir / "评分标准.md"
    requirements.write_text("旧需求", encoding="utf-8")
    scoring.write_text("旧评分", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    try:
        service.import_document(
            source_path=source,
            project_root=tmp_path,
            confirm_overwrite=lambda path: path.name == "项目采购需求.md",
            confirm_sections=lambda **_kwargs: _confirmation("# 项目采购需求\n\n新需求\n", "# 评分标准\n\n新评分\n"),
        )
    except TenderImportError as exc:
        assert str(exc) == f"用户取消覆盖：{scoring}"
    else:
        raise AssertionError("TenderImportError was not raised")

    assert requirements.read_text(encoding="utf-8") == "旧需求"
    assert scoring.read_text(encoding="utf-8") == "旧评分"
    assert not (target_dir / "项目采购需求.md.bak").exists()
    assert not (target_dir / "评分标准.md.bak").exists()


def test_import_service_stops_when_manual_confirmation_cancelled(tmp_path: Path):
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
        confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(cancelled=True),
    )

    assert result.cancelled is True
    report = json.loads(result.extraction_report_path.read_text(encoding="utf-8"))
    assert report["manual_confirmation"]["cancelled"] is True
    assert not (tmp_path / "项目要求" / "项目采购需求.md").exists()


def test_import_service_keeps_section_saved_before_manual_confirmation_cancel(tmp_path: Path):
    source = tmp_path / "tender.docx"
    source.write_text("fake", encoding="utf-8")
    conversion = type("Conversion", (), {"output_dir": tmp_path / ".bid_writer" / "imports" / "import-test"})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "算法需求", "r1", "r2", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "算法评分", "s1", "s2", 0.90),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "import-test",
    )

    def confirm_sections(**kwargs):
        selection = ManualTenderSectionSelection(
            "bid_requirements",
            "# 项目采购需求\n\n已经存入的需求",
            None,
            None,
            manually_adjusted=True,
        )
        kwargs["save_section"](selection)
        return ManualTenderConfirmationResult(requirements=selection, scoring=None, cancelled=True)

    result = service.import_document(
        source_path=source,
        project_root=tmp_path,
        confirm_overwrite=lambda _path: True,
        confirm_sections=confirm_sections,
    )

    requirements_path = tmp_path / "项目要求" / "项目采购需求.md"
    scoring_path = tmp_path / "项目要求" / "评分标准.md"
    assert result.cancelled is True
    assert result.requirements_path == requirements_path
    assert result.scoring_path is None
    assert requirements_path.read_text(encoding="utf-8") == "# 项目采购需求\n\n已经存入的需求\n"
    assert not scoring_path.exists()
    assert requirements_path in result.created_paths


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
        confirm_sections=lambda **_kwargs: _confirmation(),
    )

    assert service.converter.calls[0] == (source, explicit_import_dir)
    assert result.import_dir == explicit_import_dir
    assert result.created_paths == (
        explicit_import_dir / "converted.md",
        explicit_import_dir / "conversion_map.json",
        result.extraction_report_path,
        result.requirements_path,
        result.scoring_path,
    )


def test_import_service_normalizes_explicit_relative_import_dir(tmp_path: Path, monkeypatch):
    source = tmp_path / "source" / "tender.docx"
    source.parent.mkdir()
    source.write_text("fake", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative_import_dir = Path("relative") / ".bid_writer" / "imports" / "fixed-id"
    expected_import_dir = (cwd / relative_import_dir).resolve()
    conversion = type("Conversion", (), {"output_dir": expected_import_dir})()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.92),
        scoring=TenderExtractionResult("scoring_criteria", "评分标准", "评分", "s1", "s1", 0.92),
    )
    service = TenderImportService(
        converter=FakeConverter(conversion),
        extractor=FakeExtractor(extraction),
        import_id_factory=lambda: "ignored-id",
    )
    monkeypatch.chdir(cwd)

    result = service.import_document(
        source_path=source,
        project_root=tmp_path / "项目",
        import_dir=relative_import_dir,
        confirm_overwrite=lambda _path: True,
        confirm_sections=lambda **_kwargs: _confirmation(),
    )

    assert service.converter.calls[0] == (source, expected_import_dir)
    assert result.import_dir == expected_import_dir
    assert result.extraction_report_path == expected_import_dir / "extraction_report.json"


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
        confirm_sections=lambda **_kwargs: ManualTenderConfirmationResult(cancelled=True),
    )

    assert result.cancelled is True
    assert result.created_paths == (
        result.import_dir / "converted.md",
        result.import_dir / "conversion_map.json",
        result.extraction_report_path,
    )


def test_import_service_reports_conversion_artifacts_when_converter_provides_paths(tmp_path: Path):
    source = tmp_path / "source" / "tender.docx"
    source.parent.mkdir()
    source.write_text("fake", encoding="utf-8")
    import_dir = tmp_path / ".bid_writer" / "imports" / "fixed-id"
    converted = import_dir / "converted.md"
    conversion_map = import_dir / "conversion_map.json"
    conversion = type(
        "Conversion",
        (),
        {
            "output_dir": import_dir,
            "converted_markdown_path": converted,
            "conversion_map_path": conversion_map,
        },
    )()
    extraction = TenderSectionExtraction(
        requirements=TenderExtractionResult("bid_requirements", "项目采购需求", "需求", "r1", "r1", 0.92),
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
        import_dir=import_dir,
        confirm_overwrite=lambda _path: True,
        confirm_sections=lambda **_kwargs: _confirmation(),
    )

    assert result.created_paths == (
        converted,
        conversion_map,
        result.extraction_report_path,
        result.requirements_path,
        result.scoring_path,
    )


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
            confirm_sections=lambda **_kwargs: _confirmation(),
        )
    except TenderImportError as exc:
        assert str(exc) == "暂不支持 WPS 原生格式"
    else:
        raise AssertionError("TenderImportError was not raised")
