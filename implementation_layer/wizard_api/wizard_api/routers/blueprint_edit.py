"""Edits to the full blueprint draft from the workspace: typed operations.

``use_case.blueprint.json`` in the session's folder is the canonical blueprint.
The diagram's edits reach it as a list of operations (``schemas/blueprint_ops``)
that ``services/blueprint_ops`` applies with every reference repaired. This
router writes the result as the agent's file, keeps it with a new version and
records what changed for the agent's next turn.

Every route here sits behind the ownership check, like the sessions router.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.errors import api_error, error_detail
from wizard_api.ownership import session_belongs_to_requester
from wizard_api.schemas.blueprint_ops import (
    MAX_REQUEST_BYTES,
    OperationsRequest,
    OperationsResponse,
)
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_ops,
    blueprint_service,
    draft_store,
    session_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sessions",
    tags=["blueprint"],
    dependencies=[Depends(session_belongs_to_requester)],
)

#: How much of the summaries goes into the version's note (the column holds 512).
_NOTE_SUMMARY_CHARS = 480


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


def _no_draft() -> HTTPException:
    return api_error(
        409, "no_draft", "The wizard has not written the blueprint yet; there is nothing to edit."
    )


def _agent_busy() -> HTTPException:
    return api_error(
        409, "agent_busy", "The wizard is still replying; edit the diagram when it has finished."
    )


def _changed_elsewhere() -> HTTPException:
    return api_error(
        409,
        "changed_elsewhere",
        "The blueprint has changed since this diagram was loaded; reload it and edit again.",
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
    blueprint. All operations apply, or none.

    The edit and the start of a chat turn exclude each other
    (``agent_service.editor_save``), so the agent never writes its draft while
    the edit does, and a turn that starts after it hears of the edit
    (``pending_user_edits``).
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not blueprint_ops.solution_wizard_available():
        raise api_error(503, "unavailable", "Blueprint editing is not available on this server.")
    if artifact_sync.read_draft_blueprint(session.output_dir) is None:
        raise _no_draft()
    with agent_service.editor_save(str(session_id)) as free:
        if not free or agent_service.is_busy(str(session_id)):
            raise _agent_busy()
        if payload.base_version != session.active_version:
            raise _changed_elsewhere()
        result = _apply(db, session, payload)
    # As after a chat turn: an edit of what Gate 3 approved reopens the gate.
    # Best-effort; the edit is stored whatever happens here.
    try:
        session_service.reopen_if_approved_content_changed(db, session)
    except Exception:  # noqa: BLE001 - the download keeps its own check
        logger.warning("approved content could not be compared after an edit", exc_info=True)
        db.rollback()
    db.refresh(session)
    return OperationsResponse(
        session=session_service.session_detail(db, session),
        warnings=result.warnings,
        needs_attention=result.needs_attention,
        bpmn_changed=result.bpmn_changed,
    )


def _apply(db: Session, session, payload: OperationsRequest) -> blueprint_ops.OpsResult:
    """The edit under the session's row lock, committed whole or not at all.

    The draft file is replaced before the version is stored. Should anything
    after that write fail, the files are put back as they were before the
    transaction is rolled back, so the files and the version history keep
    saying the same thing.
    """
    output_dir = session.output_dir
    try:
        db.refresh(session, with_for_update=True)
        if payload.base_version != session.active_version:
            raise _changed_elsewhere()
        # Read under the lock, with the reader the chat sync uses.
        draft = artifact_sync.read_draft_blueprint(output_dir)
        if draft is None:
            raise _no_draft()
        # A version saved before migration 003 has no copy of the draft: keep
        # the one this edit is about to replace, so it can be gone back to.
        blueprint_service.backfill_active_draft(db, session, draft)
        try:
            result = blueprint_ops.apply_operations(draft, payload.operations)
        except blueprint_ops.OperationError as exc:
            # ``code`` is the operation's own reason (not_found, cycle...), next
            # to the error code every refusal has.
            detail = error_detail(
                "invalid_operation", exc.message, field=exc.field, index=exc.index
            )
            raise HTTPException(status_code=422, detail={**detail, "code": exc.code}) from exc
        taken = draft_store.snapshot(output_dir)
        try:
            draft_store.write_draft(output_dir, result.blueprint)
            draft_store.refresh_derived_files(output_dir, result.blueprint)
            mapped = artifact_sync.blueprint_from_draft(result.blueprint)
            content = mapped.model_dump() if mapped is not None else None
            blueprint_service.add_version(
                db,
                session,
                note="Workspace edit: " + "; ".join(result.summaries)[:_NOTE_SUMMARY_CHARS],
                content=content,
                draft=result.blueprint,
            )
            metadata = dict(session.session_metadata or {})
            if content is not None:
                # The next turn's sync finds this draft adopted already.
                metadata[artifact_sync.ADOPTED_DRAFT_KEY] = artifact_sync.content_digest(content)
            key = session_service.PENDING_USER_EDITS_KEY
            pending = [e for e in metadata.get(key) or [] if isinstance(e, str)]
            metadata[key] = [*pending, *result.summaries][-session_service.MAX_PENDING_USER_EDITS :]
            session.session_metadata = metadata
            session.updated_at = datetime.now(UTC)
            db.commit()
        except BaseException:
            draft_store.restore(output_dir, taken)
            raise
    except BaseException:
        # Releases the row; a backfill goes with the rest of the edit.
        db.rollback()
        raise
    logger.info("session %s: %d blueprint operations applied", session.id, len(payload.operations))
    return result
