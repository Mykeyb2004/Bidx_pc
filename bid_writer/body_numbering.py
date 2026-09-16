"""Conservative, line-based repair of bid body headings, without rewriting prose."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_CN = "零〇一二三四五六七八九十百千两"
_FORMAL = re.compile(
    rf"^(?:(?P<one>[{_CN}]+)、|[（(](?P<two>[{_CN}]+)[）)]|"
    r"(?P<three>\d+)\.(?!\d)|[（(](?P<four>\d+)[）)])[ \t]*(?P<title>.*)$"
)
_MARKDOWN = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_EMPHASIS = re.compile(
    r"^(?P<mark>\*\*|__)(?P<title>.+?)(?P=mark)"
    r"(?P<annotation>[ \t]*(?:（[^（）]*）|\([^()]*\)))?$"
)
_CIRCLED = re.compile(r"^(?P<number>[①-⑳])[ \t]*(?P<title>.*)$")


@dataclass(frozen=True)
class BodyHeading:
    line: int
    level: int
    number: int | None
    title: str
    kind: str
    indent: str = ""
    bold: str = ""
    ending: str = ""
    annotation: str = ""


@dataclass
class NumberingInspection:
    headings: list[BodyHeading]
    issues: list[dict[str, Any]]
    duplicate_lines: list[int]


@dataclass
class NumberingRepair:
    content: str
    issues_before: list[dict[str, Any]]
    issues_after: list[dict[str, Any]]
    method: str = "none"
    edits: list[dict[str, Any]] = field(default_factory=list)


class BodyNumberingError(ValueError):
    """A body could not be repaired without making ambiguous content changes."""

    def __init__(self, content: str, report: dict[str, Any]):
        self.content = content
        self.report = report
        issues = report.get("issues_after") or []
        detail = "；".join(item["message"] for item in issues[:3])
        super().__init__(f"正文编号未能可靠修复：{detail or '标题结构不明确'}；草稿已保留，未自动保存。")


def _issue(code: str, line: int, message: str) -> dict[str, Any]:
    return {"code": code, "line": line, "message": message}


def _cn_value(text: str) -> int:
    digits = dict(zip("零一二三四五六七八九", range(10)))
    digits.update({"〇": 0, "两": 2})
    total = digit = 0
    for char in text:
        if char in digits:
            digit = digits[char]
        else:
            total += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
    return total + digit


def _cn_number(number: int) -> str:
    if not 0 < number < 10000:
        raise ValueError("单层标题数量超出支持范围")
    digits = "零一二三四五六七八九"
    result = ""
    pending_zero = False
    for unit, label in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        digit, number = divmod(number, unit)
        if digit:
            if pending_zero:
                result += "零"
            result += digits[digit] + label
            pending_zero = False
        elif result and number:
            pending_zero = True
    return result[1:] if result.startswith("一十") else result


def _marker(level: int, number: int) -> str:
    if level == 1:
        return f"{_cn_number(number)}、"
    if level == 2:
        return f"（{_cn_number(number)}）"
    if level == 3:
        return f"{number}. "
    return f"（{number}）"


def _standalone_title(title: str) -> bool:
    # Full sentences and long numbered list items are prose, not editable headings.
    return bool(title.strip()) and len(title.strip()) <= 100 and not re.search(r"[。！？!?；;]", title)


def _split_heading_line(line: str) -> tuple[str, str, str]:
    """Separate display text from indentation and Markdown hard-break suffixes."""
    raw = line.rstrip("\r\n")
    display = raw.rstrip(" \t")
    if display.endswith("\\") and not display.endswith("\\\\"):
        display = display[:-1].rstrip(" \t")
    ending = raw[len(display):] + line[len(raw):]
    indent = display[:len(display) - len(display.lstrip(" \t"))]
    return indent, display[len(indent):], ending


def _chapter_title_text(line: str) -> str:
    """Ignore presentation wrappers, never the chapter's actual number or words."""
    _, text, _ = _split_heading_line(line)
    for _ in range(2):
        markdown = _MARKDOWN.match(text)
        if markdown:
            text = markdown[2]
        emphasis = _EMPHASIS.fullmatch(text)
        if emphasis and not emphasis["annotation"]:
            text = emphasis["title"]
    return text


def _heading(line: str, line_number: int) -> BodyHeading | None:
    indent, text, ending = _split_heading_line(line)
    emphasis = _EMPHASIS.fullmatch(text)
    bold = ""
    annotation = ""
    if emphasis and emphasis["mark"] not in emphasis["title"]:
        bold = emphasis["mark"]
        annotation = emphasis["annotation"] or ""
        text = emphasis["title"]
    markdown = _MARKDOWN.match(text)
    if markdown:
        level = len(markdown[1])
        title = markdown[2]
        inner = _FORMAL.match(title)
        if inner:
            title = inner["title"]
        if _standalone_title(title):
            return BodyHeading(line_number, level, None, title, "markdown", indent, bold, ending, annotation)
        return None
    match = _FORMAL.match(text)
    if match and _standalone_title(match["title"]):
        for level, group in enumerate(("one", "two", "three", "four"), 1):
            if match[group] is not None:
                value = _cn_value(match[group]) if level < 3 else int(match[group])
                return BodyHeading(line_number, level, value, match["title"], "formal", indent, bold, ending, annotation)
    circled = _CIRCLED.match(text)
    if circled:
        title = circled["title"]
        if _standalone_title(title) and not re.search(r"[①-⑳]", title):
            # Circled markers have no defined depth in our four-level contract.
            return BodyHeading(line_number, 0, ord(circled["number"]) - ord("①") + 1, title, "circled", indent, bold, ending, annotation)
        return None
    if bold and not match and _standalone_title(text) and _standalone_title(text + annotation):
        # Emphasis identifies a candidate boundary, never a parent/child depth.
        return BodyHeading(line_number, 0, None, text, "emphasis", indent, bold, ending, annotation)
    return None


