# Fact Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build project-level fact cards stored in the main YAML config, with manual chapter extraction/editing, manual selection before chapter generation, per-chapter saved defaults, and prompt injection limited to selected cards.

**Architecture:** Add a small fact-card domain (`bid_writer/fact_cards.py`) and a YAML-backed persistence layer (`bid_writer/fact_card_store.py`) instead of extending the legacy `.bid_writer/chapter_facts.json` cache. Keep extraction, selection, conflict detection, and prompt rendering as explicit services wired through `BidWriter`, then layer GUI dialogs on top while leaving `ConfigEditorDialog` in passthrough mode.

**Tech Stack:** Python, Tkinter/ttk, PyYAML, pytest, OpenAI SDK, existing `BidWriter` / `AIWriter` services

---

## File Structure

**Create**

- `bid_writer/fact_cards.py` — fact-card dataclasses plus pure helpers for normalization, bulk text parsing, conflict detection, filtering, and prompt rendering
- `bid_writer/fact_card_store.py` — YAML-backed persistence for `fact_cards.cards` and `fact_cards.chapter_defaults`
- `bid_writer/fact_card_extractor.py` — LLM-backed draft extractor that reads saved chapter output and returns editable fact-card drafts
- `bid_writer/fact_card_dialogs.py` — reusable Tk dialogs for card library management and chapter draft review
- `tests/test_fact_cards.py` — unit tests for store roundtrip, default selection persistence, bulk parsing, filtering, and conflict detection
- `tests/test_fact_card_extractor.py` — unit tests for extractor prompt construction and JSON parsing
- `tests/test_fact_card_prompt.py` — unit tests for prompt assembly and trace payload under fact-card mode
- `tests/fixtures/fact_card_prompt_config.yaml` — prompt/trace fixture with `fact_cards.enabled: true`

**Modify**

- `bid_writer/config.py` — expose `fact_cards` config accessors without changing unrelated schema behavior
- `bid_writer/main.py` — instantiate fact-card services and provide GUI-facing save/list/resolve methods
- `bid_writer/ai_writer.py` — accept explicit selected fact cards, render the `## 事实卡片参考` block, and skip legacy `knowledge_context` in fact-card mode
- `bid_writer/generation_trace.py` — persist fact-card mode and selection details into trace context payloads
- `bid_writer/gui.py` — add menu entries, card-library dialogs, chapter extraction dialogs, single-chapter selection UI, and batch-mode default handling
- `tests/test_prompt_contract.py` — add prompt-contract assertions for the new fact-card block
- `tests/test_config_editor.py` — add passthrough regression coverage for unknown top-level `fact_cards`
- `config.example.yaml` — document the new top-level `fact_cards` block
- `docs/config_schema.md` — describe `fact_cards.cards` / `fact_cards.chapter_defaults`
- `docs/prompt_contract.md` — document the new fact-card prompt block and trace contract
- `docs/chapter_expansion_mechanism.md` — document the new single-chapter selection path and batch-generation default-only behavior

## Task 1: Add Fact-Card Domain Model and YAML Store

**Files:**
- Create: `bid_writer/fact_cards.py`
- Create: `bid_writer/fact_card_store.py`
- Modify: `bid_writer/config.py`
- Modify: `bid_writer/main.py`
- Test: `tests/test_fact_cards.py`
- Test: `tests/test_config_editor.py`

- [ ] **Step 1: Write the failing store and passthrough regression tests**

```python
from pathlib import Path

import yaml

from bid_writer.config import Config
from bid_writer.config_editor import load_config_editor_document
from bid_writer.fact_card_store import FactCardStore
from bid_writer.fact_cards import FactCardDraft, FactCardSelection


def _write_config(base_dir: Path) -> Path:
    (base_dir / "outline.md").write_text("# 项目\n## 方案\n### 质量保障措施\n", encoding="utf-8")
    (base_dir / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (base_dir / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")
    config_path = base_dir / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"

fact_cards:
  enabled: true
  cards: []
  chapter_defaults: {}
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_fact_card_store_replace_extracted_cards_reuses_matching_ids_and_cleans_defaults(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    store = FactCardStore(config)

    first = store.replace_extracted_cards(
        chapter_path="项目 > 实施周期",
        extraction_instruction="提炼周期",
        drafts=[
            FactCardDraft(name="实施周期", content="总周期为 90 日历天。", category="进度"),
        ],
    )
    store.save_chapter_defaults(
        "项目 > 质量保障措施",
        [FactCardSelection(card_id=first[0].id, usage="strong")],
    )

    second = store.replace_extracted_cards(
        chapter_path="项目 > 实施周期",
        extraction_instruction="提炼周期",
        drafts=[
            FactCardDraft(name="实施周期", content="总周期为 120 日历天。", category="进度"),
            FactCardDraft(name="阶段划分", content="分为准备、实施、验收三个阶段。", category="进度"),
        ],
    )

    payload = yaml.safe_load(Path(config.config_path).read_text(encoding="utf-8"))
    assert len(second) == 2
    assert second[0].id == first[0].id
    assert payload["fact_cards"]["chapter_defaults"].get("项目 > 质量保障措施", []) == []


def test_config_editor_preserves_top_level_fact_cards_block(tmp_path: Path):
    config_path = _write_config(tmp_path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["fact_cards"]["cards"] = [
        {
            "id": "fact_001",
            "name": "项目经理",
            "content": "项目经理由张三担任。",
            "category": "人员团队",
            "active": True,
            "source": {"type": "manual", "chapter_path": "", "extraction_instruction": ""},
            "created_at": "2026-04-24T10:00:00+08:00",
            "updated_at": "2026-04-24T10:00:00+08:00",
        }
    ]
    config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    document = load_config_editor_document(config_path)
    rendered = yaml.safe_load(document.render_yaml())

    assert rendered["fact_cards"]["cards"][0]["name"] == "项目经理"
```

- [ ] **Step 2: Run the targeted tests to confirm they fail before implementation**

Run: `uv run pytest tests/test_fact_cards.py tests/test_config_editor.py::test_config_editor_preserves_top_level_fact_cards_block -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'bid_writer.fact_card_store'` and missing `fact_cards` accessors.

