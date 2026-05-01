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
    pattern: '第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)'
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: '(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)'
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
    pattern: '第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)'
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: '(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)'
    priority: 60
""".strip(),
        encoding="utf-8",
    )
    config = load_boundary_config(boundary_file)
    blocks = [
        _block("chapter5", "第五章 采购需求", 1, heading_level=2),
        _block("req", "本项目服务内容包括调查、分析、成果提交和验收。", 2),
        _block("chapter6", "第六章 评分标准", 3, heading_level=2),
        _block("score", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", 4, block_type="table"),
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
    pattern: '第\\s*(?P<ordinal>[一二三四五六七八九十百千万零〇0-9０-９]+)\\s*章\\s*(?P<title>.*)'
    priority: 100
fallback_markers:
  - name: chinese_top
    pattern: '(?P<ordinal>[一二三四五六七八九十百千万]+)\\s*[、.．]\\s*(?P<title>.+)'
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
        _block("score_body", "| 评分项 | 分值 |\n| --- | --- |\n| 服务 | 10分 |", 5, block_type="table"),
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
