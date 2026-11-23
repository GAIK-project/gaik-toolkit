"""The error answers wizard_api gives, and the trace id that ties them to the log.

Every refusal and failure answers in one shape::

    {"detail": {"error": "<stable code>", "message": "<short text>", "trace_id": "<id>", ...}}

``error`` is the code a caller branches on (``sandbox_busy``, ``gate_not_ready``,
``poc_package_incomplete``...), ``message`` is a short line a person can read, and
the extra keys are what the person needs to act (the gate, the missing piece, the
package's problems). ``trace_id`` is the one the web app sent in ``x-trace-id``,
or a fresh one, and is on every log line written about the request.

The cause of a failure (an exception's text, a server path, a stack trace, a
Kubernetes message) is logged with that trace id and never put in the answer:
``internal_error`` below is how a route reports one.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

TRACE_HEADER = "x-trace-id"
# The web app sends a UUID; anything else (or nothing) gets a fresh one, so a
# header cannot carry arbitrary text into the log and back out in an answer.
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

_trace_id: ContextVar[str | None] = ContextVar("wizard_trace_id", default=None)

# The code a plain-text refusal gets. The texts themselves are the routes' own
# fixed words ("session not found"), never an exception's.
STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    411: "length_required",
    413: "too_large",
    422: "invalid_request",
    429: "busy",
    500: "internal_error",
    502: "upstream_error",
    503: "unavailable",
}

INTERNAL_MESSAGE = "Something went wrong on the server."


def current_trace_id() -> str:
    """The trace id of the request being served (a fresh one outside a request)."""
    tid = _trace_id.get()
    if tid is None:
        tid = str(uuid.uuid4())
        _trace_id.set(tid)
    return tid


def _incoming_trace_id(scope: Scope) -> str:
    for name, value in scope.get("headers") or []:
        if name.decode("latin-1").lower() == TRACE_HEADER:
            candidate = value.decode("latin-1").strip()
            if _TRACE_ID_RE.match(candidate):
                return candidate
            break
    return str(uuid.uuid4())


class TraceIdMiddleware:
    """Give every request a trace id: the caller's ``x-trace-id`` or a fresh one.

    Plain ASGI rather than BaseHTTPMiddleware, so the context variable is set in
    the task that runs the route and its streaming body, and the id is echoed on
    the response (an SSE stream included) without buffering it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        tid = _incoming_trace_id(scope)
        token = _trace_id.set(tid)
        # Also on the scope's state: the 500 handler runs in the outermost
        # middleware, outside this context.
        scope.setdefault("state", {})["trace_id"] = tid

        async def send_with_trace(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-trace-id"
                ]
                headers.append((TRACE_HEADER.encode(), tid.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            _trace_id.reset(token)


def error_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """The ``detail`` of an error answer (also the body of an SSE error frame)."""
    return {"error": code, "message": message, "trace_id": current_trace_id(), **extra}


def _count_refusal(code: Any, status: int | str) -> None:
    from wizard_api import ops_metrics

    ops_metrics.refusal(code if isinstance(code, str) else "other", status)


def stream_error(code: str, message: str) -> dict[str, Any]:
    """An SSE error frame: ``error`` stays ``true`` (the stream contract), the code is ``code``."""
    _count_refusal(code, "stream")
    return {"error": True, "code": code, "message": message, "trace_id": current_trace_id()}


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> HTTPException:
    """A refusal the person can act on: a stable code and our own short words.

    ``message`` must be text this code wrote (or an exception's text only where
    that exception's messages are all written for the user, like a gate's). The
    extra keys go into the detail as they are.
    """
    return HTTPException(
        status_code=status_code,
        detail=error_detail(code, message, **extra),
        headers=headers,
    )


def internal_error(
    status_code: int,
    code: str,
    message: str,
    cause: BaseException | None = None,
    *,
    log_message: str | None = None,
    **extra: Any,
) -> HTTPException:
    """A failure whose cause stays in the log: the answer says only ``message``.

    The cause is logged here with the trace id, so the id the person is shown
    leads to it.
    """
    logger.error(
        "%s (trace_id=%s): %s",
        code,
        current_trace_id(),
        log_message or (f"{type(cause).__name__}: {cause}" if cause else "no cause given"),
        exc_info=cause,
    )
    return api_error(status_code, code, message, **extra)


def log_cause(code: str, cause: BaseException | str) -> str:
    """Log a failure reported in a stream (where no exception is raised); returns the trace id."""
    tid = current_trace_id()
    if isinstance(cause, BaseException):
        logger.error("%s (trace_id=%s): %s", code, tid, cause, exc_info=cause)
    else:
        logger.error("%s (trace_id=%s): %s", code, tid, cause)
    return tid


def public_run_message(status: Any) -> str | None:
    """What a run's status may say to the person.

    Only the runner's own words (the ten-minute limit). A failed Job's message
    is Kubernetes' ("Job has reached the specified backoff limit"); it names no
    cause the person can act on, and is logged instead. The reason for a failed
    run comes from the run's own log (``case_service.failure_reason``).
    """
    phase = getattr(status, "phase", None)
    message = getattr(status, "message", None)
    if phase == "timeout":
        return message
    if message:
        logger.info(
            "run %s ended %s (trace_id=%s): %s",
            getattr(status, "run_id", "?"),
            phase,
            current_trace_id(),
            message,
        )
    return None


def _request_trace_id(request: Request) -> str:
    tid = getattr(request.state, "trace_id", None)
    return tid if isinstance(tid, str) else current_trace_id()


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Every HTTPException answers in the one shape; a plain text detail gets a code."""
    tid = _request_trace_id(request)
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), str):
        body = {**detail, "trace_id": detail.get("trace_id") or tid}
    else:
        text = detail if isinstance(detail, str) and detail else None
        body = {
            "error": STATUS_CODES.get(exc.status_code, "error"),
            "message": text or ("request refused" if exc.status_code < 500 else INTERNAL_MESSAGE),
            "trace_id": tid,
        }
    headers = dict(exc.headers or {})
    headers[TRACE_HEADER] = tid
    _count_refusal(body.get("error"), exc.status_code)
    return JSONResponse({"detail": body}, status_code=exc.status_code, headers=headers)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A malformed request: which field and why, without echoing the input back."""
    tid = _request_trace_id(request)
    _count_refusal("invalid_request", 422)
    fields = [
        {"loc": list(err.get("loc", ())), "msg": str(err.get("msg", "")), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse(
        {
            "detail": {
                "error": "invalid_request",
                "message": "the request is not valid",
                "trace_id": tid,
                "errors": fields,
            }
        },
        status_code=422,
        headers={TRACE_HEADER: tid},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything no route caught: logged in full, answered with the trace id only."""
    tid = _request_trace_id(request)
    _count_refusal("internal_error", 500)
    logger.error(
        "unhandled error on %s %s (trace_id=%s)",
        request.method,
        request.url.path,
        tid,
        exc_info=exc,
    )
    return JSONResponse(
        {"detail": {"error": "internal_error", "message": INTERNAL_MESSAGE, "trace_id": tid}},
        status_code=500,
        headers={TRACE_HEADER: tid},
    )


def install(app: Any) -> None:
    """Register the trace id middleware and the handlers on ``app``."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
