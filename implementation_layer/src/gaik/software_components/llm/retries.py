"""Retry a model call only on a failure that may pass when it is sent again.

A rate limit (429), a server error (5xx), a timeout and a lost connection may pass;
a refused request (400 for a bad parameter or a too-long prompt, 401, 403, 404,
422) is refused again, so sending it again only adds the waits before the same
error. The check reads the HTTP status of the OpenAI, Anthropic, LiteLLM, httpx and
Google Gen AI errors, and the connection and timeout errors of those SDKs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# 408 is a request timeout: the server gave up waiting, as a client timeout would.
_RETRY_STATUS = frozenset({408, 429})
# Connection and timeout errors of the OpenAI and Anthropic SDKs (LiteLLM's derive
# from OpenAI's), by class name, so no optional SDK has to be imported to check.
_TRANSIENT_NAMES = frozenset({"APIConnectionError", "APITimeoutError"})


def _status(error: BaseException) -> int | None:
    """The HTTP status an SDK error carries, or None."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    # httpx.HTTPStatusError keeps it on the response.
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return status
    # Google Gen AI errors carry it as ``code``; elsewhere ``code`` means other things.
    code = getattr(error, "code", None)
    if type(error).__module__.startswith("google.") and isinstance(code, int):
        return code
    return None


def _transport_may_pass(error: BaseException | None) -> bool | None:
    """For an httpx transport error, whether it may pass; None for anything else.

    A timeout, a network error (connect, read, write, close) or a server that broke
    the protocol may pass. An unsupported scheme, a proxy refusal or a request the
    client itself could not form is the same on every try.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx comes with the openai SDK
        return None
    if not isinstance(error, httpx.TransportError):
        return None
    return isinstance(
        error, httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError
    )


def is_transient_error(error: BaseException) -> bool:
    """Whether ``error`` may pass on another try: 429, 5xx, a timeout, a lost connection."""
    status = _status(error)
    if status is not None:
        return status in _RETRY_STATUS or 500 <= status <= 599
    if isinstance(error, TimeoutError | ConnectionError):
        return True
    transport = _transport_may_pass(error)
    if transport is not None:
        return transport
    if any(cls.__name__ in _TRANSIENT_NAMES for cls in type(error).__mro__):
        # The SDKs raise these from the httpx error underneath; judge by that one.
        return _transport_may_pass(error.__cause__) is not False
    return False


def with_retries(
    call: Callable[[], T],
    *,
    tries: int = 4,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Return ``call()``, trying up to ``tries`` times while it fails transiently.

    Waits 1, 2, 4, ... seconds between tries (``sleep``, by default
    ``time.sleep``). Any other error, and the last transient one, is raised as it is.
    """
    if tries < 1:
        raise ValueError("tries must be at least 1")
    for attempt in range(tries):
        try:
            return call()
        except Exception as error:
            if attempt == tries - 1 or not is_transient_error(error):
                raise
            (sleep or time.sleep)(2**attempt)
    raise AssertionError("unreachable")  # pragma: no cover
