from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import bid_writer.ai_writer as ai_writer_module
import bid_writer.chapter_summary_generator as summary_generator_module
from bid_writer.main import BidWriter


class DummyCompletionClient:
    calls: list[str] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    def create(self, *, messages, **kwargs):
        del kwargs
        prompt = messages[1]["content"]
        self.calls.append(prompt)
        if "第二版正文" in prompt:
            content = "第二版摘要，强调更新后的章节要点。"
        elif "第一版正文" in prompt:
            content = "第一版摘要，强调原有章节要点。"
        elif "质量保障措施" in prompt:
            content = "质量保障措施规划摘要，覆盖质量机制、职责分工与衔接关系。"
        else:
            content = "通用章节摘要。"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class DummyOpenAI:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.chat = SimpleNamespace(completions=DummyCompletionClient())


def _write_project_files(project_root: Path) -> None:
    (project_root / "outline.md").write_text(
        "\n".join(
            [
                "# 综合服务项目投标方案",
                "## 项目实施方案",
                "### 人员配置方案",
                "### 质量保障措施",
                "### 进度计划安排",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "bid_requirements.md").write_text("采购需求正文", encoding="utf-8")
    (project_root / "scoring_criteria.md").write_text("评分标准正文", encoding="utf-8")


def _write_config(config_path: Path, project_root: Path) -> None:
    config_path.write_text(
        f"""
project:
  root_dir: "{project_root}"
  bidder_name: "测试投标主体"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./bid_requirements.md"
    scoring_criteria_file: "./scoring_criteria.md"
  output_dir: "./output"

processing:
  path: "full_context"

models:
  generation:
    base_url: "https://example.com/v1"
    api_key: "test-key"
    model: "test-model"
  pruning:
    model: "test-pruning-model"

runtime:
  stream:
    enabled: false
""".strip(),
        encoding="utf-8",
    )


def _build_bid_writer(tmp_path: Path, monkeypatch) -> BidWriter:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_project_files(project_root)
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, project_root)
    monkeypatch.setattr(ai_writer_module, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(summary_generator_module, "OpenAI", DummyOpenAI)
    DummyCompletionClient.reset()
    bid_writer = BidWriter(str(config_path))
    assert bid_writer.load_outline() is True
    return bid_writer


def test_bid_writer_can_persist_and_resolve_chapter_dependencies(tmp_path: Path, monkeypatch):
    bid_writer = _build_bid_writer(tmp_path, monkeypatch)
    parser = bid_writer.parser
    assert parser is not None

    target = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 质量保障措施")
    dep_a = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 人员配置方案")
    dep_b = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 进度计划安排")
    assert target is not None
    assert dep_a is not None
    assert dep_b is not None

    bid_writer.set_chapter_dependencies(target, [dep_a, dep_b])
    resolved = bid_writer.get_dependency_headings(target)
    all_sources = bid_writer.get_all_dependency_source_headings()
    source_counts = bid_writer.get_dependency_source_usage_counts()
    source_targets = bid_writer.get_dependency_source_targets()
    target_sources = bid_writer.get_dependency_target_sources()

    assert [heading.full_path for heading in resolved] == [dep_a.full_path, dep_b.full_path]
    assert [heading.full_path for heading in all_sources] == [dep_a.full_path, dep_b.full_path]
    assert source_counts == {
        dep_a.full_path: 1,
        dep_b.full_path: 1,
    }
    assert {
        source_path: [heading.title for heading in targets]
        for source_path, targets in source_targets.items()
    } == {
        dep_a.full_path: [target.title],
        dep_b.full_path: [target.title],
    }
    assert {
        target_path: [heading.title for heading in sources]
        for target_path, sources in target_sources.items()
    } == {
        target.full_path: [dep_a.title, dep_b.title],
    }
    assert bid_writer.chapter_dependency_store.path.exists()


def test_output_summary_reuses_cache_until_section_body_changes(tmp_path: Path, monkeypatch):
    bid_writer = _build_bid_writer(tmp_path, monkeypatch)
    parser = bid_writer.parser
    assert parser is not None
    heading = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 质量保障措施")
    assert heading is not None

    bid_writer.file_saver.save(heading, "第一版正文")
    assert bid_writer.get_output_summary_status(heading) == "needs_refresh"
    summary_first = bid_writer.get_available_chapter_summary(heading)
    summary_second = bid_writer.get_available_chapter_summary(heading)

    assert summary_first is not None
    assert summary_first.source_kind == "output"
    assert summary_first.summary == "第一版摘要，强调原有章节要点。"
    assert summary_second is not None
    assert summary_second.summary == summary_first.summary
    assert bid_writer.get_output_summary_status(heading) == "up_to_date"
    assert len(DummyCompletionClient.calls) == 1

    bid_writer.file_saver.save(heading, "第二版正文", overwrite=True)
    assert bid_writer.get_output_summary_status(heading) == "needs_refresh"
    summary_third = bid_writer.get_available_chapter_summary(heading)

    assert summary_third is not None
    assert summary_third.summary == "第二版摘要，强调更新后的章节要点。"
    assert len(DummyCompletionClient.calls) == 2


def test_planned_summary_is_cached_and_reused_without_output(tmp_path: Path, monkeypatch):
    bid_writer = _build_bid_writer(tmp_path, monkeypatch)
    parser = bid_writer.parser
    assert parser is not None
    heading = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 质量保障措施")
    assert heading is not None

    summary_first = bid_writer.ensure_planned_chapter_summary(heading)
    summary_second = bid_writer.get_available_chapter_summary(heading)

    assert summary_first is not None
    assert summary_first.source_kind == "planned"
    assert "质量保障措施规划摘要" in summary_first.summary
    assert summary_second is not None
    assert summary_second.summary == summary_first.summary
    assert len(DummyCompletionClient.calls) == 1


def test_dependency_summary_block_formats_titles_and_summaries(tmp_path: Path, monkeypatch):
    bid_writer = _build_bid_writer(tmp_path, monkeypatch)
    parser = bid_writer.parser
    assert parser is not None
    heading = parser.find_heading_by_full_path("综合服务项目投标方案 > 项目实施方案 > 质量保障措施")
    assert heading is not None

    summary = bid_writer.ensure_planned_chapter_summary(heading)
    assert summary is not None

    block = bid_writer.format_dependency_summary_block([summary])

    assert "请参考以下关联章节摘要" in block
    assert f"- {heading.title}：" in block
    assert "请参考以上章节总结内容进行扩写。" in block
