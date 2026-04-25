from pathlib import Path

import yaml

from bid_writer.config import Config
from bid_writer.fact_card_store import FactCardStore
from bid_writer.fact_cards import FactCardDraft, FactCardSelection, parse_bulk_fact_card_input
from bid_writer.main import BidWriter


def _build_config(tmp_path: Path, fact_cards_block: str = "") -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "outline.md").write_text(
        "# 项目\n## 技术方案\n### 质量保障措施\n### 实施方案\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            """
project:
  root_dir: "./project"
  inputs:
    outline_file: "./outline.md"
""".strip()
            + ("\n" + fact_cards_block.strip() if fact_cards_block.strip() else "")
        ),
        encoding="utf-8",
    )
    return config_path


def test_parse_bulk_fact_card_input_splits_name_and_content():
    drafts = parse_bulk_fact_card_input(
        "企业资质：具备建筑工程施工总承包一级资质\n\n服务承诺: 提供7×24小时响应\n无效行\n 项目经理 ： 张三 "
    )

    assert drafts == [
        FactCardDraft(name="企业资质", content="具备建筑工程施工总承包一级资质"),
        FactCardDraft(name="服务承诺", content="提供7×24小时响应"),
        FactCardDraft(name="项目经理", content="张三"),
    ]


def test_fact_card_store_lists_cards_and_filters_active_only(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 历史案例
      content: 近三年完成 5 个同类项目
      active: false
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    active_cards = store.list_cards()
    all_cards = store.list_cards(active_only=False)

    assert [(card.id, card.content, card.category) for card in active_cards] == [
        ("card-a", "一级资质", "资质")
    ]
    assert [card.id for card in all_cards] == ["card-a", "card-b"]


def test_fact_card_store_saves_and_reads_chapter_defaults_with_usage(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 服务承诺
      content: 7×24小时响应
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_chapter_defaults(
        "技术方案 > 质量保障措施",
        [
            FactCardSelection(card_id="card-a", usage="strong"),
            FactCardSelection(card_id="missing-card", usage="reference"),
            FactCardSelection(card_id="card-b", usage="reference"),
        ],
    )

    assert saved == [
        FactCardSelection(card_id="card-a", usage="strong"),
        FactCardSelection(card_id="card-b", usage="reference"),
    ]
    assert store.list_chapter_defaults("技术方案 > 质量保障措施") == saved

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"] == {
        "技术方案 > 质量保障措施": [
            {"card_id": "card-a", "usage": "strong"},
            {"card_id": "card-b", "usage": "reference"},
        ]
    }


def test_fact_card_store_replaces_extracted_cards_with_content_schema(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-old-a
      name: 企业资质证书
      content: 初始值
      category: 资质
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 质量保障措施
        extraction_instruction: 旧指令
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: keep-other
      name: 实施团队配置
      content: 保留
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 实施方案
        extraction_instruction: 旧指令
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: card-old-a
        usage: strong
""",
    )
    store = FactCardStore(Config(str(config_path)))

    replaced = store.replace_extracted_cards(
        "技术方案 > 质量保障措施",
        "提取可复用资质与承诺",
        [
            FactCardDraft(name="企业资质 证书", content="更新后", category="资质"),
            FactCardDraft(name="服务承诺", content="新增卡片", category="承诺"),
        ],
    )

    assert [card.id for card in replaced] == ["card-old-a", "fact-card-2"]
    assert [(card.name, card.content, card.source.type) for card in replaced] == [
        ("企业资质 证书", "更新后", "chapter_extract"),
        ("服务承诺", "新增卡片", "chapter_extract"),
    ]
    assert replaced[0].source.extraction_instruction == "提取可复用资质与承诺"
    assert replaced[0].created_at == "2026-04-24T10:00:00+00:00"
    assert replaced[0].updated_at != "2026-04-24T10:00:00+00:00"

    active_cards = store.list_cards(active_only=False)
    assert [(card.id, card.name, card.content) for card in active_cards] == [
        ("card-old-a", "企业资质 证书", "更新后"),
        ("keep-other", "实施团队配置", "保留"),
        ("fact-card-2", "服务承诺", "新增卡片"),
    ]


