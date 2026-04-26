# Fact Card Scope Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move fact-card scope and enforcement into the card model so active global cards are automatically injected into every chapter and strong/reference behavior is card-owned.

**Architecture:** Extend the fact-card domain model first, then update YAML persistence, prompt assembly, extraction, and GUI layers to use the new fields. `chapter_defaults` becomes a local-card selection list only; prompt rendering groups selected cards by `enforcement` and labels each card by `scope`.

**Tech Stack:** Python dataclasses, PyYAML, Tkinter/ttk, pytest, uv.

**Repo Policy Note:** Do not create git commits unless the user explicitly asks; task checkpoints use `git diff --check` and targeted tests instead of commit steps.

---

## File Structure

- Modify: `bid_writer/fact_cards.py` — add `scope` / `enforcement` fields, validation helpers, updated selection model, conflict detection, bulk parsing, and prompt rendering.
- Modify: `bid_writer/fact_card_store.py` — persist new card fields, auto-include global cards, filter chapter defaults to local cards, remove `usage` from saved defaults.
- Modify: `bid_writer/main.py` — route generation card resolution through the new chapter prompt resolver.
- Modify: `bid_writer/fact_card_extractor.py` — require and parse `scope` / `enforcement` from model extraction output.
- Modify: `bid_writer/fact_card_dialogs.py` — add scope/enforcement editors, remove per-selection usage combobox, show read-only enforcement metadata.
- Modify: `bid_writer/gui.py` — show global-card auto-inclusion summary and local-only selection behavior in generation parameter dialog.
- Modify: `tests/test_fact_cards.py` — update store, parsing, selection, and conflict tests for card-owned metadata.
- Modify: `tests/test_fact_card_extractor.py` — update extraction prompt and parser expectations.
- Modify: `tests/test_fact_card_prompt.py` — update prompt/trace expectations and global auto-inclusion coverage.
- Modify: `tests/test_fact_card_dialogs.py` — update dialog/editor tests for new fields and no per-selection usage.
- Modify: `tests/fixtures/fact_card_prompt_config.yaml` — update fixture schema.
- Modify: `config.example.yaml` — document new empty schema and example comments.
- Modify: `docs/config_schema.md` — replace `usage` with `scope` / `enforcement`.
- Modify: `docs/prompt_contract.md` — document new prompt semantics and trace payload.
- Modify: `docs/chapter_expansion_mechanism.md` — document global auto-inclusion and local defaults.

---

### Task 1: Domain Model And Prompt Renderer

**Files:**
- Modify: `bid_writer/fact_cards.py`
- Modify: `tests/test_fact_cards.py`

- [ ] **Step 1: Write failing domain tests**

Append these tests to `tests/test_fact_cards.py`, updating the import block to include `FactCard`, `FactCardSource`, `SelectedFactCard`, `build_fact_card_prompt_section`, and `detect_strong_fact_card_conflicts`.

