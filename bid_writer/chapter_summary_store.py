from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import Config
from .outline_parser import HeadingNode


def _now_string() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


@dataclass(frozen=True)
class ChapterSummaryRecord:
    chapter_full_path: str
    title: str
    source_kind: str
    source_hash: str
    summary: str
    generated_at: str


class ChapterSummaryStore:
    """持久化保存章节摘要缓存。"""

    def __init__(self, config: Config):
        self.config = config
        self.base_dir = config.project_root_path / ".bid_writer"
        self.path = self.base_dir / "chapter_summaries.json"

    def get(self, heading: HeadingNode | str) -> Optional[ChapterSummaryRecord]:
        full_path = heading.full_path if isinstance(heading, HeadingNode) else str(heading)
        item = self._load_payload().get("items", {}).get(full_path)
        if not isinstance(item, dict):
            return None
        summary = str(item.get("summary", "") or "").strip()
        if not summary:
            return None
        return ChapterSummaryRecord(
            chapter_full_path=full_path,
            title=str(item.get("title", "") or ""),
            source_kind=str(item.get("source_kind", "") or ""),
            source_hash=str(item.get("source_hash", "") or ""),
            summary=summary,
            generated_at=str(item.get("generated_at", "") or ""),
        )

    def save(
        self,
        *,
        heading: HeadingNode,
        source_kind: str,
        source_hash: str,
        summary: str,
    ) -> ChapterSummaryRecord:
        normalized_summary = summary.strip()
        record = ChapterSummaryRecord(
            chapter_full_path=heading.full_path,
            title=heading.title,
            source_kind=source_kind.strip(),
            source_hash=source_hash.strip(),
            summary=normalized_summary,
            generated_at=_now_string(),
        )
        payload = self._load_payload()
        items = payload.setdefault("items", {})
        items[heading.full_path] = {
            "title": record.title,
            "source_kind": record.source_kind,
            "source_hash": record.source_hash,
            "summary": record.summary,
            "generated_at": record.generated_at,
        }
        payload["updated_at"] = record.generated_at
        _write_json_atomic(self.path, payload)
        return record

    def _load_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": 1,
                "updated_at": "",
                "items": {},
            }

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
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
