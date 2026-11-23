"""The ``.env`` file is read when gaik first reads its configuration, not on import.

gaik's configuration helpers (``get_llm_config``, ``get_openai_config`` and the
parsers' own) read keys and endpoints from environment variables, and for
convenience they also take them from a ``.env`` file. Importing gaik reads no file
and changes no environment: the file is loaded once, the first time one of those
helpers runs, and never overrides a variable that is already set.

A service that passes its configuration explicitly, or that does not want a stray
``.env`` file picked up, sets ``GAIK_NO_DOTENV=1``: gaik then reads only the
environment it was given.

The file is looked up as python-dotenv's ``load_dotenv()`` does from gaik's own
modules: walking up from the installed package (for a virtual environment inside a
project, that finds the project's ``.env``), or, in a notebook, ``python -c``, a
debugger or a coverage run, walking up from the working directory at the first call.
A file found there can set provider keys and endpoints; a service sets
``GAIK_NO_DOTENV=1``.
"""

from __future__ import annotations

import os
import threading

NO_DOTENV_ENV = "GAIK_NO_DOTENV"

_loaded = False
_lock = threading.Lock()


def load_env_file() -> None:
    """Load ``.env`` into the environment once, without overriding set variables."""
    global _loaded
    if _loaded:
        return
    # A second thread waits here until the first has read the file, so it never reads
    # the environment half loaded.
    with _lock:
        if _loaded:
            return
        if os.getenv(NO_DOTENV_ENV, "").strip().lower() in {"1", "true", "yes"}:
            _loaded = True
            return
        try:
            from dotenv import load_dotenv
        except ImportError:
            _loaded = True
            return
        # A read that raises is not marked done: the next config read tries again
        # instead of going on without the file's keys and endpoints.
        load_dotenv()
        _loaded = True
