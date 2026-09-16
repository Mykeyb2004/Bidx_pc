"""Missing prose boundaries may be recovered; Mermaid must stay byte-for-byte."""

import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from bid_writer.ai_writer import GenerationCancelledError
from bid_writer.body_layout import prepare_layout, repair_layout
from bid_writer.body_numbering import BodyNumberingError, inspect_numbering, protected_code_lines
from test_numbering_generation import FakeTrace, heading, make_writer


FIXTURES = Path(__file__).parent / "fixtures/body_numbering"
SOURCE = (FIXTURES / "joined_522.md").read_text()
EXPECTED = (FIXTURES / "joined_522_expected.md").read_text()
PROPOSAL = json.loads((FIXTURES / "joined_522_proposal.json").read_text())


def code_text(text):
    protected, _ = protected_code_lines(text)
    return "".join(line for n, line in enumerate(text.splitlines(keepends=True), 1) if n in protected)


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_real_522_keeps_all_text_and_mermaid_and_is_idempotent(eol):
    source = SOURCE.replace("\n", eol)
    prepared = prepare_layout(source)
    assert len(prepared.candidates) == 25
    assert len(prepared.edits) == 9
    result = repair_layout(prepared, proposal=PROPOSAL)
    assert result.content == EXPECTED.replace("\n", eol)
    assert not result.issues_after
    assert [h.level for h in inspect_numbering(result.content).headings].count(1) == 7
    assert [h.level for h in inspect_numbering(result.content).headings].count(2) == 25
    assert code_text(result.content) == code_text(source)
    assert "mermaidflowchart TDA[" in result.content
    assert "G --> FF --> I[" in result.content
    assert result.content.replace(eol, "") == source.replace(eol, "")
    assert len(result.edits) == 34
    # Replay actual edit coordinates, not just a whitespace-stripped comparison.
    replay = source
    for stage in ("layout_local", "layout_model"):
        for edit in sorted((e for e in result.edits if e["stage"] == stage), key=lambda e: e["offset"], reverse=True):
            assert edit["before"] == ""
            replay = replay[:edit["offset"]] + edit["after"] + replay[edit["offset"]:]
    assert replay == result.content
    again = repair_layout(prepare_layout(result.content))
    assert again.content == result.content and not again.edits and not again.issues_after


def test_real_522_one_request_and_trace_records_raw_source(monkeypatch):
    writer, calls, options = make_writer(json.dumps(PROPOSAL, ensure_ascii=False))
    trace = FakeTrace()
    monkeypatch.setattr(writer, "_finalize_trace_session_async", lambda session, content, **kwargs: session.finalize(content, **kwargs))
    result = writer.finalize_generation(heading(), SOURCE, trace)
    assert result.content == EXPECTED
    assert trace.raw_content == SOURCE
    assert trace.content == EXPECTED and trace.finalized["status"] == "completed"
    assert len(calls) == 1 and options[0]["max_retries"] == 0
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert len(payload["boundary_candidates"]) == 25
    assert len(payload["editable_headings"]) == 7
    assert result.postprocess["format_repair_applied"]
    assert result.postprocess["numbering_repair_method"] == "model"


def test_previous_522_recovers_short_colon_leadin_and_all_three_levels():
    source = (FIXTURES / "joined_522_previous.md").read_text()
    expected = (FIXTURES / "joined_522_previous_expected.md").read_text()
    proposal = (FIXTURES / "joined_522_previous_proposal.json").read_text()
    writer, calls, _ = make_writer(proposal)
    result = writer.finalize_generation(heading(), source)
    assert result.content == expected
    assert len(calls) == 1
    assert len(inspect_numbering(result.content).headings) == 33
    assert code_text(result.content) == code_text(source)
    assert result.content.replace("\n", "") == source.replace("\n", "")
    assert "（二）摸排对象\n\n志愿服务力量摸排对象主要包括以下类别：" in result.content


