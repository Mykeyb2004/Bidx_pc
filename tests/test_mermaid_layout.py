"""Recover graph layout while preserving nodes, labels and edge semantics."""

import json

import pytest

from bid_writer.body_layout import prepare_layout
from bid_writer.mermaid_layout import repair_mermaid_layout
from bid_writer.body_numbering import BodyNumberingError, inspect_numbering
from test_numbering_generation import FakeTrace, heading, make_writer


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
@pytest.mark.parametrize("direction", ["TD", "LR", "RL", "TB", "BT"])
def test_glued_boundaries_and_spaced_edges_are_repaired(eol, direction):
    source = f"一、目标\n摸排图```mermaidflowchart {direction}A[登记]\nG --> F F --> I\n```二、后续措施".replace("\n", eol)
    expected = f"一、目标\n摸排图\n\n```mermaid\nflowchart {direction}\nA[登记]\nG --> F \nF --> I\n```\n\n二、后续措施".replace("\n", eol)
    content, edits = repair_mermaid_layout(source)
    assert content == expected
    assert content.replace(eol, "") == source.replace(eol, "")
    replay = source
    for edit in reversed(edits):
        assert edit["before"] == ""
        replay = replay[:edit["offset"]] + edit["after"] + replay[edit["offset"]:]
    assert replay == content
    assert repair_mermaid_layout(content) == (content, [])


@pytest.mark.parametrize("line", [
    "G --> FF --> I", "G-->FF-->I", "G --> F --> I",
    'A["G --> F F --> I"] --> B', "A[G --> F F --> I] --> B",
    "A[G --> F\nF --> I I --> J] --> B",  # Multiline label.
    "%% G --> F F --> I", "A --> B %% G --> F F --> I",
    "A -- G --> F F --> I --> B", "A -->|G --> F F --> I| B",
    "G --> F; F --> I", "classDef default fill:red", "style F fill:red",
    "G --> F F", "G --> F F -->",  # Incomplete statements.
    'A["包含 ``` 的标签"] --> B',
])
def test_valid_or_ambiguous_graph_content_is_preserved(line):
    source = f"```mermaid\nflowchart TD\n{line}\n```"
    assert repair_mermaid_layout(source) == (source, [])


@pytest.mark.parametrize("line,expected", [
    ("G --> F F --> I", "G --> F \nF --> I"),
    ("G-->F\tF-->I", "G-->F\t\nF-->I"),
    ("G --> F F --> I I --> J", "G --> F \nF --> I \nI --> J"),
    ("G --> F[审核] F --> I[入库]", "G --> F[审核] \nF --> I[入库]"),
    ("G --> F F --> I %% 原始注释", "G --> F \nF --> I %% 原始注释"),
])
def test_complete_edges_split_without_touching_tokens(line, expected):
    source = f"```mermaid\ngraph LR\n{line}\n```"
    assert repair_mermaid_layout(source)[0] == f"```mermaid\ngraph LR\n{expected}\n```"


@pytest.mark.parametrize("source", [
    "```text\n图名```mermaidflowchart TDA-->B B-->C\n```",
    "````markdown\n```mermaidflowchart TDA-->B B-->C\n```\n````",
    "> 图名```mermaidflowchart TDA-->B B-->C```",
    "| 说明 | ```mermaidflowchart TDA-->B B-->C``` |",
    "行内示例 ` ```mermaidflowchart TDA-->B B-->C``` `",
    "图名```mermaidflowchart TDA-->B B-->C",  # No closing fence.
    "```mermaid\nflowchart TD\nA[未闭合\n```",
    "```mermaid\nflowchart TD\nA-->B\n```mermaid\nflowchart TD\nC-->D\n```",
])
def test_examples_and_unbounded_blocks_are_not_repaired(source):
    assert repair_mermaid_layout(source) == (source, [])


def test_tilde_fences_and_other_diagram_types_only_get_block_boundaries():
    source = "业务图~~~mermaid\nsequenceDiagram\nA->>B: G --> F F --> I\n~~~后续正文。"
    expected = "业务图\n\n~~~mermaid\nsequenceDiagram\nA->>B: G --> F F --> I\n~~~\n\n后续正文。"
    assert repair_mermaid_layout(source)[0] == expected


