import json
import shutil
from pathlib import Path

import pytest

import bid_writer.ai_writer as ai_writer_module
from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.fact_card_store import FactCardStore
from bid_writer.fact_cards import FactCardConflictError, SelectedFactCard
from bid_writer.outline_parser import parse_outline


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class DummyOpenAI:
    def __init__(self, *args, **kwargs):
        del args, kwargs


def _prepare_config_workspace(tmp_path: Path) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for fixture in FIXTURES_DIR.iterdir():
        destination = workspace / fixture.name
        if fixture.is_dir():
            shutil.copytree(fixture, destination)
        elif fixture.is_file():
            shutil.copy2(fixture, destination)

    config_path = workspace / "fact_card_prompt_config.yaml"
    config = Config(str(config_path))
    config._config.setdefault("generation_trace", {})["directory"] = str(workspace / "trace-output")
    config._config.setdefault("runtime", {}).setdefault("trace", {})["directory"] = str(workspace / "trace-output")
    config._config.setdefault("output", {})["directory"] = str(workspace / "output")
    config._config.setdefault("project", {})["output_dir"] = str(workspace / "output")
    return config


def _build_writer(monkeypatch, config: Config) -> AIWriter:
    monkeypatch.setattr(ai_writer_module, "OpenAI", DummyOpenAI)
    return AIWriter(config)


def _select_leaf_heading(config: Config, title: str):
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title(title)
    assert heading is not None
    assert not heading.children
    return heading


def test_resolve_selected_cards_fails_fast_on_strong_conflict(tmp_path: Path):
    config = _prepare_config_workspace(tmp_path)
    store = FactCardStore(config)

    with pytest.raises(FactCardConflictError) as exc_info:
        store.resolve_selected_cards(
            [
                {"card_id": "card-manager-a"},
                {"card_id": "card-manager-b"},
            ]
        )

    error = exc_info.value
    assert len(error.conflicts) == 1
    assert error.conflicts[0].normalized_name == "项目经理"
    assert {card.card_id for card in error.conflicts[0].cards} == {"card-manager-a", "card-manager-b"}


def test_fact_card_mode_prompt_includes_fact_cards(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    store = FactCardStore(config)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    selected_cards = store.resolve_chapter_prompt_cards(heading.full_path)
    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=selected_cards,
    )
    block_map = {block["id"]: block for block in result.prompt_contract_blocks}

    assert "## 事实卡片参考" in result.prompt
    assert "企业资质" in result.prompt
    assert "服务承诺" in result.prompt
    assert "## 投标方知识库" not in result.prompt
    assert block_map["fact_card_context"]["section_names"] == ["fact_card_context"]
    assert "knowledge_context" not in block_map


def test_full_context_fact_card_context_follows_task_and_scope(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    store = FactCardStore(config)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    selected_cards = store.resolve_chapter_prompt_cards(heading.full_path)
    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=selected_cards,
    )

    section_order = [section["name"] for section in result.prompt_sections]
    assert section_order.index("bid_requirements") < section_order.index("task_card")
    assert section_order.index("scoring_criteria") < section_order.index("task_card")
    assert section_order.index("task_card") < section_order.index("scope_reference")
    assert section_order.index("scope_reference") < section_order.index("fact_card_context")


def test_fact_card_mode_without_selected_cards_injects_no_fact_context(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=[],
    )
    block_map = {block["id"]: block for block in result.prompt_contract_blocks}

    assert "## 事实卡片参考" not in result.prompt
    assert "## 投标方知识库" not in result.prompt
    assert block_map["fact_card_context"]["section_names"] == []
    assert "knowledge_context" not in block_map


def test_fact_card_mode_prompt_auto_includes_global_cards_without_defaults(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "进度计划安排")

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


def test_prepare_generation_trace_context_records_fact_card_payload(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    store = FactCardStore(config)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    selected_cards = store.resolve_chapter_prompt_cards(heading.full_path)
    prepared = writer.prepare_generation(
        heading,
        target_words=1200,
        stream=False,
        fact_card_mode=True,
        selected_fact_cards=selected_cards,
    )

    assert prepared.trace_session is not None

    payload = json.loads(prepared.trace_session.artifact_paths["context_assembly"].read_text(encoding="utf-8"))

    assert payload["fact_card_mode"] is True
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


def test_fact_card_mode_disabled_ignores_selected_cards_and_trace(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path)
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    conflicting_cards = [
        {
            "card_id": "card-manager-a",
            "name": "项目经理",
            "content": "项目经理由张三担任。",
            "scope": "local",
            "enforcement": "strong",
            "source": {"type": "manual"},
        },
        {
            "card_id": "card-manager-b",
            "name": "项目经理",
            "content": "项目经理由李四担任。",
            "scope": "local",
            "enforcement": "strong",
            "source": {"type": "manual"},
        },
    ]

    selected_cards = []
    for item in conflicting_cards:
        selected_cards.append(
            SelectedFactCard(
                card_id=item["card_id"],
                name=item["name"],
                content=item["content"],
                scope=item["scope"],
                enforcement=item["enforcement"],
            )
        )

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=False,
        selected_fact_cards=selected_cards,
    )
    prepared = writer.prepare_generation(
        heading,
        target_words=1200,
        stream=False,
        fact_card_mode=False,
        selected_fact_cards=selected_cards,
    )

    assert "## 事实卡片参考" not in result.prompt
    assert result.fact_card_selection == []
    assert prepared.trace_session is not None

    payload = json.loads(prepared.trace_session.artifact_paths["context_assembly"].read_text(encoding="utf-8"))
    assert payload["fact_card_mode"] is False
    assert payload["fact_card_selection"] == []