def _scan(text: str, chapter_title: str) -> tuple[list[BodyHeading], list[int], list[dict[str, Any]]]:
    headings: list[BodyHeading] = []
    duplicates: list[int] = []
    issues: list[dict[str, Any]] = []
    fence_char = ""
    fence_length = 0
    first_content = True
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        fence = _FENCE.match(line.rstrip("\r\n"))
        if fence_char:
            if fence and fence[1][0] == fence_char and len(fence[1]) >= fence_length and not fence[2].strip():
                fence_char = ""
            continue
        if fence:
            fence_char, fence_length = fence[1][0], len(fence[1])
            first_content = False
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if first_content and chapter_title:
            plain = _chapter_title_text(line)
            if plain == chapter_title.strip():
                duplicates.append(number)
                issues.append(_issue("repeated_chapter_title", number, f"第{number}行重复了输入章节标题"))
                first_content = False
                continue
        first_content = False
        if stripped.startswith(">") or stripped.count("|") >= 2:
            continue
        candidate = _heading(line, number)
        if candidate:
            headings.append(candidate)
            if candidate.kind in {"emphasis", "circled"}:
                issues.append(_issue("nonstandard_heading", number, f"第{number}行使用加粗或圈号标题，需确认层级并转换为正式序号"))
        if _MARKDOWN.match(stripped.removeprefix("**")):
            issues.append(_issue("markdown_heading", number, f"第{number}行使用了 Markdown 标题"))
    if fence_char:
        issues.append(_issue("unclosed_fence", 0, "正文存在未闭合的代码围栏，无法可靠判断后续标题"))
    return headings, duplicates, issues


def _valid_levels(levels: list[int]) -> bool:
    return bool(levels) and levels[0] == 1 and all(
        type(level) is int and 1 <= level <= 4 and (i == 0 or level <= levels[i - 1] + 1)
        for i, level in enumerate(levels)
    )


def inspect_numbering(text: str, chapter_title: str = "") -> NumberingInspection:
    headings, duplicates, issues = _scan(text, chapter_title)
    if not headings:
        issues.append(_issue("missing_formal_hierarchy", 0, "正文缺少可辨认的正式层级标题"))
    else:
        first = headings[0]
        if first.kind != "formal" or first.level != 1 or first.number != 1:
            issues.append(_issue("numbering_start", first.line, f"第{first.line}行的首个正文标题必须从“一、”开始"))
        families = {item.kind for item in headings}
        if len(families) > 1:
            issues.append(_issue("mixed_heading_styles", first.line, "正文混用了不同样式的标题，层级需要确认"))
        elif not _valid_levels([item.level for item in headings]):
            issues.append(_issue("heading_levels", first.line, "标题层级存在缺失或跳级"))
        counters = [0] * 4
        for item in headings:
            if item.kind != "formal":
                continue
            counters[item.level - 1] += 1
            counters[item.level:] = [0] * (4 - item.level)
            if item.number != counters[item.level - 1]:
                issues.append(_issue("heading_sequence", item.line, f"第{item.line}行标题编号不连续或未随父级重置"))
    return NumberingInspection(headings, issues, duplicates)


def repair_numbering(
    text: str,
    chapter_title: str = "",
    *,
    proposal: Any = None,
) -> NumberingRepair:
    inspection = inspect_numbering(text, chapter_title)
    if not inspection.issues:
        return NumberingRepair(text, [], [])
    headings = inspection.headings
    failure = NumberingRepair(text, inspection.issues, inspection.issues)
    if not headings or any(item["code"] == "unclosed_fence" for item in inspection.issues):
        return failure
    if proposal is None:
        if len({item.kind for item in headings}) != 1 or headings[0].kind not in {"formal", "markdown"}:
            return failure
        levels = [item.level - headings[0].level + 1 for item in headings]
        method = "local"
    else:
        # The model supplies structure only. It never supplies replacement text.
        if not isinstance(proposal, dict) or set(proposal) != {"headings"}:
            return failure
        nodes = proposal["headings"]
        if not isinstance(nodes, list) or len(nodes) != len(headings):
            return failure
        levels = []
        for node, original in zip(nodes, headings):
            if not isinstance(node, dict) or set(node) != {"line", "level"}:
                return failure
            if type(node["line"]) is not int or node["line"] != original.line:
                return failure
            levels.append(node["level"])
        method = "model"
    if not _valid_levels(levels):
        return failure

    lines = text.splitlines(keepends=True)
    edits: list[dict[str, Any]] = []
    counters = [0] * 4
    for item, level in zip(headings, levels):
        counters[level - 1] += 1
        counters[level:] = [0] * (4 - level)
        new_line = item.indent + item.bold + _marker(level, counters[level - 1]) + item.title + item.bold + item.annotation + item.ending
        old_line = lines[item.line - 1]
        if old_line != new_line:
            edits.append({"line": item.line, "before": old_line, "after": new_line})
            lines[item.line - 1] = new_line
    for number in inspection.duplicate_lines:
        edits.append({"line": number, "before": lines[number - 1], "after": ""})
        lines[number - 1] = ""
    candidate = "".join(lines)
    after = inspect_numbering(candidate, chapter_title)
    if after.issues:
        return failure
    # All edits are constructed from original headings, never model-authored text.
    return NumberingRepair(candidate, inspection.issues, [], method, edits)