def test_all_four_heading_levels_and_mermaid_on_one_line():
    source = "一、总体安排（一）摸排流程1. 信息登记（1）现场核验```mermaidflowchart TDA[登记] --> B[核验] B --> C[入库]```（2）后续跟踪二、保障措施"
    expected = "一、总体安排\n\n（一）摸排流程\n\n1. 信息登记\n\n（1）现场核验\n\n```mermaid\nflowchart TD\nA[登记] --> B[核验] \nB --> C[入库]\n```\n\n（2）后续跟踪\n\n二、保障措施"
    writer, calls, _ = make_writer()
    result = writer.finalize_generation(heading(), source)
    assert result.content == expected
    assert [h.level for h in inspect_numbering(result.content).headings] == [1, 2, 3, 4, 4, 1]
    assert not calls


def test_glued_prose_headings_and_multiple_graphs_share_one_model_budget():
    source = "一、摸排目标（一）登记安排项目组负责登记，形成台账。```mermaidflowchart TDA-->B B-->C```（二）复核安排项目组逐项复核，确认结果。```mermaidgraph LRG --> FF --> I```二、服务保障"
    prepared = prepare_layout(source)
    assert len(prepared.candidates) == 2
    nodes = {h.line: {"line": h.line, "level": h.level} for h in inspect_numbering(prepared.content).headings}
    for candidate, prefix in zip(prepared.candidates, ["（一）登记安排", "（二）复核安排"]):
        nodes[candidate["line"]] = {"line": candidate["line"], "level": 2, "prefix": prefix}
    proposal = {"headings": [nodes[n] for n in sorted(nodes)]}
    writer, calls, _ = make_writer(json.dumps(proposal))
    trace = FakeTrace()
    result = writer.finalize_generation(heading(), source, trace)
    assert len(calls) == 1 and trace.raw_content == source
    assert [h.title for h in inspect_numbering(result.content).headings] == ["摸排目标", "登记安排", "复核安排", "服务保障"]
    assert "（一）登记安排\n\n项目组" in result.content
    assert "（二）复核安排\n\n项目组" in result.content
    assert "G --> FF --> I" in result.content
    assert result.content.replace("\n", "") == source
    replay = source
    for stage in ("mermaid_layout", "layout_local", "layout_model"):
        for edit in sorted((e for e in result.numbering_report["edits"] if e["stage"] == stage), key=lambda e: e["offset"], reverse=True):
            replay = replay[:edit["offset"]] + edit["after"] + replay[edit["offset"]:]
    assert replay == result.content


def test_failed_heading_repair_discards_mermaid_edits_and_keeps_original():
    source = "一、摸排目标（一）登记安排项目组负责登记，形成台账。```mermaidflowchart TDA-->B B-->C```"
    writer, calls, _ = make_writer('{"headings":[]}')
    with pytest.raises(BodyNumberingError) as caught:
        writer.finalize_generation(heading(), source)
    assert caught.value.content == source and caught.value.report["edits"] == []
    assert len(calls) == 1


@pytest.mark.parametrize("source", [
    "一、安排\n（一）对应二、三项工作",
    "一、安排\n（一）按照二、三项工作",
    "一、安排\n（一）依据二、三项工作",
])
def test_number_references_do_not_create_parent_heading_boundaries(source):
    assert not prepare_layout(source).edits


def test_long_prose_before_inline_graph_and_title_after_it_are_separated():
    paragraph = "项目组依据核验记录逐项登记，形成可追溯的服务台账。" * 6
    source = "一、目标\n" + paragraph + "```mermaidflowchart TDA-->B```二、保障"
    writer, calls, _ = make_writer()
    result = writer.finalize_generation(heading(), source)
    assert paragraph + "\n\n```mermaid\nflowchart TD\nA-->B\n```\n\n二、保障" in result.content
    assert not calls
