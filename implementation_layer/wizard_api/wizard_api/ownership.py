"""Which user a request acts for, and whether a session is theirs (#134, review K2).

The web app checks ownership in its proxy, but wizard_api itself handed any
session to anyone holding the service token: ``GET /sessions/{id}`` looked the
session up by UUID alone. Anything that reached the API with the token — the
wizard agent before #197, a sandbox job, a test driver — could read or change
every user's sessions.

Now the proxy names the user it acts for in ``X-Wizard-User-Id``, and every
``/sessions/{session_id}/...`` route checks that the session belongs to that
user before the handler runs. This is a router-level dependency on purpose,
like the service-token middleware: a per-handler check is the kind that gets
forgotten on the next route, and sprint4 added nine of them.

A mismatch is a 404, not a 403, so a caller cannot tell "not yours" from
"does not exist". A request *without* the header is accepted while
``WIZARD_REQUIRE_USER_HEADER`` is unset: the sandbox Job's init container and
the stack E2E helpers still call the API with the token alone (#203 / B3 add
the header there). Once every caller sends it, set the variable and a missing
header becomes a 400.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from wizard_api import config, telemetry
from wizard_api.db import get_db

USER_HEADER = "X-Wizard-User-Id"


def requesting_user(
    x_wizard_user_id: str | None = Header(default=None, alias=USER_HEADER),
) -> str | None:
    """The user the caller acts for, or None when the header is absent (and allowed to be)."""
    user_id = (x_wizard_user_id or "").strip()
    if user_id:
        return user_id
    if config.user_header_required():
        raise HTTPException(status_code=400, detail=f"{USER_HEADER} header required")
    return None


def session_belongs_to_requester(
    request: Request,
    user_id: str | None = Depends(requesting_user),
    db: Session = Depends(get_db),
) -> None:
    """Router dependency: a ``/sessions/{session_id}/...`` route is served only
    for the session's owner. Routes without a session in the path (list, create)
    check the user themselves.

    A request that passes the check is also named after its session in its
    trace, so what the user does in a session (the PoC tab's uploads too) is
    listed under that session and not beside it. A refused request is not named,
    and neither is one without the header, whose session nothing has checked."""
    raw = request.path_params.get("session_id")
    if raw is None or user_id is None:
        return
    try:
        session_id = uuid.UUID(str(raw))
    except ValueError:
        return  # the handler's own validation answers 422
    # Imported here: services import the router's neighbours and this module
    # must stay importable from the schemas' side without a cycle.
    from wizard_api.services import session_service

    session = session_service.get_session(db, session_id)
    if session is not None and session.user_id != user_id:
        from wizard_api import ops_metrics

        ops_metrics.ownership_denied.add(1)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="session not found")
    telemetry.name_session(session_id)


def require_same_user(user_id: str | None, claimed: str, what: str) -> None:
    """For list/create: the user named in the request must be the header's user."""
    if user_id is not None and claimed != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"{what} does not match {USER_HEADER}",
        )
