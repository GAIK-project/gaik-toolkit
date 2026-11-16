"""HTTP calls to model and parsing services with short, generic error messages.

A failed request raises the same ``requests`` exception type as before, with a message
that names only the service, the kind of error and the HTTP status. The response body,
the URL and the headers (which carry the key or token) stay out of the message and out
of the exception's context; the body and the URL without its query string go to the
debug log only. An ``HTTPError`` keeps a stripped ``response`` with the status code,
the reason and a ``Retry-After`` header, so a caller can still back off on 429 or 503;
it has no body, URL or request.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

_LOGGED_BODY_CHARS = 500


def url_for_log(url: str) -> str:
    """``url`` without user info, query string or fragment."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _stripped(response: Any) -> requests.Response | None:
    """A response with the status, the reason and ``Retry-After`` only."""
    if response is None:
        return None
    stripped = requests.Response()
    stripped.status_code = getattr(response, "status_code", None)
    stripped.reason = getattr(response, "reason", "") or ""
    retry_after = (getattr(response, "headers", None) or {}).get("Retry-After")
    if retry_after:
        stripped.headers["Retry-After"] = retry_after
    stripped._content = b""
    return stripped


def _send(method: str, url: str, service: str, **kwargs: Any) -> requests.Response:
    try:
        # Looked up on the module at call time, so tests can replace requests.post.
        response = getattr(requests, method)(url, **kwargs)
        response.raise_for_status()
    except requests.HTTPError as exc:
        response = exc.response
        status = getattr(response, "status_code", None)
        reason = getattr(response, "reason", "") or ""
        body = getattr(response, "text", "") or ""
        logger.debug(
            "%s request to %s failed with HTTP %s: %s",
            service,
            url_for_log(url),
            status,
            body[:_LOGGED_BODY_CHARS],
        )
        raise requests.HTTPError(
            f"{service} request failed: HTTP {status} {reason}".rstrip(),
            response=_stripped(response),
        ) from None
    except requests.RequestException as exc:
        logger.debug("%s request to %s failed: %s", service, url_for_log(url), type(exc).__name__)
        raise type(exc)(f"{service} request failed: {type(exc).__name__}") from None
    return response


def post(url: str, *, service: str, **kwargs: Any) -> requests.Response:
    """``requests.post`` whose errors carry no body, URL or headers (module docstring)."""
    return _send("post", url, service, **kwargs)


def get(url: str, *, service: str, **kwargs: Any) -> requests.Response:
    """``requests.get`` whose errors carry no body, URL or headers (module docstring)."""
    return _send("get", url, service, **kwargs)


def describe_empty_gemini_response(payload: Any) -> str:
    """Why a Gemini response has no usable text, from its block and finish reasons only.

    The rest of the payload (model output, safety ratings, usage) stays out of the
    message; the reasons and the usage go to the debug log, the content nowhere.
    """
    if not isinstance(payload, dict):
        return "the response was not a JSON object"
    reasons = []
    feedback = payload.get("promptFeedback") or {}
    block = feedback.get("blockReason") if isinstance(feedback, dict) else None
    if block:
        reasons.append(f"block reason {block}")
    candidates = payload.get("candidates") or []
    first = candidates[0] if isinstance(candidates, list) and candidates else None
    finish = first.get("finishReason") if isinstance(first, dict) else None
    # The candidates' content can quote the document, so only the reasons are logged.
    logger.debug(
        "Gemini response without usable text: %d candidate(s), block reason %s, finish "
        "reason %s, usage %s",
        len(candidates) if isinstance(candidates, list) else 0,
        block,
        finish,
        payload.get("usageMetadata"),
    )
    if finish:
        reasons.append(f"finish reason {finish}")
    return ", ".join(reasons) or "no reason given"
