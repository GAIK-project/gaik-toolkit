"""Event-loop factory for `uvicorn --loop api.loop_factory:loop_factory`.

Only needed for local development on Windows.

Uvicorn picks the event loop like this (`uvicorn/loops/asyncio.py`)::

    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop

and ``use_subprocess`` is true whenever ``--reload`` or ``--workers`` is set
(`uvicorn/config.py`). So the standard dev command — ``uvicorn ... --reload`` —
hands the app a ``SelectorEventLoop``, and on Windows that loop cannot create
subprocesses at all: ``asyncio.create_subprocess_exec`` raises
``NotImplementedError``.

The Solution Wizard needs exactly that. `ClaudeSDKClient.connect()` spawns the
bundled Claude CLI as a subprocess, so with ``--reload`` every
``POST /wizard/start`` fails with a 500 while the same code works fine without
it. Linux is unaffected, which is why production never saw this.

Forcing ``ProactorEventLoop`` on Windows fixes it — Proactor supports
subprocesses. Everywhere else this keeps uvloop when it is installed.

Note the calling convention: for a *custom* ``--loop`` uvicorn passes this
function straight to ``asyncio.Runner`` without calling it first, unlike its own
built-in factories which are factory-of-factories. So this must take no required
arguments and return a loop **instance**.
"""

from __future__ import annotations

import asyncio
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()  # type: ignore[attr-defined]

    try:
        import uvloop
    except ImportError:
        return asyncio.new_event_loop()
    return uvloop.new_event_loop()
