from pathlib import Path

from bid_writer.env_local_prompt import build_missing_env_local_prompt


def test_outline_prompt_includes_required_and_optional_env_text(tmp_path: Path):
    env_path = tmp_path / ".env.local"

    prompt = build_missing_env_local_prompt(
        env_path=env_path,
        purpose="outline",
        file_exists=False,
    )

    assert "生成大纲前需要先配置模型连接" in prompt
    assert "BID_WRITER_API_BASE_URL=https://api.openai.com/v1" in prompt
    assert "BID_WRITER_API_KEY=你的 API Key" in prompt
    assert "BID_WRITER_MODEL=gpt-5.4" in prompt
    assert "BID_WRITER_OUTLINE_API_KEY=你的 API Key" in prompt


def test_chapter_prompt_focuses_on_main_generation_env_text(tmp_path: Path):
    env_path = tmp_path / ".env.local"

    prompt = build_missing_env_local_prompt(
        env_path=env_path,
        purpose="chapter",
        file_exists=True,
    )

    assert "扩写章节前需要先配置 .env.local" in prompt
    assert "BID_WRITER_API_KEY=你的 API Key" in prompt
    assert "BID_WRITER_OUTLINE_API_KEY" not in prompt
