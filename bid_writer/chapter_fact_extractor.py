from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from .chapter_fact_store import ChapterFactRecord, ChapterFactStore, ExtractedFact
from .config import Config
from .file_saver import FileSaver
from .outline_parser import HeadingNode


@dataclass(frozen=True)
class ChapterFactResult:
    chapter_full_path: str
    title: str
    facts: list[ExtractedFact]


class ChapterFactExtractor:
    """从已生成章节正文中提取可复用 facts。"""

    _FACT_LINE_RE = re.compile(
        r"^\s*[-*]?\s*\[(global|local)\]\s*([^:：]+?)\s*[:：]\s*(.+?)\s*$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        config: Config,
        file_saver: FileSaver,
        fact_store: ChapterFactStore,
    ):
        self.config = config
        self.file_saver = file_saver
        self.fact_store = fact_store

    def get_output_fact_status(self, heading: HeadingNode) -> str:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return "missing_output"

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return "missing_output"

        source_hash = self._hash_source(content)
        cached = self.fact_store.get(heading)
        if cached is not None and cached.source_hash == source_hash:
            return "up_to_date"
        return "needs_refresh"

    def ensure_output_facts(self, heading: HeadingNode) -> Optional[ChapterFactResult]:
        if not self.config.chapter_facts_enabled:
            return None

        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return None

        content = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not content:
            return None

        source_hash = self._hash_source(content)
        cached = self.fact_store.get(heading)
        if cached is not None and cached.source_hash == source_hash:
            return self._to_result(cached)

        facts = self._extract_facts(heading, content)
        if facts is None:
            return None

        record = self.fact_store.save(
            heading=heading,
            source_hash=source_hash,
            facts=facts,
        )
        return self._to_result(record)

    def _extract_facts(self, heading: HeadingNode, content: str) -> Optional[list[ExtractedFact]]:
        client, model = self._get_client_and_model()
        prompt = "\n\n".join(
            [
                "请从以下标书章节正文中提取所有可被其他章节引用的事实性信息。",
                "提取规则：",
                "1. 只提取具体事实断言：时间节点、人员数量/姓名、技术选型、服务承诺、数量指标、流程阶段划分等。",
                "2. 不要提取概括性描述或修饰性表述。",
                "3. 每条事实单独占一行，格式必须为：- [global] 类别: 具体内容 或 - [local] 类别: 具体内容。",
                "4. 如果信息可能被不同主题章节复用，标记为 [global]；否则标记为 [local]。",
                f"5. 最多输出 {self.config.chapter_facts_max_facts_per_chapter} 条事实。",
                "6. 如果没有可提取的硬事实，只输出“无可提取事实”。",
                f"章节标题：{heading.title}",
                f"章节路径：{heading.full_path}",
                "章节正文：",
                content,
            ]
        )
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max(800, self.config.chapter_facts_max_facts_per_chapter * 120),
                messages=[
                    {
                        "role": "system",
                        "content": "你是标书事实提炼助手，只输出结构化事实，不输出解释。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception:
            return None

        content_text = (response.choices[0].message.content or "").strip()
        return self.parse_fact_response(
            content_text,
            max_facts=self.config.chapter_facts_max_facts_per_chapter,
        )

    @classmethod
    def parse_fact_response(cls, content: str, *, max_facts: int) -> list[ExtractedFact]:
        normalized = content.strip()
        if not normalized or normalized == "无可提取事实":
            return []

        facts: list[ExtractedFact] = []
        for line in normalized.splitlines():
            match = cls._FACT_LINE_RE.match(line)
            if not match:
                continue
            scope, category, value = match.groups()
            facts.append(
                ExtractedFact(
                    scope=scope.lower(),
                    category=category.strip(),
                    value=value.strip(),
                )
            )
            if len(facts) >= max(1, max_facts):
                break
        return facts

    def _get_client_and_model(self) -> tuple[OpenAI, str]:
        if self.config.pruning_api_is_configured:
            client = OpenAI(
                base_url=self.config.pruning_api_base_url,
                api_key=self.config.pruning_api_key,
                timeout=self.config.pruning_timeout_seconds,
                max_retries=self.config.pruning_max_retries,
            )
            return client, self.config.pruning_model
        client = OpenAI(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        return client, self.config.model

    @staticmethod
    def _hash_source(content: str) -> str:
        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
        return f"output:{digest}"

    @staticmethod
    def _to_result(record: ChapterFactRecord) -> ChapterFactResult:
        return ChapterFactResult(
            chapter_full_path=record.chapter_full_path,
            title=record.title,
            facts=record.facts,
        )
