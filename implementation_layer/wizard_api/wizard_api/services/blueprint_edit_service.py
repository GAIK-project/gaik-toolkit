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
from pydantic import ValidationError
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
    A step ``new`` makes ``ai`` (it was not, or it was with a component that
    ``new`` takes away) is remembered as one: without a component the draft's
    automated task would show as ``io``.
    """
    reserved = other_ids(draft, old)
    operations = blueprint_ops.operations_from_v2_diff(old, new, reserved_ids=reserved)
    ids = blueprint_ops.v2_step_ids(old, new, reserved_ids=reserved)
    fields = blueprint_ops.field_edits_from_v2_diff(old, new, ids)
    old_steps = {str(s.get("id")): s for s in old.get("steps") or [] if isinstance(s, dict)}

    def made_ai(step: dict[str, Any]) -> bool:
        if step.get("type") != "ai":
            return False
        before = old_steps.get(str(step.get("id")))
        if before is None or before.get("type") != "ai":
            return True
        # Still ai, with the component cleared.
        return bool(before.get("component")) and not step.get("component")

    made = {
        ids[str(s.get("id"))] for s in new.get("steps") or [] if isinstance(s, dict) and made_ai(s)
    }
    return Edit([*operations, *fields], made)


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

    def change(draft: dict[str, Any], metadata: dict[str, Any]) -> _Write | None:
        try:
            edit = operations_for(draft)
            # A save of the whole reduced blueprint that changes nothing in the
            # draft is no edit; typed operations are what the user asked for.
            whole_save = isinstance(edit, Edit)
            if not whole_save:
                operations = list(edit)
                # A step the user made an automated task is an AI step: without a
                # component it would show as ``io`` (``artifact_sync.AI_STEPS_KEY``).
                edit = Edit(
                    operations,
                    {
                        op.step_id
                        for op in operations
                        if getattr(op, "op", None) == "set_step_type"
                        and op.type == "automated_task"
                    },
                )
            if not edit.operations:
                return None
            result = blueprint_ops.apply_operations(draft, edit.operations)
        except blueprint_ops.OperationError as exc:
            raise _invalid(exc) from exc
        marked = artifact_sync.ai_steps(metadata)
        ai = artifact_sync.still_without_component(result.blueprint, marked | edit.ai_steps)
        if whole_save and result.blueprint == draft and ai == marked:
            return None
        # Only add_lane makes a user lane; remove_lane and the write's own
        # participants (_write) take them away.
        removed = set(result.lanes_removed)
        lanes = [
            lane
            for lane in [*artifact_sync.user_lane_list(metadata), *result.lanes_added]
            if lane not in removed
        ]
        return _Write(
            blueprint=result.blueprint,
            summaries=list(result.summaries),
            ai=ai,
            user_lanes=lanes,
            note=note
            if note is not None
            else "Workspace edit: " + "; ".join(result.summaries)[:_NOTE_SUMMARY_CHARS],
            result=result,
        )

    written = _write(db, session, base_version, change)
    return written.result if written is not None else None


#: The note of the version an undo adds.
UNDO_NOTE = "Undo"
#: The note of the version an undo keeps the agent's unsaved file in.
BEFORE_UNDO_NOTE = "Before undo"
#: The note of the version an edit keeps the agent's unsaved file in.
AGENT_CHANGES_NOTE = "Agent changes kept"


def _keep_unsaved_draft(
    db: Session, session, draft: dict[str, Any], marked: frozenset[str], *, note: str
):
    """Keep the agent's file as a version of its own when no version holds it.

    Returns the version added, or None when the file is already held.

    The agent can change its file in a field the reduced view has no place for
    (``parameters``, ``data_handling``): the chat sync then adds no version, so
    the active version's draft is an older one. A write that replaces the file
    would lose that work, and an undo would go back past it. Runs inside the
    write's transaction, so a write that fails leaves no version behind. A
    version without a draft (saved before migration 004) is not this case: the
    backfill gives it the file's draft.
    """
    active = blueprint_service.get_active_version(db, session)
    if active is None or active.draft is None or active.draft == draft:
        return None
    mapped = artifact_sync.blueprint_from_draft(draft, marked)
    added = blueprint_service.add_version(
        db,
        session,
        note=note,
        content=mapped.model_dump() if mapped is not None else None,
        draft=draft,
    )
    # So the write's own version is numbered after it.
    db.flush()
    return added


def nothing_to_undo() -> HTTPException:
    return api_error(409, "nothing_to_undo", "There is no earlier blueprint to go back to.")


def cannot_undo() -> HTTPException:
    return api_error(
        409,
        "cannot_undo",
        "The earlier blueprint is no longer valid and cannot be restored; ask the wizard instead.",
    )


def undo(db: Session, session, *, base_version: int) -> None:
    """Restore the draft of the version before the last write, as a new version.

    The draft restored is that of the newest version older than the active one
    that carries one, or, right after an undo, older than the version that undo
    restored (``blueprint_service.UNDO_CURSOR_KEY``): repeated undos walk back.
    Any other write removes the cursor, so the walk starts again from it. A
    version that shows the same draft and AI steps as now is passed over. The
    AI steps without a component are those of the version restored.

    When the agent's file differs from the active version's draft (the agent
    changed what the reduced view does not show), it is first kept as a
    version of its own (note ``"Before undo"``), so the undo loses no work.

    Goes through the flow of an edit, with its refusals (``no_draft``,
    ``agent_busy``, ``changed_elsewhere``); also refused with 409
    ``nothing_to_undo`` when no older version carries a draft, and
    ``cannot_undo`` when that draft is no longer a valid blueprint. Nothing
    changes when refused.
    """

    def change(draft: dict[str, Any], metadata: dict[str, Any]) -> _Write:
        cursor = metadata.get(blueprint_service.UNDO_CURSOR_KEY)
        # Only while the active version is the one that undo added: a write
        # that kept the cursor (a version stored without a draft) ends the walk.
        active = blueprint_service.get_active_version(db, session)
        walking = isinstance(cursor, int) and active is not None and active.note == UNDO_NOTE
        marked = artifact_sync.still_without_component(draft, artifact_sync.ai_steps(metadata))
        before = cursor if walking else None
        while True:
            target = blueprint_service.get_previous_draft_version(db, session, before=before)
            if target is None or not isinstance(target.draft, dict):
                raise nothing_to_undo()
            restored = target.draft
            ai = _ai_steps_of(target, restored)
            # A version that shows what is shown now is no step back.
            if restored != draft or ai != marked:
                break
            before = target.version
        try:
            draft_store.validate_draft(restored)
        except ValidationError as exc:
            raise cannot_undo() from exc
        # Newer than the version restored, the kept version is no step the walk
        # goes back to.
        kept = _keep_unsaved_draft(db, session, draft, marked, note=BEFORE_UNDO_NOTE)
        # What the walk goes back from: the version restored by the last undo
        # while it walks, else the active one.
        reverted = active
        if walking:
            reverted = next(
                (v for v in blueprint_service.list_versions(db, session.id) if v.version == cursor),
                active,
            )
        return _Write(
            blueprint=restored,
            summaries=[_undo_summary(reverted, target, kept)],
            ai=ai,
            note=UNDO_NOTE,
            undo_cursor=target.version,
        )

    _write(db, session, base_version, change)


#: Notes of the versions that hold the agent's own file.
_AGENT_NOTES = frozenset({artifact_sync.AGENT_DRAFT_NOTE, AGENT_CHANGES_NOTE, BEFORE_UNDO_NOTE})
#: Notes the server gives the versions a user's save or edit adds (a canvas save,
#: an undo, an operation: "Workspace edit: ...").
_USER_NOTES = frozenset({UNDO_NOTE, "BPMN canvas sync"})
_USER_NOTE_PREFIX = "Workspace edit:"


def _writer_of(version) -> str | None:
    """``"agent"`` or ``"user"`` for a version whose note says who wrote it, else None.

    Any other note (a form save with its own text, a gate step) says nothing
    reliable, so the undo's message claims no writer for it.
    """
    note = version.note if version is not None else ""
    if note in _AGENT_NOTES:
        return "agent"
    if note in _USER_NOTES or note.startswith(_USER_NOTE_PREFIX):
        return "user"
    return None


def _undo_summary(reverted, target, kept) -> str:
    """The sentence that tells the agent which version an undo went back from.

    An undo can go back from the user's edit or from the agent's own turn; the
    agent must know which, and when it is its own, that the package it built
    may no longer match the blueprint. Only version numbers are named: no text
    of the user or of a document enters it.
    """
    back = f"the blueprint is back to version {target.version}."
    writer = _writer_of(reverted)
    number = reverted.version if reverted is not None else None
    if number is None:
        text = f"Undid the last change: {back}"
    elif writer == "agent":
        text = (
            f"Undid the agent's last change (version {number}): {back} The PoC package "
            "built from it may not match the blueprint now; rebuild it if it is out of date."
        )
    elif writer == "user":
        text = f"Undid the user's workspace edit (version {number}): {back}"
    else:
        text = f"Undid version {number}: {back}"
    if kept is not None:
        text += f" The agent's unsaved file changes were kept as version {kept.version}."
    return text


def _ai_steps_of(version, draft: dict[str, Any]) -> frozenset[str]:
    """The AI steps without a component (``artifact_sync.AI_STEPS_KEY``) as
    ``version`` showed them: its steps of type ``ai`` that are automated tasks
    without a component in its ``draft``. The session's marks cannot say: a
    step leaves them for good once it gets a component."""
    content = version.content if isinstance(version.content, dict) else {}
    shown = {
        str(s.get("id"))
        for s in content.get("steps") or []
        if isinstance(s, dict) and s.get("type") == "ai"
    }
    return artifact_sync.still_without_component(draft, shown)


@dataclass
class _Write:
    """What a write stores: the draft, what the agent is told, the version's note."""

    blueprint: dict[str, Any]
    summaries: list[str]
    ai: frozenset[str]
    note: str
    #: The version an undo restored (``blueprint_service.UNDO_CURSOR_KEY``);
    #: None for every other write, which removes the cursor.
    undo_cursor: int | None = None
    #: What the caller gets back (an edit's ``blueprint_ops.OpsResult``).
    result: Any = None
    #: The lanes the user added once this write is made
    #: (``artifact_sync.USER_LANES_KEY``), before ``_write`` keeps only those
    #: still participants; None keeps them as they are.
    user_lanes: list[str] | None = None