- [ ] **Step 3: Implement the dataclasses, store, config hooks, and `BidWriter` service wiring**

```python
# bid_writer/fact_cards.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactCardSource:
    type: str
    chapter_path: str = ""
    extraction_instruction: str = ""


@dataclass(frozen=True)
class FactCard:
    id: str
    name: str
    content: str
    category: str
    active: bool
    source: FactCardSource
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FactCardDraft:
    name: str
    content: str
    category: str


@dataclass(frozen=True)
class FactCardSelection:
    card_id: str
    usage: str
```

```python
# bid_writer/fact_card_store.py
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import json

import yaml

from .chapter_dependency_store import _now_string
from .config import Config
from .fact_cards import FactCard, FactCardDraft, FactCardSelection, FactCardSource


class FactCardStore:
    def __init__(self, config: Config):
        self.config = config
        self.path = Path(config.config_path)

    def list_cards(self, *, active_only: bool = True) -> list[FactCard]:
        payload = self._load_fact_cards_payload()
        cards = [self._card_from_payload(item) for item in payload.get("cards", []) if isinstance(item, dict)]
        if active_only:
            cards = [card for card in cards if card.active]
        return cards

    def list_chapter_defaults(self, chapter_path: str) -> list[FactCardSelection]:
        payload = self._load_fact_cards_payload()
        raw_items = payload.get("chapter_defaults", {}).get(chapter_path, [])
        return [
            FactCardSelection(card_id=str(item.get("card_id", "")).strip(), usage=str(item.get("usage", "reference")).strip())
            for item in raw_items
            if isinstance(item, dict) and str(item.get("card_id", "")).strip()
        ]

    def save_chapter_defaults(self, chapter_path: str, selections: list[FactCardSelection]) -> None:
        config_payload = self._load_config_payload()
        fact_cards = config_payload.setdefault("fact_cards", {"enabled": True, "cards": [], "chapter_defaults": {}})
        defaults = fact_cards.setdefault("chapter_defaults", {})
        normalized = [
            {"card_id": item.card_id, "usage": item.usage}
            for item in selections
            if item.card_id.strip()
        ]
        if normalized:
            defaults[chapter_path] = normalized
        else:
            defaults.pop(chapter_path, None)
        self._write_config_payload(config_payload)

    def replace_extracted_cards(
        self,
        *,
        chapter_path: str,
        extraction_instruction: str,
        drafts: list[FactCardDraft],
    ) -> list[FactCard]:
        config_payload = self._load_config_payload()
        fact_cards = config_payload.setdefault("fact_cards", {"enabled": True, "cards": [], "chapter_defaults": {}})
        existing_cards = [self._card_from_payload(item) for item in fact_cards.get("cards", []) if isinstance(item, dict)]
        existing_extract_cards = [
            card
            for card in existing_cards
            if card.source.type == "chapter_extract" and card.source.chapter_path == chapter_path
        ]
        keep_cards = [
            card
            for card in existing_cards
            if not (card.source.type == "chapter_extract" and card.source.chapter_path == chapter_path)
        ]
        reused_by_name = {self._normalize(card.name): card for card in existing_extract_cards}
        now = _now_string()
        replaced_cards: list[FactCard] = []
        for draft in drafts:
            existing = reused_by_name.get(self._normalize(draft.name))
            card_id = existing.id if existing is not None else self._new_id(draft.name, draft.content, now)
            created_at = existing.created_at if existing is not None else now
            replaced_cards.append(
                FactCard(
                    id=card_id,
                    name=draft.name.strip(),
                    content=draft.content.strip(),
                    category=draft.category.strip() or "未分类",
                    active=True,
                    source=FactCardSource(
                        type="chapter_extract",
                        chapter_path=chapter_path,
                        extraction_instruction=extraction_instruction.strip(),
                    ),
                    created_at=created_at,
                    updated_at=now,
                )
            )
        fact_cards["cards"] = [self._card_to_payload(card) for card in [*keep_cards, *replaced_cards]]
        self._remove_missing_default_refs(fact_cards, {card.id for card in [*keep_cards, *replaced_cards]})
        self._write_config_payload(config_payload)
        return replaced_cards
```

```python
# bid_writer/config.py
@property
def fact_cards_enabled(self) -> bool:
    return self._get_bool(("fact_cards", "enabled"), default=False)
```

```python
# bid_writer/main.py
from .fact_card_store import FactCardStore

def _rebuild_services(self) -> None:
    self.ai_writer = AIWriter(self.config)
    self.file_saver = FileSaver(
        self.config.output_directory,
        self.config.output_prefix,
        max_filename_length=self.config.output_filename_max_length,
        empty_filename_fallback=self.config.output_empty_filename_fallback,
        include_title_header=self.config.output_include_title_header,
        overwrite_existing=self.config.output_overwrite_existing,
    )
    self.fact_card_store = FactCardStore(self.config)

def list_fact_cards(self):
    return self.fact_card_store.list_cards()

def save_chapter_default_fact_cards(self, chapter_path: str, selections):
    self.fact_card_store.save_chapter_defaults(chapter_path, selections)
    self.reload_config()
```

```python
# bid_writer/fact_card_store.py
def _load_config_payload(self) -> dict:
    payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _load_fact_cards_payload(self) -> dict:
    return self._load_config_payload().get("fact_cards", {}) or {}


def _write_config_payload(self, payload: dict) -> None:
    self.path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _card_from_payload(self, item: dict) -> FactCard:
    source_payload = item.get("source", {}) if isinstance(item.get("source"), dict) else {}
    return FactCard(
        id=str(item.get("id", "")).strip(),
        name=str(item.get("name", "")).strip(),
        content=str(item.get("content", "")).strip(),
        category=str(item.get("category", "")).strip() or "未分类",
        active=bool(item.get("active", True)),
        source=FactCardSource(
            type=str(source_payload.get("type", "manual")).strip() or "manual",
            chapter_path=str(source_payload.get("chapter_path", "")).strip(),
            extraction_instruction=str(source_payload.get("extraction_instruction", "")).strip(),
        ),
        created_at=str(item.get("created_at", "")).strip(),
        updated_at=str(item.get("updated_at", "")).strip(),
    )


def _card_to_payload(self, card: FactCard) -> dict:
    return {
        "id": card.id,
        "name": card.name,
        "content": card.content,
        "category": card.category,
        "active": card.active,
        "source": {
            "type": card.source.type,
            "chapter_path": card.source.chapter_path,
            "extraction_instruction": card.source.extraction_instruction,
        },
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }


def _normalize(self, text: str) -> str:
    return "".join(text.split()).lower()


def _new_id(self, name: str, content: str, now: str) -> str:
    seed = f"{name.strip()}|{content.strip()}|{now}"
    return "fact_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def _remove_missing_default_refs(self, fact_cards: dict, valid_ids: set[str]) -> None:
    defaults = fact_cards.setdefault("chapter_defaults", {})
    for chapter_path, items in list(defaults.items()):
        kept = [item for item in items if item.get("card_id") in valid_ids]
        if kept:
            defaults[chapter_path] = kept
        else:
            defaults.pop(chapter_path, None)
```

