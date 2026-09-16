import json
import threading
from types import SimpleNamespace

import pytest

from bid_writer.ai_writer import AIWriter, GenerationCancelledError
from bid_writer.body_numbering import BodyNumberingError
from bid_writer.outline_parser import HeadingNode


def make_writer(response="", error=None):
    writer = AIWriter.__new__(AIWriter)
    writer.config = SimpleNamespace(
        prompt_bidder_name="", model="test-model", temperature=0.2,
        max_tokens=1000, api_top_p=None, api_seed=None, reasoning_effort=None,
        api_timeout_seconds=1,
    )
    calls = []
    options = []

    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    def with_options(**kwargs):
        options.append(kwargs)
        return writer.client

    writer.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        with_options=with_options,
    )
    return writer, calls, options


def heading():
    return HeadingNode(level=4, title="3.3.1 动态监测", full_path="项目 > 3.3.1 动态监测", line_number=1)


class FakeTrace:
    trace_id = "test-numbering"
    finished = False

    def record_numbering_repair(self, raw_content, report):
        self.raw_content = raw_content
        self.report = report

    def finalize(self, content, **kwargs):
        self.finished = True
        self.content = content
        self.finalized = kwargs


def test_local_repair_never_calls_model_and_keeps_original_trace(monkeypatch):
    writer, calls, _ = make_writer()
    trace = FakeTrace()
    monkeypatch.setattr(writer, "_finalize_trace_session_async", lambda session, content, **kwargs: session.finalize(content, **kwargs))
    original = "### 3.3.1 动态监测\n\n（一）目标\n\n12人服务。\n\n1. 安排"
    result = writer.finalize_generation(heading(), original, trace)
    assert result.content == "\n一、目标\n\n12人服务。\n\n（一）安排"
    assert result.postprocess["format_repair_applied"]
    assert result.postprocess["numbering_repair_method"] == "local"
    assert not calls
    assert trace.raw_content == original
    assert trace.report["edits"]
    assert trace.finalized["status"] == "completed"


def test_model_assists_once_with_structure_only():
    plan = {"headings": [{"line": 1, "level": 1}, {"line": 5, "level": 2}]}
    writer, calls, options = make_writer(json.dumps(plan))
    original = "（一）目标\n\n服务12人。\n\n### 岗位职责"
    result = writer.finalize_generation(heading(), original)
    assert result.content == "一、目标\n\n服务12人。\n\n（一）岗位职责"
    assert result.postprocess["numbering_repair_method"] == "model"
    assert len(calls) == 1
    assert calls[0]["stream"] is False
    assert options[0]["max_retries"] == 0
    assert [m["role"] for m in calls[0]["messages"]] == ["system", "user"]


@pytest.mark.parametrize("response", ["not json", '{"headings":[]}', '{"headings":[{"line":3,"level":1}]}'])
def test_invalid_repair_is_failed_keeps_original_and_never_retries(response):
    writer, calls, _ = make_writer(response)
    trace = FakeTrace()
    original = "（一）目标\n\n服务12人。\n\n### 岗位职责"
    with pytest.raises(BodyNumberingError) as caught:
        writer.finalize_generation(heading(), original, trace)
    assert caught.value.content == original
    assert len(calls) == 1
    assert trace.content == original
    assert trace.finalized["status"] == "failed"
    assert not trace.finalized["postprocess"]["format_repair_applied"]


def test_missing_heading_does_not_call_model_or_fabricate_content():
    writer, calls, _ = make_writer()
    with pytest.raises(BodyNumberingError):
        writer.finalize_generation(heading(), "项目服务人数为12人。")
    assert not calls


def test_cancelled_repair_never_saves_or_completes():
    writer, calls, _ = make_writer()
    event = threading.Event()
    event.set()
    trace = FakeTrace()
    with pytest.raises(GenerationCancelledError):
        writer.finalize_generation(heading(), "（一）目标", trace, cancel_event=event)
    assert not calls
    assert trace.finalized["status"] == "cancelled"


def test_cancellation_during_structure_request_is_responsive():
    writer, _, _ = make_writer()
    event = threading.Event()
    release = threading.Event()

    def create(**kwargs):
        event.set()
        release.wait(2)
        return SimpleNamespace(choices=[])

    writer.client.chat.completions.create = create
    try:
        with pytest.raises(GenerationCancelledError):
            writer.finalize_generation(heading(), "（一）目标\n\n### 职责", cancel_event=event)
    finally:
        release.set()


def test_structure_request_timeout_stops_without_retry_or_late_edits():
    writer, _, _ = make_writer()
    writer.config.api_timeout_seconds = 0.02
    release = threading.Event()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        release.wait(2)
        return SimpleNamespace(choices=[])

    writer.client.chat.completions.create = create
    original = "（一）目标\n\n### 职责"
    try:
        with pytest.raises(BodyNumberingError) as caught:
            writer.finalize_generation(heading(), original)
        assert caught.value.content == original
        assert "TimeoutError" in caught.value.report["model_error"]
        assert len(calls) == 1
    finally:
        release.set()


def test_generation_and_stream_replacement_use_same_validation(monkeypatch):
    writer, _, _ = make_writer()
    monkeypatch.setattr(writer, "prepare_generation", lambda *args, **kwargs: SimpleNamespace(trace_session=None))
    monkeypatch.setattr(writer, "expand_raw", lambda prepared: iter(["（一）目", "标\n\n正文。\n\n（二）职责"]))
    chunks = list(writer.expand(heading(), stream=True))
    assert chunks[-1] == writer.STREAM_REPLACE_SENTINEL + "一、目标\n\n正文。\n\n二、职责"
    monkeypatch.setattr(writer, "expand_raw", lambda prepared: "正文没有标题。")
    with pytest.raises(BodyNumberingError):
        writer.expand(heading(), stream=False)