def test_long_colon_heading_can_be_confirmed_without_splitting():
    source = "一、实施安排\n\n（一）社会救助志愿服务力量摸排工作中的基本要求和业务范围："
    proposal = {"headings": [
        {"line": 1, "level": 1},
        {"line": 3, "level": 2, "prefix": source.splitlines()[2]},
    ]}
    result = repair_layout(prepare_layout(source), proposal=proposal)
    assert result.content == source and not result.edits and not result.issues_after


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("valid", [True, False])
def test_real_522_gui_saves_only_repaired_prose_and_keeps_mermaid(monkeypatch, tmp_path, stream, valid):
    from test_numbering_gui import prepare_workspace
    window, _, calls, path = prepare_workspace(
        monkeypatch, tmp_path, SOURCE, stream=stream,
        response=json.dumps(PROPOSAL) if valid else '{"headings":[]}',
    )
    result = window._generate_into_workspace(heading(), "", 1200, 0, auto_extract_facts=True, show_error_dialog=False)
    assert len(calls) == 1
    if valid:
        assert result == "success" and window.saves == [EXPECTED]
        assert path.read_text() == EXPECTED
        assert code_text(path.read_text()) == code_text(SOURCE)
    else:
        assert result == "failed" and not window.saves and not window.facts
        assert path.read_text() == "原有正式正文"
        assert window._workspace_generation_failures[heading().full_path].partial_content == SOURCE


@pytest.mark.parametrize("source,expected", [
    ("一、组织安排（一）人员职责\n正文。", "一、组织安排\n\n（一）人员职责\n正文。"),
    ("一、组织安排二、服务保障", "一、组织安排\n\n二、服务保障"),
    ("一、安排\n**（一）人员职责**项目人员负责登记。", "一、安排\n**（一）人员职责**\n\n项目人员负责登记。"),
    ("一、安排\n统计表| 指标 | 数据 |\n|---|---|\n| 人数 | 12 |", "一、安排\n统计表\n\n| 指标 | 数据 |\n|---|---|\n| 人数 | 12 |"),
])
def test_unambiguous_boundaries_need_no_model(source, expected):
    writer, calls, _ = make_writer()
    result = writer.finalize_generation(heading(), source)
    assert result.content == expected
    assert not calls


@pytest.mark.parametrize("tail", [
    "1. 真实性原则。保留该段全部信息。",
    "资料为3.5万元，正文包括（一）采集、（二）核验。",
    "| 内容 | 编号 |\n|---|---|\n| （一）目标正文，应保留。 | 1 |",
    "> （一）引用文字，需要原样保留。",
    "标题|甲|乙|\n|---|---|---|",  # Column counts do not match.
    "正文说明。|甲|乙|\n|---|---|",  # Not a caption.
    "```text\n一、组织（一）人员正文，应保留。\n```",
])
def test_prose_tables_quotes_and_code_are_not_split(tail):
    source = "一、实施安排\n\n" + tail
    layout = prepare_layout(source)
    assert not layout.edits and not layout.candidates
    assert repair_layout(layout).content == source


@pytest.mark.parametrize("mark", ["**", "__"])
@pytest.mark.parametrize("suffix", ["  \n", "\\\n", "  \r\n", "\\\r\n"])
def test_existing_formal_bold_title_keeps_hard_breaks(mark, suffix):
    source = f"{mark}一、实施安排{mark}{suffix}正文。"
    prepared = prepare_layout(source)
    assert prepared.content == source and not prepared.edits and not prepared.candidates
    assert repair_layout(prepared).content == source


