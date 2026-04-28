import json
from pathlib import Path

from bid_writer.config import Config
from bid_writer.h2_project_background import H2ProjectBackgroundGenerator
from bid_writer.outline_parser import parse_outline


def _write_config(tmp_path: Path, *, requirements: str = "项目需求") -> Config:
    (tmp_path / "outline.md").write_text("# 项目\n## 项目理解\n### 现状分析\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text(requirements, encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
  output_dir: "./output"

processing:
  path: "auto"
  project_background:
    enabled: true
    max_chars: 500
    h2:
      cache_dir: "./cache/h2-bg"
      max_evidence_blocks: 3
      max_evidence_chars: 1200
      min_evidence_blocks: 1
""".strip(),
        encoding="utf-8",
    )
    return Config(str(config_path))


def test_h2_generator_finds_h2_ancestor_and_collects_h2_nodes(tmp_path: Path):
    config = _write_config(tmp_path)
    parser = parse_outline(
        "# 项目\n"
        "## 项目理解\n"
        "### 现状分析\n"
        "#### 政策背景\n"
        "## 服务方案\n"
        "### 工作流程\n"
    )
    generator = H2ProjectBackgroundGenerator(config)
    leaf = parser.find_heading_by_title("政策背景")
    assert leaf is not None

    h2 = generator.find_h2_ancestor(leaf)
    h2_nodes = generator.collect_h2_nodes(parser)

    assert h2.title == "项目理解"
    assert [node.full_path for node in h2_nodes] == ["项目 > 项目理解", "项目 > 服务方案"]


def test_h2_generator_cache_key_changes_when_subtree_changes(tmp_path: Path):
    config = _write_config(tmp_path)
    generator = H2ProjectBackgroundGenerator(config)
    parser_a = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    parser_b = parse_outline("# 项目\n## 项目理解\n### 现状分析\n### 服务边界\n")
    h2_a = parser_a.find_heading_by_title("项目理解")
    h2_b = parser_b.find_heading_by_title("项目理解")
    assert h2_a is not None and h2_b is not None

    key_a = generator.cache_key_for_h2(h2_a)
    key_b = generator.cache_key_for_h2(h2_b)

    assert key_a != key_b


def test_h2_generator_writes_and_reads_json_cache(tmp_path: Path):
    config = _write_config(tmp_path)
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    h2 = parser.find_heading_by_title("项目理解")
    assert h2 is not None
    generator = H2ProjectBackgroundGenerator(config)
    result = generator.build_result(
        h2=h2,
        summary="围绕项目理解形成背景。",
        evidence_unit_ids=["requirements_0"],
        evidence_blocks=["项目需求原文"],
        cache_status="miss",
    )

    generator.write_cache(result)
    cached = generator.read_cache(h2)
    cache_files = list((tmp_path / "cache" / "h2-bg").glob("h2_*.json"))

    assert cached is not None
    assert cached.cache_status == "hit"
    assert cached.summary == "围绕项目理解形成背景。"
    assert cached.evidence_unit_ids == ["requirements_0"]
    assert cached.evidence_blocks == ["项目需求原文"]
    assert cached.h2_full_path == "项目 > 项目理解"
    assert len(cache_files) == 1
    payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["h2_full_path"] == "项目 > 项目理解"


def test_h2_background_uses_requirement_evidence_only_and_precomputes_all_h2(tmp_path: Path, monkeypatch):
    requirements = (
        "# 采购需求\n"
        "项目理解要求说明政策背景、建设目标和现状问题。\n\n"
        "项目理解还应覆盖需求边界、服务对象和项目痛点。\n\n"
        "服务方案要求说明实施流程、质量检查和交付安排。\n"
    )
    config = _write_config(tmp_path, requirements=requirements)
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 1
    config._config["processing"]["project_background"]["h2"]["max_evidence_blocks"] = 2
    parser = parse_outline(
        "# 项目\n"
        "## 项目理解\n"
        "### 现状分析\n"
        "## 服务方案\n"
        "### 实施流程\n"
    )
    generator = H2ProjectBackgroundGenerator(config)
    prompts: list[str] = []

    def fake_compute(h2, evidence_blocks):
        prompts.append("\n".join(evidence_blocks))
        return f"{h2.title}摘要：{evidence_blocks[0][:12]}"

    monkeypatch.setattr(generator, "_compute_summary", fake_compute)

    report = generator.precompute_all(parser)

    assert report.total_h2 == 2
    assert report.generated == 2
    assert report.cache_hits == 0
    assert report.failed == 0
    assert [result.h2_title for result in report.results] == ["项目理解", "服务方案"]
    assert all(result.evidence_blocks for result in report.results)
    assert any("项目理解要求" in prompt for prompt in prompts)
    assert any("服务方案要求" in prompt for prompt in prompts)


def test_h2_background_falls_back_when_evidence_is_insufficient(tmp_path: Path, monkeypatch):
    config = _write_config(tmp_path, requirements="完全无关的采购需求。")
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 2
    config._config["processing"]["project_background"]["h2"]["fallback"] = "raw_evidence"
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    h2 = parser.find_heading_by_title("项目理解")
    assert h2 is not None
    generator = H2ProjectBackgroundGenerator(config)
    monkeypatch.setattr(generator, "_compute_summary", lambda h2, evidence_blocks: "不应调用")

    result = generator.get_or_generate(h2)

    assert result.cache_status == "fallback"
    assert "证据片段不足" in result.fallback_reason
    assert result.summary == "完全无关的采购需求。"
    assert result.evidence_blocks == ["完全无关的采购需求。"]


def test_h2_background_generate_missing_false_returns_empty_fallback(tmp_path: Path):
    config = _write_config(tmp_path, requirements="项目理解要求说明政策背景。")
    config._config["processing"]["project_background"]["h2"]["generate_missing_on_single"] = False
    config._config["processing"]["project_background"]["h2"]["fallback"] = "empty"
    parser = parse_outline("# 项目\n## 项目理解\n### 现状分析\n")
    heading = parser.find_heading_by_title("现状分析")
    assert heading is not None
    generator = H2ProjectBackgroundGenerator(config)

    result = generator.get_for_heading(heading)

    assert result.cache_status == "fallback"
    assert result.summary == ""
    assert "缓存缺失" in result.fallback_reason


def test_bid_writer_precompute_h2_project_backgrounds_uses_loaded_outline(tmp_path: Path, monkeypatch):
    requirements = (
        "项目理解要求说明政策背景和现状问题。\n\n"
        "服务方案要求说明实施流程和交付安排。\n"
    )
    config = _write_config(tmp_path, requirements=requirements)
    config._config["processing"]["project_background"]["h2"]["min_evidence_blocks"] = 1
    from bid_writer.main import BidWriter

    writer = BidWriter(str(config.config_path))
    assert writer.load_outline() is True
    monkeypatch.setattr(
        writer.ai_writer.h2_project_background_generator,
        "_compute_summary",
        lambda h2, evidence_blocks: f"{h2.title}摘要",
    )

    report = writer.precompute_h2_project_backgrounds()

    assert report.total_h2 == 1
    assert report.generated == 1
    assert report.results[0].h2_title == "项目理解"
