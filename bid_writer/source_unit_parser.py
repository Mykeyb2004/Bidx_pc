"""
采购需求与评分标准的统一分段解析器。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .retrieval_models import SourceUnit


_MARKDOWN_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
_MARKDOWN_TABLE_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_TABLE_ALIGN_CELL_RE = re.compile(r'^:?-{3,}:?$')
_LEADING_NUMBER_RE = re.compile(r'^\s*[\d一二三四五六七八九十百千万零]+(?:[.、]\d+)*[.、]?\s*')
_LIST_ITEM_START_RE = re.compile(
    r'^\s*(?:[-*+]|(?:\d+(?:\.\d+)*)[.、)]|[一二三四五六七八九十]+、|[（(]\d+[)）]|[（(][一二三四五六七八九十]+[)）])\s+'
)
_SCORE_RE = re.compile(r'(?:满分|得分|分值|权重|得|计|共计)?\s*\d+(?:\.\d+)?\s*分')
_GENERIC_SCORE_TITLE_RE = re.compile(r'^(?:评分标准|评审标准|评审内容|评审办法|评分办法)\s*[:：]?\s*$', re.I)


@dataclass
class _StructuredBlock:
    block_type: str
    section_path: str
    lines: list[str]
    order_index: int

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


class SourceUnitParser:
    """将 Markdown 文本解析成统一的源文片段。"""

    def parse_requirements(self, text: str) -> list[SourceUnit]:
        blocks = self._merge_heading_blocks(self._parse_structured_blocks(text))
        units: list[SourceUnit] = []
        next_index = 0
        for block in blocks:
            if block.block_type == "table":
                table_units, next_index = self._parse_generic_table_units(block, "requirements", next_index)
                units.extend(table_units)
                continue

            unit = self._build_text_unit(
                doc_type="requirements",
                block_type="heading_block" if block.block_type == "heading_block" else "paragraph",
                section_path=block.section_path,
                lines=block.lines,
                order_index=next_index,
            )
            if unit is None:
                continue
            units.append(unit)
            next_index += 1
        return units

    def parse_scoring(self, text: str, parse_mode: str = "auto") -> list[SourceUnit]:
        units: list[SourceUnit] = []
        next_index = 0
        normalized_mode = (parse_mode or "auto").strip().lower()

        if normalized_mode in {"auto", "table_only"}:
            table_units = self.parse_scoring_table_units(text, start_index=next_index)
            units.extend(table_units)
            next_index += len(table_units)

        if normalized_mode in {"auto", "text_only"}:
            text_units = self.parse_scoring_text_units(text, start_index=next_index)
            units.extend(text_units)

        deduped: list[SourceUnit] = []
        seen: set[tuple[str, str, str]] = set()
        for unit in units:
            key = (
                unit.section_path.strip(),
                unit.title.strip(),
                unit.source_text_exact.strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(unit)
        return deduped

    def parse_scoring_table_units(self, text: str, start_index: int = 0) -> list[SourceUnit]:
        blocks = self._parse_structured_blocks(text)
        units: list[SourceUnit] = []
        next_index = start_index
        for block in blocks:
            if block.block_type != "table":
                continue
            parsed_units, next_index = self._parse_scoring_table_block(block, next_index)
            units.extend(parsed_units)
        return units

    def parse_scoring_text_units(self, text: str, start_index: int = 0) -> list[SourceUnit]:
        blocks = self._merge_heading_blocks(self._parse_structured_blocks(text))
        units: list[SourceUnit] = []
        next_index = start_index

        for block in blocks:
            if block.block_type == "table":
                continue
            parts = self._split_scoring_parts(block.lines)
            for part_lines in parts:
                unit = self._build_text_unit(
                    doc_type="scoring",
                    block_type="text_rule",
                    section_path=block.section_path,
                    lines=part_lines,
                    order_index=next_index,
                )
                if unit is None:
                    continue
                if (
                    not unit.weight_text
                    and not self._looks_like_scoring_item_start(part_lines[0].strip())
                    and not _GENERIC_SCORE_TITLE_RE.match(part_lines[0].strip())
                    and not unit.title
                    and len(unit.source_text.strip()) < 18
                ):
                    continue
                units.append(unit)
                next_index += 1
        return units

    def _parse_structured_blocks(self, text: str) -> list[_StructuredBlock]:
        lines = text.splitlines()
        heading_stack: list[str] = []
        blocks: list[_StructuredBlock] = []
        current_lines: list[str] = []
        order_index = 0

        def current_section_path() -> str:
            return " > ".join(heading_stack)

        def flush_current() -> None:
            nonlocal current_lines, order_index
            if not current_lines:
                return
            blocks.append(
                _StructuredBlock(
                    block_type="text",
                    section_path=current_section_path(),
                    lines=current_lines[:],
                    order_index=order_index,
                )
            )
            order_index += 1
            current_lines = []

        index = 0
        while index < len(lines):
            raw_line = lines[index].rstrip()
            stripped = raw_line.strip()

            heading_match = _MARKDOWN_HEADING_RE.match(stripped)
            if heading_match:
                flush_current()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(title)
                index += 1
                continue

            if self._is_table_start(lines, index):
                flush_current()
                table_lines: list[str] = []
                while index < len(lines) and _MARKDOWN_TABLE_LINE_RE.match(lines[index].rstrip()):
                    table_lines.append(lines[index].rstrip())
                    index += 1
                blocks.append(
                    _StructuredBlock(
                        block_type="table",
                        section_path=current_section_path(),
                        lines=table_lines,
                        order_index=order_index,
                    )
                )
                order_index += 1
                continue

            if not stripped:
                flush_current()
                index += 1
                continue

            current_lines.append(raw_line)
            index += 1

        flush_current()
        return blocks

    @staticmethod
    def _is_table_start(lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        first = lines[index].rstrip()
        second = lines[index + 1].rstrip()
        if not _MARKDOWN_TABLE_LINE_RE.match(first) or not _MARKDOWN_TABLE_LINE_RE.match(second):
            return False
        header = SourceUnitParser._split_markdown_row(first)
        align_row = SourceUnitParser._split_markdown_row(second)
        return (
            len(header) == len(align_row)
            and len(header) > 1
            and all(_TABLE_ALIGN_CELL_RE.match(cell.replace(" ", "")) for cell in align_row)
        )

    @staticmethod
    def _split_markdown_row(line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    @classmethod
    def _merge_heading_blocks(cls, blocks: list[_StructuredBlock]) -> list[_StructuredBlock]:
        merged: list[_StructuredBlock] = []
        index = 0
        while index < len(blocks):
            block = blocks[index]
            if (
                block.block_type == "text"
                and cls._looks_like_heading_block(block.text)
                and index + 1 < len(blocks)
                and blocks[index + 1].block_type == "text"
                and blocks[index + 1].section_path == block.section_path
            ):
                merged.append(
                    _StructuredBlock(
                        block_type="heading_block",
                        section_path=block.section_path,
                        lines=block.lines + blocks[index + 1].lines,
                        order_index=block.order_index,
                    )
                )
                index += 2
                continue
            merged.append(block)
            index += 1
        return merged

    @staticmethod
    def _clean_line(text: str) -> str:
        cleaned = text.replace("**", "").replace("<br>", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _title_core(text: str) -> str:
        stripped = _MARKDOWN_HEADING_RE.sub(lambda match: match.group(2).strip(), text.strip())
        stripped = _LEADING_NUMBER_RE.sub("", stripped)
        return re.sub(r"\s+", " ", stripped).strip()

    @classmethod
    def _looks_like_heading_block(cls, block: str) -> bool:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            return False
        if len(lines) > 2:
            return False
        if len(block) <= 36:
            return True
        first_line = lines[0]
        return bool(
            first_line.startswith(("#", "**", "一、", "二、", "三、", "四、", "五、"))
            or re.match(r"^\d+(?:\.\d+)*", first_line)
        )

    @classmethod
    def _looks_like_scoring_item_start(cls, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if _LIST_ITEM_START_RE.match(stripped):
            return True
        if _SCORE_RE.search(stripped) and len(stripped) <= 80:
            return True
        return stripped.endswith("：") and len(stripped) <= 36

    @staticmethod
    def _extract_weight_text(text: str) -> str:
        match = _SCORE_RE.search(text)
        return match.group(0).strip() if match else ""

    @classmethod
    def _strip_weight_from_title(cls, title: str) -> str:
        stripped = _SCORE_RE.sub("", title).strip()
        stripped = re.sub(r"[（(]\s*[)）]$", "", stripped).strip()
        return stripped or title

    def _build_text_unit(
        self,
        doc_type: str,
        block_type: str,
        section_path: str,
        lines: list[str],
        order_index: int,
    ) -> Optional[SourceUnit]:
        raw_lines = [line.rstrip() for line in lines if line.strip()]
        if not raw_lines:
            return None

        cleaned_lines = [self._clean_line(line) for line in raw_lines if self._clean_line(line)]
        if not cleaned_lines:
            return None

        title = ""
        body_lines = cleaned_lines
        if len(cleaned_lines) >= 2 and self._looks_like_heading_block("\n".join(cleaned_lines[:2])):
            title = self._strip_weight_from_title(self._title_core(cleaned_lines[0]))
            body_lines = cleaned_lines[1:]
        elif len(cleaned_lines) >= 2 and len(cleaned_lines[0]) <= 26:
            title = self._strip_weight_from_title(self._title_core(cleaned_lines[0]))
            body_lines = cleaned_lines[1:]
        elif doc_type == "scoring" and self._looks_like_scoring_item_start(cleaned_lines[0]):
            title = self._strip_weight_from_title(self._title_core(cleaned_lines[0]))
            body_lines = cleaned_lines[1:]

        body = " ".join(body_lines).strip()
        if not body:
            body = " ".join(cleaned_lines).strip()
        if not body:
            return None

        weight_text = self._extract_weight_text(cleaned_lines[0])
        source_text_exact = "\n".join(raw_lines).strip()
        if doc_type == "scoring":
            source_text_exact = body

        return SourceUnit(
            unit_id=f"{doc_type}-{order_index:04d}",
            doc_type=doc_type,
            section_path=section_path,
            block_type=block_type,
            title=title,
            weight_text=weight_text,
            source_text=body,
            source_text_exact=source_text_exact,
            order_index=order_index,
        )

    def _parse_generic_table_units(
        self,
        block: _StructuredBlock,
        doc_type: str,
        start_index: int,
    ) -> tuple[list[SourceUnit], int]:
        header = self._split_markdown_row(block.lines[0])
        rows = [self._split_markdown_row(line) for line in block.lines[2:] if _MARKDOWN_TABLE_LINE_RE.match(line)]
        units: list[SourceUnit] = []
        next_index = start_index
        for row in rows:
            if len(row) != len(header):
                continue
            non_empty = [cell for cell in row if cell.strip()]
            if not non_empty:
                continue
            title = non_empty[0].strip()
            body = "；".join(cell.strip() for cell in non_empty[1:] if cell.strip()) or title
            units.append(
                SourceUnit(
                    unit_id=f"{doc_type}-{next_index:04d}",
                    doc_type=doc_type,
                    section_path=block.section_path,
                    block_type="table_row",
                    title=self._title_core(title),
                    source_text=body,
                    source_text_exact=" | ".join(non_empty),
                    order_index=next_index,
                )
            )
            next_index += 1
        return units, next_index

    @staticmethod
    def _find_header_index(headers: list[str], candidates: list[str]) -> Optional[int]:
        normalized_headers = [header.strip().lower() for header in headers]
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for index, header in enumerate(normalized_headers):
                if header == candidate_lower:
                    return index
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for index, header in enumerate(normalized_headers):
                if candidate_lower in header:
                    return index
        return None

    def _parse_scoring_table_block(
        self,
        block: _StructuredBlock,
        start_index: int,
    ) -> tuple[list[SourceUnit], int]:
        headers = self._split_markdown_row(block.lines[0])
        rows = [self._split_markdown_row(line) for line in block.lines[2:] if _MARKDOWN_TABLE_LINE_RE.match(line)]
        subitem_index = self._find_header_index(headers, ["子项", "评分项", "评审因素", "项目", "子项目"])
        standard_index = self._find_header_index(headers, ["评审标准", "评分标准", "评审内容", "标准"])
        weight_index = self._find_header_index(headers, ["权重", "分值", "满分", "分数"])
        if subitem_index is None or standard_index is None:
            return [], start_index

        units: list[SourceUnit] = []
        next_index = start_index
        for row in rows:
            if len(row) <= max(subitem_index, standard_index):
                continue
            subitem = row[subitem_index].strip()
            standard = row[standard_index].strip()
            weight = row[weight_index].strip() if weight_index is not None and len(row) > weight_index else ""
            if not subitem or not standard:
                continue
            units.append(
                SourceUnit(
                    unit_id=f"scoring-{next_index:04d}",
                    doc_type="scoring",
                    section_path=block.section_path,
                    block_type="table_row",
                    title=self._title_core(subitem),
                    weight_text=weight,
                    source_text=standard,
                    source_text_exact=standard,
                    order_index=next_index,
                )
            )
            next_index += 1
        return units, next_index

    def _split_scoring_parts(self, lines: list[str]) -> list[list[str]]:
        normalized_lines = [line.rstrip() for line in lines if line.strip()]
        if not normalized_lines:
            return []

        parts: list[list[str]] = []
        current: list[str] = []
        start_count = 0

        for line in normalized_lines:
            stripped = line.strip()
            if self._looks_like_scoring_item_start(stripped):
                start_count += 1
                if current:
                    parts.append(current)
                current = [line]
                continue
            if current:
                current.append(line)
            else:
                current = [line]

        if current:
            parts.append(current)

        if start_count >= 2:
            return parts
        return [normalized_lines]