#: Makes the write from the draft and the session's metadata as read under the
#: session's lock; None when there is nothing to write. It may refuse the write
#: with an ``HTTPException``.
_Change = Callable[[dict[str, Any], dict[str, Any]], "_Write | None"]


def _write(db: Session, session, base_version: int | None, change: _Change) -> _Write | None:
    """The flow every write from the workspace shares: the checks, the write
    under the session's lock and, after it, the reopen check of Gate 3."""
    if not blueprint_ops.solution_wizard_available():
        raise unavailable()
    if artifact_sync.read_draft_blueprint(session.output_dir) is None:
        raise no_draft()
    with agent_service.editor_save(str(session.id)) as free:
        if not free or agent_service.is_busy(str(session.id)):
            raise agent_busy()
        if base_version is not None and base_version != session.active_version:
            raise changed_elsewhere()
        written = _apply(db, session, base_version, change)
    if written is None:
        return None
    # As after a chat turn: an edit of what Gate 3 approved reopens the gate.
    # Best-effort; the edit is stored whatever happens here.
    try:
        session_service.reopen_if_approved_content_changed(db, session)
    except Exception:  # noqa: BLE001 - the download keeps its own check
        logger.warning("approved content could not be compared after an edit", exc_info=True)
        db.rollback()
    db.refresh(session)
    return written


