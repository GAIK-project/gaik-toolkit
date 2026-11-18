"""Edits to the full blueprint draft from the workspace: typed operations.

``use_case.blueprint.json`` in the session's folder is the canonical blueprint.
The diagram's edits reach it as a list of operations (``schemas/blueprint_ops``)
that ``services/blueprint_ops`` applies with every reference repaired.
``services/blueprint_edit_service`` writes the result as the agent's file, keeps
it with a new version and records what changed for the agent's next turn, for
the old saves (PATCH /blueprint, /bpmn/sync) too.

Every route here sits behind the ownership check, like the sessions router.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.errors import api_error
from wizard_api.ownership import session_belongs_to_requester
from wizard_api.schemas.blueprint_ops import (
    MAX_REQUEST_BYTES,
    OperationsRequest,
    OperationsResponse,
)
from wizard_api.services import blueprint_edit_service, session_service

router = APIRouter(
    prefix="/sessions",
    tags=["blueprint"],
    dependencies=[Depends(session_belongs_to_requester)],
)


async def _operations_body(request: Request) -> OperationsRequest:
    """The request body as ``OperationsRequest``, read only up to ``MAX_REQUEST_BYTES``.

    Read here rather than as a body parameter so a larger body is refused (413)
    at its first byte over the limit, also when it comes without a length.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise _too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_REQUEST_BYTES:
            raise _too_large()
    try:
        return OperationsRequest.model_validate_json(bytes(body))
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from None


def _too_large() -> HTTPException:
    return api_error(
        413, "too_large", f"An edit is at most {MAX_REQUEST_BYTES // 1024} KB of operations."
    )


@router.post("/{session_id}/blueprint/operations", response_model=OperationsResponse)
def apply_blueprint_operations(
    session_id: uuid.UUID,
    payload: OperationsRequest = Depends(_operations_body),
    db: Session = Depends(get_db),
) -> OperationsResponse:
    """Apply the operations to the agent's draft, write it and keep it as a new version.

    Refused with 409 while there is no draft (``no_draft``), while the agent
    replies (``agent_busy``) and when ``base_version`` is not the active version
    (``changed_elsewhere``: another tab or the agent saved meanwhile); with 422
    ``invalid_operation`` when an operation cannot be applied or would break the
    blueprint. All operations apply, or none. See
    ``blueprint_edit_service.apply_edit``, the flow the old saves share.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    result = blueprint_edit_service.apply_edit(
        db,
        session,
        base_version=payload.base_version,
        operations_for=lambda draft: payload.operations,
    )
    if result is None:  # not reached: a request has at least one operation
        raise HTTPException(status_code=500, detail="the edit changed nothing")
    return OperationsResponse(
        session=session_service.session_detail(db, session),
        warnings=result.warnings,
        needs_attention=result.needs_attention,
        bpmn_changed=result.bpmn_changed,
    )
