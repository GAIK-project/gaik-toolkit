"""A result belongs to the user whose run made it.

The demo keeps generated PDFs, subtitles and tabular sessions by a random id for a
while after the run. The web app's proxy (``proxy.ts``) sends the signed-in user's id
in ``X-GAIK-User`` on every request it forwards; the browser cannot set it, since the
proxy builds the forwarded headers from scratch. A run records that user next to its
result id, and a later fetch, question or delete by id is answered only for the same
user. Any other caller gets the same 404 as for an unknown id, so an id does not tell
whether it exists.

A run that reached the API without the header (a call from inside the pod, such as
``api/smoke.py``) records no user; such a result is served only to a caller without
one either. Through the proxy every run is signed in, so this never opens a user's
result to a visitor.

Entries go after ``TTL_SECONDS``, longer than any route keeps its result.
"""

from __future__ import annotations

import threading
import time

from fastapi import Header, HTTPException

USER_HEADER = "x-gaik-user"
TTL_SECONDS = 48 * 3600

_owners: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def current_user(x_gaik_user: str = Header("", alias=USER_HEADER)) -> str:
    """The user the proxy forwarded the request for, or "" without one."""
    return x_gaik_user.strip()


def remember_owner(result_id: str, user: str) -> None:
    """Record ``user`` as the owner of ``result_id``, dropping expired entries."""
    now = time.time()
    with _lock:
        for rid in [r for r, (_, t) in _owners.items() if now - t > TTL_SECONDS]:
            del _owners[rid]
        _owners[result_id] = (user, now)


def owned_by(result_id: str, user: str) -> bool:
    """True if ``result_id`` was recorded for ``user``."""
    with _lock:
        entry = _owners.get(result_id)
    return entry is not None and entry[0] == user


def require_owner(result_id: str, user: str, detail: str) -> None:
    """Raise the route's own 404 unless ``result_id`` belongs to ``user``."""
    if not owned_by(result_id, user):
        raise HTTPException(status_code=404, detail=detail)


def forget_owner(result_id: str) -> None:
    """Drop the entry of a result that was deleted."""
    with _lock:
        _owners.pop(result_id, None)
