"""
Retry logic for transient API errors.

Ported from QAdental's enhancement.py and transcription_gpt4o_diarize.py.
Handles exponential backoff for general errors and special 429 rate-limit handling.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _is_transient(exc: Exception) -> bool:
    """Return True if *exc* is a transient OpenAI error worth retrying."""
    # openai is a core dependency — import at call time to keep the module
    # importable even when the openai SDK is unavailable (e.g. type-checking).
    try:
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
            return True
    except ImportError:
        pass

    # Standard library connection/timeout errors
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True

    # Also retry on generic connection/timeout errors from httpx (used by
    # the GPT-4o diarize HTTP path).
    cls_name = type(exc).__name__
    if cls_name in ("TimeoutException", "ConnectError", "ReadTimeout"):
        return True

    return False


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if *exc* signals a 429 rate limit."""
    try:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
    except ImportError:
        pass
    # httpx-based detection (GPT-4o HTTP path stores status on the exception)
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status == 429


def _get_retry_after(exc: Exception) -> float | None:
    """Extract ``Retry-After`` header value from an API error, if present."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is not None:
        try:
            return float(retry_after)
        except (ValueError, TypeError):
            pass
    return None


def with_retry(
    func: Callable[[], T],
    *,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_429_retries: int = 4,
) -> T:
    """Execute *func* with retry logic for transient errors.

    - **Transient errors** (connection, timeout): up to *max_retries* attempts
      with exponential backoff starting at *base_delay*.
    - **429 rate-limit errors**: up to *max_429_retries* **additional**
      attempts with exponential backoff (1.5 s, 3 s, 6 s, 12 s …).
      ``Retry-After`` header is honoured when present.
    - **Permanent errors** (content filter, bad request, auth, …): raised
      immediately without retry.

    Args:
        func: Zero-argument callable to execute.
        max_retries: Max retries for transient (non-429) errors.
        base_delay: Initial delay in seconds for exponential backoff.
        max_429_retries: Extra retry budget specifically for 429 errors.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception on exhaustion.
    """
    total_budget = max_retries + 1 + max_429_retries
    rate_limit_retries_used = 0
    general_retries_used = 0
    last_exc: Exception | None = None

    for attempt in range(total_budget):
        try:
            return func()
        except Exception as exc:
            last_exc = exc

            if _is_rate_limit(exc):
                if rate_limit_retries_used >= max_429_retries:
                    logger.error(
                        "Rate limited after %d retries, giving up",
                        rate_limit_retries_used,
                    )
                    raise

                retry_after = _get_retry_after(exc)
                delay = (
                    retry_after if retry_after else base_delay * 1.5 * (2**rate_limit_retries_used)
                )
                rate_limit_retries_used += 1
                logger.warning(
                    "Rate limited (429), retry %d/%d in %.1fs",
                    rate_limit_retries_used,
                    max_429_retries,
                    delay,
                )
                time.sleep(delay)
                continue

            if _is_transient(exc):
                if general_retries_used >= max_retries:
                    logger.error(
                        "Transient error after %d retries, giving up: %s",
                        general_retries_used,
                        exc,
                    )
                    raise

                delay = base_delay * (2**general_retries_used)
                general_retries_used += 1
                logger.warning(
                    "Transient error, retry %d/%d in %.1fs: %s",
                    general_retries_used,
                    max_retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue

            # Permanent error — raise immediately
            raise

    # Should not reach here, but just in case
    raise last_exc  # type: ignore[misc]