- [ ] **Step 4: Run the targeted tests again to verify the new store behavior**

Run: `uv run pytest tests/test_fact_cards.py tests/test_config_editor.py::test_config_editor_preserves_top_level_fact_cards_block -q`

Expected: PASS

- [ ] **Step 5: Commit the store foundation**

```bash
git add tests/test_fact_cards.py tests/test_config_editor.py bid_writer/fact_cards.py bid_writer/fact_card_store.py bid_writer/config.py bid_writer/main.py
git commit -m "feat: add fact card domain and yaml store"
```

## Task 2: Add Draft Extraction and Bulk Manual Parsing

**Files:**
- Create: `bid_writer/fact_card_extractor.py`
- Modify: `bid_writer/fact_cards.py`
- Modify: `bid_writer/main.py`
- Test: `tests/test_fact_card_extractor.py`
- Test: `tests/test_fact_cards.py`

- [ ] **Step 1: Write the failing extractor and bulk-input tests**

```python
from pathlib import Path

from bid_writer.config import Config
from bid_writer.fact_card_extractor import FactCardExtractor
from bid_writer.fact_cards import parse_bulk_fact_card_input
from bid_writer.file_saver import FileSaver
from bid_writer.outline_parser import parse_outline


def test_parse_bulk_fact_card_input_splits_name_and_content():
    drafts = parse_bulk_fact_card_input(
        "项目经理：项目经理由张三担任。\n\n实施周期：总周期为 90 日历天。"
    )
    assert [item.name for item in drafts] == ["项目经理", "实施周期"]
    assert drafts[1].content == "总周期为 90 日历天。"


def test_fact_card_extractor_builds_instructional_prompt_and_parses_json(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "outline.md").write_text("# 项目\n## 方案\n### 服务承诺\n", encoding="utf-8")
    (tmp_path / "bid_requirements.md").write_text("采购需求", encoding="utf-8")
    (tmp_path / "scoring_criteria.md").write_text("评分标准", encoding="utf-8")

    class DummyClient:
        class _Chat:
            class _Completions:
                def create(self, **kwargs):
                    self.last_kwargs = kwargs
                    return type(
                        "Resp",
                        (),
                        {
                            "choices": [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Msg",
                                            (),
                                            {
                                                "content": '[{"name":"响应时效","content":"提供 7×24 小时响应支持。","category":"服务承诺"}]'
                                            },
                                        )()
                                    },
                                )()
                            ]
                        },
                    )()
            completions = _Completions()
        chat = _Chat()

    monkeypatch.setattr("bid_writer.fact_card_extractor.OpenAI", lambda **_: DummyClient())
    config = Config(str(config_path))
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title("服务承诺")
    file_saver = FileSaver(str(tmp_path / "output"), "")
    extractor = FactCardExtractor(config, file_saver)

    prompt = extractor.build_prompt(heading, "正文内容", "突出服务承诺")
    drafts = extractor.parse_response(
        '[{"name":"响应时效","content":"提供 7×24 小时响应支持。","category":"服务承诺"}]',
        max_cards=5,
    )

    assert "提炼要求：突出服务承诺" in prompt
    assert drafts[0].name == "响应时效"
```

- [ ] **Step 2: Run the extraction tests to confirm they fail first**

Run: `uv run pytest tests/test_fact_card_extractor.py tests/test_fact_cards.py::test_parse_bulk_fact_card_input_splits_name_and_content -q`

Expected: FAIL with missing `FactCardExtractor` and missing `parse_bulk_fact_card_input`.

- [ ] **Step 3: Implement the extractor prompt, JSON parser, and `BidWriter` wrapper**

```python
# bid_writer/fact_cards.py
def parse_bulk_fact_card_input(text: str) -> list[FactCardDraft]:
    drafts: list[FactCardDraft] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "：" not in line:
            continue
        name, content = line.split("：", 1)
        if name.strip() and content.strip():
            drafts.append(FactCardDraft(name=name.strip(), content=content.strip(), category="未分类"))
    return drafts
```

```python
# bid_writer/fact_card_extractor.py
from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI

from .config import Config
from .fact_cards import FactCardDraft
from .file_saver import FileSaver
from .outline_parser import HeadingNode


class FactCardExtractor:
    def __init__(self, config: Config, file_saver: FileSaver):
        self.config = config
        self.file_saver = file_saver

    def build_prompt(self, heading: HeadingNode, body: str, instruction: str) -> str:
        return "\n\n".join(
            [
                "请从以下标书章节正文中提炼可复用的事实卡片。",
                "输出要求：只输出 JSON 数组，每个元素包含 name、content、category 三个字段。",
                f"提炼要求：{instruction.strip() or '提炼跨章节可复用的事实。'}",
                f"章节标题：{heading.title}",
                f"章节路径：{heading.full_path}",
                "章节正文：",
                body,
            ]
        )

    def parse_response(self, content: str, *, max_cards: int) -> list[FactCardDraft]:
        payload = json.loads(content.strip() or "[]")
        drafts: list[FactCardDraft] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            body = str(item.get("content", "")).strip()
            category = str(item.get("category", "")).strip() or "未分类"
            if not name or not body:
                continue
            drafts.append(FactCardDraft(name=name, content=body, category=category))
            if len(drafts) >= max_cards:
                break
        return drafts

    def extract_output_drafts(self, heading: HeadingNode, instruction: str) -> Optional[list[FactCardDraft]]:
        filepath = self.file_saver.find_existing_filepath(heading)
        if filepath is None or not filepath.exists():
            return None
        body = self.file_saver.load_section_body(filepath, heading.title).strip()
        if not body:
            return None
        client = OpenAI(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            temperature=0,
            max_tokens=max(600, self.config.chapter_facts_max_facts_per_chapter * 120),
            messages=[
                {"role": "system", "content": "你是标书事实卡片提炼助手，只输出 JSON 数组，不输出解释。"},
                {"role": "user", "content": self.build_prompt(heading, body, instruction)},
            ],
        )
        return self.parse_response(
            (response.choices[0].message.content or "").strip(),
            max_cards=self.config.chapter_facts_max_facts_per_chapter,
        )
```

