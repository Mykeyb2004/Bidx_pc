from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

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


class ChapterDependencyStore:
    """持久化保存章节依赖关系。"""

    def __init__(self, config: Config):
        self.config = config
        self.base_dir = config.project_root_path / ".bid_writer"
        self.path = self.base_dir / "chapter_dependencies.json"

    def list_dependency_paths(self, target: HeadingNode | str) -> list[str]:
        target_path = target.full_path if isinstance(target, HeadingNode) else str(target)
        payload = self._load_payload()
        item = payload.get("items", {}).get(target_path, {})
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for value in dependencies:
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def set_dependencies(self, target: HeadingNode, dependencies: list[HeadingNode]) -> None:
        payload = self._load_payload()
        items = payload.setdefault("items", {})

        dependency_paths: list[str] = []
        seen: set[str] = {target.full_path}
        for dependency in dependencies:
            normalized = dependency.full_path.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            dependency_paths.append(normalized)

        if dependency_paths:
            items[target.full_path] = {
                "title": target.title,
                "dependencies": dependency_paths,
            }
        else:
            items.pop(target.full_path, None)

        payload["updated_at"] = _now_string()
        _write_json_atomic(self.path, payload)

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
