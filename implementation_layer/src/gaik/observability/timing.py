"""Small timing utilities shared by gaik components."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import monotonic


@contextmanager
def measure_duration() -> Iterator[Callable[[], float]]:
    """Yield a callable that returns elapsed seconds since the block began.

    Use it to attach wall-clock latency to a result without sprinkling
    ``time.monotonic()`` reads through the call site:

        with measure_duration() as elapsed:
            ...do work...
        record.duration_s = elapsed()

    The callable can be invoked multiple times — typical usage calls it
    once after the block, but reading mid-block (e.g. to log progress)
    is also valid.
    """
    start = monotonic()
    yield lambda: monotonic() - start