```python
# bid_writer/main.py
from .fact_card_extractor import FactCardExtractor

def _rebuild_services(self) -> None:
    self.fact_card_extractor = FactCardExtractor(self.config, self.file_saver)

def extract_fact_card_drafts_from_output(self, heading: HeadingNode, instruction: str):
    return self.fact_card_extractor.extract_output_drafts(heading, instruction)
```

- [ ] **Step 4: Run the extraction tests again**

Run: `uv run pytest tests/test_fact_card_extractor.py tests/test_fact_cards.py::test_parse_bulk_fact_card_input_splits_name_and_content -q`

Expected: PASS

- [ ] **Step 5: Commit the extraction layer**

```bash
git add tests/test_fact_card_extractor.py tests/test_fact_cards.py bid_writer/fact_cards.py bid_writer/fact_card_extractor.py bid_writer/main.py
git commit -m "feat: add fact card draft extraction"
```

## Task 3: Render Fact Cards into Prompt and Trace

**Files:**
- Modify: `bid_writer/fact_cards.py`
- Modify: `bid_writer/ai_writer.py`
- Modify: `bid_writer/generation_trace.py`
- Test: `tests/test_fact_card_prompt.py`
- Modify: `tests/test_prompt_contract.py`
- Create: `tests/fixtures/fact_card_prompt_config.yaml`

- [ ] **Step 1: Write the failing prompt and trace tests**

```python
import json
from pathlib import Path

import bid_writer.ai_writer as ai_writer_module
from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.fact_cards import FactCard, FactCardSource, SelectedFactCard, detect_strong_fact_card_conflicts
from bid_writer.outline_parser import parse_outline


class DummyOpenAI:
    def __init__(self, *args, **kwargs):
        del args, kwargs


def _build_writer(monkeypatch, config: Config) -> AIWriter:
    monkeypatch.setattr(ai_writer_module, "OpenAI", DummyOpenAI)
    return AIWriter(config)


def _selected_cards() -> list[SelectedFactCard]:
    source = FactCardSource(type="manual")
    return [
        SelectedFactCard(
            card=FactCard(
                id="fact_001",
                name="项目经理",
                content="项目经理由张三担任。",
                category="人员团队",
                active=True,
                source=source,
                created_at="2026-04-24T10:00:00+08:00",
                updated_at="2026-04-24T10:00:00+08:00",
            ),
            usage="strong",
        ),
        SelectedFactCard(
            card=FactCard(
                id="fact_002",
                name="响应时效",
                content="提供 7×24 小时响应支持。",
                category="服务承诺",
                active=True,
                source=source,
                created_at="2026-04-24T10:00:00+08:00",
                updated_at="2026-04-24T10:00:00+08:00",
            ),
            usage="reference",
        ),
    ]


def test_detect_strong_fact_card_conflicts():
    source = FactCardSource(type="manual")
    conflicts = detect_strong_fact_card_conflicts(
        [
            SelectedFactCard(
                card=FactCard("a", "实施周期", "总周期为 90 日历天。", "进度", True, source, "x", "x"),
                usage="strong",
            ),
            SelectedFactCard(
                card=FactCard("b", "实施周期", "总周期为 120 日历天。", "进度", True, source, "x", "x"),
                usage="strong",
            ),
        ]
    )
    assert conflicts[0].name == "实施周期"


def test_build_prompt_result_includes_fact_card_section_and_skips_knowledge_context(monkeypatch, tmp_path):
    config = Config(str((Path("tests/fixtures") / "fact_card_prompt_config.yaml").resolve()))
    writer = _build_writer(monkeypatch, config)
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title("质量保障措施")

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=_selected_cards(),
    )

    assert "## 事实卡片参考" in result.prompt
    assert "## 投标方知识库" not in result.prompt
    assert any(block["id"] == "fact_card_context" for block in result.prompt_contract_blocks)


def test_trace_payload_records_fact_card_selection(monkeypatch, tmp_path):
    config = Config(str((Path("tests/fixtures") / "fact_card_prompt_config.yaml").resolve()))
    writer = _build_writer(monkeypatch, config)
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title("质量保障措施")

    prepared = writer.prepare_generation(
        heading,
        target_words=1200,
        stream=False,
        fact_card_mode=True,
        selected_fact_cards=_selected_cards(),
    )

    payload = json.loads(
        prepared.trace_session.artifact_paths["context_assembly"].read_text(encoding="utf-8")
    )
    assert payload["fact_card_mode"] is True
    assert payload["fact_card_selection"][0]["card_id"] == "fact_001"
```

- [ ] **Step 2: Run the prompt and trace tests before changing `AIWriter`**

Run: `uv run pytest tests/test_fact_card_prompt.py tests/test_prompt_contract.py -q`

Expected: FAIL with unexpected keyword argument `fact_card_mode` and missing `fact_card_context` block.

- [ ] **Step 3: Implement conflict detection, prompt rendering, and trace recording**

