import json
import shutil
from pathlib import Path

import pytest

import bid_writer.ai_writer as ai_writer_module
from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.context_pruner import ChapterContext
from bid_writer.fact_card_store import FactCardStore
from bid_writer.outline_parser import parse_outline


FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_BLOCK_IDS = [
    "system_constraints",
    "chapter_task",
    "structure_rules",
    "chapter_scope",
    "project_background",
    "fact_card_context",
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
        destination = workspace / fixture.name
        if fixture.is_dir():
            shutil.copytree(fixture, destination)
        elif fixture.is_file():
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

    result = writer.build_prompt_result(heading, target_words=900)

    assert result.prompt.strip()
    assert [block["id"] for block in result.prompt_contract_blocks] == EXPECTED_BLOCK_IDS


def test_current_prompt_config_exposes_expected_prompt_contract_blocks(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        additional_requirements="请突出质量控制节点。",
        target_words=1200,
    )

    assert [block["id"] for block in result.prompt_contract_blocks] == EXPECTED_BLOCK_IDS
    block_map = {block["id"]: block for block in result.prompt_contract_blocks}
    assert block_map["system_constraints"]["prompt_kind"] == "system"
    assert block_map["chapter_task"]["section_names"] == ["task_card", "additional_requirements"]
    assert "knowledge_context" not in block_map
    assert block_map["fact_card_context"]["section_names"] == []
    assert "source_context" in block_map["system_constraints"]


def test_fact_card_prompt_contract_exposes_fact_card_block(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "fact_card_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    store = FactCardStore(config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        fact_card_mode=True,
        selected_fact_cards=store.resolve_chapter_prompt_cards(heading.full_path),
    )

    fact_card_block = next(block for block in result.prompt_contract_blocks if block["id"] == "fact_card_context")
    assert fact_card_block["section_names"] == ["fact_card_context"]
    assert "build_fact_card_prompt_section" in fact_card_block["source_context"]


def test_extra_rules_are_folded_into_structure_contract(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)
    structure_section = next(
        section["content"]
        for section in result.prompt_sections
        if section["name"] == "structure_contract"
    )

    assert "请为以下标书章节撰写投标正文。" not in result.prompt
    assert "## 其他写作要求" not in result.prompt
    assert "请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。" in structure_section
    assert "请根据以上任务卡，结合采购需求、评分标准撰写投标正文。" in structure_section
    assert "内容要专业、严谨，符合标书撰写规范。" in structure_section
    assert (
        "- 请优先围绕当前章节任务卡、上下文材料和章节边界展开，不要偏题，不要与同级章节重复。"
        in structure_section
    )
    assert (
        "- 在满足完整响应前提下，优先提高针对性、可执行性和评审可读性，不为凑篇幅重复展开。"
        in structure_section
    )
    assert "- 篇幅目标：建议控制在 1200-1400 字，优先完整覆盖本章重点，不为凑字数重复展开。" in result.prompt
    assert "- 结构要求：默认使用正式层级序号组织正文，不要写成整篇无序号的长段落。" not in result.prompt


def test_system_prompt_keeps_global_gate_rules(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)

    system_prompt = writer.build_system_prompt()

    assert system_prompt.startswith("你是一位专业的标书撰写专家。")
    assert "【最高优先级输出强约束】" in system_prompt
    assert "投标主体统一使用“测试投标主体”表述" in system_prompt
    assert "严禁使用Markdown标题符号（#）。" in system_prompt
    assert "默认使用正式层级序号组织正文" in system_prompt
    assert "旧字段不应再进入 system prompt" not in system_prompt


def test_system_prompt_fails_fast_when_global_gate_file_missing(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    gate_file = Path(config.config_path).parent / "roles" / "system_gate_rules.md"
    gate_file.unlink()
    writer = _build_writer(monkeypatch, config)

    with pytest.raises(FileNotFoundError, match="system_gate_rules.md"):
        writer.build_system_prompt()


def test_system_prompt_ignores_legacy_gate_switches(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)

    system_prompt = writer.build_system_prompt()

    assert "严禁使用Markdown标题符号（#）。" in system_prompt
    assert "禁止输出不必要的英文、英文缩写或中英对照。" in system_prompt
    assert "旧字段不应再进入 system prompt" not in system_prompt


def test_full_context_prompt_uses_short_system_reminder_instead_of_repeating_global_rules(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。" in result.prompt
    assert "## 结构输出硬要求" not in result.prompt
    assert "本次正文默认采用显式层级结构" not in result.prompt
    assert "严禁使用Markdown标题符号（#）。" not in result.prompt


def test_user_prompt_still_keeps_task_side_extra_rules(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "请根据以上任务卡，结合采购需求、评分标准撰写投标正文。" in result.prompt
    assert "内容要专业、严谨，符合标书撰写规范。" in result.prompt
    assert "- 结构要求：默认使用正式层级序号组织正文，不要写成整篇无序号的长段落。" not in result.prompt


def test_full_context_prompt_includes_current_heading_full_path(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "- 当前章节路径：综合服务项目投标方案 > 项目实施方案 > 质量保障措施" in result.prompt
    assert (
        "- 写作依据：优先依据前文固定参考材料中的招标需求与评分标准组织内容，"
        "并严格围绕当前章节任务卡和章节边界展开。"
    ) in result.prompt
    assert "## 章节边界参考" in result.prompt
    assert "## 完整总大纲参考" not in result.prompt
    assert result.prompt.index("请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。") < result.prompt.index("## 招标需求参考")
    assert "## 投标方知识库" not in result.prompt
    assert result.prompt.index("## 评分标准参考") < result.prompt.index("## 章节任务卡")
    assert result.prompt.index("## 章节任务卡") < result.prompt.index("## 章节边界参考")


def test_prompt_ignores_deprecated_output_format_and_first_line_template(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("writing", {})["output_format"] = "Markdown格式"
    config._config.setdefault("writing", {})["first_line_template"] = "#### {title}"
    config._config.setdefault("prompt", {})["output_format"] = "旧提示词格式"
    config._config.setdefault("prompt", {})["first_line_template"] = "### {full_path}"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)
    block_map = {block["id"]: block for block in result.prompt_contract_blocks}

    assert "- 输出方式：直接写投标正文，不重复标题，不写说明性语句。" in result.prompt
    assert "按“Markdown格式”组织内容" not in result.prompt
    assert "旧提示词格式" not in result.prompt
    assert "## 首行要求" not in result.prompt
    assert "#### 质量保障措施" not in result.prompt
    assert "first_line_rule" not in block_map["structure_rules"]["section_names"]
    assert "prompt.output_format" not in block_map["chapter_task"]["source_context"]
    assert "prompt.first_line_template" not in block_map["structure_rules"]["source_context"]


def test_full_context_prompt_ignores_deprecated_knowledge_context(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "## 投标方知识库" not in result.prompt
    assert "公司名称：测试投标主体" not in result.prompt
    assert "项目经理：张三" not in result.prompt
    assert "（来源：knowledge_company.md）" not in result.prompt


def test_finalize_generation_does_not_replace_bidder_alias_inside_technical_term(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("project", {})["bidder_name"] = "杭州菲尔德咨询"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.finalize_generation(heading, "项目分析应覆盖基本单位划分原则，并明确样本单位抽取范围。")

    assert result.content == "项目分析应覆盖基本单位划分原则，并明确样本单位抽取范围。"
    assert result.postprocess["bidder_reference_normalized"] is False
    assert result.postprocess["bidder_reference_replacements"] == 0


def test_finalize_generation_still_replaces_standalone_bidder_alias(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("project", {})["bidder_name"] = "杭州菲尔德咨询"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.finalize_generation(heading, "项目组织由本单位负责统筹实施与质量控制。")

    assert result.content == "项目组织由杭州菲尔德咨询负责统筹实施与质量控制。"
    assert result.postprocess["bidder_reference_normalized"] is True
    assert result.postprocess["bidder_reference_replacements"] == 1


def test_finalize_generation_ignores_deprecated_format_switches(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("writing", {})["allow_markdown_headings"] = False
    config._config.setdefault("writing", {})["summary_title"] = ""
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.finalize_generation(heading, "## 标题\n\n一、总结\n正文内容。")

    assert "markdown_headings" not in result.postprocess["format_repair_issues"]
    assert "forbidden_summary" not in result.postprocess["format_repair_issues"]


def test_task_card_omits_mermaid_control_when_limit_is_zero(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "流程图控制" not in result.prompt


def test_task_card_includes_mermaid_control_when_limit_is_positive(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("writing", {})["max_mermaid_flowcharts_per_section"] = 3
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert (
        "- 流程图控制：生成的文档中适当绘制不超过3个Mermaid图示，用于呈现关键流程、步骤衔接、角色协作或机制闭环；"
        "必须使用```mermaid代码块，可按内容需要选择合适的 Mermaid 图类型，图内文案保持简洁。"
    ) in result.prompt


def test_runtime_mermaid_override_can_disable_configured_prompt_rule(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("writing", {})["max_mermaid_flowcharts_per_section"] = 3
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(
        heading,
        target_words=1200,
        max_mermaid_flowcharts_per_section_override=0,
    )

    assert "流程图控制" not in result.prompt


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
        {
            "get_or_generate": staticmethod(
                lambda _heading, *, system_prompt, shared_prompt_prefix, scope_reference: (
                    "1. 先回应项目目标。\n2. 再回应质量评分点。"
                )
            )
        },
    )()
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "- 章节写作计划：" in result.prompt
    assert "1. 先回应项目目标。" in result.prompt
    assert "2. 再回应质量评分点。" in result.prompt


def test_full_context_chapter_writing_plan_uses_shared_prefix_layout(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {}).setdefault("full_context", {}).setdefault(
        "chapter_writing_plan",
        {},
    )["enabled"] = True
    writer = _build_writer(monkeypatch, config)

    captured: dict[str, str] = {}

    class DummyPlanGenerator:
        @staticmethod
        def get_or_generate(_heading, *, system_prompt, shared_prompt_prefix, scope_reference):
            captured["system_prompt"] = system_prompt
            captured["shared_prompt_prefix"] = shared_prompt_prefix
            captured["scope_reference"] = scope_reference
            return "1. 先回应采购需求。\n2. 再逐条覆盖评分关注。"

    writer.chapter_writing_plan_generator = DummyPlanGenerator()

    heading = _select_leaf_heading(config, "质量保障措施")
    result = writer.build_prompt_result(heading, target_words=1200)

    assert captured["system_prompt"] == writer.build_system_prompt()
    assert captured["shared_prompt_prefix"].startswith("请严格遵守 system 中全部硬门禁，直接输出当前章节投标正文。")
    assert "## 投标方知识库" not in captured["shared_prompt_prefix"]
    assert "## 项目背景" not in captured["shared_prompt_prefix"]
    assert "## 招标需求参考" in captured["shared_prompt_prefix"]
    assert "## 评分标准参考" in captured["shared_prompt_prefix"]
    assert "## 章节边界参考" not in captured["shared_prompt_prefix"]
    assert captured["scope_reference"].startswith("## 章节边界参考")
    assert result.prompt.startswith(captured["shared_prompt_prefix"])
    assert result.prompt.index("## 章节任务卡") > result.prompt.index("## 评分标准参考")
    assert result.prompt.index("## 章节边界参考") > result.prompt.index("## 章节任务卡")


def test_trace_context_payload_contains_prompt_contract_and_prompt_sections(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    prepared = writer.prepare_generation(
        heading,
        additional_requirements="请保持条理清晰。",
        target_words=1200,
        stream=False,
    )

    assert prepared.trace_session is not None

    context_payload_path = prepared.trace_session.artifact_paths["context_assembly"]
    payload = json.loads(context_payload_path.read_text(encoding="utf-8"))
    heading_payload = json.loads(prepared.trace_session.artifact_paths["heading"].read_text(encoding="utf-8"))

    assert "prompt_contract" in payload
    assert "prompt_sections" in payload
    assert payload["prompt_contract"]["block_order"] == EXPECTED_BLOCK_IDS
    assert [block["id"] for block in payload["prompt_contract"]["blocks"]] == EXPECTED_BLOCK_IDS
    block_map = {block["id"]: block for block in payload["prompt_contract"]["blocks"]}
    assert "knowledge_context" not in block_map
    assert block_map["fact_card_context"]["section_names"] == []
    assert block_map["system_constraints"]["source_context"]
    assert heading_payload["target_words"] == 1200
    assert heading_payload["target_word_range"] == {"baseline": 1200, "lower": 1200, "upper": 1400}


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

    prepared = writer.prepare_generation(heading, target_words=1200, stream=False)

    assert prepared.trace_session is not None

    prepared.trace_session.finalize("测试正文")
    summary = prepared.trace_session.artifact_paths["summary"].read_text(encoding="utf-8")

    assert f"- processing_path: {processing_path}" in summary
    assert "- target_word_range: 1200-1400" in summary


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
            chapter_focus_terms=["质量保障措施"],
            requirement_brief="1. 建立质量检查机制。\n2. 强化过程留痕。",
            requirement_brief_status="extracted",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "- 写作依据：优先根据下方评分关注和需求要点组织内容。" in result.prompt
    assert "## 需求要点" in result.prompt
    assert "## 需求原文摘录" not in result.prompt


def test_auto_prompt_uses_h2_project_background(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "auto"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    monkeypatch.setattr(
        writer.context_pruner,
        "build_context",
        lambda _: ChapterContext(
            chapter_focus_terms=["质量保障措施"],
            requirement_seed="质量保障应建立过程检查机制。",
            retrieval_mode="path=auto;vector=off;classify=off",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    class DummyH2BackgroundGenerator:
        @staticmethod
        def get_for_heading(_heading):
            from bid_writer.h2_project_background import H2ProjectBackgroundResult

            return H2ProjectBackgroundResult(
                h2_title="项目实施方案",
                h2_full_path="综合服务项目投标方案 > 项目实施方案",
                summary="H2专属背景摘要。",
                evidence_unit_ids=["requirements_0"],
                evidence_blocks=["采购需求证据片段"],
                source_hash="source",
                subtree_hash="tree",
                cache_status="hit",
                precomputed=True,
            )

    writer.h2_project_background_generator = DummyH2BackgroundGenerator()
    writer.project_background_generator = type(
        "DummyGlobalBackground",
        (),
        {"get_or_generate": staticmethod(lambda: "全局背景不应进入 auto h2 prompt。")},
    )()

    result = writer.build_prompt_result(heading, target_words=1200)

    assert "## 项目背景" in result.prompt
    assert "H2专属背景摘要。" in result.prompt
    assert "全局背景不应进入 auto h2 prompt。" not in result.prompt
    block = next(block for block in result.prompt_contract_blocks if block["id"] == "project_background")
    assert "H2ProjectBackgroundGenerator.get_for_heading" in block["source_context"]
    assert result.project_background_trace["h2_title"] == "项目实施方案"
    assert result.project_background_trace["cache_status"] == "hit"


def test_full_context_prompt_skips_project_background_even_when_configured(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "full_context"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)

    calls: list[str] = []

    writer.project_background_generator = type(
        "DummyGlobalBackground",
        (),
        {"get_or_generate": staticmethod(lambda: calls.append("called") or "全局项目背景摘要。")},
    )()
    heading = _select_leaf_heading(config, "质量保障措施")

    result = writer.build_prompt_result(heading, target_words=1200)

    assert calls == []
    assert "## 项目背景" not in result.prompt
    assert "全局项目背景摘要。" not in result.prompt
    block = next(block for block in result.prompt_contract_blocks if block["id"] == "project_background")
    assert block["section_names"] == []
    assert result.project_background_trace == {}


def test_trace_records_h2_project_background_evidence(monkeypatch, tmp_path):
    config = _prepare_config_workspace(tmp_path, "current_prompt_config.yaml")
    config._config.setdefault("processing", {})["path"] = "auto"
    config._config.setdefault("processing", {}).setdefault("project_background", {})["enabled"] = True
    config._config["processing"]["project_background"]["scope"] = "h2_auto"
    writer = _build_writer(monkeypatch, config)
    heading = _select_leaf_heading(config, "质量保障措施")

    monkeypatch.setattr(
        writer.context_pruner,
        "build_context",
        lambda _: ChapterContext(
            chapter_focus_terms=["质量保障措施"],
            requirement_seed="质量保障应建立过程检查机制。",
            requirement_blocks=[],
            retrieval_mode="path=auto;vector=off;classify=off",
        ),
    )
    monkeypatch.setattr(writer.context_pruner, "dump_debug", lambda *args, **kwargs: None)

    class DummyH2BackgroundGenerator:
        @staticmethod
        def get_for_heading(_heading):
            from bid_writer.h2_project_background import H2ProjectBackgroundResult

            return H2ProjectBackgroundResult(
                h2_title="项目实施方案",
                h2_full_path="综合服务项目投标方案 > 项目实施方案",
                summary="H2专属背景摘要。",
                evidence_unit_ids=["requirements_7"],
                evidence_blocks=["采购需求证据片段"],
                source_hash="source",
                subtree_hash="tree",
                cache_status="hit",
                precomputed=True,
            )

    writer.h2_project_background_generator = DummyH2BackgroundGenerator()

    prepared = writer.prepare_generation(heading, target_words=1200, stream=False)
    assert prepared.trace_session is not None
    prepared.trace_session.finalize("测试正文")

    context_payload = json.loads(
        prepared.trace_session.artifact_paths["context_assembly"].read_text(encoding="utf-8")
    )
    summary = prepared.trace_session.artifact_paths["summary"].read_text(encoding="utf-8")

    assert context_payload["project_background"]["scope"] == "h2"
    assert context_payload["project_background"]["h2_title"] == "项目实施方案"
    assert context_payload["project_background"]["evidence_unit_ids"] == ["requirements_7"]
    assert context_payload["project_background"]["evidence_blocks"] == ["采购需求证据片段"]
    assert "- project_background_scope: h2" in summary
    assert "- project_background_h2: 项目实施方案" in summary
    assert "- project_background_evidence_blocks: 1" in summary
    assert "- project_background_cache_status: hit" in summary
