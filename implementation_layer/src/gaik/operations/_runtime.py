"""Quiet stdout per thread and per asyncio task, and worker threads for async callers.

gaik's components print. ``contextlib.redirect_stdout`` swaps ``sys.stdout`` for the whole
process, so two threads that use it at once lose or leak output. Here ``sys.stdout`` is
replaced once by a proxy that sends output to the caller's own buffer while the caller is
inside ``quiet_stdout()``, and to the real stream otherwise. The buffer is a context
variable: every thread and every asyncio task has its own, so a block may span an ``await``.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import io
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any, TextIO, TypeVar

T = TypeVar("T")

# The buffer of the capturing thread or task, shared by every proxy this module installed.
# A task, and a thread started with `asyncio.to_thread`, starts with a copy of its
# creator's context: work started inside a block is captured with it, other work is not.
_capture: contextvars.ContextVar[io.StringIO | None] = contextvars.ContextVar(
    "gaik_quiet_stdout", default=None
)
_install_lock = threading.Lock()


def _buffer() -> io.StringIO | None:
    return _capture.get()


class _ThreadStdout(io.TextIOBase):
    """Stands in for ``sys.stdout``: a capturing thread or task writes to its buffer, others
    to the real stream."""

    def __init__(self, real: TextIO | None) -> None:
        super().__init__()
        self._real = real

    def _stream(self) -> TextIO | None:
        buffer = _buffer()
        if buffer is not None:
            return buffer
        if getattr(self._real, "closed", False):
            # A library that read `sys.stdout` once still holds this proxy, and the stream
            # it stood in for is gone: write where the process prints now.
            current = sys.stdout
            return sys.__stdout__ if current is self else current
        return self._real

    def write(self, text: str) -> int:
        stream = self._stream()
        return len(text) if stream is None else stream.write(text)

    def flush(self) -> None:
        stream = self._stream()
        if stream is not None:
            stream.flush()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        if _buffer() is not None:
            return False
        stream = self._stream()
        try:
            return stream is not None and stream.isatty()
        except ValueError:  # that stream is closed as well
            return False

    def fileno(self) -> int:
        if self._real is None:
            # A process without a console has no stdout at all.
            raise io.UnsupportedOperation("fileno")
        return self._real.fileno()

    def close(self) -> None:
        """Do nothing: the real stream is not this proxy's to close."""

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self._real, "encoding", None) or "utf-8"

    @property
    def errors(self) -> str | None:  # type: ignore[override]
        return getattr(self._real, "errors", None)

    def __getattr__(self, name: str) -> Any:
        # `buffer`, `reconfigure`, `name`, `mode` and the like belong to the real stream.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real, name)


def _install() -> None:
    """Put the proxy in place: once, and again when something else replaced ``sys.stdout``."""
    with _install_lock:
        if not isinstance(sys.stdout, _ThreadStdout):
            sys.stdout = _ThreadStdout(sys.stdout)


@contextlib.contextmanager
def quiet_stdout() -> Iterator[io.StringIO]:
    """Keep what the current thread or asyncio task prints inside the block out of stdout.

    Yields the buffer that holds the printed text. A nested block yields the outer buffer.
    Other threads and tasks print as before, also while this block waits in an ``await``.
    A task or an ``asyncio.to_thread`` call started inside the block is captured with it.
    The proxy stays in place for the life of the process.
    """
    outer = _buffer()
    if outer is not None:
        _install()
        yield outer
        return
    buffer = io.StringIO()
    token = _capture.set(buffer)
    _install()
    try:
        yield buffer
    finally:
        _capture.reset(token)


@contextlib.contextmanager
def maybe_quiet(quiet: bool) -> Iterator[None]:
    """``quiet_stdout()`` when ``quiet`` is set, nothing otherwise."""
    if not quiet:
        yield
        return
    with quiet_stdout():
        yield


def need(operation: str, package: str) -> ImportError:
    """The error for an operation whose extra is not installed.

    The component packages swallow a missing dependency, so the import itself would only say
    "cannot import name".
    """
    return ImportError(f"{operation} needs {package}: pip install 'gaik[operations]'")


async def run_async(
    fn: Callable[..., T], /, *args: Any, deadline: float | None = None, **kwargs: Any
) -> T:
    """Run a blocking call in a worker thread and wait for it.

    Works for any blocking gaik call, not only the operations. With ``deadline`` (seconds)
    the wait ends with ``TimeoutError``; the thread cannot be stopped and ends when its own
    request timeout does.
    """
    call = asyncio.to_thread(functools.partial(fn, *args, **kwargs))
    if deadline is None:
        return await call
    return await asyncio.wait_for(call, timeout=deadline)
