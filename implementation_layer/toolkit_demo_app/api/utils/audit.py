"""One audit line per run: who, when, which route, how it ended. No content.

The demo had no log that ties a run to a user. The web app's proxy names the signed-in
user in ``X-GAIK-User`` on every run and result download (``proxy.ts``,
``lib/api-access.ts``); this middleware writes one line for each such request and for
every state-changing request, to the ``gaik.audit`` logger:

    audit user=6f1c... method=POST route=/pipeline/document status=200 ms=5321

The user is the account id the proxy sends (a random id, no name or e-mail), ``-``
without one; the route is the matched template (``/pipeline/pdf/{job_id}``), never the
raw path, query, headers, body or file names. A streamed response is logged when its
last chunk is sent, or when the client goes away. Writing the line never affects the
request.
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


def _user_of(scope) -> str | None:
    for name, value in scope.get("headers") or ():
        if name.decode("latin-1").lower() == USER_HEADER:
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
                route = getattr(scope.get("route"), "path", None) or "unmatched"
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
