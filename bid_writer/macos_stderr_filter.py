"""Filters noisy native macOS stderr lines emitted by Tk/Cocoa."""

from __future__ import annotations

import contextlib
import os
import re
import sys
import threading
from collections.abc import Callable, Iterator


_MACOS_IMK_MACH_PORT_RE = re.compile(
    rb"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
    rb"[^\[]+\[\d+:\d+\] error messaging the mach port for "
    rb"IMKCFRunLoopWakeUpReliable$"
)


def should_suppress_macos_stderr_line(line: bytes) -> bool:
    """Return True for the known benign macOS IMK stderr noise line."""

    return bool(_MACOS_IMK_MACH_PORT_RE.match(line.rstrip(b"\r\n")))


class StderrLineFilter:
    """Incrementally filter stderr bytes while preserving unrelated output."""

    def __init__(
        self,
        *,
        write: Callable[[bytes], object],
        should_suppress: Callable[[bytes], bool],
    ) -> None:
        self._write = write
        self._should_suppress = should_suppress
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> None:
        """Process a raw stderr chunk."""

        if not chunk:
            return

        self._buffer.extend(chunk)
        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                return

            line = bytes(self._buffer[: newline_index + 1])
            del self._buffer[: newline_index + 1]
            if not self._should_suppress(line):
                self._write(line)

    def flush(self) -> None:
        """Forward any pending partial line unless it matches the filter."""

        if not self._buffer:
            return

        line = bytes(self._buffer)
        self._buffer.clear()
        if not self._should_suppress(line):
            self._write(line)


@contextlib.contextmanager
def suppress_native_macos_stderr_noise() -> Iterator[None]:
    """Suppress known benign macOS Tk/Cocoa stderr noise during GUI startup."""

    if sys.platform != "darwin":
        yield
        return

    try:
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError, ValueError):
        yield
        return

    saved_stderr_fd = os.dup(stderr_fd)
    read_fd, write_fd = os.pipe()

    def forward_stderr() -> None:
        line_filter = StderrLineFilter(
            write=lambda data: os.write(saved_stderr_fd, data),
            should_suppress=should_suppress_macos_stderr_line,
        )
        try:
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                line_filter.feed(chunk)
            line_filter.flush()
        finally:
            with contextlib.suppress(OSError):
                os.close(read_fd)

    reader = threading.Thread(
        target=forward_stderr,
        name="bid-writer-stderr-filter",
        daemon=True,
    )

    try:
        os.dup2(write_fd, stderr_fd)
        os.close(write_fd)
        reader.start()
        yield
    finally:
        with contextlib.suppress(Exception):
            sys.stderr.flush()
        os.dup2(saved_stderr_fd, stderr_fd)
        reader.join(timeout=1.0)
        with contextlib.suppress(OSError):
            os.close(saved_stderr_fd)
