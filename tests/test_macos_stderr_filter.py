import sys

from bid_writer.macos_stderr_filter import (
    StderrLineFilter,
    should_suppress_macos_stderr_line,
    suppress_native_macos_stderr_noise,
)


def _filter_output(*chunks: bytes) -> bytes:
    forwarded: list[bytes] = []
    line_filter = StderrLineFilter(
        write=forwarded.append,
        should_suppress=should_suppress_macos_stderr_line,
    )
    for chunk in chunks:
        line_filter.feed(chunk)
    line_filter.flush()
    return b"".join(forwarded)


def test_filters_native_macos_imk_mach_port_noise() -> None:
    imk_line = (
        b"2026-04-28 12:34:15.733 python[51955:1037480] "
        b"error messaging the mach port for IMKCFRunLoopWakeUpReliable\n"
    )

    assert should_suppress_macos_stderr_line(imk_line)
    assert _filter_output(b"before\n", imk_line, b"after\n") == b"before\nafter\n"


def test_filter_handles_split_native_stderr_chunks() -> None:
    prefix = b"2026-04-28 12:34:15.733 python[51955:1037480] "

    assert (
        _filter_output(
            b"before\n",
            prefix,
            b"error messaging the mach port for IMKCFRunLoopWakeUpReliable\n",
            b"after\n",
        )
        == b"before\nafter\n"
    )


def test_filter_preserves_unrelated_stderr() -> None:
    traceback_line = b"Traceback (most recent call last):\n"
    exception_line = (
        b"RuntimeError: error messaging the mach port for "
        b"IMKCFRunLoopWakeUpReliable\n"
    )

    assert not should_suppress_macos_stderr_line(exception_line)
    assert (
        _filter_output(traceback_line, exception_line)
        == traceback_line + exception_line
    )


def test_context_manager_preserves_stderr_after_suppressed_line(capfd, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    with suppress_native_macos_stderr_noise():
        sys.stderr.write("keep-before\n")
        sys.stderr.write(
            "2026-04-28 12:34:15.733 python[51955:1037480] "
            "error messaging the mach port for IMKCFRunLoopWakeUpReliable\n"
        )
        sys.stderr.write("keep-after\n")

    captured = capfd.readouterr()
    assert captured.err == "keep-before\nkeep-after\n"
