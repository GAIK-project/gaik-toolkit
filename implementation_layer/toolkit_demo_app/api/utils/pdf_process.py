"""The PDF check (``pdf_content.check``) in a process of its own.

The check's budgets and deadline bound its own work, but it is Python code that
holds the interpreter while it runs, for seconds on a hard file, and a search
it starts cannot be stopped from inside. In the API's process every other
request would wait; in a process of its own only that process does:

- It is stopped after ``PROCESS_SECONDS`` and the file refused as too complex.
- On Linux it may map at most ``PROCESS_MEMORY`` and runs at a lower priority
  than the API; on other systems the check's budgets alone bound it.
- It runs ``pdf_content.py`` as a script on the standard library alone, with
  none of the API's environment variables.
- Each process checks one file. ``SPARE_PROCESSES`` wait ready, so a check
  does not wait for Python to start; a spare ends when the API ends.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

try:
    from utils import pdf_content
except ImportError:
    from api.utils import pdf_content

#: Seconds a check's process may run before it is stopped: longer than the
#: check's own deadline, which it looks at between its steps, so that this
#: stops only a check that overruns that deadline.
PROCESS_SECONDS = pdf_content.CHECK_SECONDS + 5.0
#: Address space a check's process may map (Linux). The decode budget keeps a
#: check well below it; one that needs more is refused.
PROCESS_MEMORY = 1024 * 1024 * 1024
#: Processes started ahead of the checks; ``upload_check`` runs two at a time.
SPARE_PROCESSES = 2
#: Environment variables a check's process keeps: only what an interpreter
#: may need to start, none of the API's settings or credentials.
_KEPT_ENV = ("SYSTEMROOT", "LD_LIBRARY_PATH")

logger = logging.getLogger(__name__)
_spares: list[subprocess.Popen[bytes]] = []
_spares_lock = threading.Lock()


def _command() -> list[str]:
    """``-I -S``: no environment variables, script directory or site packages.
    A virtual environment's base interpreter runs it, as multiprocessing does,
    so no launcher stands in between on Windows."""
    base = getattr(sys, "_base_executable", "") or ""
    python = base if base and os.path.isfile(base) else sys.executable
    script = Path(pdf_content.__file__).resolve()
    return [python, "-I", "-S", str(script), str(PROCESS_MEMORY)]


def _start() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        _command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={key: os.environ[key] for key in _KEPT_ENV if key in os.environ},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _process() -> subprocess.Popen[bytes]:
    """A process for one check: the spare that waited longest, or a new one.
    Spares are then started for the next checks."""
    with _spares_lock:
        process = None
        while _spares and process is None:
            spare = _spares.pop(0)
            if spare.poll() is None:
                process = spare
            else:
                spare.communicate()  # ended on its own: close its pipes
        if process is None:
            process = _start()
        try:
            while len(_spares) < SPARE_PROCESSES:
                _spares.append(_start())
        except OSError:
            pass  # the next check starts its own
    return process


def check(data: bytes) -> None:
    """``pdf_content.check`` in a process of its own; raises as it does.

    A process that has to be stopped is a file too complex to check; one that
    fails or gives no outcome, a file that cannot be checked.
    """
    if not data:
        return pdf_content.check(data)  # nothing to read
    try:
        process = _process()
    except OSError as exc:
        logger.warning("The PDF check could not start its process: %s", exc)
        raise pdf_content.TooComplexError(pdf_content.NOT_CHECKABLE) from exc
    try:
        out, err = process.communicate(data, timeout=PROCESS_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise pdf_content.TooComplexError(pdf_content.TOO_COMPLEX) from None
    except OSError as exc:  # the process went away while the file was sent
        process.kill()
        logger.warning("The PDF check's process could not be reached: %s", exc)
        raise pdf_content.TooComplexError(pdf_content.NOT_CHECKABLE) from exc
    except BaseException:
        process.kill()  # this thread is being stopped, and so is its check
        raise
    kind = message = ""
    if process.returncode == 0:
        try:
            outcome = json.loads(out)
            kind, message = str(outcome["outcome"]), str(outcome["message"])
        except (ValueError, KeyError, TypeError):
            pass
    if kind == "pass":
        return None
    if kind == "active":
        raise pdf_content.ActiveContentError(message)
    if kind == "complex":
        raise pdf_content.TooComplexError(message)
    last = err.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
    logger.warning("The PDF check's process ended with %s: %s", process.returncode, last[0][:200])
    raise pdf_content.TooComplexError(pdf_content.NOT_CHECKABLE)
