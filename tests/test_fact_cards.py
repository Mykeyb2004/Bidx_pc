from pathlib import Path

import yaml

from bid_writer.config import Config
from bid_writer.fact_card_store import FactCardStore
from bid_writer.fact_cards import (
    FactCard,
    FactCardDraft,
    FactCardSelection,
    FactCardSource,
    SelectedFactCard,
    build_fact_card_prompt_section,
    detect_strong_fact_card_conflicts,
    parse_bulk_fact_card_input,
)
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


def test_fact_card_prompt_includes_usage_rules():
    cards = [
        SelectedFactCard(
            card_id="local-reference",
            name="统计指标",
            content="文化统计指标体系采用五维矩阵结构。",
            scope="local",
            enforcement="reference",
        ),
    ]

    section = build_fact_card_prompt_section(cards)

    assert "若事实卡片与采购需求或评分标准冲突，以采购需求和评分标准为准。" in section
    assert "参考事实只在与当前章节标题、评分关注或项目背景直接相关时吸收" in section
    assert "不要照搬来源章节中的“本章节”“本文”“上述内容”等指代" in section


def test_fact_card_prompt_strips_meta_opening_for_legacy_cards():
    cards = [
        SelectedFactCard(
            card_id="local-reference",
            name="统计指标",
            content="本章节明确文化统计指标体系采用五维矩阵结构。",
            scope="local",
            enforcement="reference",
        ),
    ]

    section = build_fact_card_prompt_section(cards)

    assert "- [局部] 统计指标：文化统计指标体系采用五维矩阵结构。" in section
    assert "- [局部] 统计指标：本章节明确" not in section


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
      scope: local
      enforcement: reference
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 历史案例
      content: 近三年完成 5 个同类项目
      scope: local
      enforcement: reference
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