```python
# bid_writer/fact_cards.py
def normalize_fact_card_name(text: str) -> str:
    return "".join(text.split()).lower()


def normalize_fact_card_text(text: str) -> str:
    return " ".join(text.split()).lower()


@dataclass(frozen=True)
class SelectedFactCard:
    card: FactCard
    usage: str


@dataclass(frozen=True)
class FactCardConflict:
    name: str
    left: SelectedFactCard
    right: SelectedFactCard


def detect_strong_fact_card_conflicts(selected_cards: list[SelectedFactCard]) -> list[FactCardConflict]:
    strong_cards = [item for item in selected_cards if item.usage == "strong"]
    conflicts: list[FactCardConflict] = []
    for index, left in enumerate(strong_cards):
        for right in strong_cards[index + 1:]:
            if normalize_fact_card_name(left.card.name) != normalize_fact_card_name(right.card.name):
                continue
            if normalize_fact_card_text(left.card.content) == normalize_fact_card_text(right.card.content):
                continue
            conflicts.append(FactCardConflict(name=left.card.name, left=left, right=right))
    return conflicts


def build_fact_card_prompt_section(selected_cards: list[SelectedFactCard]) -> str:
    if not selected_cards:
        return ""
    strong_lines = [
        f"- [{item.card.category}] {item.card.name}：{item.card.content}"
        for item in selected_cards
        if item.usage == "strong"
    ]
    reference_lines = [
        f"- [{item.card.category}] {item.card.name}：{item.card.content}"
        for item in selected_cards
        if item.usage == "reference"
    ]
    blocks = [
        "## 事实卡片参考",
        "以下事实卡片由用户为本次章节扩写显式选定。除以下内容外，不要自行引入未被选中的投标方事实。",
    ]
    if strong_lines:
        blocks.extend(
            [
                "",
                "### 强约束事实",
                *strong_lines,
                "",
                "要求：若正文涉及上述相关信息，必须保持一致；不得输出冲突表述，不得擅自改写为其他数字、人名、周期或承诺。",
            ]
        )
    if reference_lines:
        blocks.extend(
            [
                "",
                "### 参考事实",
                *reference_lines,
                "",
                "要求：相关时优先参考吸收；若与本章关联较弱，可不强行写入。",
            ]
        )
    return "\n".join(blocks)
```

```python
# bid_writer/ai_writer.py
_PROMPT_CONTRACT_BLOCKS = (
    ("system_constraints", "System Constraints", "system"),
    ("chapter_task", "Chapter Task", "user"),
    ("structure_rules", "Structure Rules", "user"),
    ("chapter_scope", "Chapter Scope", "user"),
    ("project_background", "Project Background", "user"),
    ("fact_card_context", "Fact Card Context", "user"),
    ("knowledge_context", "Knowledge Context", "user"),
    ("requirement_context", "Requirement Context", "user"),
    ("scoring_context", "Scoring Context", "user"),
)

def build_prompt_result(
    self,
    heading: HeadingNode,
    additional_requirements: str = "",
    target_words: int = 500,
    max_mermaid_flowcharts_per_section_override: Optional[int] = None,
    min_words: Optional[int] = None,
    status_callback: Optional[Callable[[str, str], None]] = None,
    fact_card_mode: bool = False,
    selected_fact_cards: Optional[list[SelectedFactCard]] = None,
) -> PromptBuildResult:
    fact_card_section = build_fact_card_prompt_section(selected_fact_cards or [])
    if pruned_context is None:
        self._append_prompt_sections(prompt_parts, prompt_sections, full_context_sections)
        if fact_card_mode:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "fact_card_context",
                fact_card_section,
            )
    else:
        if fact_card_mode:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "fact_card_context",
                fact_card_section,
            )
        elif knowledge_context:
            self._append_prompt_section(
                prompt_parts,
                prompt_sections,
                "knowledge_context",
                knowledge_context,
            )

def prepare_generation(
    self,
    heading: HeadingNode,
    additional_requirements: str = "",
    target_words: int = 500,
    stream: bool = True,
    max_mermaid_flowcharts_per_section_override: Optional[int] = None,
    min_words: Optional[int] = None,
    status_callback: Optional[Callable[[str, str], None]] = None,
    fact_card_mode: bool = False,
    selected_fact_cards: Optional[list[SelectedFactCard]] = None,
) -> PreparedGeneration:
    prompt_result = self.build_prompt_result(
        heading,
        additional_requirements,
        target_words,
        max_mermaid_flowcharts_per_section_override=max_mermaid_flowcharts_per_section_override,
        min_words=min_words,
        status_callback=status_callback,
        fact_card_mode=fact_card_mode,
        selected_fact_cards=selected_fact_cards,
    )
    system_prompt = self.build_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt_result.prompt},
    ]
    request_options = self._build_request_options(messages, stream=stream)
    trace_session = self.trace_logger.start_session(
        heading=heading,
        additional_requirements=additional_requirements,
        target_words=target_words,
        target_word_range=target_word_range,
        stream=stream,
        system_prompt=system_prompt,
        user_prompt=prompt_result.prompt,
        prompt_sections=prompt_result.prompt_sections,
        prompt_contract_blocks=prompt_result.prompt_contract_blocks,
        context_mode=prompt_result.context_mode,
        pruned_context=prompt_result.pruned_context,
        full_context_stats=prompt_result.full_context_stats,
        request_options=request_options,
        fact_card_mode=fact_card_mode,
        selected_fact_cards=selected_fact_cards or [],
    )
```

```python
# bid_writer/generation_trace.py
def __init__(
    self,
    config: Config,
    heading: HeadingNode,
    additional_requirements: str,
    target_words: int,
    target_word_range: TargetWordRange,
    stream: bool,
    system_prompt: str,
    user_prompt: str,
    prompt_sections: list[dict[str, Any]],
    prompt_contract_blocks: list[dict[str, Any]],
    context_mode: str,
    pruned_context: Optional[ChapterContext],
    full_context_stats: dict[str, Any],
    request_options: dict[str, Any],
    fact_card_mode: bool,
    selected_fact_cards: list[SelectedFactCard],
):
    self.fact_card_mode = fact_card_mode
    self.selected_fact_cards = selected_fact_cards

payload["fact_card_mode"] = self.fact_card_mode
payload["fact_card_selection"] = [
    {
        "card_id": item.card.id,
        "name": item.card.name,
        "category": item.card.category,
        "usage": item.usage,
    }
    for item in self.selected_fact_cards
]
```

- [ ] **Step 4: Run the prompt/trace suite again**

Run: `uv run pytest tests/test_fact_card_prompt.py tests/test_prompt_contract.py -q`

