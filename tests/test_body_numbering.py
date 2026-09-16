"""章节内部编号修复必须保留标题文字和全部非标题内容。"""

import pytest

from bid_writer.body_numbering import inspect_numbering, repair_numbering


def test_promotes_entire_tree_and_is_idempotent():
    source = "（一）实施组织\n\n人数为12人。\n\n1. 岗位职责\n\n职责正文。\n\n（1）质量复核\n\n复核正文。\n\n（二）服务保障\n\n保障正文。"
    expected = "一、实施组织\n\n人数为12人。\n\n（一）岗位职责\n\n职责正文。\n\n1. 质量复核\n\n复核正文。\n\n二、服务保障\n\n保障正文。"
    result = repair_numbering(source)
    assert result.content == expected
    assert result.method == "local"
    assert result.issues_after == []
    assert repair_numbering(result.content).content == expected
    assert repair_numbering(result.content).edits == []


def test_restarts_counters_under_each_parent():
    source = "二、组织\n\n（四）人员\n\n3. 核验\n\n（2）记录\n\n（三）资源\n\n7. 台账\n\n五、验收\n\n（六）程序"
    result = repair_numbering(source)
    assert result.content == "一、组织\n\n（一）人员\n\n1. 核验\n\n（1）记录\n\n（二）资源\n\n1. 台账\n\n二、验收\n\n（一）程序"
    assert not result.issues_after


def test_valid_body_is_unchanged_including_intro_and_inline_enumerations():
    source = "项目说明，一是登记，二是复核。\n\n一、实施方案\n\n（一）原则\n\n1. 真实性原则。数据应完整保留，不得改写。\n\n（二）验收"
    result = repair_numbering(source)
    assert result.content == source
    assert result.method == "none"
    assert not result.issues_after


def test_removes_only_exact_opening_duplicate_and_converts_markdown():
    source = "### 3.3.1 动态监测\n\n## 监测目标\n\n正文仍提到3.3.1 动态监测。\n\n### 服务安排\n\n数据为3.5万元。"
    result = repair_numbering(source, "3.3.1 动态监测")
    assert result.content == "\n一、监测目标\n\n正文仍提到3.3.1 动态监测。\n\n（一）服务安排\n\n数据为3.5万元。"
    assert not result.issues_after


def test_preserves_tables_fences_crlf_and_long_numbered_paragraphs():
    protected = "| 序号 | 内容 |\r\n|---|---|\r\n| （一） | 12人 |\r\n\r\n```mermaid\r\n# 图内注释\r\n1. graph syntax\r\n```\r\n\r\n~~~text\r\n（一）保留示例\r\n~~~\r\n"
    source = "（一）执行安排\r\n\r\n" + protected + "\r\n（1）按约定完成记录，不得变更既有数据。\r\n"
    result = repair_numbering(source)
    assert result.content == source.replace("（一）执行安排", "一、执行安排", 1)
    assert protected in result.content
    assert not result.issues_after


@pytest.mark.parametrize("source", ["纯正文，没有标题。", "", "1. 真实性原则。保留该段全部信息。"])
def test_does_not_invent_headings(source):
    result = repair_numbering(source)
    assert result.content == source
    assert result.issues_after
    assert not result.edits


def test_mixed_families_require_model_then_use_only_validated_line_levels():
    source = "（一）执行安排\n\n正文12人。\n\n### 岗位责任\n\n原始正文。"
    assert repair_numbering(source).issues_after
    result = repair_numbering(source, proposal={"headings": [{"line": 1, "level": 1}, {"line": 5, "level": 2}]})
    assert result.content == "一、执行安排\n\n正文12人。\n\n（一）岗位责任\n\n原始正文。"
    assert result.method == "model"
    assert not result.issues_after


@pytest.mark.parametrize("headings", [
    [{"line": 1, "level": 1}],  # 不得漏掉另一处 Markdown 标题
    [{"line": 1, "level": 1}, {"line": 3, "level": 2}, {"line": 5, "level": 2}],
    [{"line": 1, "level": 1}, {"line": 1, "level": 2}],
    [{"line": 5, "level": 1}, {"line": 1, "level": 2}],
    [{"line": 1, "level": 1}, {"line": 5, "level": 3}],
    [{"line": 1, "level": 1}, {"line": 5, "level": 5}],
    [{"line": 1, "level": True}, {"line": 5, "level": 2}],
    [{"line": 1, "level": 1, "text": "被改写"}, {"line": 5, "level": 2}],
])
def test_rejects_invalid_model_edits_without_changing_content(headings):
    source = "（一）执行安排\n\n正文12人。\n\n### 岗位责任\n\n原始正文。"
    result = repair_numbering(source, proposal={"headings": headings})
    assert result.issues_after
    assert result.content == source
    assert not result.edits


@pytest.mark.parametrize("source", ["1. 目标\n\n（1）措施", "（1）目标\n\n（2）措施", "二、目标\n\n五、措施"])
def test_promotes_lower_starts_and_fixes_non_initial_numbers(source):
    result = repair_numbering(source)
    assert result.content.startswith("一、目标")
    assert not result.issues_after
    assert repair_numbering(result.content).method == "none"


def test_unclosed_fence_is_rejected_without_partial_edit():
    source = "（一）目标\n\n```mermaid\n（一）图内文字"
    result = repair_numbering(source)
    assert result.content == source
    assert {issue["code"] for issue in result.issues_after} >= {"unclosed_fence"}
    assert not result.edits


def test_detects_markdown_and_wrong_first_level():
    report = inspect_numbering("### 3.3.1 当前章节\n\n（一）监测目标", "3.3.1 当前章节")
    assert {issue["code"] for issue in report.issues} >= {"repeated_chapter_title", "numbering_start"}