```python
def test_fact_card_requires_scope_and_enforcement():
    valid = FactCard.from_dict(
        {
            "id": "card-a",
            "name": "企业资质",
            "content": "一级资质",
            "category": "资质",
            "scope": "global",
            "enforcement": "strong",
            "active": True,
            "source": {"type": "manual"},
        }
    )

    assert valid is not None
    assert valid.scope == "global"
    assert valid.enforcement == "strong"
    assert valid.to_dict()["scope"] == "global"
    assert valid.to_dict()["enforcement"] == "strong"

    assert FactCard.from_dict(
        {
            "id": "missing-scope",
            "name": "企业资质",
            "content": "一级资质",
            "enforcement": "strong",
            "source": {"type": "manual"},
        }
    ) is None
    assert FactCard.from_dict(
        {
            "id": "bad-enforcement",
            "name": "企业资质",
            "content": "一级资质",
            "scope": "global",
            "enforcement": "must",
            "source": {"type": "manual"},
        }
    ) is None


def test_fact_card_prompt_groups_by_enforcement_and_labels_scope():
    cards = [
        SelectedFactCard(
            card_id="global-strong",
            name="企业资质",
            content="一级资质",
            scope="global",
            enforcement="strong",
        ),
        SelectedFactCard(
            card_id="local-reference",
            name="实施经验",
            content="近三年 5 个同类项目",
            scope="local",
            enforcement="reference",
        ),
    ]

    section = build_fact_card_prompt_section(cards)

    assert "### 强制事实" in section
    assert "- [全局] 企业资质：一级资质" in section
    assert "### 参考事实" in section
    assert "- [局部] 实施经验：近三年 5 个同类项目" in section


def test_strong_conflict_detection_uses_card_enforcement():
    conflicts = detect_strong_fact_card_conflicts(
        [
            SelectedFactCard(
                card_id="a",
                name="项目经理",
                content="张三",
                scope="global",
                enforcement="strong",
            ),
            SelectedFactCard(
                card_id="b",
                name="项目经理",
                content="李四",
                scope="local",
                enforcement="strong",
            ),
            SelectedFactCard(
                card_id="c",
                name="项目经理",
                content="王五",
                scope="local",
                enforcement="reference",
            ),
        ]
    )

    assert len(conflicts) == 1
    assert {card.card_id for card in conflicts[0].cards} == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_fact_cards.py::test_fact_card_requires_scope_and_enforcement tests/test_fact_cards.py::test_fact_card_prompt_groups_by_enforcement_and_labels_scope tests/test_fact_cards.py::test_strong_conflict_detection_uses_card_enforcement -q
```

Expected: FAIL because `FactCard` and `SelectedFactCard` do not yet expose `scope` / `enforcement`.

- [ ] **Step 3: Update fact-card dataclasses and helpers**

In `bid_writer/fact_cards.py`, add constants and normalizers near the existing regex:

```python
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
```

Change `FactCardDraft`, `FactCard`, `SelectedFactCard`, and `FactCardSelection` to this shape:

```python
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
```

In `FactCard.from_dict()`, read and require normalized `scope` / `enforcement`; in `FactCard.to_dict()`, always emit both fields. Replace `FactCardSelection` with `card_id` only:

```python
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
```

Replace `SelectedFactCard` with:

```python
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
```

Update `SelectedFactCard.to_prompt_dict()` and `to_trace_payload()` so both emit `scope` and `enforcement` and no longer emit `usage`.

- [ ] **Step 4: Update conflict detection and prompt rendering**

In `detect_strong_fact_card_conflicts()`, replace `card.usage != "strong"` with `card.enforcement != "strong"`.

Replace `build_fact_card_prompt_section()` with:

```python
def build_fact_card_prompt_section(selected_cards: list[SelectedFactCard]) -> str:
    if not selected_cards:
        return ""

    strong_cards = [card for card in selected_cards if card.enforcement == "strong"]
    reference_cards = [card for card in selected_cards if card.enforcement != "strong"]

    lines = [
        "## 事实卡片参考",
        "以下事实卡片已进入当前章节扩写上下文；“强制事实”必须保持一致，“参考事实”可按章节需要择优吸收。",
    ]
    if strong_cards:
        lines.append("### 强制事实")
        lines.extend(_format_fact_card_prompt_line(card) for card in strong_cards)
    if reference_cards:
        lines.append("### 参考事实")
        lines.extend(_format_fact_card_prompt_line(card) for card in reference_cards)
    return "\n".join(lines)


def _format_fact_card_prompt_line(card: SelectedFactCard) -> str:
    scope_label = FACT_CARD_SCOPE_LABELS.get(card.scope, card.scope or "未标记")
    return f"- [{scope_label}] {card.name}：{card.content}"
```

Ensure `SelectedFactCard.to_prompt_dict()` and `to_trace_payload()` emit `scope` and `enforcement`.

- [ ] **Step 5: Update bulk parser tests and implementation**

Replace `test_parse_bulk_fact_card_input_splits_name_and_content()` with a new-format test:

```python
def test_parse_bulk_fact_card_input_reads_scope_and_enforcement():
    drafts = parse_bulk_fact_card_input(
        "企业资质｜全局｜强制：具备建筑工程施工总承包一级资质\n"
        "服务承诺|local|reference: 提供7×24小时响应\n"
        "无效行\n"
        " 项目经理 ｜ 局部 ｜ 参考 ： 张三 "
    )

    assert drafts == [
        FactCardDraft(
            name="企业资质",
            content="具备建筑工程施工总承包一级资质",
            scope="global",
            enforcement="strong",
        ),
        FactCardDraft(
            name="服务承诺",
            content="提供7×24小时响应",
            scope="local",
            enforcement="reference",
        ),
        FactCardDraft(
            name="项目经理",
            content="张三",
            scope="local",
            enforcement="reference",
        ),
    ]
```

Update `_BULK_FACT_CARD_LINE_RE` and `parse_bulk_fact_card_line()` to accept `名称｜作用域｜约束：内容`, with Chinese aliases `全局/局部/强制/参考` normalized to `global/local/strong/reference`.

- [ ] **Step 6: Run domain tests**

Run:

```bash
uv run pytest tests/test_fact_cards.py::test_fact_card_requires_scope_and_enforcement tests/test_fact_cards.py::test_fact_card_prompt_groups_by_enforcement_and_labels_scope tests/test_fact_cards.py::test_strong_conflict_detection_uses_card_enforcement tests/test_fact_cards.py::test_parse_bulk_fact_card_input_reads_scope_and_enforcement -q
```

Expected: PASS.

---

### Task 2: Store Resolution And Chapter Defaults

**Files:**
- Modify: `bid_writer/fact_card_store.py`
- Modify: `bid_writer/main.py`
- Modify: `tests/test_fact_cards.py`

- [ ] **Step 1: Update fixture YAML in store tests**

For every `fact_cards.cards` item in `tests/test_fact_cards.py`, add:

```yaml
scope: local
enforcement: reference
```

Use `scope: global` and `enforcement: strong` only in tests specifically covering global auto-inclusion or strong conflicts. Remove every `usage:` entry from `chapter_defaults`; each entry should be only:

```yaml
- card_id: card-a
```

- [ ] **Step 2: Add failing store tests**

Append:

```python
def test_resolve_chapter_prompt_cards_auto_includes_global_cards(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: global-a
      name: 企业资质
      content: 一级资质
      scope: global
      enforcement: strong
      active: true
      source:
        type: manual
    - id: local-a
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
    - id: inactive-global
      name: 不启用
      content: 不应出现
      scope: global
      enforcement: reference
      active: false
      source:
        type: manual
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: local-a
""",
    )
    store = FactCardStore(Config(str(config_path)))

    selected = store.resolve_chapter_prompt_cards("技术方案 > 质量保障措施")

    assert [(card.card_id, card.scope, card.enforcement) for card in selected] == [
        ("global-a", "global", "strong"),
        ("local-a", "local", "reference"),
    ]


def test_save_chapter_defaults_filters_global_cards_and_writes_card_ids_only(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: global-a
      name: 企业资质
      content: 一级资质
      scope: global
      enforcement: strong
      active: true
      source:
        type: manual
    - id: local-a
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_chapter_defaults(
        "技术方案 > 质量保障措施",
        [FactCardSelection(card_id="global-a"), FactCardSelection(card_id="local-a")],
    )

    assert saved == [FactCardSelection(card_id="local-a")]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == [
        {"card_id": "local-a"}
    ]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_fact_cards.py::test_resolve_chapter_prompt_cards_auto_includes_global_cards tests/test_fact_cards.py::test_save_chapter_defaults_filters_global_cards_and_writes_card_ids_only -q
```

Expected: FAIL because global cards are not auto-included and defaults still preserve `usage`.

- [ ] **Step 4: Implement global/local resolution in store**

In `bid_writer/fact_card_store.py`, add helper methods:

```python
@staticmethod
def _active_global_cards(cards: list[FactCard]) -> list[FactCard]:
    return [card for card in cards if card.active and card.scope == "global"]


@staticmethod
def _active_local_cards_by_id(cards: list[FactCard]) -> dict[str, FactCard]:
    return {card.id: card for card in cards if card.active and card.scope == "local"}
```

Update `resolve_chapter_prompt_cards()` to:

