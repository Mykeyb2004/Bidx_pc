from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_BULK_FACT_CARD_LINE_RE = re.compile(r"^\s*(?P<name>[^:：]+?)\s*[:：]\s*(?P<content>.+?)\s*$")


def normalize_fact_card_name(name: str) -> str:
    return "".join(character.lower() for character in str(name).strip() if not character.isspace())


@dataclass(frozen=True)
class FactCardSource:
    type: str = "manual"
    chapter_path: str = ""
    extraction_instruction: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCardSource":
        data = payload if isinstance(payload, dict) else {}
        source_type = str(data.get("type", data.get("source_type", "manual")) or "manual").strip() or "manual"
        if source_type == "chapter_output":
            source_type = "chapter_extract"
        return cls(
            type=source_type,
            chapter_path=str(
                data.get("chapter_path", data.get("chapter_full_path", data.get("outline_path", ""))) or ""
            ).strip(),
            extraction_instruction=str(data.get("extraction_instruction", "") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {"type": self.type}
        if self.chapter_path:
            payload["chapter_path"] = self.chapter_path
        if self.extraction_instruction:
            payload["extraction_instruction"] = self.extraction_instruction
        return payload


@dataclass(frozen=True)
class FactCardDraft:
    name: str
    content: str
    category: str = ""
    card_id: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCardDraft" | None:
        data = payload if isinstance(payload, dict) else {}
        name = str(data.get("name", "") or "").strip()
        content = str(data.get("content", data.get("value", "")) or "").strip()
        category = str(data.get("category", "") or "").strip()
        if not name or not content:
            return None
        card_id = str(data.get("card_id", data.get("id", "")) or "").strip()
        return cls(name=name, content=content, category=category, card_id=card_id)

    def to_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "content": self.content}
        if self.category:
            payload["category"] = self.category
        if self.card_id:
            payload["card_id"] = self.card_id
        return payload


@dataclass(frozen=True)
class FactCard:
    id: str
    name: str
    content: str
    category: str = ""
    active: bool = True
    source: FactCardSource = field(default_factory=FactCardSource)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCard" | None:
        data = payload if isinstance(payload, dict) else {}
        card_id = str(data.get("id", "") or "").strip()
        name = str(data.get("name", "") or "").strip()
        content = str(data.get("content", data.get("value", "")) or "").strip()
        if not card_id or not name or not content:
            return None
        return cls(
            id=card_id,
            name=name,
            content=content,
            category=str(data.get("category", "") or "").strip(),
            active=bool(data.get("active", True)),
            source=FactCardSource.from_dict(data.get("source")),
            created_at=str(data.get("created_at", "") or "").strip(),
            updated_at=str(data.get("updated_at", "") or "").strip(),
        )

    @property
    def normalized_name(self) -> str:
        return normalize_fact_card_name(self.name)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "active": self.active,
            "source": self.source.to_dict(),
        }
        if self.category:
            payload["category"] = self.category
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.updated_at:
            payload["updated_at"] = self.updated_at
        return payload


@dataclass(frozen=True)
class FactCardSelection:
    card_id: str
    usage: str = "reference"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCardSelection" | None:
        data = payload if isinstance(payload, dict) else {}
        card_id = str(data.get("card_id", data.get("id", "")) or "").strip()
        usage = str(data.get("usage", "reference") or "reference").strip().lower() or "reference"
        if not card_id:
            return None
        if usage == "required":
            usage = "strong"
        elif usage == "optional":
            usage = "reference"
        if usage not in {"strong", "reference"}:
            usage = "reference"
        return cls(card_id=card_id, usage=usage)

    def to_dict(self) -> dict[str, Any]:
        return {"card_id": self.card_id, "usage": self.usage or "reference"}