Expected: PASS

- [ ] **Step 5: Commit the prompt integration**

```bash
git add tests/test_fact_card_prompt.py tests/test_prompt_contract.py tests/fixtures/fact_card_prompt_config.yaml bid_writer/fact_cards.py bid_writer/ai_writer.py bid_writer/generation_trace.py
git commit -m "feat: inject selected fact cards into prompts"
```

## Task 4: Add Fact-Card Library and Extraction Review Dialogs

**Files:**
- Create: `bid_writer/fact_card_dialogs.py`
- Modify: `bid_writer/gui.py`
- Modify: `bid_writer/main.py`

- [ ] **Step 1: Create reusable dialogs for card library and extraction draft review**

```python
# bid_writer/fact_card_dialogs.py
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from .fact_cards import FactCard, FactCardDraft
from .gui import apply_window_surface, style_text_widget


@dataclass(frozen=True)
class FactCardDraftDialogResult:
    drafts: list[FactCardDraft]
    extraction_instruction: str


class FactCardDraftDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, title: str, instruction: str, drafts: list[FactCardDraft]):
        super().__init__(parent)
        apply_window_surface(self)
        self.result: FactCardDraftDialogResult | None = None
        self.title(title)
        self.geometry("980x620")
        self.transient(parent)
        self.grab_set()
        self._instruction_text = tk.Text(self, height=4)
        style_text_widget(self._instruction_text)
        self._instruction_text.insert("1.0", instruction)
        self._instruction_text.pack(fill=tk.X, padx=16, pady=(16, 8))
        self._tree = ttk.Treeview(self, columns=("name", "category"), show="headings")
        self._tree.heading("name", text="事实名称")
        self._tree.heading("category", text="分类")
        self._tree.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
```

```python
# bid_writer/fact_card_dialogs.py
class FactCardLibraryDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, cards: list[FactCard]):
        super().__init__(parent)
        apply_window_surface(self)
        self.title("事实卡片库管理")
        self.geometry("1080x720")
        self.transient(parent)
        self.grab_set()
        self._tree = ttk.Treeview(
            self,
            columns=("name", "category", "source_type", "source_chapter"),
            show="headings",
        )
        for column, label in (
            ("name", "事实名称"),
            ("category", "分类"),
            ("source_type", "来源"),
            ("source_chapter", "来源章节"),
        ):
            self._tree.heading(column, text=label)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)


class FactCardSelectionDialog(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, cards: list[FactCard], defaults):
        super().__init__(parent)
        self._usage_vars: dict[str, tk.StringVar] = {}
        self._selected_vars: dict[str, tk.BooleanVar] = {}
        ttk.Label(self, text="事实卡片", style="SectionTitle.TLabel").pack(anchor="w", pady=(8, 6))
        for card in cards:
            row = ttk.Frame(self)
            row.pack(fill=tk.X, pady=2)
            self._selected_vars[card.id] = tk.BooleanVar(
                value=any(item.card_id == card.id for item in defaults)
            )
            self._usage_vars[card.id] = tk.StringVar(
                value=next((item.usage for item in defaults if item.card_id == card.id), "reference")
            )
            ttk.Checkbutton(row, text=f"{card.name}（{card.category}）", variable=self._selected_vars[card.id]).pack(side=tk.LEFT)
            ttk.Combobox(row, textvariable=self._usage_vars[card.id], values=("strong", "reference"), width=10).pack(side=tk.RIGHT)

    def collect(self) -> list[FactCardSelection]:
        return [
            FactCardSelection(card_id=card_id, usage=self._usage_vars[card_id].get())
            for card_id, selected in self._selected_vars.items()
            if selected.get()
        ]
```

- [ ] **Step 2: Wire the dialogs into the main window menus and chapter actions**

```python
# bid_writer/gui.py
from .fact_card_dialogs import FactCardDraftDialog, FactCardLibraryDialog, FactCardSelectionDialog

def create_menu_bar(self):
    self.action_menu.add_command(label="管理事实卡片", command=self.open_fact_card_library)
    self.action_menu.add_command(label="提炼当前章节事实卡片", command=self.extract_selected_fact_cards)

def create_outline_context_menu(self):
    self.outline_context_menu.add_command(
        label="提炼事实卡片",
        command=self.extract_context_menu_fact_cards,
    )

def open_fact_card_library(self):
    dialog = FactCardLibraryDialog(self, self.bid_writer.list_fact_cards())
    self.wait_window(dialog)

def extract_selected_fact_cards(self):
    heading = self._get_single_selected_leaf_heading()
    if heading is None:
        messagebox.showwarning("提示", "请先选中一个可扩写章节。", parent=self)
        return
    self._open_fact_card_extraction_dialog(heading)
```

```python
# bid_writer/main.py
def replace_extracted_fact_cards(self, heading: HeadingNode, instruction: str, drafts):
    saved = self.fact_card_store.replace_extracted_cards(
        chapter_path=heading.full_path,
        extraction_instruction=instruction,
        drafts=drafts,
    )
    self.reload_config()
    return saved

def save_manual_fact_cards(self, drafts):
    saved = self.fact_card_store.save_manual_cards(drafts)
    self.reload_config()
    return saved
```

- [ ] **Step 3: Run the non-GUI regression tests to ensure the new dialog imports do not break the suite**

Run: `uv run pytest tests/test_fact_cards.py tests/test_fact_card_extractor.py tests/test_fact_card_prompt.py -q`

Expected: PASS

- [ ] **Step 4: Run a manual GUI smoke test for library and extraction review**

Run: `uv run python run.py`

Expected:
- The main menu shows `管理事实卡片`
- The chapter right-click menu shows `提炼事实卡片`
- Opening the extraction dialog for a chapter allows editing drafts before saving
- Saving writes a `fact_cards:` block into the active config YAML

- [ ] **Step 5: Commit the GUI management dialogs**

```bash
git add bid_writer/fact_card_dialogs.py bid_writer/gui.py bid_writer/main.py
git commit -m "feat: add fact card library and extraction dialogs"
```

## Task 5: Integrate Single-Chapter Selection, Batch Defaults, and Conflict Blocking

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `bid_writer/main.py`
- Modify: `bid_writer/ai_writer.py`
- Modify: `tests/test_fact_cards.py`