def test_fact_card_store_reads_tracked_statistics_config_cards(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: fact-card-2
      name: 文化统计指标体系
      content: 文化领域统计指标体系采用机构运行、业务产出、市场消费、资金投入、人员配置五大维度。
      scope: local
      enforcement: strong
      active: true
      source:
        type: chapter_extract
        chapter_path: 项目 > 技术方案 > 质量保障措施
      category: 指标
      created_at: "2026-04-27T07:18:32+00:00"
      updated_at: "2026-04-27T07:18:32+00:00"
""",
    )
    store = FactCardStore(Config(str(config_path)))

    cards = store.list_cards(active_only=False)

    assert [card.id for card in cards] == ["fact-card-2"]
    assert [(card.scope, card.enforcement) for card in cards] == [
        ("local", "strong"),
    ]


def test_fact_card_store_saves_and_reads_chapter_defaults_with_card_ids(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: card-a
      name: 企业资质
      content: 一级资质
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
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
            FactCardSelection(card_id="card-a"),
            FactCardSelection(card_id="missing-card"),
            FactCardSelection(card_id="card-b"),
        ],
    )

    assert saved == [
        FactCardSelection(card_id="card-a"),
        FactCardSelection(card_id="card-b"),
    ]
    assert store.list_chapter_defaults("技术方案 > 质量保障措施") == saved

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"] == {
        "技术方案 > 质量保障措施": {
            "should_reference": True,
            "selections": [
                {"card_id": "card-a"},
                {"card_id": "card-b"},
            ],
        }
    }


def test_fact_card_store_saves_chapter_reference_state_without_cards(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards: []
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_chapter_defaults(
        "技术方案 > 质量保障措施",
        [],
        should_reference_fact_cards=True,
    )

    assert saved == []
    state = store.get_chapter_default_state("技术方案 > 质量保障措施")
    assert state.should_reference_fact_cards is True
    assert state.selections == []

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"] == {
        "技术方案 > 质量保障措施": {
            "should_reference": True,
            "selections": [],
        }
    }


def test_resolve_chapter_prompt_cards_respects_saved_disabled_reference_state(tmp_path: Path):
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
        [FactCardSelection(card_id="local-a")],
        should_reference_fact_cards=False,
    )

    assert saved == [FactCardSelection(card_id="local-a")]
    state = store.get_chapter_default_state("技术方案 > 质量保障措施")
    assert state.should_reference_fact_cards is False
    assert state.selections == [FactCardSelection(card_id="local-a")]
    assert store.resolve_chapter_prompt_cards("技术方案 > 质量保障措施") == []

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == {
        "should_reference": False,
        "selections": [{"card_id": "local-a"}],
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
      scope: local
      enforcement: reference
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
      scope: local
      enforcement: reference
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
""",
    )
    store = FactCardStore(Config(str(config_path)))

    replaced = store.replace_extracted_cards(
        "技术方案 > 质量保障措施",
        "提取可复用资质与承诺",
        [
            FactCardDraft(name="企业资质 证书", content="更新后", category="资质", scope="local", enforcement="reference"),
            FactCardDraft(name="服务承诺", content="新增卡片", category="承诺", scope="local", enforcement="reference"),
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
      scope: local
      enforcement: reference
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
      scope: local
      enforcement: reference
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
        [FactCardDraft(name="实施周期", content="A 章节新值", category="进度", scope="local", enforcement="reference")],
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
      scope: local
      enforcement: reference
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
            FactCardDraft(name="企业资质证书", content="更新值一", category="资质", scope="local", enforcement="reference"),
            FactCardDraft(name="企业资质 证书", content="更新值二", category="资质", scope="local", enforcement="reference"),
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
      scope: local
      enforcement: reference
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
        [FactCardSelection(card_id="card-a")],
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
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: card-a
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
            FactCardDraft(name="企业资质", content="一级资质", category="资质", scope="local", enforcement="reference"),
            FactCardDraft(name="服务承诺", content="7×24小时响应", category="承诺", scope="local", enforcement="reference"),
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


def test_save_manual_cards_skips_direct_drafts_without_scope_and_enforcement(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_manual_cards([FactCardDraft(name="企业资质", content="一级资质")])

    assert saved == []
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["cards"] == []


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
      scope: local
      enforcement: reference
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: extract-a
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
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
      - card_id: extract-a
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_manual_cards(
        [FactCardDraft(name="企业资质", content="一级资质", category="资质", scope="local", enforcement="reference")]
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
        {"card_id": "manual-a"},
        {"card_id": "extract-a"},
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
      scope: local
      enforcement: reference
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: manual-a
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
                scope="local",
                enforcement="reference",
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
        {"card_id": "manual-a"}
    ]


def test_save_library_cards_updates_existing_cards_and_preserves_sources(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: manual-a
      name: 企业资质
      content: 一级资质
      scope: local
      enforcement: reference
      category: 资质
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: extract-a
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
      category: 承诺
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 质量保障措施
        extraction_instruction: 提炼承诺
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: manual-a
      - card_id: extract-a
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_library_cards(
        [
            FactCardDraft(
                card_id="manual-a",
                name="企业资质证书",
                content="具备建筑工程施工总承包一级资质",
                category="资质证书",
                scope="local",
                enforcement="reference",
            ),
            FactCardDraft(
                card_id="extract-a",
                name="服务响应承诺",
                content="提供 7×24 小时响应支持",
                category="服务承诺",
                scope="local",
                enforcement="reference",
            ),
            FactCardDraft(name="项目经理", content="项目经理由张三担任", category="人员团队", scope="local", enforcement="reference"),
        ]
    )

    assert [(card.id, card.name, card.content, card.source.type) for card in saved] == [
        ("manual-a", "企业资质证书", "具备建筑工程施工总承包一级资质", "manual"),
        ("extract-a", "服务响应承诺", "提供 7×24 小时响应支持", "chapter_extract"),
        ("fact-card-3", "项目经理", "项目经理由张三担任", "manual"),
    ]

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [
        (item["id"], item["name"], item["content"], item["category"], item["source"]["type"])
        for item in payload["fact_cards"]["cards"]
    ] == [
        ("manual-a", "企业资质证书", "具备建筑工程施工总承包一级资质", "资质证书", "manual"),
        ("extract-a", "服务响应承诺", "提供 7×24 小时响应支持", "服务承诺", "chapter_extract"),
        ("fact-card-3", "项目经理", "项目经理由张三担任", "人员团队", "manual"),
    ]
    assert payload["fact_cards"]["cards"][1]["source"]["chapter_path"] == "技术方案 > 质量保障措施"
    assert payload["fact_cards"]["cards"][1]["source"]["extraction_instruction"] == "提炼承诺"
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == [
        {"card_id": "manual-a"},
        {"card_id": "extract-a"},
    ]


def test_save_library_card_updates_single_card_source_instruction(tmp_path: Path):
    config_path = _build_config(
        tmp_path,
        """
fact_cards:
  enabled: true
  cards:
    - id: manual-a
      name: 企业资质
      content: 一级资质
      scope: global
      enforcement: strong
      category: 资质
      active: true
      source:
        type: manual
    - id: extract-a
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
      category: 承诺
      active: true
      source:
        type: chapter_extract
        chapter_path: 技术方案 > 质量保障措施
        extraction_instruction: 提炼承诺
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: extract-a
""",
    )
    store = FactCardStore(Config(str(config_path)))

    saved = store.save_library_card(
        FactCardDraft(
            card_id="extract-a",
            name="服务响应承诺",
            content="提供 7×24 小时响应支持",
            category="服务承诺",
            scope="local",
            enforcement="strong",
        ),
        source=FactCardSource(
            type="chapter_extract",
            chapter_path="技术方案 > 质量保障措施",
            extraction_instruction="重新提炼服务承诺",
        ),
    )

    assert [(card.id, card.name, card.source.extraction_instruction) for card in saved] == [
        ("manual-a", "企业资质", ""),
        ("extract-a", "服务响应承诺", "重新提炼服务承诺"),
    ]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [
        (item["id"], item["name"], item["source"]["type"], item["source"].get("chapter_path"), item["source"].get("extraction_instruction"))
        for item in payload["fact_cards"]["cards"]
    ] == [
        ("manual-a", "企业资质", "manual", None, None),
        ("extract-a", "服务响应承诺", "chapter_extract", "技术方案 > 质量保障措施", "重新提炼服务承诺"),
    ]
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == [{"card_id": "extract-a"}]


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
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
    - id: card-b
      name: 服务承诺
      content: 7×24小时响应
      scope: local
      enforcement: reference
      active: true
      source:
        type: manual
      created_at: "2026-04-24T10:00:00+00:00"
      updated_at: "2026-04-24T10:00:00+00:00"
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: card-a
""",
    )
    writer = BidWriter(str(config_path))

    selected = writer.resolve_generation_fact_cards(
        "技术方案 > 质量保障措施",
        [FactCardSelection(card_id="card-b")],
        fact_card_mode=True,
    )

    assert [(card.card_id, card.scope, card.enforcement) for card in selected] == [("card-b", "local", "reference")]


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
      scope: local
      enforcement: reference
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
        [FactCardSelection(card_id="card-a")],
    )

    assert writer.config.fact_cards_enabled is True
    assert isinstance(writer.fact_card_store, FactCardStore)
    assert [card.id for card in listed] == ["card-a"]
    assert saved == [FactCardSelection(card_id="card-a")]


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


def test_resolve_chapter_prompt_cards_respects_saved_global_exclusions(tmp_path: Path):
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
    - id: global-b
      name: 服务边界
      content: 不转包
      scope: global
      enforcement: reference
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
  chapter_defaults:
    技术方案 > 质量保障措施:
      - card_id: global-a
        selected: false
      - card_id: local-a
""",
    )
    store = FactCardStore(Config(str(config_path)))

    selected = store.resolve_chapter_prompt_cards("技术方案 > 质量保障措施")

    assert [(card.card_id, card.scope) for card in selected] == [
        ("global-b", "global"),
        ("local-a", "local"),
    ]
    assert store.list_chapter_defaults("技术方案 > 质量保障措施") == [
        FactCardSelection(card_id="global-a", selected=False),
        FactCardSelection(card_id="local-a"),
    ]


def test_manual_generation_selections_can_exclude_global_cards(tmp_path: Path):
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

    selected = store.resolve_chapter_prompt_cards(
        "技术方案 > 质量保障措施",
        [
            FactCardSelection(card_id="global-a", selected=False),
            FactCardSelection(card_id="local-a"),
        ],
    )

    assert [(card.card_id, card.scope) for card in selected] == [
        ("local-a", "local"),
    ]


def test_save_chapter_defaults_keeps_global_exclusions_and_local_selections(tmp_path: Path):
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
        [
            FactCardSelection(card_id="global-a", selected=False),
            FactCardSelection(card_id="local-a"),
        ],
    )

    assert saved == [
        FactCardSelection(card_id="global-a", selected=False),
        FactCardSelection(card_id="local-a"),
    ]
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["fact_cards"]["chapter_defaults"]["技术方案 > 质量保障措施"] == {
        "should_reference": True,
        "selections": [
            {"card_id": "global-a", "selected": False},
            {"card_id": "local-a"},
        ],
    }