def _invalid(exc: blueprint_ops.OperationError) -> HTTPException:
    # ``code`` is the operation's own reason (not_found, cycle...), next to the
    # error code every refusal has.
    detail = error_detail("invalid_operation", exc.message, field=exc.field, index=exc.index)
    return HTTPException(status_code=422, detail={**detail, "code": exc.code})


def _apply(db: Session, session, base_version: int | None, change: _Change) -> _Write | None:
    """The write under the session's row lock, committed whole or not at all.

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
        metadata = dict(session.session_metadata or {})
        written = change(draft, metadata)
        if written is None:
            db.rollback()
            return None
        # A version saved before migration 004 has no copy of the draft: keep
        # the one this write is about to replace, so it can be gone back to.
        blueprint_service.backfill_active_draft(db, session, draft)
        # The agent's work that no version holds (an undo has kept it already).
        _keep_unsaved_draft(
            db,
            session,
            draft,
            artifact_sync.still_without_component(draft, artifact_sync.ai_steps(metadata)),
            note=AGENT_CHANGES_NOTE,
        )
        taken = draft_store.snapshot(output_dir)
        try:
            draft_store.write_draft(output_dir, written.blueprint)
            # Every write (an edit, an undo, a save) keeps only the user's
            # lanes that are still participants of what it writes.
            metadata = artifact_sync.with_user_lanes(
                metadata,
                written.user_lanes
                if written.user_lanes is not None
                else artifact_sync.user_lane_list(metadata),
                written.blueprint,
            )
            lanes = artifact_sync.user_lanes(metadata)
            draft_store.refresh_derived_files(output_dir, written.blueprint, extra_lane_ids=lanes)
            mapped = artifact_sync.blueprint_from_draft(written.blueprint, written.ai)
            content = mapped.model_dump() if mapped is not None else None
            blueprint_service.add_version(
                db, session, note=written.note, content=content, draft=written.blueprint
            )
            if written.ai:
                metadata[artifact_sync.AI_STEPS_KEY] = sorted(written.ai)
            else:
                metadata.pop(artifact_sync.AI_STEPS_KEY, None)
            if content is not None:
                # The next turn's sync finds this draft adopted already.
                metadata[artifact_sync.ADOPTED_DRAFT_KEY] = artifact_sync.content_digest(content)
            if written.undo_cursor is not None:
                metadata[blueprint_service.UNDO_CURSOR_KEY] = written.undo_cursor
            else:
                metadata = blueprint_service.without_undo_cursor(metadata)
            key = session_service.PENDING_USER_EDITS_KEY
            pending = [e for e in metadata.get(key) or [] if isinstance(e, str)]
            metadata[key] = [*pending, *written.summaries][
                -session_service.MAX_PENDING_USER_EDITS :
            ]
            session.session_metadata = metadata
            session.updated_at = datetime.now(UTC)
            db.commit()
        except BaseException:
            draft_store.restore(output_dir, taken)
            raise
    except BaseException:
        # Releases the row; a backfill goes with the rest of the write.
        db.rollback()
        raise
    logger.info("session %s: blueprint written (%s)", session.id, written.note[:80])
    return written
