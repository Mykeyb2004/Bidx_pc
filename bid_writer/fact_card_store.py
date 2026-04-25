from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import Config
from .fact_cards import (
    FactCard,
    FactCardConflictError,
    FactCardDraft,
    FactCardSelection,
    FactCardSource,
    SelectedFactCard,
    detect_strong_fact_card_conflicts,
)


class FactCardStore:
    """基于配置文件顶层 fact_cards 块的事实卡片存储。"""

    def __init__(self, config: Config):
        self.config = config
        self.config_path = Path(config.config_path)

    def list_cards(self, active_only: bool = True) -> list[FactCard]:
        cards = self._load_cards()
        return [card for card in cards if card.active] if active_only else cards

    def list_chapter_defaults(self, chapter_path: str) -> list[FactCardSelection]:
        payload = self._load_config_payload()
        block = self._normalize_fact_cards_block(payload)
        chapter_defaults = block.setdefault("chapter_defaults", {})
        selections = self._coerce_selection_list(chapter_defaults.get(chapter_path))
        filtered = self._filter_existing_selections(selections, self._cards_from_block(block))
        if filtered != selections:
            if filtered:
                chapter_defaults[chapter_path] = [selection.to_dict() for selection in filtered]
            else:
                chapter_defaults.pop(chapter_path, None)
            payload["fact_cards"] = block
            self._save_config_payload(payload)
        return filtered

    def resolve_selected_cards(
        self,
        selections: Iterable[FactCardSelection | dict[str, Any]],
    ) -> list[SelectedFactCard]:
        normalized_selections = self._coerce_selection_iterable(selections)
        cards_by_id = {card.id: card for card in self.list_cards()}
        resolved: list[SelectedFactCard] = []
        seen: set[str] = set()
        for selection in normalized_selections:
            if not selection.card_id or selection.card_id in seen:
                continue
            card = cards_by_id.get(selection.card_id)
            if card is None:
                continue
            seen.add(selection.card_id)
            resolved.append(SelectedFactCard.from_fact_card(card, usage=selection.usage))

        conflicts = detect_strong_fact_card_conflicts(resolved)
        if conflicts:
            raise FactCardConflictError(conflicts)
        return resolved

    def resolve_chapter_prompt_cards(
        self,
        chapter_path: str,
        selections: Iterable[FactCardSelection | dict[str, Any]] | None = None,
    ) -> list[SelectedFactCard]:
        if selections is None:
            normalized_selections = self.list_chapter_defaults(chapter_path)
        else:
            normalized_selections = self._coerce_selection_iterable(selections)
        return self.resolve_selected_cards(normalized_selections)

    def save_chapter_defaults(
        self,
        chapter_path: str,
        selections: Iterable[FactCardSelection | dict[str, Any]],
    ) -> list[FactCardSelection]:
        payload = self._load_config_payload()
        block = self._normalize_fact_cards_block(payload)
        cleaned = self._filter_existing_selections(self._coerce_selection_iterable(selections), self._cards_from_block(block))
        chapter_defaults = block.setdefault("chapter_defaults", {})
        if cleaned:
            chapter_defaults[chapter_path] = [selection.to_dict() for selection in cleaned]
        else:
            chapter_defaults.pop(chapter_path, None)
        payload["fact_cards"] = block
        self._save_config_payload(payload)
        return cleaned

    def save_manual_cards(
        self,
        drafts: Iterable[FactCardDraft | dict[str, Any]],
    ) -> list[FactCard]:
        payload = self._load_config_payload()
        block = self._normalize_fact_cards_block(payload)
        existing_cards = self._cards_from_block(block)
        manual_cards = [card for card in existing_cards if card.source.type == "manual"]
        manual_cards_by_id = {card.id: card for card in manual_cards}
        manual_cards_by_name: dict[str, list[FactCard]] = {}
        for card in manual_cards:
            manual_cards_by_name.setdefault(card.normalized_name, []).append(card)

        now = self._now_iso()
        replacements: list[FactCard] = []
        reused_ids: set[str] = set()
        next_generated_id = 1

        for position, item in enumerate(drafts, start=1):
            draft = self._coerce_draft(item)
            if draft is None:
                continue

            matched = manual_cards_by_id.get(draft.card_id) if draft.card_id not in reused_ids else None
            if matched is None:
                matched_cards = manual_cards_by_name.get(self._normalized_name(draft.name), [])
                matched = next((card for card in matched_cards if card.id not in reused_ids), None)
            if matched is not None:
                replacements.append(
                    FactCard(
                        id=matched.id,
                        name=draft.name,
                        content=draft.content,
                        category=draft.category,
                        active=True,
                        source=FactCardSource(type="manual"),
                        created_at=matched.created_at,
                        updated_at=now,
                    )
                )
                reused_ids.add(matched.id)
                continue

            next_generated_id = max(next_generated_id, position)
            while self._id_exists(f"fact-card-{next_generated_id}", existing_cards, replacements):
                next_generated_id += 1
            replacements.append(
                FactCard(
                    id=f"fact-card-{next_generated_id}",
                    name=draft.name,
                    content=draft.content,
                    category=draft.category,
                    active=True,
                    source=FactCardSource(type="manual"),
                    created_at=now,
                    updated_at=now,
                )
            )
            next_generated_id += 1

        updated_cards = [card for card in existing_cards if card.source.type != "manual"]
        updated_cards.extend(replacements)
        block["cards"] = [card.to_dict() for card in updated_cards]
        self._clean_all_chapter_defaults(block)
        payload["fact_cards"] = block
        self._save_config_payload(payload)
        return replacements

    def replace_extracted_cards(
        self,
        chapter_path: str,
        extraction_instruction: str,
        drafts: Iterable[FactCardDraft | dict[str, Any]],
    ) -> list[FactCard]:
        payload = self._load_config_payload()
        block = self._normalize_fact_cards_block(payload)
        existing_cards = self._cards_from_block(block)
        extracted_cards = [
            card
            for card in existing_cards
            if card.source.type == "chapter_extract" and self._same_path(card.source.chapter_path, chapter_path)
        ]
        extracted_cards_by_name: dict[str, list[FactCard]] = {}
        for card in extracted_cards:
            extracted_cards_by_name.setdefault(card.normalized_name, []).append(card)
        now = self._now_iso()

        replacements: list[FactCard] = []
        reused_ids: set[str] = set()
        next_generated_id = 1
        for position, item in enumerate(drafts, start=1):
            draft = self._coerce_draft(item)
            if draft is None:
                continue
            matched_cards = extracted_cards_by_name.get(self._normalized_name(draft.name), [])
            matched = matched_cards.pop(0) if matched_cards else None
            source = FactCardSource(
                type="chapter_extract",
                chapter_path=chapter_path,
                extraction_instruction=extraction_instruction.strip(),
            )
            if matched is not None:
                replacements.append(
                    FactCard(
                        id=matched.id,
                        name=draft.name,
                        content=draft.content,
                        category=draft.category,
                        active=True,
                        source=source,
                        created_at=matched.created_at,
                        updated_at=now,
                    )
                )
                reused_ids.add(matched.id)
                continue

            next_generated_id = max(next_generated_id, position)
            while self._id_exists(f"fact-card-{next_generated_id}", existing_cards, replacements):
                next_generated_id += 1
            replacements.append(
                FactCard(
                    id=f"fact-card-{next_generated_id}",
                    name=draft.name,
                    content=draft.content,
                    category=draft.category,
                    active=True,
                    source=source,
                    created_at=now,
                    updated_at=now,
                )
            )
            next_generated_id += 1

        updated_cards: list[FactCard] = []
        replacement_by_id = {card.id: card for card in replacements}
        for card in existing_cards:
            is_target = card.source.type == "chapter_extract" and self._same_path(card.source.chapter_path, chapter_path)
            if is_target:
                replacement = replacement_by_id.get(card.id)
                if replacement is not None:
                    updated_cards.append(replacement)
                continue
            updated_cards.append(card)
        updated_cards.extend([card for card in replacements if card.id not in reused_ids])

        block["cards"] = [card.to_dict() for card in updated_cards]
        self._clean_all_chapter_defaults(block)
        payload["fact_cards"] = block
        self._save_config_payload(payload)
        return replacements

    @staticmethod
    def _normalized_name(name: str) -> str:
        return "".join(character.lower() for character in str(name).strip() if not character.isspace())

    @staticmethod
    def _id_exists(card_id: str, existing_cards: list[FactCard], replacement_cards: list[FactCard]) -> bool:
        return any(card.id == card_id for card in [*existing_cards, *replacement_cards])

    @staticmethod
    def _coerce_draft(item: FactCardDraft | dict[str, Any]) -> FactCardDraft | None:
        if isinstance(item, FactCardDraft):
            return item
        return FactCardDraft.from_dict(item if isinstance(item, dict) else None)

    def _load_cards(self) -> list[FactCard]:
        payload = self._load_config_payload()
        block = self._normalize_fact_cards_block(payload)
        return self._cards_from_block(block)

    @staticmethod
    def _cards_from_block(block: dict[str, Any]) -> list[FactCard]:
        raw_cards = block.get("cards", [])
        if not isinstance(raw_cards, list):
            return []
        cards: list[FactCard] = []
        for item in raw_cards:
            card = FactCard.from_dict(item)
            if card is not None:
                cards.append(card)
        return cards

    def _clean_all_chapter_defaults(self, block: dict[str, Any]) -> None:
        chapter_defaults = block.setdefault("chapter_defaults", {})
        cards = self._cards_from_block(block)
        for chapter_path in list(chapter_defaults):
            selections = self._coerce_selection_list(chapter_defaults.get(chapter_path))
            filtered = self._filter_existing_selections(selections, cards)
            if filtered:
                chapter_defaults[chapter_path] = [selection.to_dict() for selection in filtered]
            else:
                chapter_defaults.pop(chapter_path, None)

    @staticmethod
    def _coerce_selection_iterable(
        selections: Iterable[FactCardSelection | dict[str, Any]],
    ) -> list[FactCardSelection]:
        normalized: list[FactCardSelection] = []
        for item in selections:
            if isinstance(item, FactCardSelection):
                normalized.append(item)
                continue
            selection = FactCardSelection.from_dict(item if isinstance(item, dict) else None)
            if selection is not None:
                normalized.append(selection)
        return normalized

    @classmethod
    def _coerce_selection_list(cls, payload: Any) -> list[FactCardSelection]:
        if isinstance(payload, list):
            return cls._coerce_selection_iterable(payload)
        if isinstance(payload, dict):
            raw_ids = payload.get("card_ids")
            if isinstance(raw_ids, list):
                return [
                    FactCardSelection(card_id=str(card_id).strip(), usage="reference")
                    for card_id in raw_ids
                    if str(card_id).strip()
                ]
        return []

    @staticmethod
    def _filter_existing_selections(
        selections: list[FactCardSelection],
        cards: list[FactCard],
    ) -> list[FactCardSelection]:
        existing_ids = {card.id for card in cards}
        filtered: list[FactCardSelection] = []
        seen: set[str] = set()
        for selection in selections:
            if not selection.card_id or selection.card_id in seen or selection.card_id not in existing_ids:
                continue
            seen.add(selection.card_id)
            filtered.append(selection)
        return filtered

    @staticmethod
    def _normalize_fact_cards_block(payload: dict[str, Any]) -> dict[str, Any]:
        raw_block = payload.get("fact_cards", {})
        block = dict(raw_block) if isinstance(raw_block, dict) else {}
        cards = block.get("cards", [])
        chapter_defaults = block.get("chapter_defaults", {})
        block["enabled"] = bool(block.get("enabled", False))
        block["cards"] = cards if isinstance(cards, list) else []
        block["chapter_defaults"] = chapter_defaults if isinstance(chapter_defaults, dict) else {}
        return block

    def _load_config_payload(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}
        return payload if isinstance(payload, dict) else {}

    def _save_config_payload(self, payload: dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(payload, file, allow_unicode=True, sort_keys=False)
        self.config.reload()

    @staticmethod
    def _same_path(left: str, right: str) -> bool:
        normalized_left = str(left or "").strip()
        normalized_right = str(right or "").strip()
        if not normalized_left or not normalized_right:
            return False
        return normalized_left == normalized_right

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
