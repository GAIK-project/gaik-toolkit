"""Edits to the full blueprint draft from the workspace: typed operations.

``use_case.blueprint.json`` in the session's folder is the canonical blueprint.
The diagram's edits reach it as a list of operations (``schemas/blueprint_ops``)
that ``services/blueprint_ops`` applies with every reference repaired.
``services/blueprint_edit_service`` writes the result as the agent's file, keeps
it with a new version and records what changed for the agent's next turn, for
the old saves (PATCH /blueprint, /bpmn/sync) and the JSON view's full save
(PUT /blueprint/full) too. Where the user placed the
diagram's shapes is no part of the blueprint: ``PUT /bpmn/layout`` keeps it
apart (``services/bpmn_layout``).

Every route here sits behind the ownership check, like the sessions router.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.errors import api_error
from wizard_api.ownership import session_belongs_to_requester
from wizard_api.schemas.blueprint import SessionDetailResponse
from wizard_api.schemas.blueprint_ops import (
    MAX_BLUEPRINT_CHARS,
    MAX_FULL_REQUEST_BYTES,
    MAX_REQUEST_BYTES,
    READONLY_SECTIONS,
    FullBlueprintRequest,
    FullBlueprintResponse,
    OperationsRequest,
    OperationsResponse,
    UndoRequest,
)
from wizard_api.services import (
    artifact_sync,
    blueprint_edit_service,
    blueprint_ops,
    bpmn_layout,
    draft_store,
    session_service,
)

router = APIRouter(
    prefix="/sessions",
    tags=["blueprint"],
    dependencies=[Depends(session_belongs_to_requester)],
)


async def _limited_body(request: Request, what: str, limit: int = MAX_REQUEST_BYTES) -> bytes:
    """The request body, read only up to ``limit`` bytes (``MAX_REQUEST_BYTES``).

    Read here rather than as a body parameter so a larger body is refused (413)
    at its first byte over the limit, also when it comes without a length.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large(what)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise _too_large(what)
    return bytes(body)


async def _operations_body(request: Request) -> OperationsRequest:
    """The request body as ``OperationsRequest``, at most ``MAX_REQUEST_BYTES``."""
    body = await _limited_body(request, "An edit is at most {kb} KB of operations.")
    try:
        return OperationsRequest.model_validate_json(body)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from None


