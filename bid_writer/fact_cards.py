from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_BULK_FACT_CARD_LINE_RE = re.compile(
    r"^\s*(?P<name>[^|｜:：]+?)\s*[|｜]\s*(?P<scope>[^|｜:：]+?)\s*[|｜]\s*"
    r"(?P<enforcement>[^:：]+?)\s*[:：]\s*(?P<content>.+?)\s*$"
)
_FACT_CARD_META_OPENING_RE = re.compile(
    r"^\s*(?:本章节|本章|本文|上述内容|该章节|当前章节|本节)"
    r"(?:明确|指出|说明|认为|提出|强调|体现|围绕|主要)?"
)

VALID_FACT_CARD_SCOPES = {"global", "local"}
VALID_FACT_CARD_ENFORCEMENTS = {"strong", "reference"}
FACT_CARD_SCOPE_LABELS = {"global": "全局", "local": "局部"}
FACT_CARD_ENFORCEMENT_LABELS = {"strong": "强制", "reference": "参考"}


def normalize_fact_card_scope(scope: str) -> str:
    value = str(scope or "").strip().lower()
    return value if value in VALID_FACT_CARD_SCOPES else ""


def normalize_fact_card_enforcement(enforcement: str) -> str:
    value = str(enforcement or "").strip().lower()
    return value if value in VALID_FACT_CARD_ENFORCEMENTS else ""


def normalize_fact_card_name(name: str) -> str:
    return "".join(character.lower() for character in str(name).strip() if not character.isspace())


def normalize_fact_card_content_for_prompt(content: str) -> str:
    cleaned = _FACT_CARD_META_OPENING_RE.sub("", str(content or ""), count=1)
    return cleaned.lstrip("，,。；;：:、 \t")


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
    scope: str = ""
    enforcement: str = ""
    card_id: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCardDraft" | None:
        data = payload if isinstance(payload, dict) else {}
        name = str(data.get("name", "") or "").strip()
        content = str(data.get("content", data.get("value", "")) or "").strip()
        category = str(data.get("category", "") or "").strip()
        scope = normalize_fact_card_scope(str(data.get("scope", "") or ""))
        enforcement = normalize_fact_card_enforcement(str(data.get("enforcement", "") or ""))
        if not name or not content or not scope or not enforcement:
            return None
        card_id = str(data.get("card_id", data.get("id", "")) or "").strip()
        return cls(
            name=name,
            content=content,
            category=category,
            scope=scope,
            enforcement=enforcement,
            card_id=card_id,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "content": self.content,
            "scope": self.scope,
            "enforcement": self.enforcement,
        }
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
    scope: str = ""
    enforcement: str = ""
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
        scope = normalize_fact_card_scope(str(data.get("scope", "") or ""))
        enforcement = normalize_fact_card_enforcement(str(data.get("enforcement", "") or ""))
        if not card_id or not name or not content or not scope or not enforcement:
            return None
        return cls(
            id=card_id,
            name=name,
            content=content,
            category=str(data.get("category", "") or "").strip(),
            scope=scope,
            enforcement=enforcement,
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
            "scope": self.scope,
            "enforcement": self.enforcement,
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

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FactCardSelection" | None:
        data = payload if isinstance(payload, dict) else {}
        card_id = str(data.get("card_id", data.get("id", "")) or "").strip()
        if not card_id:
            return None
        return cls(card_id=card_id)

    def to_dict(self) -> dict[str, Any]:
        return {"card_id": self.card_id}


@dataclass(frozen=True)
class SelectedFactCard:
    card_id: str
    name: str
    content: str
    scope: str
    enforcement: str
    category: str = ""
    source: FactCardSource = field(default_factory=FactCardSource)

    @classmethod
    def from_fact_card(cls, card: FactCard) -> "SelectedFactCard":
        return cls(
            card_id=card.id,
            name=card.name,
            content=card.content,
            scope=card.scope,
            enforcement=card.enforcement,
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
            "scope": self.scope,
            "enforcement": self.enforcement,
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
            "scope": self.scope,
            "enforcement": self.enforcement,
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
        if card.enforcement != "strong":
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

    strong_cards = [card for card in selected_cards if card.enforcement == "strong"]
    reference_cards = [card for card in selected_cards if card.enforcement != "strong"]

    lines = [
        "## 事实卡片参考",
        "以下事实卡片已进入当前章节扩写上下文；“强制事实”必须保持一致，“参考事实”可按章节需要择优吸收。",
        "使用规则：",
        "- 若事实卡片与采购需求或评分标准冲突，以采购需求和评分标准为准。",
        "- 参考事实只在与当前章节标题、评分关注或需求要点直接相关时吸收，不要为使用卡片而偏题。",
        "- 不要照搬来源章节中的“本章节”“本文”“上述内容”等指代，应改写为适配当前章节的正文表述。",
    ]
    if strong_cards:
        lines.append("### 强制事实")
        lines.extend(_format_fact_card_prompt_line(card) for card in strong_cards)
    if reference_cards:
        lines.append("### 参考事实")
        lines.extend(_format_fact_card_prompt_line(card) for card in reference_cards)
    return "\n".join(lines)


def _format_fact_card_prompt_line(card: SelectedFactCard) -> str:
    scope_label = FACT_CARD_SCOPE_LABELS.get(card.scope, card.scope)
    return f"- [{scope_label}] {card.name}：{normalize_fact_card_content_for_prompt(card.content)}"


def _normalize_bulk_fact_card_scope(scope: str) -> str:
    aliases = {"全局": "global", "局部": "local"}
    value = str(scope or "").strip()
    return normalize_fact_card_scope(aliases.get(value, value))


def _normalize_bulk_fact_card_enforcement(enforcement: str) -> str:
    aliases = {"强制": "strong", "参考": "reference"}
    value = str(enforcement or "").strip()
    return normalize_fact_card_enforcement(aliases.get(value, value))


def parse_bulk_fact_card_line(line: str) -> FactCardDraft | None:
    match = _BULK_FACT_CARD_LINE_RE.match(str(line or ""))
    if not match:
        return None
    name = match.group("name").strip()
    scope = _normalize_bulk_fact_card_scope(match.group("scope"))
    enforcement = _normalize_bulk_fact_card_enforcement(match.group("enforcement"))
    content = match.group("content").strip()
    if not name or not content or not scope or not enforcement:
        return None
    return FactCardDraft(name=name, content=content, scope=scope, enforcement=enforcement)


def parse_bulk_fact_card_input(text: str) -> list[FactCardDraft]:
    drafts: list[FactCardDraft] = []
    for line in str(text or "").splitlines():
        draft = parse_bulk_fact_card_line(line)
        if draft is not None:
            drafts.append(draft)
    return drafts
