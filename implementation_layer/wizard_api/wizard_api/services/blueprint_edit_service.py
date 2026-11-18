"""The one way the workspace writes the agent's draft: typed operations.

``use_case.blueprint.json`` in the session's folder is the canonical blueprint.
Every edit from the workspace reaches it as operations (``schemas/blueprint_ops``):
the diagram's edits (``POST /blueprint/operations``) and the old saves, the
Blueprint form's PATCH and the diagram's ``/bpmn/sync``, whose changes to the
reduced blueprint are turned into operations (``blueprint_ops.operations_from_v2_diff``).

:func:`apply_edit` applies them, writes the result as the agent's file, keeps it
with a new version and records what changed for the agent's next turn. Its
refusals are ``HTTPException`` with the API's error shape (``errors.api_error``),
as the routes that call it answer them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from wizard_api.errors import api_error, error_detail
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_ops,
    blueprint_service,
    draft_store,
    session_service,
)

logger = logging.getLogger(__name__)

#: How much of the summaries goes into the version's note (the column holds 512).
_NOTE_SUMMARY_CHARS = 480


@dataclass
class Edit:
    """Operations, and the steps the save made AI steps (``artifact_sync.AI_STEPS_KEY``)."""

    operations: list[Any]
    ai_steps: set[str] = field(default_factory=set)


#: Makes the operations (or an ``Edit``) from the draft as read under the
#: session's lock. It may refuse the edit with an ``HTTPException`` or a
#: ``blueprint_ops.OperationError``.
OperationsFor = Callable[[dict[str, Any]], "list[Any] | Edit"]


def no_draft() -> HTTPException:
    return api_error(
        409, "no_draft", "The wizard has not written the blueprint yet; there is nothing to edit."
    )


def agent_busy() -> HTTPException:
    return api_error(
        409, "agent_busy", "The wizard is still replying; edit the diagram when it has finished."
    )


def changed_elsewhere() -> HTTPException:
    return api_error(
        409,
        "changed_elsewhere",
        "The blueprint has changed since this diagram was loaded; reload it and edit again.",
    )


def unavailable() -> HTTPException:
    return api_error(503, "unavailable", "Blueprint editing is not available on this server.")


def unsupported_edit(fields: list[str]) -> HTTPException:
    """422 for a save that changes what no operation can change, naming it."""
    return api_error(
        422,
        "unsupported_edit",
        "This save changes what can only be changed by asking the wizard: " + ", ".join(fields),
        fields=fields,
    )


def reduced_view(
    draft: dict[str, Any] | None, ai: frozenset[str] = frozenset()
) -> dict[str, Any] | None:
    """The reduced (V2) blueprint of the draft, with its steps' descriptions;
    None when the draft has no workflow yet. ``ai``: see ``artifact_sync.AI_STEPS_KEY``."""
    if draft is None:
        return None
    mapped = artifact_sync.blueprint_from_draft(draft, ai)
    if mapped is None:
        return None
    view = mapped.model_dump()
    descriptions = {
        str(s.get("id")): s.get("description")
        for s in (draft.get("workflow") or {}).get("steps") or []
        if isinstance(s, dict) and isinstance(s.get("description"), str) and s.get("description")
    }
    for step in view["steps"]:
        if step["id"] in descriptions:
            step["description"] = descriptions[step["id"]]
    return view


def other_ids(draft: dict[str, Any], view: dict[str, Any]) -> set[str]:
    """Ids in the draft besides the view's steps, which a new step may not take."""
    steps = (draft.get("workflow") or {}).get("steps") or []
    manual = (draft.get("business_process") or {}).get("manual_steps") or []
    ids = {str(s.get("id")) for s in [*steps, *manual] if isinstance(s, dict) and s.get("id")}
    return ids - {str(s.get("id")) for s in view.get("steps") or []}


def v2_edit(draft: dict[str, Any], old: dict[str, Any], new: dict[str, Any]) -> Edit:
    """What turns the reduced blueprint ``old`` (read from ``draft``) into ``new``.

    The steps' order, names, types and descriptions as operations, then the
    other fields the reduced blueprint shows (the use case's name and
    description, the goal, the integration targets, each step's component and
    settings) carried into the draft, see ``blueprint_ops.field_edits_from_v2_diff``.
    A step ``new`` makes ``ai``, which was not, is remembered as one: without a
    component the draft's automated task would show as ``io``.
    """
    reserved = other_ids(draft, old)
    operations = blueprint_ops.operations_from_v2_diff(old, new, reserved_ids=reserved)
    ids = blueprint_ops.v2_step_ids(old, new, reserved_ids=reserved)
    fields = blueprint_ops.field_edits_from_v2_diff(old, new, ids)
    old_types = {str(s.get("id")): s.get("type") for s in old.get("steps") or []}
    made_ai = {
        ids[str(s.get("id"))]
        for s in new.get("steps") or []
        if isinstance(s, dict) and s.get("type") == "ai" and old_types.get(str(s.get("id"))) != "ai"
    }
    return Edit([*operations, *fields], made_ai)