- [ ] **Step 1: Write failing tests for default resolution and empty-default clearing**

```python
from pathlib import Path

from bid_writer.config import Config
from bid_writer.fact_card_store import FactCardStore
from bid_writer.fact_cards import FactCardDraft, FactCardSelection


def test_save_chapter_defaults_clears_key_when_selection_is_empty(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    store = FactCardStore(config)
    saved = store.save_manual_cards([FactCardDraft(name="项目经理", content="项目经理由张三担任。", category="人员团队")])
    store.save_chapter_defaults("项目 > 质量保障措施", [FactCardSelection(card_id=saved[0].id, usage="strong")])
    store.save_chapter_defaults("项目 > 质量保障措施", [])
    assert store.list_chapter_defaults("项目 > 质量保障措施") == []


def test_resolve_generation_fact_cards_prefers_manual_selection_over_defaults(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    store = FactCardStore(config)
    saved = store.save_manual_cards(
        [
            FactCardDraft(name="项目经理", content="项目经理由张三担任。", category="人员团队"),
            FactCardDraft(name="响应时效", content="提供 7×24 小时响应支持。", category="服务承诺"),
        ]
    )
    store.save_chapter_defaults("项目 > 质量保障措施", [FactCardSelection(card_id=saved[0].id, usage="strong")])

    resolved = store.resolve_selected_cards([FactCardSelection(card_id=saved[1].id, usage="reference")])

    assert [item.card.id for item in resolved] == [saved[1].id]
    assert resolved[0].usage == "reference"
```

- [ ] **Step 2: Run the selection tests to confirm they fail**

Run: `uv run pytest tests/test_fact_cards.py::test_save_chapter_defaults_clears_key_when_selection_is_empty tests/test_fact_cards.py::test_resolve_generation_fact_cards_prefers_manual_selection_over_defaults -q`

Expected: FAIL because `save_manual_cards` / `resolve_selected_cards` do not exist yet.

- [ ] **Step 3: Implement selection persistence, single-vs-batch behavior, and conflict blocking**

```python
# bid_writer/fact_card_store.py
def save_manual_cards(self, drafts: list[FactCardDraft]) -> list[FactCard]:
    config_payload = self._load_config_payload()
    fact_cards = config_payload.setdefault("fact_cards", {"enabled": True, "cards": [], "chapter_defaults": {}})
    now = _now_string()
    saved_cards = [
        FactCard(
            id=self._new_id(draft.name, draft.content, now),
            name=draft.name.strip(),
            content=draft.content.strip(),
            category=draft.category.strip() or "未分类",
            active=True,
            source=FactCardSource(type="manual"),
            created_at=now,
            updated_at=now,
        )
        for draft in drafts
        if draft.name.strip() and draft.content.strip()
    ]
    fact_cards["cards"] = [*fact_cards.get("cards", []), *[self._card_to_payload(card) for card in saved_cards]]
    self._write_config_payload(config_payload)
    return saved_cards


def resolve_selected_cards(self, selections: list[FactCardSelection]) -> list[SelectedFactCard]:
    cards_by_id = {card.id: card for card in self.list_cards(active_only=True)}
    return [
        SelectedFactCard(card=cards_by_id[item.card_id], usage=item.usage)
        for item in selections
        if item.card_id in cards_by_id
    ]
```

```python
# bid_writer/main.py
def resolve_generation_fact_cards(self, heading: HeadingNode, manual_selections=None, *, fact_card_mode: bool = False):
    if not fact_card_mode:
        return []
    selections = manual_selections if manual_selections is not None else self.fact_card_store.list_chapter_defaults(heading.full_path)
    return self.fact_card_store.resolve_selected_cards(selections)
```

```python
# bid_writer/gui.py
def batch_generate(self):
    selected_headings = self._get_selected_leaf_headings()
    params = self._get_generation_params(selected_headings=selected_headings)
    auto_extract_facts = False

def _get_generation_params(self, *, selected_headings, initial_requirements: str = "", dependency_hint: str = ""):
    is_single_heading = len(selected_headings) == 1
    fact_card_mode = self.bid_writer.config.fact_cards_enabled
    if fact_card_mode and is_single_heading:
        selector = FactCardSelectionDialog(
            dialog,
            cards=self.bid_writer.list_fact_cards(),
            defaults=self.bid_writer.fact_card_store.list_chapter_defaults(selected_headings[0].full_path),
        )
        selector.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
    elif fact_card_mode:
        ttk.Label(
            dialog,
            text="批量生成时只读取各章节已保存的默认事实卡片方案，本次不提供整批共用选择。",
            justify=tk.LEFT,
        ).pack(padx=20, pady=(0, 10), anchor=tk.W)
    remember_fact_cards_var = tk.BooleanVar(value=False)
    if fact_card_mode and is_single_heading:
        ttk.Checkbutton(
            dialog,
            text="记住为本章节默认卡片方案",
            variable=remember_fact_cards_var,
        ).pack(padx=20, pady=(0, 12), anchor=tk.W)

    def on_ok():
        additional_req = req_text.get("1.0", tk.END).strip()
        selected_fact_cards = selector.collect() if fact_card_mode and is_single_heading else None
        result["cancelled"] = False
        result["requirements"] = additional_req
        result["target_words"] = target_words
        result["max_mermaid_flowcharts_per_section"] = max_mermaid_flowcharts_per_section
        result["fact_card_mode"] = fact_card_mode
        result["fact_card_selections"] = selected_fact_cards
        result["remember_fact_cards"] = remember_fact_cards_var.get()
        dialog.destroy()
```

