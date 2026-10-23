"""Step 1：prompt 缓存用量观测的单元测试。"""

from types import SimpleNamespace

from bid_writer.ai_writer import AIWriter


def test_extract_usage_openai_style():
    usage = SimpleNamespace(
        prompt_tokens=1000,
        prompt_tokens_details=SimpleNamespace(cached_tokens=640),
    )
    assert AIWriter._extract_cache_usage(usage) == {
        "prompt_tokens": 1000,
        "cached_tokens": 640,
        "cache_hit_rate": 0.64,
    }


def test_extract_usage_deepseek_style():
    usage = SimpleNamespace(prompt_tokens=1000, prompt_cache_hit_tokens=300)
    stats = AIWriter._extract_cache_usage(usage)
    assert stats["cached_tokens"] == 300
    assert stats["cache_hit_rate"] == 0.3


def test_extract_usage_none_and_zero():
    assert AIWriter._extract_cache_usage(None) == {}
    zero = SimpleNamespace(prompt_tokens=0)
    assert AIWriter._extract_cache_usage(zero)["cache_hit_rate"] == 0.0


class _FakeUsage:
    def __init__(self, prompt, cached):
        self.prompt_tokens = prompt
        self.prompt_tokens_details = SimpleNamespace(cached_tokens=cached)


class _StreamWithTrailingUsage:
    """模拟真实网关：finish_reason chunk 之后才发尾随的 usage-only chunk。"""

    def __iter__(self):
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="正文"), finish_reason=None)],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=""), finish_reason="stop")],
            usage=None,
        )
        # 关键：usage 在 finish_reason 之后，choices 为空
        yield SimpleNamespace(choices=[], usage=_FakeUsage(1000, 512))

    def close(self):
        pass


def test_stream_captures_trailing_usage_chunk(monkeypatch):
    """回归：reader 见到 finish_reason 后必须继续读到尾随 usage chunk。"""
    writer = AIWriter.__new__(AIWriter)
    writer.config = SimpleNamespace(generation_stream_idle_timeout_seconds=5, api_timeout_seconds=5)
    writer.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: _StreamWithTrailingUsage())
        )
    )
    logged = {}
    monkeypatch.setattr(
        AIWriter, "_log_cache_usage",
        lambda self, usage, **kw: logged.update(self._extract_cache_usage(usage)),
    )

    tokens = list(writer._stream_expand_raw({"stream": True}))
    assert "".join(tokens) == "正文"
    assert logged == {"prompt_tokens": 1000, "cached_tokens": 512, "cache_hit_rate": 0.512}


def test_stream_request_options_opt_in_usage(monkeypatch):
    monkeypatch.setenv("BID_WRITER_REPORT_USAGE", "1")
    from bid_writer.config import Config

    writer = AIWriter.__new__(AIWriter)
    writer.config = Config.__new__(Config)
    # 只验证开关行为，避免构造完整 Config/OpenAI client
    monkeypatch.setattr(type(writer.config), "model", property(lambda self: "m"))
    monkeypatch.setattr(type(writer.config), "temperature", property(lambda self: 0.3))
    monkeypatch.setattr(type(writer.config), "max_tokens", property(lambda self: 100))
    monkeypatch.setattr(type(writer.config), "api_top_p", property(lambda self: None))
    monkeypatch.setattr(type(writer.config), "api_seed", property(lambda self: None))
    monkeypatch.setattr(type(writer.config), "reasoning_effort", property(lambda self: None))
    monkeypatch.setattr(type(writer.config), "report_usage", property(lambda self: True))

    stream_opts = writer._build_request_options([], stream=True)
    assert stream_opts["stream_options"] == {"include_usage": True}
    sync_opts = writer._build_request_options([], stream=False)
    assert "stream_options" not in sync_opts
