"""Recover unambiguous Mermaid line boundaries without rewriting graph tokens."""

from __future__ import annotations

import re
from typing import Any

from .body_numbering import _FENCE, _INLINE_MERMAID


_ID = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_ARROW = re.compile(r"(?:-->|==>|-\.->|---)")
_DECLARATION = re.compile(r"(?:flowchart|graph)[ \t]+(?:TD|TB|BT|LR|RL)")
_PAIRS = {"[": "]", "(": ")", "{": "}"}


def _balanced_end(text: str, start: int) -> int | None:
    stack: list[str] = []
    quote = ""
    escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in '\"`':
            quote = char
        elif char in _PAIRS:
            stack.append(_PAIRS[char])
        elif char in "])}":
            if not stack or stack.pop() != char:
                return None
            if not stack:
                return pos + 1
    return None


def _node_end(text: str, start: int) -> int | None:
    match = _ID.match(text, start)
    if not match:
        return None
    end = match.end()
    if end < len(text) and text[end] in _PAIRS:
        return _balanced_end(text, end)
    return end


def _edge_breaks(line: str) -> list[int]:
    """Accept complete simple edge chains only, never label/comment fragments."""
    positions: list[int] = []
    cursor = len(line) - len(line.lstrip(" \t"))
    end = _node_end(line, cursor)
    if end is None:
        return []
    edges = 0
    while end < len(line):
        cursor = end
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
        if cursor == len(line) or line.startswith("%%", cursor):
            return positions
        arrow = _ARROW.match(line, cursor)
        if arrow:
            cursor = arrow.end()
            while cursor < len(line) and line[cursor] in " \t":
                cursor += 1
            # Pipe labels and other Mermaid constructs are deliberately left alone.
            node = _node_end(line, cursor)
            if node is None:
                return []
            end = node
            edges += 1
            continue
        if not edges or cursor == end:
            return []
        node = _node_end(line, cursor)
        if node is None or not _ARROW.match(line, node + len(line[node:]) - len(line[node:].lstrip(" \t"))):
            return []
        positions.append(cursor)
        end = node
        edges = 0
    return positions


def _closing_fence(text: str, start: int, fence: str) -> tuple[int, int] | None:
    """Find a matching fence outside node labels, quoted text and comments."""
    pos = start
    while pos < len(text):
        if text.startswith("%%", pos):
            newline = re.search(r"[\r\n]", text[pos:])
            if newline is None:
                return None
            pos += newline.end()
        elif text[pos] in _PAIRS:
            end = _balanced_end(text, pos)
            if end is None:
                return None
            pos = end
        elif text.startswith(fence, pos):
            end = pos + len(fence)
            while end < len(text) and text[end] == fence[0]:
                end += 1
            if text[end:].startswith("mermaid"):
                return None  # A second opener cannot close an unfinished block.
            return pos, end
        elif text[pos] in '\"`':
            quoted = re.match(r'"(?:\\.|[^"\\])*"|`[^`]*`', text[pos:])
            if quoted is None:
                return None
            pos += quoted.end()
        else:
            pos += 1
    return None


def _literal_spans(text: str) -> list[tuple[int, int]]:
    """Protect multiline node labels, quoted strings and line comments."""
    spans: list[tuple[int, int]] = []
    pos = 0
    while pos < len(text):
        end = None
        if text.startswith("%%", pos):
            newline = re.search(r"[\r\n]", text[pos:])
            end = pos + newline.start() if newline else len(text)
        elif text[pos] in _PAIRS:
            end = _balanced_end(text, pos) or len(text)
        elif text[pos] in '\"`':
            quoted = re.match(r'"(?:\\.|[^"\\])*"|`[^`]*`', text[pos:])
            end = pos + quoted.end() if quoted else len(text)
        if end is not None:
            spans.append((pos, end))
            pos = end
        else:
            pos += 1
    return spans


def _require_break(text: str, pos: int, count: int, reason: str,
                   positions: dict[int, tuple[int, str]]) -> None:
    # Existing CRLF counts as one break; horizontal whitespace is preserved.
    before = re.search(r"(?:[ \t]*(?:\r\n|[\r\n]))*[ \t]*$", text[:pos])[0]
    after = re.match(r"(?:[ \t]*(?:\r\n|[\r\n]))*[ \t]*", text[pos:])[0]
    present = len(re.findall(r"\r\n|[\r\n]", before + after))
    missing = count - present
    if missing > 0 and missing > positions.get(pos, (0, ""))[0]:
        positions[pos] = (missing, reason)


def repair_mermaid_layout(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Insert newlines only in bounded Mermaid blocks; leave ambiguous text intact."""
    positions: dict[int, tuple[int, str]] = {}
    offset = 0
    other_fence = ""
    while offset < len(text):
        line_start = offset
        newline = re.search(r"\r\n|[\r\n]", text[offset:])
        line = text[offset:offset + newline.end()] if newline else text[offset:]
        offset += len(line)
        display = line.rstrip("\r\n")
        fence = _FENCE.match(display)
        if other_fence:
            if fence and fence[1][0] == other_fence[0] and len(fence[1]) >= len(other_fence) and not fence[2].strip():
                other_fence = ""
            continue
        opener = _INLINE_MERMAID.search(display)
        prefix = display[:opener.start()] if opener else ""
        if not opener or re.search(r"[`~]", prefix) or display.lstrip().startswith((">", "|")):
            if fence:
                other_fence = fence[1]
            continue
        start, body_start = line_start + opener.start(), line_start + opener.end()
        closing = _closing_fence(text, body_start, opener["fence"])
        if closing is None:
            break  # Do not reinterpret later prose inside an unbounded block.
        close_start, close_end = closing
        offset = close_end  # The same source line can contain more prose/graphs.
        if text[:start].strip():
            _require_break(text, start, 2, "分开图名或正文与 Mermaid 开围栏", positions)
        _require_break(text, body_start, 1, "分开 Mermaid 语言标记与图声明", positions)
        _require_break(text, close_start, 1, "使 Mermaid 闭围栏独立成行", positions)
        if text[close_end:].strip():
            _require_break(text, close_end, 2, "分开 Mermaid 闭围栏与后续正文", positions)
        body = text[body_start:close_start]
        leading = len(body) - len(body.lstrip())
        declaration = _DECLARATION.match(body, leading)
        if declaration:
            literals = _literal_spans(body)
            graph_start = declaration.end()
            tail = body[graph_start:]
            first_node = graph_start + len(tail) - len(tail.lstrip(" \t"))
            if first_node < len(body) and _node_end(body, first_node) is not None:
                _require_break(text, body_start + first_node, 1, "分开 Mermaid 图声明与首条语句", positions)
            # Only flowchart/graph uses the node/arrow grammar handled here.
            graph_offset = body_start + graph_start
            for graph_line in body[graph_start:].splitlines(keepends=True):
                for split in _edge_breaks(graph_line.rstrip("\r\n")):
                    body_pos = graph_offset + split - body_start
                    if not any(start <= body_pos < end for start, end in literals):
                        _require_break(text, graph_offset + split, 1, "分开由空格粘连的 Mermaid 连线语句", positions)
                graph_offset += len(graph_line)
    eol_match = re.search(r"\r\n|\n|\r", text)
    eol = eol_match[0] if eol_match else "\n"
    edits = [{"stage": "mermaid_layout", "offset": pos, "before": "", "after": eol * count, "reason": reason}
             for pos, (count, reason) in sorted(positions.items())]
    content = text
    for edit in reversed(edits):
        pos = edit["offset"]
        content = content[:pos] + edit["after"] + content[pos:]
    return content, edits