```python
def resolve_chapter_prompt_cards(
    self,
    chapter_path: str,
    selections: Iterable[FactCardSelection | dict[str, Any]] | None = None,
) -> list[SelectedFactCard]:
    cards = self.list_cards(active_only=False)
    global_cards = self._active_global_cards(cards)
    local_cards_by_id = self._active_local_cards_by_id(cards)
    normalized_selections = (
        self.list_chapter_defaults(chapter_path)
        if selections is None
        else self._coerce_selection_iterable(selections)
    )

    resolved: list[SelectedFactCard] = []
    seen: set[str] = set()
    for card in global_cards:
        resolved.append(SelectedFactCard.from_fact_card(card))
        seen.add(card.id)
    for selection in normalized_selections:
        if selection.card_id in seen:
            continue
        card = local_cards_by_id.get(selection.card_id)
        if card is None:
            continue
        resolved.append(SelectedFactCard.from_fact_card(card))
        seen.add(card.id)

    conflicts = detect_strong_fact_card_conflicts(resolved)
    if conflicts:
        raise FactCardConflictError(conflicts)
    return resolved
```

Keep `resolve_selected_cards()` as a public compatibility point inside the codebase, but change its semantics to active globals plus provided local selections:

```python
def resolve_selected_cards(
    self,
    selections: Iterable[FactCardSelection | dict[str, Any]],
) -> list[SelectedFactCard]:
    return self.resolve_chapter_prompt_cards("", selections)
```

- [ ] **Step 5: Update chapter default filtering**

Change `_filter_existing_selections()` to accept only active local cards:

```python
existing_local_ids = {card.id for card in cards if card.active and card.scope == "local"}
```

Change `_coerce_selection_list()` so list entries are parsed as `FactCardSelection(card_id=...)` only; do not read `usage`.

Update `save_chapter_defaults()` and `_clean_all_chapter_defaults()` so persisted entries call `selection.to_dict()` and therefore save only `card_id`.

- [ ] **Step 6: Persist new fields in save methods**

In `save_manual_cards()`, `save_library_cards()`, and `replace_extracted_cards()`, pass `scope=draft.scope` and `enforcement=draft.enforcement` into every `FactCard(...)` constructor.

Each affected constructor block should include:

```python
scope=draft.scope,
enforcement=draft.enforcement,
```

- [ ] **Step 7: Update main generation resolver**

In `bid_writer/main.py`, replace the fact-card mode branch in `resolve_generation_fact_cards()` with:

```python
if not fact_card_mode:
    return []
return self.fact_card_store.resolve_chapter_prompt_cards(
    self._resolve_heading_path(heading),
    manual_selections,
)
```

This ensures global cards are included for both manual selections and saved defaults.

- [ ] **Step 8: Run store tests**

Run:

```bash
uv run pytest tests/test_fact_cards.py -q
```

Expected: PASS after all old `usage` assertions are updated to `card_id`-only assertions and all test card YAML includes `scope` / `enforcement`.

---

### Task 3: Prompt Trace And Fact-Card Prompt Tests

**Files:**
- Modify: `tests/fixtures/fact_card_prompt_config.yaml`
- Modify: `tests/test_fact_card_prompt.py`
- Modify: `bid_writer/ai_writer.py`

- [ ] **Step 1: Update prompt fixture**

In `tests/fixtures/fact_card_prompt_config.yaml`, update each card:

```yaml
scope: global
enforcement: strong
```

for cards that should automatically appear in every chapter, and:

```yaml
scope: local
enforcement: reference
```

for cards controlled by `chapter_defaults`.

Update `chapter_defaults` entries from:

```yaml
- card_id: card-service
  usage: reference
```

to:

```yaml
- card_id: card-service
```

- [ ] **Step 2: Update prompt tests**

In `tests/test_fact_card_prompt.py`, replace `usage` assertions with `scope` / `enforcement` assertions. Example expected payload:

