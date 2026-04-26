from pathlib import Path

from bid_writer.config import Config
from bid_writer.fact_card_extractor import FactCardExtractor
from bid_writer.fact_cards import FactCardDraft
from bid_writer.main import BidWriter
from bid_writer.outline_parser import parse_outline


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeEmptyResponse:
    def __init__(self):
        self.choices = []


class _FakeCompletions:
    def __init__(self, content: str):
        self.calls: list[dict] = []
        self.content = content

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.content)


class _FailingCompletions:
    def create(self, **kwargs):
        del kwargs
        raise RuntimeError("mock timeout")


class _FakeChat:
    def __init__(self, completions: _FakeCompletions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions: _FakeCompletions):
        self.chat = _FakeChat(completions)


class _FakeFileSaver:
    def __init__(self, filepath: Path, content: str):
        self.filepath = filepath
        self.content = content

    def find_existing_filepath(self, heading):
        return self.filepath

    def load_section_body(self, filepath: Path, title: str | None = None) -> str:
        assert filepath == self.filepath
        return self.content


def _build_config(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    output_root = tmp_path / "output"
    project_root.mkdir()
    output_root.mkdir()
    (project_root / "outline.md").write_text(
        "# 项目\n## 技术方案\n### 质量保障措施\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "./project"
  inputs:
    outline_file: "./outline.md"
output:
  directory: "./output"
fact_cards:
  enabled: true
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _get_heading(config: Config, title: str):
    parser = parse_outline(config.get_outline_content())
    heading = parser.find_heading_by_title(title)
    assert heading is not None
    return heading


def test_fact_card_extractor_builds_prompt_with_heading_context_and_parses_json(tmp_path: Path):
    config_path = _build_config(tmp_path)
    config = Config(str(config_path))
    heading = _get_heading(config, "质量保障措施")
    output_path = tmp_path / "output" / "quality.md"
    output_path.write_text("已生成正文", encoding="utf-8")
    completions = _FakeCompletions(
        '[{"name":"项目经理","content":"张三，5年经验","category":"人员","scope":"global","enforcement":"strong"},'
        '{"name":"服务承诺","content":"7×24小时响应","category":"承诺","scope":"local","enforcement":"reference"}]'
    )
    extractor = FactCardExtractor(
        config=config,
        file_saver=_FakeFileSaver(output_path, "项目经理由张三担任。\n服务承诺为7×24小时响应。"),
    )
    extractor._get_client_and_model = lambda: (_FakeClient(completions), "mock-model")

    drafts = extractor.extract_from_output(heading, "提取能直接复用到其他章节的事实卡片")

    assert drafts == [
        FactCardDraft(
            name="项目经理",
            content="张三，5年经验",
            category="人员",
            scope="global",
            enforcement="strong",
        ),
    ]
    request = completions.calls[0]
    assert request["model"] == "mock-model"
    prompt = request["messages"][1]["content"]
    assert "章节标题：质量保障措施" in prompt
    assert f"章节路径：{heading.full_path}" in prompt
    assert "用户要求：提取能直接复用到其他章节的事实卡片" in prompt
    assert "只输出 1 张事实卡片" in prompt
    assert "每项字段必须包含：name、content、scope、enforcement" in prompt
    assert "scope 只能是 global 或 local" in prompt
    assert "enforcement 只能是 strong 或 reference" in prompt
    assert "最能代表本章节核心内容" in prompt
    assert "章节正文：" in prompt
    assert "项目经理由张三担任" in prompt


def test_fact_card_extractor_rejects_missing_scope_or_enforcement():
    result = FactCardExtractor.parse_draft_response_with_diagnostics(
        '[{"name":"企业资质","content":"一级资质","category":"资质"}]'
    )

    assert result.drafts == []
    assert result.message == "模型返回了数组，但没有包含可保存的事实卡片。"
    assert "scope" in result.detail
    assert "enforcement" in result.detail


def test_fact_card_extractor_parse_json_array_response_filters_invalid_items():
    drafts = FactCardExtractor.parse_draft_response(
        '[{"name":" 企业资质 ","content":" 一级资质 ","category":"资质","scope":"global","enforcement":"strong"},'
        '{"name":"服务承诺","content":"7×24小时响应"},{"name":"","content":"忽略"},{"title":"无效"}]'
    )

    assert drafts == [
        FactCardDraft(
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        )
    ]


def test_fact_card_extractor_parse_json_code_fence_response():
    drafts = FactCardExtractor.parse_draft_response(
        "```json\n[{\"name\":\"企业资质\",\"content\":\"一级资质\",\"category\":\"资质\",\"scope\":\"global\",\"enforcement\":\"strong\"}]\n```"
    )

    assert drafts == [
        FactCardDraft(
            name="企业资质",
            content="一级资质",
            category="资质",
            scope="global",
            enforcement="strong",
        )
    ]


def test_fact_card_extractor_returns_empty_on_missing_response_content(tmp_path: Path):
    config_path = _build_config(tmp_path)
    config = Config(str(config_path))
    heading = _get_heading(config, "质量保障措施")
    output_path = tmp_path / "output" / "quality.md"
    output_path.write_text("已生成正文", encoding="utf-8")

    class _EmptyCompletions:
        def create(self, **kwargs):
            del kwargs
            return _FakeEmptyResponse()

    extractor = FactCardExtractor(
        config=config,
        file_saver=_FakeFileSaver(output_path, "项目经理由张三担任。"),
    )
    extractor._get_client_and_model = lambda: (_FakeClient(_EmptyCompletions()), "mock-model")

    assert extractor.extract_from_output(heading, "提取事实") == []


def test_fact_card_extractor_reports_api_exception_details(tmp_path: Path):
    config_path = _build_config(tmp_path)
    config = Config(str(config_path))
    heading = _get_heading(config, "质量保障措施")
    output_path = tmp_path / "output" / "quality.md"
    output_path.write_text("已生成正文", encoding="utf-8")
    extractor = FactCardExtractor(
        config=config,
        file_saver=_FakeFileSaver(output_path, "项目经理由张三担任。"),
    )
    extractor._get_client_and_model = lambda: (_FakeClient(_FailingCompletions()), "mock-model")

    result = extractor.extract_from_output_with_diagnostics(heading, "提取事实")

    assert result.drafts == []
    assert result.message == "调用模型提炼事实卡片失败。"
    assert "RuntimeError: mock timeout" in result.detail


def test_fact_card_extractor_reports_invalid_json_response_excerpt():
    result = FactCardExtractor.parse_draft_response_with_diagnostics("我无法提取事实卡片")

    assert result.drafts == []
    assert result.message == "模型返回不是合法 JSON，无法解析事实卡片。"
    assert "解析错误" in result.detail
    assert result.raw_response_excerpt == "我无法提取事实卡片"


def test_bid_writer_extracts_fact_card_drafts_from_output(tmp_path: Path):
    config_path = _build_config(tmp_path)
    writer = BidWriter(str(config_path))
    heading = _get_heading(writer.config, "质量保障措施")
    calls: list[tuple[object, str]] = []

    class _StubExtractor:
        def extract_from_output(self, heading_arg, instruction: str = ""):
            calls.append((heading_arg, instruction))
            return [
                FactCardDraft(
                    name="项目经理",
                    content="张三",
                    category="人员",
                    scope="global",
                    enforcement="strong",
                )
            ]

    writer.fact_card_extractor = _StubExtractor()

    drafts = writer.extract_fact_card_drafts_from_output(heading, "提取项目人员")

    assert drafts == [
        FactCardDraft(
            name="项目经理",
            content="张三",
            category="人员",
            scope="global",
            enforcement="strong",
        )
    ]
    assert calls == [(heading, "提取项目人员")]
