from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .chapter_summary_store import _now_string, _write_json_atomic
from .config import Config
from .outline_parser import HeadingNode


@dataclass(frozen=True)
class ExtractedFact:
    scope: str
    category: str
    value: str


@dataclass(frozen=True)
class ChapterFactRecord:
    chapter_full_path: str
    title: str
    source_hash: str
    facts: list[ExtractedFact]
    extracted_at: str


class ChapterFactStore:
    """持久化保存章节 facts 缓存。"""

    def __init__(self, config: Config):
        self.config = config
        self.base_dir = config.project_root_path / ".bid_writer"
        self.path = self.base_dir / "chapter_facts.json"

    def get(self, heading: HeadingNode | str) -> Optional[ChapterFactRecord]:
        full_path = heading.full_path if isinstance(heading, HeadingNode) else str(heading)
        item = self._load_payload().get("items", {}).get(full_path)
        if not isinstance(item, dict):
            return None
        facts_payload = item.get("facts", [])
        if not isinstance(facts_payload, list):
            facts_payload = []
        facts: list[ExtractedFact] = []
        for fact in facts_payload:
            if not isinstance(fact, dict):
                continue
            category = str(fact.get("category", "") or "").strip()
            value = str(fact.get("value", "") or "").strip()
            if not category or not value:
                continue
            facts.append(
                ExtractedFact(
                    scope=str(fact.get("scope", "") or "local").strip().lower(),
                    category=category,
                    value=value,
                )
            )
        return ChapterFactRecord(
            chapter_full_path=full_path,
            title=str(item.get("title", "") or ""),
            source_hash=str(item.get("source_hash", "") or ""),
            facts=facts,
            extracted_at=str(item.get("extracted_at", "") or ""),
        )

    def save(
        self,
        *,
        heading: HeadingNode,
        source_hash: str,
        facts: list[ExtractedFact],
    ) -> ChapterFactRecord:
        record = ChapterFactRecord(
            chapter_full_path=heading.full_path,
            title=heading.title,
            source_hash=source_hash.strip(),
            facts=list(facts),
            extracted_at=_now_string(),
        )
        payload = self._load_payload()
        items = payload.setdefault("items", {})
        items[heading.full_path] = {
            "title": record.title,
            "source_hash": record.source_hash,
            "facts": [
                {
                    "scope": fact.scope,
                    "category": fact.category,
                    "value": fact.value,
                }
                for fact in record.facts
            ],
            "extracted_at": record.extracted_at,
        }
        payload["updated_at"] = record.extracted_at
        _write_json_atomic(self.path, payload)
        return record

    def _load_payload(self) -> dict:
        if not self.path.exists():
            return {
                "version": 1,
                "updated_at": "",
                "items": {},
            }

        try:
            import json

            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {
                "version": 1,
                "updated_at": "",
                "items": {},
            }

        if not isinstance(payload, dict):
            payload = {}
        items = payload.get("items", {})
        if not isinstance(items, dict):
            items = {}
        return {
            "version": 1,
            "updated_at": str(payload.get("updated_at", "") or ""),
            "items": items,
        }
