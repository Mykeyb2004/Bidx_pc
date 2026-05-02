from pathlib import Path

import pytest

from bid_writer.config import Config
from bid_writer.outline_generator import (
    OutlineGenerationError,
    OutlineGenerator,
    clean_outline_response,
    format_outline_numbering,
    validate_outline_text,
)


def _write_config(tmp_path: Path) -> Path:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "标书架构师.md").write_text("你是标书架构师。", encoding="utf-8")
    (tmp_path / "outline.md").write_text("# 旧大纲\n## 旧章节\n### 旧小节\n#### 旧单元\n", encoding="utf-8")
    (tmp_path / "requirements.md").write_text("采购需求：需要满意度调查服务。", encoding="utf-8")
    (tmp_path / "scoring.md").write_text("评分标准：项目理解 10 分；实施方案 30 分。", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project:
  root_dir: "."
  bidder_name: "测试投标主体"
  outline_locked: false
  outline_generation:
    role_file: "./roles/标书架构师.md"
  inputs:
    outline_file: "./outline.md"
    bid_requirements_file: "./requirements.md"
    scoring_criteria_file: "./scoring.md"
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_prompt_contains_inputs_and_h4_contract(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))
    generator = OutlineGenerator(config)

    prompt = generator.build_user_prompt()

    assert "测试投标主体" in prompt
    assert "满意度调查服务" in prompt
    assert "项目理解 10 分" in prompt
    assert "标题层级必须固定到 H4" in prompt
    assert "不得输出 ##### 或更深层级标题" in prompt


def test_clean_outline_response_keeps_headings_and_downgrades_deeper_levels():
    result = clean_outline_response(
        """
```markdown
# 项目
说明文字
## 项目理解
### 需求分析
##### 采购需求响应
```
""".strip()
    )

    assert result.outline_text == "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n"
    assert result.warnings == ["已将 1 个 H5/H6 标题降级为 H4。"]


def test_validate_outline_text_requires_h4_leaf_units():
    messages = validate_outline_text("# 项目\n## 章\n### 节\n")

    assert any(item.level == "error" and "至少包含 1 个 H4" in item.text for item in messages)


def test_validate_outline_text_blocks_skipped_heading_levels():
    messages = validate_outline_text("# 项目\n### 跳级小节\n#### 写作单元\n")

    assert any(item.level == "error" and "不能从 H1 直接跳到 H3" in item.text for item in messages)


def test_format_outline_numbering_recalculates_moved_h2_blocks():
    formatted = format_outline_numbering(
        """
# 项目
## 2. 实施方案
### 2.3 服务流程
#### 2.3.9 响应机制
## 1. 项目理解
### 1.1 需求分析
#### 1.1.1 采购需求响应
""".strip()
    )

    assert formatted == "\n".join(
        [
            "# 项目",
            "## 1. 实施方案",
            "### 1.1 服务流程",
            "#### 1.1.1 响应机制",
            "## 2. 项目理解",
            "### 2.1 需求分析",
            "#### 2.1.1 采购需求响应",
            "",
        ]
    )


def test_format_outline_numbering_preserves_score_prefix_text():
    formatted = format_outline_numbering(
        "# 项目\n## 3. 项目分析（12分）：国家政策指导下的项目目标\n### 3.1 国家政策指导下开展工作\n#### 3.1.1 未成年人保护法政策要求响应\n"
    )

    assert "## 1. 项目分析（12分）：国家政策指导下的项目目标" in formatted
    assert "### 1.1 国家政策指导下开展工作" in formatted
    assert "#### 1.1.1 未成年人保护法政策要求响应" in formatted


def test_missing_architect_role_file_blocks_generation(tmp_path: Path):
    config_path = _write_config(tmp_path)
    (tmp_path / "roles" / "标书架构师.md").unlink()
    config = Config(str(config_path))

    with pytest.raises(OutlineGenerationError, match="大纲生成角色文件不存在"):
        OutlineGenerator(config).generate()


def test_generate_uses_fake_client_and_returns_clean_outline(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeMessage:
        content = "# 项目\n## 项目理解\n### 需求分析\n#### 采购需求响应\n"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake_client = FakeClient()

    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: fake_client)
    result = generator.generate(stream=False)

    assert result.outline_text.endswith("#### 采购需求响应\n")
    call = fake_client.chat.completions.calls[0]
    assert call["model"] == config.outline_model
    assert call["temperature"] == config.outline_temperature
    assert call["max_tokens"] == config.outline_max_tokens
    assert call["stream"] is False


def test_generate_streams_tokens_and_reports_stages(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeChunk:
        def __init__(self, token: str = "", finish_reason: str | None = None):
            self.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "delta": type("Delta", (), {"content": token})(),
                        "finish_reason": finish_reason,
                    },
                )()
            ]

    class FakeStream:
        def __iter__(self):
            yield FakeChunk("## 项目理解\n")
            yield FakeChunk("### 需求分析\n")
            yield FakeChunk("#### 采购需求响应\n")
            yield FakeChunk(finish_reason="stop")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return FakeStream()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    stages: list[tuple[str, str]] = []
    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: FakeClient())
    result = generator.generate(
        status_callback=lambda stage, message: stages.append((stage, message)),
    )

    assert result.outline_text == "## 项目理解\n### 需求分析\n#### 采购需求响应\n"
    assert ("准备大纲请求", "正在准备大纲生成请求...") in stages
    assert ("请求模型", "正在发起大纲生成请求...") in stages
    assert ("等待首批输出", "正在请求模型并等待首批内容...") in stages
    assert ("接收内容", "已收到首批内容，正在流式接收大纲...") in stages
    assert ("清理与校验", "正在清理与校验大纲结果...") in stages


def test_generate_can_run_without_streaming_but_still_reports_stages(tmp_path: Path):
    config = Config(str(_write_config(tmp_path)))

    class FakeMessage:
        content = "# 项目\n## 章\n### 节\n#### 单元\n"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is False
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    stages: list[str] = []
    generator = OutlineGenerator(config, client_factory=lambda **_kwargs: FakeClient())
    result = generator.generate(
        stream=False,
        status_callback=lambda stage, _message: stages.append(stage),
    )

    assert result.outline_text.endswith("#### 单元\n")
    assert stages == [
        "准备大纲请求",
        "请求模型",
        "等待完整返回",
        "清理与校验",
    ]