```python
assert payload["fact_card_selection"] == [
    {
        "card_id": "card-qualification",
        "name": "企业资质",
        "content": "具备建筑工程施工总承包一级资质。",
        "scope": "global",
        "enforcement": "strong",
        "source": {"type": "manual"},
    },
    {
        "card_id": "card-service",
        "name": "服务承诺",
        "content": "提供7×24小时响应机制。",
        "scope": "local",
        "enforcement": "reference",
        "source": {"type": "manual"},
    },
]
```

Update any direct `SelectedFactCard(...)` construction to include:

```python
scope="global",
enforcement="strong",
```

or:

```python
scope="local",
enforcement="reference",
```

- [ ] **Step 3: Add global auto-inclusion prompt test**

Add:

```python
def test_fact_card_mode_prompt_auto_includes_global_cards_without_defaults(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "实施方案")

    selected_cards = FactCardStore(config).resolve_chapter_prompt_cards(heading.full_path)
    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=selected_cards,
    )

    assert "## 事实卡片参考" in result.prompt
    assert "[全局] 企业资质" in result.prompt
    assert "[局部] 服务承诺" not in result.prompt
```

- [ ] **Step 4: Verify AI writer serialization path**

`AIWriter._serialize_fact_card_selection()` should not need structural changes if `SelectedFactCard.to_trace_payload()` was updated in Task 1. Run the prompt tests to confirm.

- [ ] **Step 5: Run prompt tests**

Run:

```bash
uv run pytest tests/test_fact_card_prompt.py tests/test_prompt_contract.py -q
```

Expected: PASS after fixtures and contract expectations use `scope` / `enforcement`.

---

### Task 4: Extraction Prompt And Parser

**Files:**
- Modify: `bid_writer/fact_card_extractor.py`
- Modify: `tests/test_fact_card_extractor.py`

- [ ] **Step 1: Update extractor tests**

In `test_fact_card_extractor_builds_prompt_with_heading_context_and_parses_json()`, change fake model content to include new fields:

```python
completions = _FakeCompletions(
    '[{"name":"项目经理","content":"张三，5年经验","category":"人员","scope":"global","enforcement":"strong"},'
    '{"name":"服务承诺","content":"7×24小时响应","category":"承诺","scope":"local","enforcement":"reference"}]'
)
```

Update expected draft:

```python
assert drafts == [
    FactCardDraft(
        name="项目经理",
        content="张三，5年经验",
        category="人员",
        scope="global",
        enforcement="strong",
    ),
]
```

Assert prompt content includes:

```python
assert "每项字段必须包含：name、content、scope、enforcement" in prompt
assert "scope 只能是 global 或 local" in prompt
assert "enforcement 只能是 strong 或 reference" in prompt
```

- [ ] **Step 2: Add invalid metadata parser test**

Add:

```python
def test_fact_card_extractor_rejects_missing_scope_or_enforcement():
    result = FactCardExtractor.parse_draft_response_with_diagnostics(
        '[{"name":"企业资质","content":"一级资质","category":"资质"}]'
    )

    assert result.drafts == []
    assert result.message == "模型返回了数组，但没有包含可保存的事实卡片。"
    assert "scope" in result.detail
    assert "enforcement" in result.detail
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_fact_card_extractor.py::test_fact_card_extractor_builds_prompt_with_heading_context_and_parses_json tests/test_fact_card_extractor.py::test_fact_card_extractor_rejects_missing_scope_or_enforcement -q
```

Expected: FAIL because extractor prompt and diagnostics still only require `name/content/category`.

- [ ] **Step 4: Update extractor prompt**

In `FactCardExtractor.build_prompt()`, replace the output requirements lines with:

```python
"3. 每项字段必须包含：name、content、scope、enforcement，可选 category。",
"4. scope 只能是 global 或 local：主体信息、资质能力、统一承诺、全项目通用要求用 global；只适用于当前章节主题、局部措施、局部流程的内容用 local。",
"5. enforcement 只能是 strong 或 reference：必须全文一致、不能被改写成相反含义的信息用 strong；仅供借鉴、可按章节选择性吸收的信息用 reference。",
"6. 选择最能代表本章节核心内容、最适合后续章节复用或引用的一条事实。",
"7. 内容必须具体、可验证、信息密度高，避免泛泛总结、修饰性评价和重复表述。",
```