def test_partial_valid_heading_does_not_hide_glued_heading_and_can_keep_prose():
    source = "一、目标\n\n（一）人员安排项目人员负责登记，形成台账。\n\n（二）按要求登记，不得外泄。"
    proposal = {"headings": [
        {"line": 1, "level": 1},
        {"line": 3, "level": 2, "prefix": "（一）人员安排"},
        {"line": 5, "level": None, "prefix": None},
    ]}
    result = repair_layout(prepare_layout(source), proposal=proposal)
    assert result.content == source.replace("（一）人员安排", "（一）人员安排\n\n")
    assert not result.issues_after


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "boolean_line", "boolean_level", "wrong_prefix", "rewritten_prefix", "whole_line", "body_in_title", "extra_field", "code_line", "wrong_root", "not_object"])
def test_invalid_boundary_suggestions_fail_atomically(mutation):
    proposal = copy.deepcopy(PROPOSAL)
    node = proposal["headings"][1]
    if mutation == "missing": proposal["headings"].pop()
    elif mutation == "duplicate": proposal["headings"][2] = dict(node)
    elif mutation == "reordered": proposal["headings"].reverse()
    elif mutation == "boolean_line": node["line"] = True
    elif mutation == "boolean_level": node["level"] = True
    elif mutation == "wrong_prefix": node["prefix"] = "（二）适用范围"
    elif mutation == "rewritten_prefix": node["prefix"] = "（一）目标"
    elif mutation == "whole_line": node["prefix"] = prepare_layout(SOURCE).candidates[0]["text"]
    elif mutation == "body_in_title": node["prefix"] = prepare_layout(SOURCE).candidates[0]["text"].split("，", 2)[0] + "，"
    elif mutation == "extra_field": node["replacement"] = "任意正文"
    elif mutation == "code_line": node["line"] = 75
    elif mutation == "wrong_root": proposal["headings"][0]["level"] = 2
    elif mutation == "not_object": proposal = []
    writer, calls, _ = make_writer(json.dumps(proposal, ensure_ascii=False))
    trace = FakeTrace()
    with pytest.raises(BodyNumberingError) as caught:
        writer.finalize_generation(heading(), SOURCE, trace)
    assert caught.value.content == SOURCE
    assert not caught.value.report["edits"]
    assert trace.content == SOURCE and trace.finalized["status"] == "failed"
    assert len(calls) == 1


def test_boundary_split_maps_numbering_and_exact_duplicate_chapter_removal():
    source = "### 3.3.1 动态监测\n\n（一）组织1. 人员安排项目组负责登记，形成台账。"
    proposal = {"headings": [
        {"line": 3, "level": 1},
        {"line": 5, "level": 2, "prefix": "1. 人员安排"},
    ]}
    result = repair_layout(prepare_layout(source, heading().title), heading().title, proposal=proposal)
    assert not result.issues_after
    assert result.content == "\n一、组织\n\n（一）人员安排\n\n项目组负责登记，形成台账。"


def test_malformed_but_bounded_mermaid_is_skipped_and_bidder_names_stay_intact():
    graph = "摸排图```mermaidflowchart TDA[本公司]\nG --> FF --> I\n```\n"
    source = "（一）实施安排\n\n本公司负责登记。\n\n" + graph + "\n（二）后续措施"
    writer, calls, _ = make_writer()
    writer.config.prompt_bidder_name = "菲尔德咨询"
    result = writer.finalize_generation(heading(), source)
    assert graph in result.content
    assert "菲尔德咨询负责登记。" in result.content
    assert "二、后续措施" in result.content
    assert not calls


@pytest.mark.parametrize("opener", ["```mermaid", "摸排图```mermaidflowchart TDA[登记]"])
def test_truly_unclosed_fence_is_never_repaired_or_sent_to_model(opener):
    source = "（一）目标\n\n" + opener + "\n（一）代码内信息，原样保留。"
    writer, calls, _ = make_writer()
    with pytest.raises(BodyNumberingError) as caught:
        writer.finalize_generation(heading(), source)
    assert caught.value.content == source and not calls
    assert any(issue["code"] == "unclosed_fence" for issue in caught.value.report["issues_after"])


@pytest.mark.parametrize("mode", ["cancel", "timeout", "invalid_json"])
def test_boundary_request_failure_keeps_original_without_second_request(mode):
    writer, calls, _ = make_writer("not-json")
    event = threading.Event()
    release = threading.Event()
    if mode != "invalid_json":
        writer.config.api_timeout_seconds = 0.02
        def create(**kwargs):
            calls.append(kwargs)
            if mode == "cancel": event.set()
            release.wait(1)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(PROPOSAL)))])
        writer.client.chat.completions.create = create
    trace = FakeTrace()
    try:
        with pytest.raises(GenerationCancelledError if mode == "cancel" else BodyNumberingError):
            writer.finalize_generation(heading(), SOURCE, trace, cancel_event=event)
        assert trace.content == SOURCE
        assert trace.finalized["status"] == ("cancelled" if mode == "cancel" else "failed")
        assert len(calls) == 1
    finally:
        release.set()