def apply_edit(
    db: Session,
    session,
    *,
    base_version: int | None,
    operations_for: OperationsFor,
    note: str | None = None,
) -> blueprint_ops.OpsResult | None:
    """Apply the operations ``operations_for`` makes to the agent's draft.

    The new version's note is ``note``, or "Workspace edit: " and the summaries
    of the operations.

    Refused with 409 while there is no draft (``no_draft``), while the agent
    replies (``agent_busy``) and when ``base_version`` is given and is not the
    active version (``changed_elsewhere``); with 422 ``invalid_operation`` when
    an operation cannot be applied or would break the blueprint. All operations
    apply, or none. Returns None, changing nothing, when there are none.

    The edit and the start of a chat turn exclude each other
    (``agent_service.editor_save``), so the agent never writes its draft while
    the edit does, and a turn that starts after it hears of the edit
    (``pending_user_edits``). An edit of what Gate 3 approved reopens the gate.
    """
    if not blueprint_ops.solution_wizard_available():
        raise unavailable()
    if artifact_sync.read_draft_blueprint(session.output_dir) is None:
        raise no_draft()
    with agent_service.editor_save(str(session.id)) as free:
        if not free or agent_service.is_busy(str(session.id)):
            raise agent_busy()
        if base_version is not None and base_version != session.active_version:
            raise changed_elsewhere()
        result = _apply(db, session, base_version, operations_for, note)
    if result is None:
        return None
    # As after a chat turn: an edit of what Gate 3 approved reopens the gate.
    # Best-effort; the edit is stored whatever happens here.
    try:
        session_service.reopen_if_approved_content_changed(db, session)
    except Exception:  # noqa: BLE001 - the download keeps its own check
        logger.warning("approved content could not be compared after an edit", exc_info=True)
        db.rollback()
    db.refresh(session)
    return result


def _invalid(exc: blueprint_ops.OperationError) -> HTTPException:
    # ``code`` is the operation's own reason (not_found, cycle...), next to the
    # error code every refusal has.
    detail = error_detail("invalid_operation", exc.message, field=exc.field, index=exc.index)
    return HTTPException(status_code=422, detail={**detail, "code": exc.code})


def _apply(
    db: Session,
    session,
    base_version: int | None,
    operations_for: OperationsFor,
    note: str | None,
) -> blueprint_ops.OpsResult | None:
    """The edit under the session's row lock, committed whole or not at all.

    The draft file is replaced before the version is stored. Should anything
    after that write fail, the files are put back as they were before the
    transaction is rolled back, so the files and the version history keep
    saying the same thing.
    """
    output_dir = session.output_dir
    try:
        db.refresh(session, with_for_update=True)
        if base_version is not None and base_version != session.active_version:
            raise changed_elsewhere()
        # Read under the lock, with the reader the chat sync uses.
        draft = artifact_sync.read_draft_blueprint(output_dir)
        if draft is None:
            raise no_draft()
        try:
            edit = operations_for(draft)
            # A save of the whole reduced blueprint that changes nothing in the
            # draft is no edit; typed operations are what the user asked for.
            whole_save = isinstance(edit, Edit)
            if not whole_save:
                edit = Edit(list(edit))
            operations = edit.operations
            if not operations:
                db.rollback()
                return None
            result = blueprint_ops.apply_operations(draft, operations)
        except blueprint_ops.OperationError as exc:
            raise _invalid(exc) from exc
        metadata = dict(session.session_metadata or {})
        marked = artifact_sync.ai_steps(metadata)
        ai = _still_without_component(result.blueprint, marked | edit.ai_steps)
        if whole_save and result.blueprint == draft and ai == marked:
            db.rollback()
            return None
        # A version saved before migration 003 has no copy of the draft: keep
        # the one this edit is about to replace, so it can be gone back to.
        blueprint_service.backfill_active_draft(db, session, draft)
        taken = draft_store.snapshot(output_dir)
        try:
            draft_store.write_draft(output_dir, result.blueprint)
            draft_store.refresh_derived_files(output_dir, result.blueprint)
            mapped = artifact_sync.blueprint_from_draft(result.blueprint, ai)
            content = mapped.model_dump() if mapped is not None else None
            blueprint_service.add_version(
                db,
                session,
                note=note
                if note is not None
                else "Workspace edit: " + "; ".join(result.summaries)[:_NOTE_SUMMARY_CHARS],
                content=content,
                draft=result.blueprint,
            )
            if ai:
                metadata[artifact_sync.AI_STEPS_KEY] = sorted(ai)
            else:
                metadata.pop(artifact_sync.AI_STEPS_KEY, None)
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
    logger.info("session %s: %d blueprint operations applied", session.id, len(operations))
    return result


def _still_without_component(
    blueprint: dict[str, Any], steps: frozenset[str] | set[str]
) -> frozenset[str]:
    """Of ``steps``, the automated tasks that have no component."""
    return frozenset(
        str(s.get("id"))
        for s in (blueprint.get("workflow") or {}).get("steps") or []
        if isinstance(s, dict)
        and str(s.get("id")) in steps
        and s.get("type") == "automated_task"
        and not s.get("component")
    )
