"""Error messages that tell the user what failed without the exception's own text.

An exception's message can carry provider response bodies, file paths, host names or
library internals. The user gets a short message with an error id; the exception goes
to the server log under the same id, so the two can be matched.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("demo_api.errors")

# A component's own ValueError explains the input it could not use ("broken.pdf: PDF has
# no text layer"), so the report demos show it, cut to this length.
_COMPONENT_MESSAGE_MAX = 300


def public_error(exc: BaseException, what: str = "The request") -> str:
    """Log ``exc`` with a new error id and return a message that names only the id."""
    from .model_settings import request_model_settings

    error_id = uuid.uuid4().hex[:12]
    if request_model_settings() is not None:
        # On the user's own key the log keeps only the type (see the credential
        # filter in model_settings.py), so the id goes in a record without exc_info.
        logger.error("error id %s: %s failed (%s)", error_id, what, type(exc).__name__)
    else:
        logger.error(
            "error id %s: %s failed",
            error_id,
            what,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    return (
        f"{what} failed on the server (error id {error_id}). "
        "Try again, or send the error id to the GAIK team."
    )


def error_detail(exc: BaseException, what: str = "The request") -> str:
    """Like ``public_error``, but an HTTPException raised on purpose keeps its detail."""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return public_error(exc, what)


def component_error(exc: BaseException, what: str = "The request") -> str:
    """Like ``error_detail``, but a component's own ValueError message is shown.

    Only ``ValueError`` itself: its subclasses (a pydantic ValidationError, say) can
    quote model output or other internals, so they get an error id like the rest.
    """
    if type(exc) is ValueError:
        return str(exc)[:_COMPONENT_MESSAGE_MAX]
    return error_detail(exc, what)
