from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from .ai_writer import AIWriter
from .config import Config
from .context_pruner import ChapterContext, ScoringCriterion
from .file_saver import FileSaver
from .outline_parser import HeadingNode
from .chapter_summary_store import ChapterSummaryRecord, ChapterSummaryStore


@dataclass(frozen=True)
class ChapterSummaryResult:
    chapter_full_path: str
    title: str
    summary: str
    source_kind: str


class ChapterSummaryGenerator:
    """按章节正文或章节规划生成可复用摘要。"""

    _OUTPUT_SUMMARY_MAX_CHARS = 240
    _PLANNED_SUMMARY_MAX_CHARS = 240

    def __init__(
        self,
        config: Config,
        ai_writer: AIWriter,
        file_saver: FileSaver,
        summary_store: ChapterSummaryStore,
    ):
        self.config = config
        self.ai_writer = ai_writer
        self.file_saver = file_saver
        self.summary_store = summary_store

    def get_available_summary(self, heading: HeadingNode) -> Optional[ChapterSummaryResult]:
        output_summary = self.ensure_output_summary(heading)
        if output_summary is not None:
            return output_summary
        return self.get_cached_planned_summary(heading)

    def get_output_summary_status(self, heading: HeadingNode) -> str:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return "missing_output"

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return "missing_output"

        source_hash = self._hash_source("output", content)
        cached = self.summary_store.get(heading)
        if (
            cached is not None
            and cached.source_kind == "output"
            and cached.source_hash == source_hash
            and cached.summary.strip()
        ):
            return "up_to_date"
        return "needs_refresh"

    def ensure_output_summary(self, heading: HeadingNode) -> Optional[ChapterSummaryResult]:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return None

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return None

        source_hash = self._hash_source("output", content)
        cached = self.summary_store.get(heading)
        if (
            cached is not None
            and cached.source_kind == "output"
            and cached.source_hash == source_hash
        ):
            return self._to_result(cached)

        summary = self._summarize_output(heading, content)
        if not summary:
            return None
        record = self.summary_store.save(
            heading=heading,
            source_kind="output",
            source_hash=source_hash,
            summary=summary,
        )
        return self._to_result(record)

    def get_cached_planned_summary(self, heading: HeadingNode) -> Optional[ChapterSummaryResult]:
        planned_source = self._build_planned_source(heading)
        if not planned_source:
            return None

        source_hash = self._hash_source("planned", planned_source)
        cached = self.summary_store.get(heading)
        if (
            cached is None
            or cached.source_kind != "planned"
            or cached.source_hash != source_hash
        ):
            return None
        return self._to_result(cached)

    def ensure_planned_summary(self, heading: HeadingNode) -> Optional[ChapterSummaryResult]:
        planned_source = self._build_planned_source(heading)
        if not planned_source:
            return None

        source_hash = self._hash_source("planned", planned_source)
        cached = self.summary_store.get(heading)
        if (
            cached is not None
            and cached.source_kind == "planned"
            and cached.source_hash == source_hash
        ):
            return self._to_result(cached)

        summary = self._summarize_planned(heading, planned_source)
        if not summary:
            return None
        record = self.summary_store.save(
            heading=heading,
            source_kind="planned",
            source_hash=source_hash,
            summary=summary,
        )
        return self._to_result(record)

    @staticmethod
    def format_dependency_summary_block(entries: list[ChapterSummaryResult]) -> str:
        if not entries:
            return ""

        lines = [
            "请参考以下关联章节摘要，保持术语、职责、承诺和章节边界一致，避免与关联章节重复或冲突。",
            "",
        ]
        for entry in entries:
            lines.append(f"- {entry.title}：{entry.summary}")
        lines.extend(
            [
                "",
                "请参考以上章节总结内容进行扩写。",
            ]
        )
        return "\n".join(lines).strip()

    def _build_planned_source(self, heading: HeadingNode) -> str:
        lines = [
            f"当前章节路径：{heading.full_path}",
            f"当前章节标题：{heading.title}",
            f"上级标题：{heading.parent.title if heading.parent else '（无）'}",
        ]

        sibling_titles = []
        if heading.parent is not None:
            sibling_titles = [node.title for node in heading.parent.children if node is not heading]
        if sibling_titles:
            lines.append(f"同级标题：{'；'.join(sibling_titles)}")

        context = self._build_planned_context(heading)
        if context is not None:
            if context.response_labels:
                lines.append(f"关联评分板块：{'；'.join(context.response_labels)}")
            if context.scoring_must_respond or context.scoring_reference:
                scoring_lines = self._format_scoring_group(
                    context.scoring_must_respond,
                    context.scoring_reference,
                )
                if scoring_lines:
                    lines.append("评分关注：")
                    lines.extend(scoring_lines)
            elif context.scoring_items:
                scoring_lines = self._format_scoring_items(context.scoring_items)
                if scoring_lines:
                    lines.append("评分关注：")
                    lines.extend(scoring_lines)

            requirement_text = (context.requirement_brief or context.requirement_seed).strip()
            if requirement_text:
                lines.append("需求要点：")
                lines.append(requirement_text)

        return "\n".join(line for line in lines if line.strip()).strip()

    def _build_planned_context(self, heading: HeadingNode) -> Optional[ChapterContext]:
        if not self.config.context_pruning_enabled:
            return None
        try:
            return self.ai_writer.context_pruner.build_context(heading)
        except Exception:
            return None

    @staticmethod
    def _format_scoring_items(items: list[ScoringCriterion]) -> list[str]:
        result: list[str] = []
        for item in items:
            parts = []
            if item.subitem:
                parts.append(item.subitem)
            if item.standard:
                parts.append(item.standard)
            if item.weight:
                parts.append(f"分值/权重：{item.weight}")
            text = "；".join(part for part in parts if part).strip()
            if text:
                result.append(f"- {text}")
        return result

    def _format_scoring_group(
        self,
        must_respond: list[ScoringCriterion],
        reference: list[ScoringCriterion],
    ) -> list[str]:
        lines: list[str] = []
        if must_respond:
            lines.append("- 必须响应：")
            lines.extend(f"  {line}" for line in self._format_scoring_items(must_respond))
        if reference:
            lines.append("- 参考：")
            lines.extend(f"  {line}" for line in self._format_scoring_items(reference))
        return lines

    def _summarize_output(self, heading: HeadingNode, content: str) -> str:
        prompt = "\n\n".join(
            [
                "请将以下已生成标书章节正文提炼为一段可复用摘要，供关联章节扩写时参考。",
                f"当前章节：{heading.title}",
                f"当前章节路径：{heading.full_path}",
                "输出要求：",
                "1. 只输出一段中文摘要，不要标题，不要列表。",
                "2. 长度控制在 160-220 字左右。",
                "3. 保留关键承诺、职责分工、关键术语、机制流程、重要时间或边界信息。",
                "4. 不要评价性语言，不要写“本章主要讲述”。",
                "章节正文：",
                content,
            ]
        )
        return self._generate_summary(
            prompt,
            max_chars=self._OUTPUT_SUMMARY_MAX_CHARS,
        )

    def _summarize_planned(self, heading: HeadingNode, planned_source: str) -> str:
        prompt = "\n\n".join(
            [
                "请基于以下章节信息，提炼一段供关联章节参考的规划摘要。",
                f"当前章节：{heading.title}",
                f"当前章节路径：{heading.full_path}",
                "输出要求：",
                "1. 只输出一段中文摘要，不要标题，不要列表。",
                "2. 长度控制在 160-220 字左右。",
                "3. 说明本章预计覆盖的核心内容、关键承诺、职责边界，以及与其他章节的衔接点。",
                "4. 不要写“将要”“拟”之类空泛话术，尽量直接描述应体现的内容。",
                "章节信息：",
                planned_source,
            ]
        )
        return self._generate_summary(
            prompt,
            max_chars=self._PLANNED_SUMMARY_MAX_CHARS,
        )

    def _generate_summary(self, prompt: str, *, max_chars: int) -> str:
        client, model = self._get_client_and_model()
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max_chars * 2,
                messages=[
                    {
                        "role": "system",
                        "content": "你是标书章节摘要助手，擅长提炼可复用、边界清晰的章节摘要。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception:
            return ""

        content = (response.choices[0].message.content or "").strip()
        return self._normalize_summary(content, max_chars=max_chars)

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        config = self.config
        if config.pruning_api_is_configured:
            client = OpenAI(
                base_url=config.pruning_api_base_url,
                api_key=config.pruning_api_key,
                timeout=config.pruning_timeout_seconds,
                max_retries=config.pruning_max_retries,
            )
            return client, config.pruning_model
        client = OpenAI(
            base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.api_timeout_seconds,
            max_retries=config.api_max_retries,
        )
        return client, config.model

    @staticmethod
    def _hash_source(source_kind: str, content: str) -> str:
        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
        return f"{source_kind}:{digest}"

    @staticmethod
    def _normalize_summary(content: str, *, max_chars: int) -> str:
        normalized = " ".join(content.split()).strip()
        if len(normalized) > max_chars:
            normalized = normalized[: max_chars - 1].rstrip("，、；;：:,.。 ") + "…"
        return normalized

    @staticmethod
    def _to_result(record: ChapterSummaryRecord) -> ChapterSummaryResult:
        return ChapterSummaryResult(
            chapter_full_path=record.chapter_full_path,
            title=record.title,
            summary=record.summary,
            source_kind=record.source_kind,
        )
