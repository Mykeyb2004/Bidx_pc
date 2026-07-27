from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


_NODE_NUMBER_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)*)(?:\.|(?=\s|$|、|:|：|-))"
)
_NODE_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")


class WritingPlanStoreError(RuntimeError):
    pass


class WritingPlanValidationError(WritingPlanStoreError):
    pass


class WritingPlanExternalModificationError(WritingPlanStoreError):
    pass


@dataclass(frozen=True)
class WritingPlanItem:
    node: str
    writing_plan: str


@dataclass(frozen=True)
class WritingPlanSnapshot:
    items: tuple[WritingPlanItem, ...]
    fingerprint: str | None

    def get(self, node: str) -> str | None:
        for item in self.items:
            if item.node == node:
                return item.writing_plan
        return None


@dataclass(frozen=True)
class WritingPlanCoverage:
    total_headings: int
    numbered_headings: int
    planned_headings: int

    @property
    def unplanned_headings(self) -> int:
        return self.total_headings - self.planned_headings

    @property
    def unnumbered_headings(self) -> int:
        return self.total_headings - self.numbered_headings


def extract_node_number(heading: str) -> str | None:
    match = _NODE_NUMBER_PATTERN.match(heading)
    if match is None:
        return None
    if (
        match.end() < len(heading)
        and heading[match.end() - 1] == "."
        and heading[match.end()].isdigit()
    ):
        return None
    return match.group(1)


def summarize_writing_plan_coverage(
    titles: Iterable[str],
    snapshot: WritingPlanSnapshot,
) -> WritingPlanCoverage:
    title_list = list(titles)
    nodes = [extract_node_number(title) for title in title_list]
    return WritingPlanCoverage(
        total_headings=len(title_list),
        numbered_headings=sum(node is not None for node in nodes),
        planned_headings=sum(
            bool(plan.strip())
            for node in nodes
            if node is not None and (plan := snapshot.get(node)) is not None
        ),
    )


class WritingPlanStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_snapshot(self) -> WritingPlanSnapshot:
        raw = self._read_bytes()
        if raw is None:
            return WritingPlanSnapshot(items=(), fingerprint=None)

        return self._snapshot_from_raw(raw)

    def save(
        self,
        node: str,
        writing_plan: str,
        *,
        expected_snapshot: WritingPlanSnapshot,
    ) -> WritingPlanSnapshot:
        normalized_node = self._validate_node(node, context="node")
        if not isinstance(writing_plan, str):
            raise WritingPlanValidationError(
                f"撰写计划项 writing_plan 必须为字符串：{self.path}"
            )

        current_raw = self._read_bytes()
        current_fingerprint = (
            hashlib.sha256(current_raw).hexdigest()
            if current_raw is not None
            else None
        )
        if current_fingerprint != expected_snapshot.fingerprint:
            raise WritingPlanExternalModificationError(
                f"撰写计划文件已被外部修改：{self.path}"
            )

        current_snapshot = (
            self._snapshot_from_raw(current_raw)
            if current_raw is not None
            else WritingPlanSnapshot(items=(), fingerprint=None)
        )
        updated_items = list(current_snapshot.items)
        existing_index = next(
            (
                index
                for index, item in enumerate(updated_items)
                if item.node == normalized_node
            ),
            None,
        )

        if not writing_plan.strip():
            if existing_index is None:
                return current_snapshot
            del updated_items[existing_index]
        else:
            updated_item = WritingPlanItem(
                node=normalized_node,
                writing_plan=writing_plan,
            )
            if existing_index is None:
                updated_items.append(updated_item)
            else:
                if updated_items[existing_index] == updated_item:
                    return current_snapshot
                updated_items[existing_index] = updated_item

        payload = {
            "version": 1,
            "items": [asdict(item) for item in updated_items],
        }
        raw = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self._write_atomic(raw)
        return WritingPlanSnapshot(
            items=tuple(updated_items),
            fingerprint=hashlib.sha256(raw).hexdigest(),
        )

    def _read_bytes(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WritingPlanStoreError(
                f"无法读取撰写计划文件：{self.path}"
            ) from exc

    def _snapshot_from_raw(self, raw: bytes) -> WritingPlanSnapshot:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WritingPlanValidationError(
                f"撰写计划文件必须为有效 UTF-8：{self.path}"
            ) from exc

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WritingPlanValidationError(
                f"撰写计划文件必须为有效 JSON：{self.path}"
            ) from exc

        if not isinstance(payload, dict):
            raise WritingPlanValidationError(
                f"撰写计划文件 JSON 根节点必须为对象：{self.path}"
            )
        version = payload.get("version")
        if type(version) is not int or version != 1:
            raise WritingPlanValidationError(
                f"撰写计划文件版本必须为 1：{self.path}"
            )
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise WritingPlanValidationError(
                f"撰写计划文件 items 必须为列表：{self.path}"
            )

        items: list[WritingPlanItem] = []
        seen_nodes: set[str] = set()
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise WritingPlanValidationError(
                    f"撰写计划文件第 {index} 个 item 必须为对象：{self.path}"
                )
            node = self._validate_node(
                raw_item.get("node"), context=f"item {index} node"
            )
            writing_plan = raw_item.get("writing_plan")
            if not isinstance(writing_plan, str):
                raise WritingPlanValidationError(
                    f"撰写计划文件第 {index} 个 item 的 writing_plan 必须为字符串："
                    f"{self.path}"
                )
            if node in seen_nodes:
                raise WritingPlanValidationError(
                    f"撰写计划文件存在重复节点“{node}”：{self.path}"
                )
            seen_nodes.add(node)
            items.append(WritingPlanItem(node=node, writing_plan=writing_plan))

        return WritingPlanSnapshot(
            items=tuple(items),
            fingerprint=hashlib.sha256(raw).hexdigest(),
        )

    def _validate_node(self, node: object, *, context: str) -> str:
        if not isinstance(node, str):
            raise WritingPlanValidationError(
                f"撰写计划文件 {context} 必须为字符串：{self.path}"
            )
        normalized = node.strip()
        if _NODE_PATTERN.fullmatch(normalized) is None:
            raise WritingPlanValidationError(
                f"撰写计划文件 {context} 必须为点分数字节点：{self.path}"
            )
        return normalized

    def _write_atomic(self, raw: bytes) -> None:
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(raw)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, self.path)
            temporary_path = None
            self._fsync_parent_directory()
        except Exception as exc:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink()
            raise WritingPlanStoreError(
                f"无法保存撰写计划文件：{self.path}"
            ) from exc

    def _fsync_parent_directory(self) -> None:
        if os.name == "nt":
            return
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        directory_fd = os.open(self.path.parent, flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