def _too_large(what: str) -> HTTPException:
    return api_error(
        413,
        "too_large",
        what.format(kb=MAX_REQUEST_BYTES // 1024, chars=f"{MAX_BLUEPRINT_CHARS:,}"),
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


async def _undo_body(request: Request) -> UndoRequest:
    """The request body as ``UndoRequest``, at most ``MAX_REQUEST_BYTES``."""
    body = await _limited_body(request, "An undo request is at most {kb} KB.")
    try:
        return UndoRequest.model_validate_json(body)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from None


@router.post("/{session_id}/blueprint/undo", response_model=SessionDetailResponse)
def undo_blueprint_edit(
    session_id: uuid.UUID,
    payload: UndoRequest = Depends(_undo_body),
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    """Go back to the blueprint before the last write, as a new version (note "Undo").

    The body is ``{"base_version": int}``, the version the workspace shows.
    Repeated undos walk back through the versions that carry a draft; any
    other write starts the walk again from the newest one. The draft is
    written as the agent's file, the diagrams are redrawn from it and the
    agent hears of the undo with its next turn, as after an edit; an undo of
    what Gate 3 approved reopens the gate. The diagram's layout is kept.

    Refused with 409 ``nothing_to_undo`` when no earlier version carries a
    draft, ``cannot_undo`` when that draft is no longer a valid blueprint,
    ``agent_busy`` while the agent replies, ``changed_elsewhere`` when
    ``base_version`` is not the active version and ``no_draft`` while there is
    no draft; nothing changes then. See ``blueprint_edit_service.undo``.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    blueprint_edit_service.undo(db, session, base_version=payload.base_version)
    return session_service.session_detail(db, session)


async def _layout_body(request: Request) -> Any:
    """The request body as JSON, at most ``MAX_REQUEST_BYTES``; checked by the route."""
    body = await _limited_body(request, "A layout is at most {kb} KB.")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise api_error(422, "invalid_layout", "The layout is not JSON.") from exc


@router.put("/{session_id}/bpmn/layout", status_code=204)
def put_bpmn_layout(
    session_id: uuid.UUID,
    data_objects: int = Query(
        1, ge=0, le=1, description="1 the layout of the full drawing, 0 of the compact one."
    ),
    payload: Any = Depends(_layout_body),
    db: Session = Depends(get_db),
) -> Response:
    """Keep where the user placed shapes and edges in the diagram; ``GET /bpmn`` applies it.

    The body is a layout, ``{"shapes": {element_id: {"x": number, "y": number}},
    "edges": {element_id: [[x, y], ...]}}``, both keys optional, keyed by the
    element ids of the drawing (``GET /bpmn/mapping``). It is merged into the
    session's layout of the drawing mode ``data_objects`` selects (1, the
    default: with data objects; 0: compact): an entry replaces the stored one
    of the same id, and ``null`` for an id removes it, which resets that shape
    or edge to where the diagram draws it. Answers 204.

    Refused with 422 ``invalid_layout`` when the body or the merged layout is
    no valid layout (see ``bpmn_layout.clean_layout``: ids, finite numbers within
    100000, 2 to 100 waypoints, at most 1000 shapes and edges together), and
    with 413 ``too_large`` over 64 KB. The blueprint is not touched: no version
    is added, and a layout is taken while the agent replies.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        bpmn_layout.save_layout(db, session, bool(data_objects), payload)
    except ValueError as exc:
        raise api_error(422, "invalid_layout", str(exc)) from exc
    return Response(status_code=204)


_BLUEPRINT_TOO_LARGE = "A blueprint is at most {chars} characters as JSON."


@router.get("/{session_id}/blueprint/full", response_model=FullBlueprintResponse)
def get_full_blueprint(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> FullBlueprintResponse:
    """The agent's draft whole, the active version it belongs to, the
    top-level sections only the server writes (``READONLY_SECTIONS``), which a
    save through ``PUT /blueprint/full`` must leave as they are, and the
    draft's digest (``draft_digest``), which that save sends back.

    Refused with 409 ``no_draft`` while the agent has not written the draft.
    Changes nothing.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    draft = artifact_sync.read_draft_blueprint(session.output_dir)
    if draft is None:
        raise blueprint_edit_service.no_draft()
    return FullBlueprintResponse(
        version=session.active_version,
        draft=draft,
        readonly_sections=list(READONLY_SECTIONS),
        draft_digest=artifact_sync.content_digest(draft),
    )


async def _full_body(request: Request) -> FullBlueprintRequest:
    """The request body as ``FullBlueprintRequest``, its draft at most
    ``MAX_BLUEPRINT_CHARS`` characters as JSON, measured as the blueprint
    measures itself (solution_wizard's ``Blueprint._limit_total_size``)."""
    body = await _limited_body(request, _BLUEPRINT_TOO_LARGE, MAX_FULL_REQUEST_BYTES)
    try:
        payload = FullBlueprintRequest.model_validate_json(body)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from None
    if len(json.dumps(payload.draft, default=str, ensure_ascii=False)) > MAX_BLUEPRINT_CHARS:
        raise _too_large(_BLUEPRINT_TOO_LARGE)
    return payload


def _readonly_section(section: str) -> HTTPException:
    return api_error(
        422,
        "readonly_section",
        f"The section {section} is kept by the wizard and cannot be edited here.",
        field=section,
    )


def _invalid_draft(exc: ValidationError) -> HTTPException:
    first = exc.errors(include_url=False)[0]
    where = ".".join(str(part) for part in first["loc"]) or "blueprint"
    return api_error(
        422, "invalid_draft", f"The blueprint is not valid: {where}: {first['msg']}", field=where
    )


@router.put("/{session_id}/blueprint/full", response_model=OperationsResponse)
def put_full_blueprint(
    session_id: uuid.UUID,
    payload: FullBlueprintRequest = Depends(_full_body),
    db: Session = Depends(get_db),
) -> OperationsResponse:
    """Replace the agent's draft with ``draft``, as one edit of the workspace.

    The body is ``{"base_version": int, "base_digest": str, "draft": {...}}``,
    ``base_digest`` the ``draft_digest`` the draft was read with, the draft at most
    ``MAX_BLUEPRINT_CHARS`` characters of JSON (413 ``too_large``; the 64 KB
    of an edit of operations does not apply). It goes through the flow every
    edit shares (``blueprint_edit_service.apply_edit``): the draft is written
    and kept with a new version (note "Workspace edit: Edited the blueprint as
    JSON"), the agent hears of it with its next turn, and an edit of what Gate
    3 approved reopens the gate. Answers as ``POST /blueprint/operations``,
    ``bpmn_changed`` saying whether the diagram has anything new to show. A
    draft equal to the one on disk adds no version.

    Refused with 409 ``no_draft``, ``agent_busy`` and ``changed_elsewhere`` as
    an edit is, ``changed_elsewhere`` also when the file is no longer the one of
    ``base_digest`` (the agent changes parts of the draft without a new
    version, and a save of the whole would undo them); with 422
    ``readonly_section`` (``field``: the first section of
    ``READONLY_SECTIONS`` it changes, adds or removes), ``invalid_draft``
    (``field``: where its first error is) when it is no valid blueprint, and
    ``invalid_operation`` when it adds an error of a refusing validator rule or
    a loop. Nothing changes when refused.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    submitted = payload.draft

    def operations_for(draft: dict[str, Any]) -> list[Any]:
        # Under the session's lock, before anything is compared with the draft.
        if artifact_sync.content_digest(draft) != payload.base_digest:
            raise blueprint_edit_service.changed_elsewhere()
        if submitted == draft:
            return []
        for section in READONLY_SECTIONS:
            before = (section in draft, draft.get(section))
            if before != (section in submitted, submitted.get(section)):
                raise _readonly_section(section)
        try:
            draft_store.validate_draft(submitted)
        except ValidationError as exc:
            raise _invalid_draft(exc) from exc
        return [blueprint_ops.ReplaceDraft(submitted)]

    result = blueprint_edit_service.apply_edit(
        db, session, base_version=payload.base_version, operations_for=operations_for
    )
    return OperationsResponse(
        session=session_service.session_detail(db, session),
        warnings=result.warnings if result is not None else [],
        needs_attention=result.needs_attention if result is not None else [],
        bpmn_changed=result.bpmn_changed if result is not None else False,
    )