- [ ] **Step 5: Update parser diagnostics**

In `parse_draft_response_with_diagnostics()`, extend the missing field checks:

```python
if not str(item.get("scope", "") or "").strip():
    missing_fields.append("scope")
if not str(item.get("enforcement", "") or "").strip():
    missing_fields.append("enforcement")
```

After missing-field checks, add invalid-value details:

```python
scope_value = str(item.get("scope", "") or "").strip()
enforcement_value = str(item.get("enforcement", "") or "").strip()
if scope_value and not normalize_fact_card_scope(scope_value):
    invalid_reasons.append("存在 scope 取值不是 global/local 的数组项。")
if enforcement_value and not normalize_fact_card_enforcement(enforcement_value):
    invalid_reasons.append("存在 enforcement 取值不是 strong/reference 的数组项。")
```

Import `normalize_fact_card_scope` and `normalize_fact_card_enforcement` from `bid_writer.fact_cards`.

- [ ] **Step 6: Run extractor tests**

Run:

```bash
uv run pytest tests/test_fact_card_extractor.py -q
```

Expected: PASS after all expected drafts include `scope` / `enforcement`.

---

### Task 5: GUI Editors And Selection Panel

**Files:**
- Modify: `bid_writer/fact_card_dialogs.py`
- Modify: `tests/test_fact_card_dialogs.py`

- [ ] **Step 1: Update dialog tests**

Update every `FactCard(...)` and `FactCardDraft(...)` construction in `tests/test_fact_card_dialogs.py` to include `scope` and `enforcement`. Example:

```python
FactCardDraft(
    card_id="manual-a",
    name="企业资质",
    content="一级资质",
    category="资质",
    scope="global",
    enforcement="strong",
)
```

Add editor validation test:

```python
def test_fact_card_draft_editor_returns_scope_and_enforcement():
    editor = fact_card_dialogs.FactCardDraftEditor.__new__(fact_card_dialogs.FactCardDraftEditor)
    editor._rows = [
        {
            "card_id": "card-a",
            "name_var": SimpleNamespace(get=lambda: "企业资质"),
            "category_var": SimpleNamespace(get=lambda: "资质"),
            "scope_var": SimpleNamespace(get=lambda: "global"),
            "enforcement_var": SimpleNamespace(get=lambda: "strong"),
            "content_text": SimpleNamespace(get=lambda *_args: "一级资质"),
        }
    ]

    assert editor.get_drafts() == [
        FactCardDraft(
            card_id="card-a",
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        )
    ]
```

Ensure `SimpleNamespace` is imported from `types` if not already available.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_fact_card_dialogs.py::test_fact_card_draft_editor_returns_scope_and_enforcement -q
```

Expected: FAIL because `FactCardDraftEditor` does not yet expose `scope_var` / `enforcement_var`.

- [ ] **Step 3: Add scope/enforcement controls to draft editor**

In `FactCardDraftEditor.add_empty_row()`, use:

```python
self.add_row(FactCardDraft(name="", content="", category="", scope="local", enforcement="reference"))
```

In `add_row()`, create variables:

```python
scope_var = tk.StringVar(value=draft.scope or "local")
enforcement_var = tk.StringVar(value=draft.enforcement or "reference")
row_data["scope_var"] = scope_var
row_data["enforcement_var"] = enforcement_var
```

Add two readonly comboboxes after category:

```python
ttk.Label(top_row, text="作用域").pack(side=tk.LEFT)
ttk.Combobox(
    top_row,
    textvariable=scope_var,
    values=("global", "local"),
    state="readonly",
    width=9,
).pack(side=tk.LEFT, padx=(6, 12))
ttk.Label(top_row, text="约束").pack(side=tk.LEFT)
ttk.Combobox(
    top_row,
    textvariable=enforcement_var,
    values=("strong", "reference"),
    state="readonly",
    width=11,
).pack(side=tk.LEFT, padx=(6, 12))
```

In `get_drafts()`, read and validate:

```python
scope = normalize_fact_card_scope(str(row["scope_var"].get()).strip())
enforcement = normalize_fact_card_enforcement(str(row["enforcement_var"].get()).strip())
if not scope:
    raise ValueError("每张卡片都需要选择作用域：global 或 local。")
