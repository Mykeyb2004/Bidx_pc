"""Regression for 3.4.3: bold headings and circled markers must reach repair."""

import json
from pathlib import Path

import pytest

from bid_writer.body_numbering import BodyNumberingError, inspect_numbering, repair_numbering
from test_numbering_generation import make_writer, FakeTrace
from bid_writer.outline_parser import HeadingNode


SOURCE_PATH = Path(__file__).parent / "fixtures/body_numbering/bold_circled_343.md"
CHAPTER_TITLE = "3.4.3 救助政策与服务资源对接落实情况跟踪"
# Fixed structure suggestion substitutes for a live model in this regression.
PROPOSAL = {"headings": [
    {"line": line, "level": level}
    for line, level in [(5, 1), (8, 1), (25, 2), (28, 2), (31, 2), (34, 2), (37, 2), (40, 1), (54, 1)]
]}


def test_real_bold_circled_body_recognizes_candidates_without_guessing_levels():
    source = SOURCE_PATH.read_text()
    inspection = inspect_numbering(source, CHAPTER_TITLE)
    assert inspection.duplicate_lines == [1]
    assert [h.line for h in inspection.headings] == [node["line"] for node in PROPOSAL["headings"]]
    assert {h.kind for h in inspection.headings} == {"emphasis", "circled"}
    assert all(h.level == 0 for h in inspection.headings)
    result = repair_numbering(source, CHAPTER_TITLE)
    assert result.content == source and result.issues_after
    assert not result.edits  # Boldness/circled style does not determine hierarchy.


def test_real_bold_circled_body_repaired_without_changing_non_headings():
    source = SOURCE_PATH.read_text()
    result = repair_numbering(source, CHAPTER_TITLE, proposal=PROPOSAL)
    assert result.method == "model" and not result.issues_after
    assert len(result.edits) == 10
    assert result.content.startswith("\n为确保")  # Opening duplicate removed, introduction retained.
    assert "**一、救助政策与服务资源对接落实情况跟踪背景与逻辑框架**  \n" in result.content
    assert "**（一）平台运行管理**  \n" in result.content
    assert "**（五）信息质量保障**  \n" in result.content
    assert "**四、Mermaid流程图展示**（用于呈现关键流程、步骤衔接、角色协作或机制闭环）  \n" in result.content
    source_lines = source.splitlines(keepends=True)
    for edit in result.edits:
        assert source_lines[edit["line"] - 1] == edit["before"]
        source_lines[edit["line"] - 1] = edit["after"]
    assert "".join(source_lines) == result.content
    inspection = inspect_numbering(result.content, CHAPTER_TITLE)
    assert not inspection.issues
    assert [h.level for h in inspection.headings] == [n["level"] for n in PROPOSAL["headings"]]
    assert not repair_numbering(result.content, CHAPTER_TITLE).edits


@pytest.mark.parametrize("suffix", ["  \n", "\\\n", "  \r\n", "\\\r\n"])
@pytest.mark.parametrize("mark", ["**", "__"])
def test_bold_heading_hard_breaks_preserved_and_duplicate_is_exact(suffix, mark):
    source = f"{mark}3.4.3 跟踪{mark}{suffix}\n{mark}①实施安排{mark}{suffix}服务12人。\n"
    result = repair_numbering(source, "3.4.3 跟踪", proposal={"headings": [{"line": 3, "level": 1}]})
    assert result.content == f"\n{mark}一、实施安排{mark}{suffix}服务12人。\n"
    assert not result.issues_after


@pytest.mark.parametrize("line", ["**重要事项。**", "**重要**：服务人数为12人。", "**重要**必须当天反馈", "①信息采集，②动态监测", "**指标**（已完成）。"])
def test_does_not_promote_emphasized_prose_or_inline_circled_lists(line):
    source = "一、执行安排\n\n" + line + "\n"
    assert len(inspect_numbering(source).headings) == 1
    assert repair_numbering(source).content == source


def test_emphasis_and_circled_text_inside_tables_fences_and_quotes_is_protected():
    source = "一、执行安排\n\n| **标题** | ①资料 |\n|---|---|\n| **内容** | ②信息 |\n\n```mermaid\n**图内文字**\n①图内编号\n```\n\n> **引用**\n"
    assert not inspect_numbering(source).issues
    assert repair_numbering(source).content == source


def test_valid_first_heading_does_not_hide_later_nonstandard_headings():
    source = "一、执行安排\n\n**信息质量保障**\n正文。\n\n②动态监测\n正文。"
    inspection = inspect_numbering(source)
    assert [h.kind for h in inspection.headings] == ["formal", "emphasis", "circled"]
    assert {issue["code"] for issue in inspection.issues} >= {"nonstandard_heading"}
    assert repair_numbering(source).issues_after


@pytest.mark.parametrize("valid", [True, False])
def test_bold_only_body_reaches_single_model_request_and_preserves_failure(valid, monkeypatch):
    writer, calls, options = make_writer(json.dumps(PROPOSAL) if valid else '{"headings":[]}')
    trace = FakeTrace()
    node = HeadingNode(level=4, title=CHAPTER_TITLE, full_path=CHAPTER_TITLE, line_number=1)
    source = SOURCE_PATH.read_text()
    monkeypatch.setattr(writer, "_finalize_trace_session_async", lambda session, content, **kwargs: session.finalize(content, **kwargs))
    if valid:
        result = writer.finalize_generation(node, source, trace)
        assert result.postprocess["numbering_repair_method"] == "model"
        assert trace.finalized["status"] == "completed"
    else:
        with pytest.raises(BodyNumberingError) as caught:
            writer.finalize_generation(node, source, trace)
        assert caught.value.content == source
        assert trace.finalized["status"] == "failed"
    assert len(calls) == 1
    assert options[0]["max_retries"] == 0
    assert trace.raw_content == source
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert [h["line"] for h in payload["editable_headings"]] == [n["line"] for n in PROPOSAL["headings"]]
