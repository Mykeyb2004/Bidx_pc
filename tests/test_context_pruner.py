from pathlib import Path

from bid_writer.config import Config
from bid_writer.context_pruner import ChapterContextPruner
from bid_writer.llm_verifier import ScoringClassification
from bid_writer.outline_parser import parse_outline


class FakeClassifier:
    def __init__(self):
        self.calls = []

    def classify_scoring(self, **kwargs):
        self.calls.append(kwargs)
        return ScoringClassification(
            must_respond_ids=[],
            reference_ids=[item["id"] for item in kwargs["all_scoring_items"]],
        )


def _write_auto_config(tmp_path: Path) -> Config:
    (tmp_path / "outline.md").write_text(
        "\n".join(
            [
                "# 项目",
                "## 项目分析",
                "### 政策响应",
                "#### 儿童福利政策",
                "#### 社会救助衔接",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "requirements.md").write_text("采购需求", encoding="utf-8")
    (tmp_path / "scoring.md").write_text(
        "\n".join(
            [
                "# 评分标准",
                "## 项目分析 12分",
                "对儿童福利政策、社会救助衔接和总体项目分析理解完整。",
                "",
                "## 人员配置 8分",
                "对项目负责人、固定管理人员和团队配置响应完整。",
            ]
        ),
        encoding="utf-8",
    )
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
  scoring_classify:
    cache_dir: "./cache/scoring-classify"
  hybrid_extract:
    scoring_parse_mode: "auto"
    scoring_max_rows: 4
""".strip(),
        encoding="utf-8",
    )
    return Config(str(config_path))


def test_auto_scoring_classification_cache_is_shared_by_h2(tmp_path: Path):
    config = _write_auto_config(tmp_path)
    parser = parse_outline(config.get_outline_content())
    first = parser.find_heading_by_title("儿童福利政策")
    second = parser.find_heading_by_title("社会救助衔接")
    assert first is not None and second is not None
    pruner = ChapterContextPruner(config)
    classifier = FakeClassifier()
    pruner.llm_verifier = classifier

    first_context = pruner.build_context(first)
    second_context = pruner.build_context(second)

    assert len(classifier.calls) == 1
    assert classifier.calls[0]["heading_title"] == "项目分析"
    assert classifier.calls[0]["heading_path"] == "项目 > 项目分析"
    assert [item["id"] for item in classifier.calls[0]["all_scoring_items"]] == [
        "scoring-0000",
        "scoring-0001",
    ]
    assert first_context.scoring_reference
    assert second_context.scoring_reference
    assert len(first_context.scoring_reference) == len(first_context.scoring_items)
    assert len(second_context.scoring_reference) == len(second_context.scoring_items)
    cache_files = list((tmp_path / "cache" / "scoring-classify").glob("h2_*.json"))
    assert len(cache_files) == 1
    assert not list((tmp_path / "cache" / "scoring-classify").glob("h4_*.json"))