if not enforcement:
    raise ValueError("每张卡片都需要选择约束：strong 或 reference。")
```

Then construct:

```python
FactCardDraft(
    card_id=str(row.get("card_id", "") or "").strip(),
    name=name,
    content=content,
    category=category,
    scope=scope,
    enforcement=enforcement,
)
```

Import `normalize_fact_card_scope` and `normalize_fact_card_enforcement`.

- [ ] **Step 4: Remove per-selection usage from selection panel**

In `FactCardSelectionPanel`, remove `_usage_vars`, `usage_combo`, and `select_all_reference()`. Replace the action button text with `全选局部卡片` and implement:

```python
def select_all(self) -> None:
    for selected_var in self._selection_vars.values():
        selected_var.set(True)
```

Change `get_selections()` to:

```python
selections.append(FactCardSelection(card_id=card.id))
```

Display card metadata in the source line:

```python
meta = f"{self._format_source(card)} · {card.scope}/{card.enforcement}"
```

- [ ] **Step 5: Update library list columns**

In `FactCardLibraryDialog`, change columns to include `scope` and `enforcement`:

```python
columns = ("name", "source", "scope", "enforcement", "category", "content")
```

Add headings and row values using `card.scope` and `card.enforcement`.

Update `_build_library_drafts()` and `_build_manual_drafts()` so every draft includes:

```python
scope=card.scope,
enforcement=card.enforcement,
```

- [ ] **Step 6: Run dialog tests**

Run:

```bash
uv run pytest tests/test_fact_card_dialogs.py -q
```

Expected: PASS after existing expectations include the new fields and no longer expect per-selection usage.

---

### Task 6: Main GUI Generation Flow

**Files:**
- Modify: `bid_writer/gui.py`
- Modify: `tests/test_fact_card_dialogs.py` if GUI behavior is unit-covered there

- [ ] **Step 1: Update single-heading fact-card area**

In `_get_generation_params()`, replace:

```python
available_cards = self.bid_writer.fact_card_store.list_cards(active_only=True)
```

with:

```python
all_active_cards = self.bid_writer.fact_card_store.list_cards(active_only=True)
global_cards = [card for card in all_active_cards if card.scope == "global"]
available_cards = [card for card in all_active_cards if card.scope == "local"]
```

Set:

```python
default_mode = bool(global_cards or available_cards or initial_selections)
```

Add a summary label before `FactCardSelectionPanel`:

```python
ttk.Label(
    fact_card_frame,
    text=f"本次将自动加入 {len(global_cards)} 张全局事实卡片；下方仅选择当前章节局部卡片。",
    justify=tk.LEFT,
    wraplength=GENERATION_DIALOG_MIN_WIDTH + GENERATION_DIALOG_EXTRA_WIDTH - 80,
).pack(anchor=tk.W, pady=(0, 8))
```

- [ ] **Step 2: Update batch-generation hint**

Replace the batch label text with:

```python
"批量生成会自动加入启用的全局事实卡片，并读取各章节已保存的局部默认卡片方案；本次不提供整批共享临时局部卡片选择。"
```

- [ ] **Step 3: Ensure saved defaults are local-only**

The GUI can keep passing `manual_fact_card_selections` to `save_chapter_default_fact_cards()`; Task 2 store filtering removes global cards and invalid entries.

- [ ] **Step 4: Run GUI-adjacent tests**

Run:

```bash
uv run pytest tests/test_fact_card_dialogs.py tests/test_gui_scaling.py -q
```

Expected: PASS. If `tests/test_gui_scaling.py` fails for unrelated GUI sizing assumptions, record the existing failure and do not broaden the scope.

---

### Task 7: Documentation, Config Examples, And Fixtures

**Files:**
- Modify: `config.example.yaml`
- Modify: `docs/config_schema.md`
- Modify: `docs/prompt_contract.md`
- Modify: `docs/chapter_expansion_mechanism.md`
- Modify: `tests/fixtures/fact_card_prompt_config.yaml`
- Modify: `tests/test_config_schema.py`
- Modify: `tests/test_prompt_contract.py`

- [ ] **Step 1: Update config example**

In `config.example.yaml`, update the `fact_cards` block to:

```yaml
fact_cards:
  enabled: true
  cards: []
  chapter_defaults: {}
