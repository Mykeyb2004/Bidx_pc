import json
import shutil
from pathlib import Path

import pytest

import bid_writer.ai_writer as ai_writer_module
from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.context_pruner import ChapterContext
from bid_writer.outline_parser import parse_outline


FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_BLOCK_IDS = [
    "system_constraints",
    "chapter_task",
    "structure_rules",
    "chapter_scope",
    "requirement_context",
    "scoring_context",
]


class DummyOpenAI:
    def __init__(self, *args, **kwargs):
        del args, kwargs


def _prepare_config_workspace(tmp_path: Path, config_name: str) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for fixture in FIXTURES_DIR.iterdir():
        if fixture.is_file():
            shutil.copy2(fixture, workspace / fixture.name)

    config_path = workspace / config_name
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


def test_legacy_prompt_config_builds_non_empty_prompt(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "legacy_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, min_words=900)

    assert result.prompt.strip()
    assert [block["id"] for block in result.prompt_contract_blocks] == EXPECTED_BLOCK_IDS


def test_current_prompt_config_exposes_expected_prompt_contract_blocks(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        additional_requirements="请突出质量控制节点。",
        min_words=1200,
    )

    assert [block["id"] for block in result.prompt_contract_blocks] == EXPECTED_BLOCK_IDS
    assert result.prompt_contract_blocks[0]["prompt_kind"] == "system"
    assert result.prompt_contract_blocks[1]["section_names"] == ["task_card", "additional_requirements"]
    assert "source_context" in result.prompt_contract_blocks[0]


def test_full_context_prompt_includes_current_heading_full_path(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, min_words=1200)

    assert "- 当前章节路径：综合服务项目投标方案 > 项目实施方案 > 质量保障措施" in result.prompt
    assert "## 章节边界参考" in result.prompt
    assert "## 完整总大纲参考" not in result.prompt


def test_full_context_prompt_can_include_chapter_writing_plan(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {}).setdefault("full_context", {}).setdefault(
        "chapter_writing_plan",
        {},
    )["enabled"] = True
    writer = _build_writer(monkeypatch, config)
    writer.chapter_writing_plan_generator = type(
        "DummyPlanGenerator",
        (),
        {"get_or_generate": staticmethod(lambda _heading, _scope: "1. 先回应项目目标。\n2. 再回应质量评分点。")},
    )()
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, min_words=1200)

    assert "- 章节写作计划：" in result.prompt
    assert "1. 先回应项目目标。" in result.prompt
    assert "2. 再回应质量评分点。" in result.prompt


def test_trace_context_payload_contains_prompt_contract_and_prompt_sections(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    prepared = writer.prepare_generation(
        heading,
        additional_requirements="请保持条理清晰。",
        min_words=1200,
        stream=False,
    )

    assert prepared.trace_session is not None

    context_payload_path = prepared.trace_session.artifact_paths["context_assembly"]
    payload = json.loads(context_payload_path.read_text(encoding="utf-8"))

    assert "prompt_contract" in payload
    assert "prompt_sections" in payload
    assert payload["prompt_contract"]["block_order"] == EXPECTED_BLOCK_IDS
    assert [block["id"] for block in payload["prompt_contract"]["blocks"]] == EXPECTED_BLOCK_IDS
    assert payload["prompt_contract"]["blocks"][0]["source_context"]


@pytest.mark.parametrize("processing_path", ["full_context", "legacy_rule", "hybrid_extract"])
def test_trace_summary_records_processing_path(monkeypatch, tmp_path, processing_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = processing_path
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    if processing_path != "full_context":
        monkeypatch.setattr(
            writer.context_pruner,
            "build_context",
            lambda _: ChapterContext(
                chapter_focus_terms=["质量保障措施"],
                retrieval_mode=f"path={processing_path};vector=off;verify=off",
            ),
        )
        monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    prepared = writer.prepare_generation(heading, min_words=1200, stream=False)

    assert prepared.trace_session is not None

    prepared.trace_session.finalize("测试正文")
    summary = prepared.trace_session.artifact_paths["summary"].read_text(encoding="utf-8")

    assert f"- processing_path: {processing_path}" in summary


def test_requirement_brief_prompt_uses_requirement_points_wording(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "legacy_rule"
    config._config.setdefault("context_pruning", {})["enabled"] = True
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    monkeypatch.setattr(
        writer.context_pruner,
        "build_context",
        lambda _: ChapterContext(
            local_outline="# 综合服务项目投标方案\n## 项目实施方案\n### 质量保障措施",
            chapter_focus_terms=["质量保障措施"],
            requirement_brief="1. 建立质量检查机制。\n2. 强化过程留痕。",
            requirement_brief_status="extracted",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    result = writer.build_prompt_result(heading, min_words=1200)

    assert "- 写作依据：优先根据下方评分关注和需求要点组织内容。" in result.prompt
    assert "## 需求要点" in result.prompt
    assert "## 需求原文摘录" not in result.prompt