def test_fact_card_store_replace_extracted_cards_matches_exact_chapter_path(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 实施周期
      content: A 章节原值
      active: true
      source:
        type: chapter_extract
        chapter_path: 项目 > A > 质量保障措施
        extraction_instruction: 原指令
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 实施周期
      content: B 章节原值
      active: true
      source:
        type: chapter_extract
        chapter_path: 项目 > B > 质量保障措施
        extraction_instruction: 原指令
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    replaced = store.replace_extracted_cards(
        "项目 > A > 质量保障措施",
        "提取 A 章节事实",
        [FactCardDraft(name="实施周期", content="A 章节新值", category="进度")],
    )

    assert [(card.id, card.content, card.source.chapter_path) for card in replaced] == [
        ("card-a", "A 章节新值", "项目 > A > 质量保障措施")
    ]

    active_cards = store.list_cards(active_only=False)
    assert [(card.id, card.content, card.source.chapter_path) for card in active_cards] == [
        ("card-a", "A 章节新值", "项目 > A > 质量保障措施"),
        ("card-b", "B 章节原值", "项目 > B > 质量保障措施"),
    ]


def test_fact_card_store_replace_extracted_cards_reuses_matching_id_only_once(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-old-a
      name: 企业资质证书
      content: 原值
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 质量保障措施
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    replaced = store.replace_extracted_cards(
        "技术方案 > 质量保障措施",
        "提取资质",
        [
            FactCardDraft(name="企业资质证书", content="更新值一", category="资质"),
            FactCardDraft(name="企业资质 证书", content="更新值二", category="资质"),
        ],
    )

    assert [(card.id, card.content) for card in replaced] == [
        ("card-old-a", "更新值一"),
        ("fact-card-2", "更新值二"),
    ]

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [(item["id"], item["content"]) for item in payload["fact_cards"]["cards"]] == [
        ("card-old-a", "更新值一"),
        ("fact-card-2", "更新值二"),
    ]


def test_fact_card_store_save_preserves_unknown_fact_cards_keys(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  library_note: 保留这个字段
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    store.save_chapter_defaults(
        "技术方案 > 质量保障措施",
        [FactCardSelection(card_id="card-a", usage="strong")],
    )

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["library_note"] == "保留这个字段"


def test_save_chapter_defaults_with_empty_list_clears_chapter_key(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: card-a
        usage: strong
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_chapter_defaults("技术方案 > 质量保障措施", [])

    assert saved == []
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"].get("chapter_defaults", {}) == {}


def test_save_manual_cards_persists_manual_cards(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_manual_cards(
        [
            FactCardDraft(name="企业资质", content="一级资质", category="资质"),
            FactCardDraft(name="服务承诺", content="7×24小时响应", category="承诺"),
        ]
    )

    assert [(card.name, card.content, card.source.type) for card in saved] == [
        ("企业资质", "一级资质", "manual"),
        ("服务承诺", "7×24小时响应", "manual"),
    ]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [(item["name"], item["source"]["type"]) for item in payload["fact_cards"]["cards"]] == [
        ("企业资质", "manual"),
        ("服务承诺", "manual"),
    ]


def test_save_manual_cards_preserves_category_and_non_manual_cards(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: manual-a
      name: 企业资质
      content: 一级资质
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: extract-a
      name: 服务承诺
      content: 7×24小时响应
      category: 承诺
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 质量保障措施
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: manual-a
        usage: strong
      - card_id: extract-a
        usage: reference
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_manual_cards(
        [FactCardDraft(name="企业资质", content="一级资质", category="资质")]
    )

    assert [(card.id, card.category, card.source.type) for card in saved] == [
        ("manual-a", "资质", "manual")
    ]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [(item["id"], item["category"], item["source"]["type"]) for item in payload["fact_cards"]["cards"]] == [
        ("extract-a", "承诺", "chapter_extract"),
        ("manual-a", "资质", "manual"),
    ]
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == [
        {"card_id": "manual-a", "usage": "strong"},
        {"card_id": "extract-a", "usage": "reference"},
    ]


def test_save_manual_cards_preserves_id_when_manual_card_is_renamed(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: manual-a
      name: 企业资质
      content: 一级资质
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: manual-a
        usage: strong
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_manual_cards(
        [
            FactCardDraft(
                card_id="manual-a",
                name="企业资质证书",
                content="具备建筑工程施工总承包一级资质",
                category="资质",
            )
        ]
    )

    assert [(card.id, card.name, card.content) for card in saved] == [
        ("manual-a", "企业资质证书", "具备建筑工程施工总承包一级资质")
    ]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [(item["id"], item["name"], item["content"]) for item in payload["fact_cards"]["cards"]] == [
        ("manual-a", "企业资质证书", "具备建筑工程施工总承包一级资质")
    ]
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == [
        {"card_id": "manual-a", "usage": "strong"}
    ]


def test_resolve_generation_fact_cards_prefers_explicit_selection_over_defaults(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 服务承诺
      content: 7×24小时响应
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: card-a
        usage: strong
""",
    )
    writer = BidWriter(str(config_path))

    selected = writer.resolve_generation_fact_cards(
        "技术方案 > 质量保障措施",
        [FactCardSelection(card_id="card-b", usage="reference")],
        fact_card_mode=True,
    )

    assert [(card.card_id, card.usage) for card in selected] == [("card-b", "reference")]


def test_bid_writer_exposes_task_1_and_task_2_fact_card_apis(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
""",
    )
    writer = BidWriter(str(config_path))

    listed = writer.list_fact_cards()
    saved = writer.save_chapter_default_fact_cards(
        "技术方案 > 质量保障措施",
        [FactCardSelection(card_id="card-a", usage="strong")],
    )

    assert writer.config.fact_cards_enabled is True
    assert isinstance(writer.fact_card_store, FactCardStore)
    assert [card.id for card in listed] == ["card-a"]
    assert saved == [FactCardSelection(card_id="card-a", usage="strong")]
