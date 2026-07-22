import threading
from types import SimpleNamespace

import pytest

from bid_writer.ai_writer import AIWriter, GenerationCancelledError


class _BlockingStreamResponse:
    def __init__(self):
        self.reader_started = threading.Event()
        self.release = threading.Event()
        self.closed = threading.Event()

    def __iter__(self):
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="首段"),
                    finish_reason=None,
                )
            ]
        )
        self.reader_started.set()
        self.release.wait(timeout=2)
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="迟到段"),
                    finish_reason="stop",
                )
            ]
        )

    def close(self):
        self.closed.set()
        self.release.set()


def test_stream_generation_cancel_closes_response_and_stops_reader():
    writer = object.__new__(AIWriter)
    writer.config = SimpleNamespace(
        generation_stream_idle_timeout_seconds=3,
        api_timeout_seconds=1,
    )
    response = _BlockingStreamResponse()
    writer.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: response),
        )
    )
    cancel_event = threading.Event()
    stream = writer._stream_expand_raw(
        {"stream": True},
        cancel_event=cancel_event,
    )

    assert next(stream) == "首段"
    assert response.reader_started.wait(timeout=1)

    cancel_event.set()
    with pytest.raises(GenerationCancelledError):
        next(stream)

    assert response.closed.wait(timeout=1)
    response.release.set()
