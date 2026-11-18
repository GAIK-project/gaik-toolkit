"""One audit line per run: who, when, which route, how it ended. No content.

The demo had no log that ties a run to a user. The web app's proxy names the signed-in
user in ``X-GAIK-User`` on every run and result download (``proxy.ts``,
``lib/api-access.ts``); this middleware writes one line for each such request and for
every state-changing request, to the ``gaik.audit`` logger:

    audit user=6f1c... method=POST route=/pipeline/document status=200 ms=5321

The user is the account id the proxy sends (a random id, no name or e-mail), and the
report runs' route handlers send it too (``lib/report-writer/gate.ts``); ``-`` without
one, which is a call from inside the pod. The route is the matched template
(``/pipeline/pdf/{job_id}``), never the raw path, query, headers, body or file names.
The account id is personal data (it leads to the account); the privacy notice says so.
A streamed response is logged when its last chunk is sent, or when the client goes
away. Writing the line never affects the request.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time

try:
    from utils.result_owner import USER_HEADER
except ImportError:
    from api.utils.result_owner import USER_HEADER

audit_logger = logging.getLogger("gaik.audit")

_STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
_USER_ID = re.compile(r"[A-Za-z0-9-]{1,64}\Z")
_USER_HEADER_BYTES = USER_HEADER.encode("latin-1")  # ASGI header names are lowercase


def route_template(scope) -> str:
    """The matched route's full template, e.g. ``/pipeline/pdf/{job_id}``.

    FastAPI keeps a route's own template (``/pdf/{job_id}``, or ``""`` for a route at
    its router's root) and adds the ``include_router`` prefix only when matching. The
    prefix is the part of the path before the part the route's pattern matches; it is
    a fixed string, so no id or query value ever reaches the result.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    pattern = getattr(route, "path_regex", None)
    path = scope.get("path", "")
    if template is None or pattern is None:
        return "unmatched"
    for start in range(len(path) + 1):
        if (start == len(path) or path[start] == "/") and pattern.match(path[start:]):
            return path[:start] + template or "/"
    return template or "unmatched"


def _user_of(scope) -> str | None:
    for name, value in scope.get("headers") or ():
        if name == _USER_HEADER_BYTES:
            user = value.decode("latin-1").strip()
            return user if _USER_ID.match(user) else "invalid"
    return None


class AuditMiddleware:
    """Write one ``gaik.audit`` line per run or per-user read; pass everything through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        user = _user_of(scope)
        method = scope.get("method", "")
        if user is None and method not in _STATE_CHANGING:
            return await self.app(scope, receive, send)

        started = time.monotonic()
        status = 500
        logged = False

        def log(outcome: int | str) -> None:
            nonlocal logged
            if logged:
                return
            logged = True
            with contextlib.suppress(Exception):
                route = route_template(scope)
                audit_logger.info(
                    "audit user=%s method=%s route=%s status=%s ms=%d",
                    user or "-",
                    method,
                    route,
                    outcome,
                    round((time.monotonic() - started) * 1000),
                )

        async def audited_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                log(status)

        try:
            await self.app(scope, receive, audited_send)
        except Exception:
            log("error")
            raise
        finally:
            # A client that left during a stream: the response never finished.
            log(f"{status}-incomplete")