```python
# bid_writer/gui.py
def _generate_into_workspace(
    self,
    heading: HeadingNode,
    additional_requirements: str,
    target_words: int,
    max_mermaid_flowcharts_per_section: int,
    auto_extract_facts: bool = False,
    show_error_dialog: bool = True,
    fact_card_selections=None,
    fact_card_mode: bool = False,
    remember_fact_cards: bool = False,
):
    selected_fact_cards = self.bid_writer.resolve_generation_fact_cards(
        heading,
        manual_selections=fact_card_selections,
        fact_card_mode=fact_card_mode,
    )
    if fact_card_mode and fact_card_selections is not None and remember_fact_cards:
        self.bid_writer.save_chapter_default_fact_cards(heading.full_path, fact_card_selections)
    conflicts = detect_strong_fact_card_conflicts(selected_fact_cards)
    if conflicts:
        conflict_text = "\n\n".join(
            [
                f"事实名称：{item.name}\nA：{item.left.card.content}\nB：{item.right.card.content}"
                for item in conflicts
            ]
        )
        messagebox.showwarning("强约束事实冲突", conflict_text, parent=self)
        return "failed"
    prepared = self.bid_writer.ai_writer.prepare_generation(
        heading,
        additional_requirements,
        target_words,
        stream=self.bid_writer.ai_writer.config.generation_stream,
        max_mermaid_flowcharts_per_section_override=max_mermaid_flowcharts_per_section,
        fact_card_mode=fact_card_mode,
        selected_fact_cards=selected_fact_cards,
    )
```

- [ ] **Step 4: Run the selection tests and a manual single-vs-batch smoke test**

Run: `uv run pytest tests/test_fact_cards.py -q`

Expected: PASS

Run: `uv run python run.py`

Expected:
- Single-chapter generation dialog shows fact-card selection controls and a `记住为本章节默认卡片方案` option
- Batch generation dialog shows the default-only hint instead of a shared selector
- Selecting conflicting `strong` cards blocks generation with a warning dialog

- [ ] **Step 5: Commit the generation-flow wiring**

```bash
git add tests/test_fact_cards.py bid_writer/fact_card_store.py bid_writer/main.py bid_writer/gui.py bid_writer/ai_writer.py
git commit -m "feat: use fact cards during chapter generation"
```

## Task 6: Update Docs, Fixtures, and the Regression Suite

**Files:**
- Modify: `config.example.yaml`
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `docs/chapter_expansion_mechanism.md`
- Create: `tests/fixtures/fact_card_prompt_config.yaml`
- Modify: `tests/test_prompt_contract.py`
- Modify: `tests/test_config_editor.py`

- [ ] **Step 1: Add the fixture and documentation updates**

```yaml
# config.example.yaml
fact_cards:
  enabled: true
  cards: []
  chapter_defaults: {}
```

```yaml
# tests/fixtures/fact_card_prompt_config.yaml
project:
  root_dir: "."
  bidder_name: "测试投标主体"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
fact_cards:
  enabled: true
  cards: []
  chapter_defaults: {}
processing:
  path: "full_context"
```

```markdown
<!-- docs/prompt_contract.md -->
| `fact_card_context` | `## 事实卡片参考` | 启用事实卡片模式且本次章节携带事实卡片选择时 | 注入当前章节显式勾选的强约束 / 参考事实卡片 |
```

```markdown
<!-- docs/chapter_expansion_mechanism.md -->
- 单章节生成时，用户可在生成参数弹窗中手动勾选事实卡片
- 批量生成时，不提供整批共用的临时卡片选择；仅读取每个章节自己的默认方案
- 启用事实卡片模式后，旧 `knowledge_context` 不再默认进入扩写 prompt
```

- [ ] **Step 2: Add the final prompt-contract and passthrough regression assertions**

```python
def test_fact_card_prompt_contract_exposes_fact_card_block(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "fact_card_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")
    source = FactCardSource(type="manual")
    selected_cards = [
        SelectedFactCard(
            card=FactCard(
                id="fact_001",
                name="项目经理",
                content="项目经理由张三担任。",
                category="人员团队",
                active=True,
                source=source,
                created_at="2026-04-24T10:00:00+08:00",
                updated_at="2026-04-24T10:00:00+08:00",
            ),
            usage="strong",
        )
    ]

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=selected_cards,
    )

    fact_card_block = next(block for block in result.prompt_contract_blocks if block["id"] == "fact_card_context")
    assert fact_card_block["section_names"] == ["fact_card_context"]
    assert "build_fact_card_prompt_section" in fact_card_block["source_context"]
```

- [ ] **Step 3: Run the final regression suite**

Run: `uv run pytest tests/test_fact_cards.py tests/test_fact_card_extractor.py tests/test_fact_card_prompt.py tests/test_prompt_contract.py tests/test_config_editor.py -q`

Expected: PASS

- [ ] **Step 4: Run one final app-level smoke check against the updated docs/config**

Run: `uv run python run.py`

Expected:
- The app still loads the active config successfully
- Fact-card menu items work against the documented `config.example.yaml` shape
- Single-chapter selection and batch default-only behavior match the updated docs

- [ ] **Step 5: Commit the documentation and regression updates**

```bash
git add config.example.yaml docs/config_schema.md docs/prompt_contract.md docs/chapter_expansion_mechanism.md tests/fixtures/fact_card_prompt_config.yaml tests/test_prompt_contract.py tests/test_config_editor.py
git commit -m "docs: document fact card workflow and contract"
```

## Self-Review

**Spec coverage**

- 项目级卡片库 / YAML 存储：Task 1
- 手录与批量录入：Task 2 + Task 4
- 章节手动提炼、保存前可编辑、重提炼不脏写：Task 2 + Task 4
- 单章节手动勾选、强约束 / 参考：Task 3 + Task 5
- 可选保存章节默认方案：Task 1 + Task 5
- 强约束冲突阻断：Task 3 + Task 5
- 批量生成仅读取已保存默认方案：Task 5 + Task 6
- 启用事实卡片后停用默认 `knowledge_context`：Task 3 + Task 6
- trace / prompt contract 可回溯：Task 3 + Task 6

**Placeholder scan**

- No `TODO` / `TBD`
- Every task lists exact files
- Every code step includes explicit snippets
- Every test step uses exact `uv run pytest ...` commands

**Type consistency**

- Core domain names are fixed as `FactCard`, `FactCardDraft`, `FactCardSelection`, `SelectedFactCard`, `FactCardConflict`
- Store methods are fixed as `save_manual_cards`, `replace_extracted_cards`, `save_chapter_defaults`, `list_chapter_defaults`, `resolve_selected_cards`
- `AIWriter` uses `fact_card_mode` and `selected_fact_cards` consistently from plan start to finish
