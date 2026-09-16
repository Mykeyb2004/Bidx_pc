"""Recover prose layout by inserting newlines; code blocks are immutable."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .body_numbering import (
    NumberingRepair, _CN, _FORMAL, _heading, _standalone_title, _valid_levels,
    inspect_numbering, protected_code_lines, repair_numbering,
)


_TOKEN = re.compile(rf"[{_CN}]+、|[（(][{_CN}]+[）)]|\d+\.(?!\d)|[（(]\d+[）)]")
_BOLD_PREFIX = re.compile(r"^[ \t]*(\*\*.+?\*\*|__.+?__)")


@dataclass
class PreparedLayout:
    original: str
    content: str
    candidates: list[dict[str, Any]]
    edits: list[dict[str, Any]]
    issues: list[dict[str, Any]]


def _newline(text: str) -> str:
    match = re.search(r"\r\n|\n|\r", text)
    return match[0] if match else "\n"


def _insert_breaks(text: str, positions: dict[int, str], stage: str) -> tuple[str, list[dict[str, Any]]]:
    """Apply only insertions, with offsets into the input of this named stage."""
    eol = _newline(text)
    pieces: list[str] = []
    edits: list[dict[str, Any]] = []
    cursor = 0
    for offset, reason in sorted(positions.items()):
        if not 0 < offset < len(text) or text[offset - 1] in "\r\n" or text[offset] in "\r\n":
            raise ValueError("无效的结构断行位置")
        pieces.extend((text[cursor:offset], eol * 2))
        edits.append({"stage": stage, "offset": offset, "before": "", "after": eol * 2, "reason": reason})
        cursor = offset
    pieces.append(text[cursor:])
    return "".join(pieces), edits


def _joined_title_breaks(line: str) -> list[int]:
    """Split consecutive formal titles only before prose punctuation begins."""
    positions: list[int] = []
    cursor = 0
    for match in _TOKEN.finditer(line):
        if match.start() <= cursor:
            continue
        prefix = line[cursor:match.start()]
        parent = _heading(prefix, 1)
        child = _heading(match[0] + "候选标题", 1)
        if not parent or parent.kind != "formal" or not child:
            continue
        if len(parent.title.strip()) < 2 or re.search(r"[，,：:。；;！？!?]|[第按依见为]$", parent.title):
            continue
        if (child.level == parent.level + 1 and child.number == 1) or (
            child.level == parent.level and child.number == parent.number + 1
        ):
            positions.append(match.start())
            cursor = match.start()
    return positions


def _table_caption_break(line: str, next_line: str) -> int | None:
    """Require a real pipe header and matching separator row, not arbitrary pipes."""
    offset = line.find("|")
    if offset <= 0 or not _standalone_title(line[:offset]):
        return None
    header = line[offset:].strip()
    separator = next_line.strip()
    if not header.endswith("|") or not separator.startswith("|") or not separator.endswith("|"):
        return None
    cells = re.split(r"(?<!\\)\|", separator)[1:-1]
    columns = re.split(r"(?<!\\)\|", header)[1:-1]
    if len(cells) < 2 or len(cells) != len(columns) or not all(cell.strip() for cell in columns):
        return None
    if not all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells):
        return None
    return offset


def prepare_layout(text: str, chapter_title: str = "") -> PreparedLayout:
    protected, _ = protected_code_lines(text)
    lines = text.splitlines(keepends=True)
    positions: dict[int, str] = {}
    offset = 0
    for number, line in enumerate(lines, 1):
        display = line.rstrip("\r\n")
        if number not in protected and not display.lstrip().startswith(">"):
            if display.count("|") >= 2:
                split = _table_caption_break(display, lines[number] if number < len(lines) else "")
                if split is not None:
                    positions[offset + split] = "分开表名与表头"
            else:
                for split in _joined_title_breaks(display):
                    positions[offset + split] = "分开粘连的正式标题"
                bold = _BOLD_PREFIX.match(display)
                if bold and bold.end() < len(display):
                    heading = _heading(bold[0], number)
                    tail = display[bold.end():]
                    if heading and heading.kind == "formal" and tail.strip() not in {"", "\\"} and not tail.lstrip().startswith(("：", ":", "（", "(")):
                        positions[offset + bold.end()] = "分开加粗正式标题与正文"
        offset += len(line)
    content, edits = _insert_breaks(text, positions, "layout_local")
    protected, _ = protected_code_lines(content)
    inspection = inspect_numbering(content, chapter_title)
    known = {item.line: item for item in inspection.headings}
    candidates: list[dict[str, Any]] = []
    for number, line in enumerate(content.splitlines(), 1):
        if number in protected or number in inspection.duplicate_lines or line.lstrip().startswith(">") or line.count("|") >= 2:
            continue
        existing = known.get(number)
        # Long lead-ins ending in a colon can pass the short-heading recognizer,
        # e.g. a title glued to "对象主要包括以下类别：". Let the model select the
        # exact prefix or confirm the whole existing heading, never trim blindly.
        if existing and not (existing.kind == "formal" and len(existing.title) >= 20 and existing.title.endswith(("：", ":"))):
            continue
        match = _FORMAL.match(line.lstrip(" \t"))
        if not match:
            continue
        title = match["title"]
        # Keep ordinary Arabic-numbered complete sentences out of boundary repair.
        # Chinese headings still need semantic judgment when glued to a sentence.
        punctuation = re.search(r"[，,：:。！？!?；;]", title)
        if not punctuation or punctuation.start() < 2:
            continue
        if match["one"] is None and match["two"] is None and punctuation[0] in "。！？!?；;":
            continue
        candidates.append({"line": number, "text": line, "standalone": existing is not None})
    issues = [{"code": "joined_layout", "line": 0, "message": "正文存在粘连的标题或表格边界"}] if edits else []
    issues.extend({"code": "joined_heading_body", "line": item["line"],
                   "message": f"第{item['line']}行疑似标题与正文粘连，需要确认断行位置"} for item in candidates)
    return PreparedLayout(text, content, candidates, edits, issues)


def repair_layout(layout: PreparedLayout, chapter_title: str = "", *, proposal: Any = None) -> NumberingRepair:
    """Validate a single combined boundary/depth proposal, then reuse numbering.

    A model-selected prefix must be an exact source prefix. It is a selector,
    never replacement text. No editable candidate can belong to a code block.
    """
    before = inspect_numbering(layout.original, chapter_title).issues + layout.issues
    failure_issues = inspect_numbering(layout.content, chapter_title).issues + [
        issue for issue in layout.issues if issue["code"] == "joined_heading_body"
    ]
    failure = NumberingRepair(layout.original, before, failure_issues)
    if any(issue["code"] == "unclosed_fence" for issue in failure_issues):
        return failure
    content = layout.content
    edits = list(layout.edits)
    numbering_proposal = proposal
    if layout.candidates:
        if proposal is None:
            return failure
        try:
            content, model_edits, numbering_proposal = _apply_boundary_proposal(layout, chapter_title, proposal)
            edits.extend(model_edits)
        except ValueError as exc:
            failure.issues_after = failure_issues + [{"code": "invalid_layout_proposal", "line": 0, "message": str(exc)}]
            return failure
    result = repair_numbering(content, chapter_title, proposal=numbering_proposal)
    if result.issues_after:
        return NumberingRepair(layout.original, before, result.issues_after)
    # repair_numbering leaves already valid trees unchanged. Reject a model
    # trying to silently reinterpret that tree instead of claiming it was used.
    if layout.candidates and numbering_proposal:
        actual = [item.level for item in inspect_numbering(result.content, chapter_title).headings]
        if actual != [item["level"] for item in numbering_proposal["headings"]]:
            return NumberingRepair(layout.original, before, [{"code": "invalid_layout_proposal", "line": 0,
                                   "message": "结构建议与修复后标题层级不一致"}])
    edits.extend(dict(edit, stage="numbering") for edit in result.edits)
    method = "model" if layout.candidates and proposal is not None else result.method
    if edits and method == "none":
        method = "local"
    return NumberingRepair(result.content, before, [], method, edits)


def _apply_boundary_proposal(layout: PreparedLayout, chapter_title: str, proposal: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(proposal, dict) or set(proposal) != {"headings"} or not isinstance(proposal["headings"], list):
        raise ValueError("结构建议必须只包含 headings 数组")
    candidates = {item["line"]: item for item in layout.candidates}
    existing = {item.line for item in inspect_numbering(layout.content, chapter_title).headings}
    expected = sorted(existing | candidates.keys())
    nodes = proposal["headings"]
    if len(nodes) != len(expected):
        raise ValueError("结构建议必须覆盖全部标题与待判断行")
    lines = layout.content.splitlines(keepends=True)
    offsets: dict[int, int] = {}
    offset = 0
    for number, line in enumerate(lines, 1):
        offsets[number] = offset
        offset += len(line)
    positions: dict[int, str] = {}
    selected: list[tuple[int, int]] = []
    for node, number in zip(nodes, expected):
        keys = {"line", "level", "prefix"} if number in candidates else {"line", "level"}
        if not isinstance(node, dict) or set(node) != keys or type(node["line"]) is not int or node["line"] != number:
            raise ValueError("结构建议的行号、顺序或字段不合法")
        if number in candidates:
            prefix = node["prefix"]
            if prefix is None and node["level"] is None:
                continue  # Ordinary numbered prose: deliberately leave it intact.
            display = lines[number - 1].rstrip("\r\n")
            if not isinstance(prefix, str) or not prefix or not display.startswith(prefix):
                raise ValueError("标题前缀不是原文中可断开的精确前缀")
            if prefix == display and candidates[number]["standalone"]:
                if type(node["level"]) is not int or not 1 <= node["level"] <= 4:
                    raise ValueError("标题层级必须为1到4的整数")
                selected.append((number, node["level"]))
                continue
            if "\n" in prefix or "\r" in prefix:
                raise ValueError("标题前缀不得跨行")
            heading = _heading(prefix, number)
            if not heading or heading.kind != "formal" or len(heading.title.strip()) < 2 or re.search(r"[，,：:]", heading.title):
                raise ValueError("标题前缀不符合独立正式标题要求")
            positions[offsets[number] + len(prefix)] = "分开模型确认的标题与正文"
        if type(node["level"]) is not int or not 1 <= node["level"] <= 4:
            raise ValueError("标题层级必须为1到4的整数")
        selected.append((number, node["level"]))
    if not _valid_levels([level for _, level in selected]):
        raise ValueError("标题层级存在缺失或跳级")
    content, edits = _insert_breaks(layout.content, positions, "layout_model")
    mapped = [{"line": number + 2 * sum(position < offsets[number] for position in positions), "level": level}
              for number, level in selected]
    if [item.line for item in inspect_numbering(content, chapter_title).headings] != [item["line"] for item in mapped]:
        raise ValueError("断行后标题与结构建议不一致")
    return content, edits, {"headings": mapped}
