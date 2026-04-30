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


def test_plain_title_paragraphs_stop_at_following_plain_section_title():
    conversion = _conversion(
        [
            _paragraph("req_title", "项目采购需求", 1),
            _paragraph("r1", "服务内容包括调查、技术支持、成果提交和验收。", 2),
            _paragraph("score_title", "评分标准", 3),
            _table("s1", "| 评分项 | 评分标准 | 分值 |\n| --- | --- | --- |\n| 服务 | 优得20分 | 20分 |", 4),
            _paragraph("contract_title", "合同条款", 5),
            _paragraph("c1", "合同正文不得进入评分标准摘录。", 6),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.start_block_id == "req_title"
    assert "评分标准" not in result.requirements.markdown
    assert result.scoring is not None
    assert result.scoring.start_block_id == "score_title"
    assert "合同正文" not in result.scoring.markdown


def test_plain_toc_rows_without_dotted_leaders_are_ignored():
    conversion = _conversion(
        [
            _heading("toc", "目录", 1),
            _paragraph("toc_req", "项目采购需求 12", 2),
            _paragraph("toc_score", "评分标准 26", 3),
            _heading("real_req", "项目采购需求", 4),
            _paragraph("r1", "采购服务内容包括范围、技术要求、成果提交和验收。", 5),
            _heading("real_score", "评分标准", 6),
            _table("s1", "| 评分项 | 评分标准 | 分值 |\n| --- | --- | --- |\n| 团队 | 人员配置得10分 | 10分 |", 7),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.requirements is not None
    assert result.requirements.start_block_id == "real_req"
    assert "项目采购需求 12" not in result.requirements.markdown
    assert result.scoring is not None
    assert result.scoring.start_block_id == "real_score"


def test_table_scoring_candidate_expands_back_to_preceding_scoring_title_and_intro():
    conversion = _conversion(
        [
            _heading("req", "采购内容及要求", 1),
            _paragraph("r1", "采购服务内容包括调查、成果提交和验收。", 2),
            _paragraph("score_title", "评分因素与分值", 3),
            _paragraph("intro", "本项目采用综合评分法，满分100分。", 4),
            _table("score_table", "| 评分项 | 评审内容 | 分值 |\n| --- | --- | --- |\n| 服务方案 | 完整得30分 | 30分 |", 5),
            _heading("contract", "合同条款", 6),
            _paragraph("c1", "合同正文", 7),
        ]
    )

    result = extract_tender_sections(conversion)

    assert result.scoring is not None
    assert result.scoring.start_block_id == "score_title"
    assert "本项目采用综合评分法" in result.scoring.markdown
    assert "完整得30分" in result.scoring.markdown
    assert "合同正文" not in result.scoring.markdown
