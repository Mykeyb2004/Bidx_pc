from __future__ import annotations

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
                f"{self.path}: writing_plan must be a string"
            )

        current_raw = self._read_bytes()
        current_fingerprint = (
            hashlib.sha256(current_raw).hexdigest()
            if current_raw is not None
            else None
        )
        if current_fingerprint != expected_snapshot.fingerprint:
            raise WritingPlanExternalModificationError(
                f"{self.path}: file was externally modified"
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
                f"{self.path}: unable to read writing plan store"
            ) from exc

    def _snapshot_from_raw(self, raw: bytes) -> WritingPlanSnapshot:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WritingPlanValidationError(
                f"{self.path}: content must be valid UTF-8"
            ) from exc

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WritingPlanValidationError(
                f"{self.path}: content must be valid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise WritingPlanValidationError(
                f"{self.path}: JSON root must be an object"
            )
        version = payload.get("version")
        if type(version) is not int or version != 1:
            raise WritingPlanValidationError(
                f"{self.path}: version must be the integer 1"
            )
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise WritingPlanValidationError(
                f"{self.path}: items must be a list"
            )

        items: list[WritingPlanItem] = []
        seen_nodes: set[str] = set()
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise WritingPlanValidationError(
                    f"{self.path}: item {index} must be an object"
                )
            node = self._validate_node(
                raw_item.get("node"), context=f"item {index} node"
            )
            writing_plan = raw_item.get("writing_plan")
            if not isinstance(writing_plan, str):
                raise WritingPlanValidationError(
                    f"{self.path}: item {index} writing_plan must be a string"
                )
            if node in seen_nodes:
                raise WritingPlanValidationError(
                    f"{self.path}: duplicate node {node}"
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
                f"{self.path}: {context} must be a string"
            )
        normalized = node.strip()
        if _NODE_PATTERN.fullmatch(normalized) is None:
            raise WritingPlanValidationError(
                f"{self.path}: {context} must match the numeric node pattern"
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
                f"{self.path}: unable to save writing plan store"
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