@dataclass(frozen=True)
class SelectedFactCard:
    card_id: str
    name: str
    content: str
    usage: str = "reference"
    category: str = ""
    source: FactCardSource = field(default_factory=FactCardSource)

    @classmethod
    def from_fact_card(cls, card: FactCard, usage: str = "reference") -> "SelectedFactCard":
        normalized_usage = FactCardSelection.from_dict({"card_id": card.id, "usage": usage})
        return cls(
            card_id=card.id,
            name=card.name,
            content=card.content,
            usage=normalized_usage.usage if normalized_usage is not None else "reference",
            category=card.category,
            source=card.source,
        )

    @property
    def normalized_name(self) -> str:
        return normalize_fact_card_name(self.name)

    def to_prompt_dict(self) -> dict[str, Any]:
        payload = {
            "card_id": self.card_id,
            "name": self.name,
            "content": self.content,
            "usage": self.usage,
            "source": self.source.to_dict(),
        }
        if self.category:
            payload["category"] = self.category
        return payload

    def to_trace_payload(self) -> dict[str, Any]:
        payload = {
            "card_id": self.card_id,
            "name": self.name,
            "content": self.content,
            "usage": self.usage,
            "source": self.source.to_dict(),
        }
        if self.category:
            payload["category"] = self.category
        return payload


@dataclass(frozen=True)
class FactCardConflict:
    normalized_name: str
    cards: tuple[SelectedFactCard, ...]
    reason: str = "strong_name_conflict"

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_name": self.normalized_name,
            "reason": self.reason,
            "cards": [card.to_trace_payload() for card in self.cards],
        }


class FactCardConflictError(ValueError):
    def __init__(self, conflicts: list[FactCardConflict]):
        self.conflicts = conflicts
        names = "、".join(sorted({conflict.normalized_name for conflict in conflicts}))
        super().__init__(f"检测到事实卡片强冲突：{names}")


def _normalize_fact_card_content(content: str) -> str:
    return re.sub(r"\s+", "", str(content or ""))


def detect_strong_fact_card_conflicts(selected_cards: list[SelectedFactCard]) -> list[FactCardConflict]:
    strong_cards_by_name: dict[str, list[SelectedFactCard]] = {}
    for card in selected_cards:
        if card.usage != "strong":
            continue
        strong_cards_by_name.setdefault(card.normalized_name, []).append(card)

    conflicts: list[FactCardConflict] = []
    for normalized_name, cards in strong_cards_by_name.items():
        if len(cards) < 2:
            continue
        unique_contents = {_normalize_fact_card_content(card.content) for card in cards}
        if len(unique_contents) <= 1:
            continue
        conflicts.append(FactCardConflict(normalized_name=normalized_name, cards=tuple(cards)))
    return conflicts


def build_fact_card_prompt_section(selected_cards: list[SelectedFactCard]) -> str:
    if not selected_cards:
        return ""

    strong_cards = [card for card in selected_cards if card.usage == "strong"]
    reference_cards = [card for card in selected_cards if card.usage != "strong"]

    lines = [
        "## 事实卡片参考",
        "以下为当前章节已选事实卡片；“强约束事实”必须保持一致，“参考事实”可按章节需要择优吸收。",
    ]
    if strong_cards:
        lines.append("### 强约束事实")
        lines.extend(f"- {card.name}：{card.content}" for card in strong_cards)
    if reference_cards:
        lines.append("### 参考事实")
        lines.extend(f"- {card.name}：{card.content}" for card in reference_cards)
    return "\n".join(lines)


def parse_bulk_fact_card_line(line: str) -> FactCardDraft | None:
    match = _BULK_FACT_CARD_LINE_RE.match(str(line or ""))
    if not match:
        return None
    name = match.group("name").strip()
    content = match.group("content").strip()
    if not name or not content:
        return None
    return FactCardDraft(name=name, content=content)


def parse_bulk_fact_card_input(text: str) -> list[FactCardDraft]:
    drafts: list[FactCardDraft] = []
    for line in str(text or "").splitlines():
        draft = parse_bulk_fact_card_line(line)
        if draft is not None:
            drafts.append(draft)
    return drafts
