from pathlib import Path

from bid_writer.ai_writer import AIWriter
from bid_writer.config import Config
from bid_writer.generation_trace import GenerationTraceSession
from bid_writer.outline_parser import parse_outline


def _config(tmp_path: Path, env_text: str = "") -> Config:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("project: {}\n", encoding="utf-8")
    if env_text:
        (tmp_path / ".env.local").write_text(env_text, encoding="utf-8")
    return Config(str(config_path))


def test_chapter_request_includes_configured_reasoning_effort(tmp_path: Path):
    writer = AIWriter(_config(tmp_path, "BID_WRITER_REASONING_EFFORT=minimal\n"))

    options = writer._build_request_options([], stream=False)

    assert options["reasoning_effort"] == "minimal"


def test_chapter_request_omits_reasoning_effort_when_unset(tmp_path: Path):
    writer = AIWriter(_config(tmp_path))

    options = writer._build_request_options([], stream=False)

    assert "reasoning_effort" not in options


def test_generation_trace_records_reasoning_effort(tmp_path: Path):
    config = _config(tmp_path, "BID_WRITER_REASONING_EFFORT=xhigh\n")
    heading = parse_outline("# 项目\n## 章节\n### 小节\n#### 单元\n").get_all_headings()[-1]
    session = GenerationTraceSession(
        config,
        heading,
        "",
        100,
        config.build_target_word_range(100),
        False,
        "system",
        "user",
        [],
        [],
        "full",
        None,
        {},
        False,
        [],
        {},
        {"model": "gpt-5.4", "reasoning_effort": "xhigh"},
    )

    assert session._sanitize_request_options()["reasoning_effort"] == "xhigh"


def test_invalid_outline_reasoning_effort_falls_back_to_primary_setting(tmp_path: Path):
    config = _config(
        tmp_path,
        "BID_WRITER_REASONING_EFFORT=high\n"
        "BID_WRITER_OUTLINE_REASONING_EFFORT=unsupported\n",
    )

    assert config.outline_reasoning_effort == "high"