```

If comments or examples are added near this block, use:

```yaml
# cards:
#   - id: fact-card-1
#     name: 企业资质
#     content: 具备建筑工程施工总承包一级资质。
#     category: 资质
#     scope: global        # global / local
#     enforcement: strong  # strong / reference
#     active: true
#     source:
#       type: manual
# chapter_defaults:
#   "项目 > 技术方案 > 质量保障措施":
#     - card_id: fact-card-2
```

- [ ] **Step 2: Update config schema docs**

In `docs/config_schema.md`, replace the `fact_cards` example so cards contain `scope` and `enforcement`, and `chapter_defaults` entries contain only `card_id`.

Replace the `usage` bullet with:

```markdown
- `scope` 只支持 `global` / `local`：全局卡片在事实卡片模式下自动进入每个章节，局部卡片只通过章节显式选择或章节默认方案进入 prompt
- `enforcement` 只支持 `strong` / `reference`：强制卡片要求扩写结果保持一致，参考卡片仅作为可引用素材
- `chapter_defaults` 以**章节完整路径**为 key，只保存局部卡片的默认 `card_id` 列表
```

- [ ] **Step 3: Update prompt contract docs**

In `docs/prompt_contract.md`, update the `fact_card_context` row description to:

```markdown
注入自动命中的全局卡片和当前章节选中的局部卡片，按 `enforcement=strong/reference` 分组，并替代默认 `knowledge_context`
```

Update input table rows so `selected_fact_cards` is described as resolved cards carrying `scope` and `enforcement`.

- [ ] **Step 4: Update chapter expansion docs**

In `docs/chapter_expansion_mechanism.md`, replace the fact-card section bullets with:

```markdown
- 全局卡片：`active=true` 且 `scope=global` 时，在启用事实卡片模式后自动进入每个章节
- 局部卡片：`scope=local` 时，只在单章节手动选择或章节默认方案命中时进入 prompt
- 强制/参考：由卡片本体 `enforcement` 决定，生成参数弹窗不再为每个章节单独设置用途
- 批量模式：自动加入全局卡片，并读取各章节局部默认方案
```

- [ ] **Step 5: Run docs-related tests**

Run:

```bash
uv run pytest tests/test_config_schema.py tests/test_prompt_contract.py -q
```

Expected: PASS after doc fixtures and contract strings are updated.

---

### Task 8: Integration Verification

**Files:**
- Verify all files touched in earlier tasks

- [ ] **Step 1: Run targeted fact-card suite**

Run:

```bash
uv run pytest tests/test_fact_cards.py tests/test_fact_card_extractor.py tests/test_fact_card_prompt.py tests/test_fact_card_dialogs.py -q
```

Expected: PASS.

- [ ] **Step 2: Run contract and config tests**

Run:

```bash
uv run pytest tests/test_prompt_contract.py tests/test_config_schema.py tests/test_config_editor.py -q
```

Expected: PASS. `tests/test_config_editor.py` should continue preserving the top-level `fact_cards` block.

- [ ] **Step 3: Run full suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS. If unrelated failures appear, capture exact failing test names and confirm they do not come from fact-card changes before stopping.

- [ ] **Step 4: Check formatting and patch health**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Manual smoke checklist**

Run the app if GUI smoke testing is desired:

```bash
uv run python run.py
```

Manual checks:

- Open “管理事实卡片”; verify each card row can edit 作用域 and 约束.
- Save a global strong card and a local reference card.
- Generate a chapter with fact-card mode enabled; verify the global card summary appears and local cards are selectable without usage dropdowns.
- Save local selections as chapter defaults; inspect YAML and confirm defaults contain only `card_id`.
- Generate another chapter with no local defaults; verify global cards still enter prompt trace.
