import asyncio
import collections
import hashlib
import io
import logging
import os
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from wizard_api import config, ops_metrics, telemetry
from wizard_api.db import get_db
from wizard_api.errors import (
    api_error,
    internal_error,
    log_cause,
    public_run_message,
    stream_error,
)
from wizard_api.owner_id import is_owner_id
from wizard_api.ownership import (
    requesting_user,
    require_same_user,
    session_belongs_to_requester,
)
from wizard_api.schemas.blueprint import SessionDetailResponse
from wizard_api.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_service,
    session_service,
)
from wizard_api.session_state import (
    GATE_KEYS,
    GateNotApprovedError,
    furthest_step_before_pending_gate,
)

# Every /sessions/{session_id}/... route is served only for the session's owner
# (X-Wizard-User-Id); see wizard_api.ownership for why this sits on the router.
logger = logging.getLogger(__name__)


def _resume_id(metadata: dict, session_id: uuid.UUID) -> str | None:
    """The stored agent conversation id to resume, or None for a fresh one."""
    stored = metadata.get("agent_sdk_session_id")
    if stored is None:
        return None
    if isinstance(stored, str) and agent_service.SDK_SESSION_ID.fullmatch(stored):
        return stored
    logger.warning(
        "session %s has a malformed agent session id stored; starting a fresh conversation",
        session_id,
    )
    return None


router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(session_belongs_to_requester)],
)


class MessageAppend(BaseModel):
    user_content: str = Field(min_length=1)
    assistant_content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.max_chat_message_chars())
    locale: str | None = Field(default=None, max_length=16)


class GateReopen(BaseModel):
    reason: str = Field(default="", max_length=500)


class VersionCreate(BaseModel):
    note: str = Field(default="", max_length=512)
    content: dict | None = None


class BlueprintPatch(BaseModel):
    content: dict
    note: str = Field(default="Blueprint päivitetty", max_length=512)


# Same ceiling as solution_wizard.bpmn_sync.MAX_BPMN_XML_CHARS, checked here so an
# oversized canvas is refused with 422 before it reaches the parser.
MAX_BPMN_XML_CHARS = 2_000_000


class BpmnSyncRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=MAX_BPMN_XML_CHARS)


@router.patch("/{session_id}/blueprint", response_model=SessionDetailResponse)
def patch_blueprint(
    session_id: uuid.UUID,
    payload: BlueprintPatch,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    blueprint_service.add_version(
        db,
        session,
        note=payload.note,
        content=payload.content,
    )
    db.commit()
    db.refresh(session)
    return session_service.session_detail(db, session)


@router.get("/{session_id}/bpmn")
def get_session_bpmn(session_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    from wizard_api.services import ai_marking, bpmn_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    detail = session_service.session_detail(db, session)
    try:
        xml = bpmn_service.generate_bpmn_xml(
            detail.blueprint.model_dump(),
            session_id=str(session_id),
            agent_draft=artifact_sync.read_draft_blueprint(session.output_dir),
        )
    except bpmn_service.BpmnGenerationError as exc:
        raise internal_error(
            503, "bpmn_unavailable", "The BPMN diagram could not be produced right now.", exc
        ) from exc
    return Response(
        content=xml,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "no-store", **ai_marking.headers()},
    )


@router.post("/{session_id}/bpmn/sync", response_model=SessionDetailResponse)
def sync_session_bpmn(
    session_id: uuid.UUID,
    payload: BpmnSyncRequest,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    from wizard_api.services import bpmn_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    detail = session_service.session_detail(db, session)
    current = detail.blueprint.model_dump()
    try:
        synced = bpmn_service.sync_blueprint_from_bpmn(current, payload.xml)
    except bpmn_service.BpmnGenerationError as exc:
        raise internal_error(
            503, "bpmn_unavailable", "The BPMN diagram could not be produced right now.", exc
        ) from exc
    # A save that changed nothing in the diagram is not a new version.
    if synced == current:
        return detail
    blueprint_service.add_version(
        db,
        session,
        note="BPMN canvas sync",
        content=synced,
    )
    db.commit()
    db.refresh(session)
    return session_service.session_detail(db, session)


def _busy(exc: Exception) -> HTTPException:
    """429 for a run the sandbox has no room for yet, with when to try again."""
    from wizard_api.services import sandbox_runner

    # RunLimitError's messages are written for the user ("the sandbox is busy:
    # 3 runs are going"), so they are passed on.
    return api_error(
        429,
        "sandbox_busy",
        str(exc),
        headers={"Retry-After": str(sandbox_runner.RunLimitError.retry_after_s)},
    )


def _sandbox_unavailable(exc: Exception) -> HTTPException:
    """503 for a deployment missing a piece of the sandbox; the piece is in the log."""
    return internal_error(
        503, "sandbox_unavailable", "The sandbox is not available right now.", exc
    )


def _agent_busy(exc: agent_service.AgentUserLimitError) -> HTTPException:
    """429 for a user whose own agents are all in use, with when to try again."""
    return api_error(
        429,
        "agent_busy",
        str(exc),
        headers={"Retry-After": str(agent_service.AgentUserLimitError.retry_after_s)},
    )


def _chat_rate_limited(exc: agent_service.ChatRateLimitError) -> HTTPException:
    """429 for a user over WIZARD_MAX_CHAT_TURNS_PER_MINUTE."""
    return api_error(
        429,
        "chat_rate_limited",
        str(exc),
        headers={"Retry-After": str(exc.retry_after_s)},
    )


def _poc_dir(output_dir: str) -> str | None:
    """Resolve the session's generated PoC folder (``<output_dir>/poc``), guarding
    against path escapes. Returns None if output_dir is unset or the resolved poc
    path would fall outside it."""
    if not output_dir:
        return None
    base = os.path.realpath(output_dir)
    poc = os.path.realpath(os.path.join(base, "poc"))
    if poc != base and not poc.startswith(base + os.sep):
        return None
    return poc


@router.get("/{session_id}/poc/files")
def list_poc_files(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """List the files in the generated PoC folder so the UI can show what the
    agent produced. Empty (generated=False) until the PoC scaffolder has run."""
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        return {"generated": False, "files": []}
    from wizard_api.services import poc_service

    # The record of which inputs the user added is the api's own, not a file of the package.
    files = [
        f
        for f in poc_service.regular_files(poc)
        if os.path.basename(f) != poc_service.UPLOADED_NAMES_FILE
    ]
    # `generated` says files exist; `ready` says they add up to a package worth
    # handing over. The UI showed a download as soon as the first was true.

    problems = poc_service.package_problems(poc)
    return {
        "generated": True,
        "files": files,
        "ready": not problems,
        "problems": problems,
        "version": poc_service.package_version(poc),
        # What a run is tied to (``latest_run_package`` in the session's metadata):
        # a result whose digest differs from this one is of an older package.
        "package_digest": _approved_package_digest(poc),
    }


@router.get("/{session_id}/poc")
def download_poc(
    session_id: uuid.UUID,
    case: str | None = Query(
        None,
        description=(
            "A case id: the zip's sample_input/ carries that case's inputs and the "
            "package's own documents (a corpus and its manifest), but not the "
            "package's example inputs. This is how a case run gets its input."
        ),
    ),
    db: Session = Depends(get_db),
) -> Response:
    """Zip the generated PoC folder and return it as a download. 404 until the
    PoC scaffolder (V1 Phase 10) has produced <output_dir>/poc."""
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=404, detail="no PoC generated yet")
    # An incomplete package is worse than no package: it downloads, it installs
    # nowhere, and it runs to no effect, which reads to the user as the wizard
    # having produced something broken rather than not having finished.
    from wizard_api.services import ai_marking, poc_service

    problems = poc_service.package_problems(poc)
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "poc_package_incomplete",
                "problems": problems,
                "message": "the generated package is not complete: " + "; ".join(problems),
            },
        )
    case_files = None
    if case:
        from wizard_api.services import case_service

        try:
            case_inputs = case_service.inputs_dir(session.output_dir, case)
            case_service.get_case(session.output_dir, case)
        except case_service.CaseNotFoundError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc
        # The package's own documents (a RAG corpus and its manifest) and the
        # case's inputs (#28); its example inputs are left out.
        try:
            case_files = case_service.case_package_inputs(
                poc_service.sample_input_dir(poc), case_inputs
            )
        except case_service.InputClashError as exc:
            raise api_error(409, "input_clash", str(exc)) from exc
    parent = os.path.dirname(poc)  # so archive entries keep the poc/ prefix
    package_config = poc_service.config_with_model_timeout(poc)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Real files only: a symlink planted in the session would otherwise
        # pull a file of its choosing into the archive.
        for rel in poc_service.regular_files(poc):
            # A case run reads only its own input, and starts from no output.
            if case_files is not None and rel.split(os.sep)[0] in (
                poc_service.SAMPLE_INPUT_DIR,
                "output",
            ):
                continue
            if rel == ai_marking.MARKER_FILE:
                continue
            fp = os.path.join(poc, rel)
            if rel == poc_service.CONFIG_NAME and package_config is not None:
                zf.writestr(os.path.relpath(fp, parent), package_config)
            else:
                zf.write(fp, os.path.relpath(fp, parent))
        for source, rel in case_files or []:
            zf.write(source, os.path.join("poc", poc_service.SAMPLE_INPUT_DIR, rel))
        zf.writestr(
            os.path.join("poc", ai_marking.MARKER_FILE),
            ai_marking.marker_json(session, "poc-package"),
        )
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="poc-{session_id}.zip"',
            "Cache-Control": "no-store",
            **ai_marking.headers(),
        },
    )


@router.post("/{session_id}/poc/generate")
def generate_poc(
    session_id: uuid.UUID,
    force: bool = Query(
        False,
        description=(
            "Scaffold over a package the agent produced. Off by default: the "
            "agent wires the real component for the case's own pattern, which "
            "this deterministic scaffolder cannot reproduce."
        ),
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Scaffold the runnable PoC package from the session's active blueprint (#93).

    Deterministic and safe to repeat: a second call after a blueprint change
    rewrites the package rather than quietly leaving the old one in place. The
    generated files are the same set the V1 scaffolder produces, and they are
    served by the two endpoints above.

    When the agent already produced a package in the conversation, this reports
    it and changes nothing unless ``force`` is set.
    """
    from wizard_api.services import poc_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    # The package is scaffolded from the approved blueprint, so Gate 2 has to
    # have been approved first. Without this the button worked at Gate 2 and
    # reported "generating the PoC package from the approved blueprint" over a
    # blueprint nobody had approved.
    if session.gate_statuses.get("gate_2") != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "gate_not_approved",
                "gate": "gate_2",
                "status": session.gate_statuses.get("gate_2", "pending"),
                "message": "approve Gate 2 before generating the PoC package",
            },
        )
    # Gate 3's blueprint-first rule (#96). The newest piece of feedback decides:
    # if it was an intent change, the blueprint has to have moved since it was
    # given, or regenerating now produces a package that disagrees with the
    # document it is supposed to come from.
    from wizard_api.services import ai_marking, blueprint_service, refinement

    history = list(session.session_metadata.get("refinements") or [])
    if history:
        last = history[-1]
        if last.get("classification") == "intent":
            active = blueprint_service.get_active_version(db, session)
            try:
                refinement.check_regeneration_allowed(
                    refinement.Refinement(
                        classification="intent",
                        feedback=last.get("feedback", ""),
                        rule=refinement.INTENT_RULE,
                    ),
                    blueprint_version_at_feedback=int(last.get("blueprint_version") or 0),
                    blueprint_version_now=active.version if active else 0,
                )
            except refinement.RefinementRejectedError as exc:
                # The rule's own words, written for the user.
                raise api_error(
                    409,
                    "blueprint_change_required",
                    str(exc),
                    feedback=last.get("feedback", ""),
                ) from exc

    if _poc_dir(session.output_dir) is None:
        raise HTTPException(status_code=409, detail="session has no usable output_dir")

    detail = session_service.session_detail(db, session)
    spec = detail.target_output_spec.model_dump() if detail.target_output_spec else None
    try:
        result = poc_service.generate_poc(
            detail.blueprint.model_dump(),
            session_id=str(session_id),
            output_dir=session.output_dir,
            target_output_spec=spec,
            force=force,
        )
        return {**result, "model": ai_marking.model()}
    except poc_service.PlaceholderBlueprintError as exc:
        # Written for the user: nothing has been designed yet.
        raise api_error(422, "blueprint_placeholder", str(exc)) from exc
    except poc_service.UnscaffoldableBlueprintError as exc:
        # scaffold_guard names the blueprint's own fields to fix.
        raise api_error(422, "blueprint_not_scaffoldable", str(exc)) from exc
    except poc_service.PackageFolderError as exc:
        raise api_error(409, "package_folder", str(exc)) from exc
    except poc_service.PocGenerationError as exc:
        # The scaffolder's or the adapter's own error: a path or a stack's worth
        # of detail, for the log (#228 asked for a reason; the trace id is it).
        raise internal_error(
            503, "poc_generation_failed", "The PoC package could not be generated.", exc
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - logged with the trace id, not a bare 500 (#228)
        raise internal_error(
            500, "poc_generation_failed", "The PoC package could not be generated.", exc
        ) from exc


@router.post("", response_model=SessionDetailResponse, status_code=201)
def create_session(
    payload: SessionCreate,
    user_id: str | None = Depends(requesting_user),
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    require_same_user(user_id, payload.user_id, "user_id")
    try:
        session_service.check_metadata_patch(payload.metadata)
    except session_service.ServerOwnedMetadataError as exc:
        raise api_error(422, "server_owned_metadata", str(exc), keys=exc.keys) from exc
    session = session_service.create_session(db, payload)
    ops_metrics.sessions_created.add(
        1, {"owner": session.user_id if is_owner_id(session.user_id) else "legacy"}
    )
    return session_service.session_detail(db, session)


@router.get("", response_model=SessionListResponse)
def list_sessions(
    user_id: str = Query(min_length=1, max_length=255),
    requester: str | None = Depends(requesting_user),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    require_same_user(requester, user_id, "user_id")
    sessions = session_service.list_sessions(db, user_id)
    return SessionListResponse(
        sessions=[SessionResponse(**session_service.session_response(s)) for s in sessions]
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> SessionDetailResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session_service.session_detail(db, session)


@router.get("/{session_id}/export")
def export_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    """Everything held for the session, as a zip for the person it belongs to."""
    from wizard_api.services import ai_marking, session_export

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    # A file, not memory: a session with recordings can be large.
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as target:
        try:
            session_export.write_archive(session, target)
        except Exception:
            os.unlink(target.name)
            raise
    logger.warning("session.export session=%s", session_id)
    return FileResponse(
        target.name,
        media_type="application/zip",
        filename=f"session-{session_id}.zip",
        headers={"Cache-Control": "no-store", **ai_marking.headers()},
        background=BackgroundTask(os.unlink, target.name),
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    reason: Literal["owner", "data-subject-request", "owner-left", "retention", "other"] = "owner",
    requester: str | None = Depends(requesting_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove the session and everything kept for it. There is no undo."""
    from wizard_api.services import session_removal

    # Other routes still accept a call that names no user; this one cannot be undone.
    if requester is None:
        raise api_error(400, "user_required", "Deleting a session needs the user it is for.")
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session_removal.is_protected(session):
        raise api_error(409, "session_protected", "This session is being kept by an operator.")
    if agent_service.is_busy(str(session_id)):
        raise api_error(409, "session_busy", "The wizard is still responding. Try again soon.")
    await agent_service.end_session(str(session_id))
    try:
        await asyncio.to_thread(session_removal.remove, db, session)
    except session_removal.ProtectedSessionError as exc:
        raise api_error(409, "session_protected", "This session is being kept.") from exc
    except Exception as exc:  # noqa: BLE001 - what is left stays listed and can be removed again
        db.rollback()
        ops_metrics.session_deletes.add(1, {"reason": reason, "outcome": "failed"})
        raise internal_error(
            503, "session_delete_failed", "The session could not be deleted. Try again.", exc
        ) from exc
    # Warning level: the deployed API drops info lines, and this record must stay.
    logger.warning("session.delete session=%s reason=%s", session_id, reason)
    ops_metrics.session_deletes.add(1, {"reason": reason, "outcome": "deleted"})
    return Response(status_code=204)


@router.patch("/{session_id}", response_model=SessionDetailResponse)
def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if payload.metadata is not None:
        try:
            session_service.check_metadata_patch(payload.metadata)
        except session_service.ServerOwnedMetadataError as exc:
            raise api_error(422, "server_owned_metadata", str(exc), keys=exc.keys) from exc
    approves_gate_3 = (payload.gate_statuses or {}).get(
        "gate_3"
    ) == "approved" and session.gate_statuses.get("gate_3") != "approved"
    with _gate_span(session, payload):
        _check_gate_readiness(session, payload)
        try:
            updated = session_service.update_session(db, session, payload)
        except GateNotApprovedError as exc:
            # 409, not 422: the request is well-formed, the session is simply not in
            # a state where it may be granted. The caller (the UI or the agent) is
            # expected to show the gate rather than retry.
            raise api_error(
                409,
                "gate_not_approved",
                str(exc),
                gate=exc.gate_key,
                gate_step=exc.gate_step,
                status=exc.status,
            ) from exc
    if approves_gate_3:
        # What the user has now accepted, to tell a later change by.
        content = _approved_content(updated)
        if content is not None:
            updated = session_service.update_session(
                db, updated, SessionUpdate(metadata={session_service.APPROVED_CONTENT_KEY: content})
            )
    return session_service.session_detail(db, updated)


def _turn_failed(frame: str) -> bool:
    """Whether a chat frame the user saw says the turn failed.

    Stopping at the turn limit carries ``error: true`` for the UI, but it is the
    agent working as configured, not a failure.
    """
    return agent_service.frame_is_error(frame) and not agent_service.frame_is_turn_limit(frame)


@contextmanager
def _gate_span(session, payload: SessionUpdate) -> Iterator[None]:
    """A ``wizard.gate`` span around a request that changes a gate, with the refusal if any."""
    changes = {
        key: (session.gate_statuses.get(key, "pending"), value)
        for key, value in (payload.gate_statuses or {}).items()
        if session.gate_statuses.get(key) != value
    }
    if not changes:
        yield
        return
    # A refused approval is an answer, not a failure of the API: no error status.
    with telemetry.tracer.start_as_current_span(
        "wizard.gate", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attributes(
            {
                "gaik.session.id": str(session.id),
                "gaik.gate": ", ".join(changes),
                "gaik.gate.from": ", ".join(old for old, _ in changes.values()),
                "gaik.gate.to": ", ".join(new for _, new in changes.values()),
            }
        )
        try:
            yield
        except HTTPException as exc:
            telemetry.record_refusal(span, "gaik.gate.refused", exc)
            raise
        except Exception as exc:
            telemetry.record_failure(span, exc)
            raise
        ops_metrics.record_gate_changes(session, changes)


def _approved_content(session) -> dict[str, str] | None:
    """Digests of the solution and of the package as they are now, or None without a draft."""

    solution = artifact_sync.solution_digest(artifact_sync.read_draft_blueprint(session.output_dir))
    if solution is None:
        return None
    poc = _poc_dir(session.output_dir)
    package = _approved_package_digest(poc) if poc and os.path.isdir(poc) else ""
    return {"solution": solution, "package": package}


def _approved_package_digest(poc: str) -> str:
    """The package as approved: what a preflight reads, and the prompts the run reads.

    ``package_version`` covers the code, the settings and the schema. The
    extraction instructions under ``prompts/`` are read at run time and decide
    the result as much as the code does, so a change to them after Gate 3 is a
    change to what was accepted too.
    """
    from wizard_api.services import poc_service

    digest = hashlib.sha256(poc_service.package_version(poc).encode())
    prompts = os.path.join(poc, "prompts")
    if os.path.isdir(prompts) and not os.path.islink(prompts):
        for name in poc_service.regular_files(prompts):
            digest.update(name.encode())
            with open(os.path.join(prompts, name), "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()[:16]


def _gate_reopened_by_turn(db: Session, session) -> str | None:
    """The number of the gate this turn's change reopened, or None. Best-effort."""
    try:
        # The agent's own tool may have changed the row behind this copy.
        db.refresh(session)
        if not _reopen_if_approved_content_changed(db, session):
            return None
        reopened = session.session_metadata.get(session_service.REOPENED_KEY) or {}
        return str(reopened.get("gate", ""))[-1:] or None
    except Exception:  # noqa: BLE001 - the reply is stored whatever happens here
        logger.warning("approved content could not be compared", exc_info=True)
        db.rollback()
        return None


def _reopen_if_approved_content_changed(db: Session, session) -> bool:
    """After a chat turn: reopen the gate whose approved content the turn changed.

    Once Gate 3 is approved the solution and its package are what the user
    accepted. Asked in the chat for another field after that, the agent
    changed its files and said "ok", and every gate stayed approved: the
    approvals then covered a solution nobody had reviewed, and the deployable
    package was offered on a test run of the old one. The agent has a tool to
    reopen a gate and is told to use it, but an approval must not depend on
    that, so the server compares what is on disk with what was approved.

    A changed solution (fields, steps, components, participants) reopens Gate
    2; a changed package alone reopens Gate 3. Before Gate 3 is approved
    nothing is compared: refining the PoC is what that gate's loop is for
    (#96). Best-effort, like the rest of the sync. True when a gate was reopened.
    """
    if session.gate_statuses.get("gate_3") != "approved":
        return False
    now = _approved_content(session)
    if now is None:
        return False
    approved = session.session_metadata.get(session_service.APPROVED_CONTENT_KEY)
    if not isinstance(approved, dict):
        # A session approved before this was kept: start from what is there now.
        session_service.update_session(
            db, session, SessionUpdate(metadata={session_service.APPROVED_CONTENT_KEY: now})
        )
        return False
    if approved.get("solution") != now["solution"]:
        gate_key = "gate_2"
    elif approved.get("package") != now["package"]:
        gate_key = "gate_3"
    else:
        return False
    try:
        session_service.reopen_gate(db, session, gate_key, by="change")
    except session_service.GateNotReopenableError:
        return False
    logger.info("session %s: %s reopened, its approved content changed", session.id, gate_key)
    return True


@router.post("/{session_id}/gates/{gate}/reopen", response_model=SessionDetailResponse)
def reopen_gate(
    session_id: uuid.UUID,
    gate: int = Path(ge=1, le=4),
    payload: GateReopen | None = None,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    """Take back the approval of a gate, and of the gates after it, for a change.

    The panel's "Change" on an approved gate. The session goes back to that
    gate's step with it pending (``session_service.reopen_gate``); the agent
    hears of it with the next message. Refused while the agent is mid-turn, as
    an approval is: the turn was started on the state it was told.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if agent_service.is_busy(str(session_id)):
        raise api_error(
            409, "agent_busy", "The wizard is still working on this step; wait for its reply."
        )
    try:
        updated = session_service.reopen_gate(
            db, session, f"gate_{gate}", reason=payload.reason if payload else "", by="user"
        )
    except session_service.GateNotReopenableError as exc:
        raise api_error(
            409, "gate_not_approved", str(exc), gate=exc.gate_key, status=exc.status
        ) from exc
    logger.info("session %s: gate_%s reopened from the panel", session_id, gate)
    return session_service.session_detail(db, updated)


def _reopen_gate_for_agent(session_id: str, gate: int, reason: str) -> str:
    """The agent's reopen_gate tool, in its own database session; returns what it is told."""
    from wizard_api.db import SessionLocal

    with SessionLocal() as db:
        session = session_service.get_session(db, uuid.UUID(session_id))
        if session is None:
            return "The session no longer exists."
        try:
            session_service.reopen_gate(db, session, f"gate_{gate}", reason=reason, by="agent")
        except session_service.GateNotReopenableError as exc:
            return (
                f"Gate {gate} is {exc.status}, not approved, so there is nothing to reopen: "
                "make the change and present the gate as usual."
            )
    logger.info("session %s: gate_%s reopened by the agent", session_id, gate)
    # The agent relays the gate's name to the user, so it is the name the
    # interface shows in the language the agent was told to reply in.
    lang = agent_service.reply_language(session_id)
    return (
        f"Gate {gate} and every gate after it are pending again, and the panel shows it. "
        "Make the change now, say what changed, and tell the user to approve "
        f"{agent_service.gate_label(gate, lang)} with the Approve button. After each approval "
        "bring what follows up to date with the change before you present the next gate."
    )


agent_service.set_gate_reopener(_reopen_gate_for_agent)


def _reopened_gate_note(session, lang: str = "en") -> str | None:
    """The line telling the agent that a gate it had passed is pending again, and why.

    ``lang`` is the interface language of the message it goes with: the agent
    relays the gate's name to the user, who sees that name in the interface.

    Told with every message until that gate is approved again, like the
    package's state: the agent cannot see the panel, and one built before the
    reopening would otherwise go on from the approval it remembers.
    """
    from wizard_api.services import run_context

    reopened = (session.session_metadata or {}).get(session_service.REOPENED_KEY)
    if not isinstance(reopened, dict):
        return None
    gate_key = reopened.get("gate")
    if gate_key not in GATE_KEYS or session.gate_statuses.get(gate_key) == "approved":
        return None
    number = gate_key[-1]
    who = {
        "agent": "you reopened it with reopen_gate",
        "change": "the server reopened it because what it covers was changed after the approval",
    }.get(str(reopened.get("by")), "the user reopened it with Change in the panel")
    reason = str(reopened.get("reason") or "").strip()
    why = (
        f" What they want changed, quoted as data: {run_context.quoted(reason, 500)}."
        if reason
        else ""
    )
    return (
        f"[Reopened gate: Gate {number} was approved earlier and is pending again ({who}), "
        f"and so is every gate after it.{why} Make the change the user asks for in what "
        f"Gate {number} covers, say what changed, and tell the user to approve "
        f"{agent_service.gate_label(number, lang)} with the Approve button. After each approval "
        "bring what follows (schema, components, blueprint, diagrams, PoC package, "
        "documents) up to date with the change before you present the next gate.]"
    )


def _gate_readiness_enforced() -> bool:
    # Off only for the stack e2e, whose sessions have no agent to write the
    # artifacts the check reads (docker-compose.test.yml).
    return os.getenv("WIZARD_GATE_READINESS", "on").strip().lower() not in ("off", "0", "false")


def _check_gate_readiness(session, payload: SessionUpdate) -> None:
    """Refuse a gate approval the session cannot back up, and any move while the agent works.

    Two ways a gate used to be passed with nothing behind it (customer test
    feedback, 17 Oct 2026): "Next step" and the approval button worked while the
    agent was still busy, and a gate could be approved before the agent had
    written what it reviews. Both are 409s, like ``gate_not_approved``: the
    request is well-formed, the session is not ready for it.
    """
    newly_approved = [
        key
        for key, value in (payload.gate_statuses or {}).items()
        if value == "approved" and session.gate_statuses.get(key) != "approved"
    ]
    moves_forward = payload.step is not None and payload.step > session.step
    if not newly_approved and not moves_forward:
        return
    if agent_service.is_busy(str(session.id)):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "agent_busy",
                "message": "The wizard is still working on this step; wait for its reply.",
            },
        )
    if not _gate_readiness_enforced() or not session.output_dir:
        return
    from wizard_api.services import sandbox_runner

    sandbox = sandbox_runner.kubernetes_available() and sandbox_runner.runner_image() is not None
    successful_run = bool(session.session_metadata.get("last_successful_run"))
    for key in newly_approved:
        missing = artifact_sync.gate_missing(
            key, session.output_dir, successful_run=successful_run, sandbox=sandbox
        )
        if missing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "gate_not_ready",
                    "gate": key,
                    "missing": missing,
                    "message": (
                        f"{key} cannot be approved yet: the wizard has not produced {missing}."
                    ),
                },
            )
        if key == "gate_3" and sandbox and _successful_run_is_of_another_package(session):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "gate_not_ready",
                    "gate": key,
                    "missing": "a successful sandbox run of the package as it is now",
                    "reason": "package_changed",
                    "message": (
                        "The last successful test run does not say which package it tested. "
                        "Run the test again, then approve."
                        if _successful_run_package(session) == session_service.UNKNOWN_RUN_PACKAGE
                        else "The package changed after the last successful test run. "
                        "Run the test again, then approve."
                    ),
                },
            )


def _successful_run_package(session) -> Any:
    return session.session_metadata.get(session_service.SUCCESSFUL_RUN_PACKAGE_KEY)


def _successful_run_is_of_another_package(session) -> bool:
    """Whether the run that passed tested a package other than the one on disk.

    A test run that succeeded stayed the session's proof whatever happened to
    the package afterwards: the agent fixed the PoC, the PoC tab still showed
    the old result with its approve button, and Gate 3 could be approved on a
    run of a package that no longer existed (12 Nov 2026). The digest kept with
    the run (``create_poc_run``) says which package it tested.

    False without a kept digest: a run recorded before the digest was kept
    opens the gate as it did. True for a run recorded since without one
    (``_record_successful_run``): it cannot be compared, so it proves nothing
    about the package on disk.
    """
    tested = _successful_run_package(session)
    if not isinstance(tested, str) or not tested:
        return False
    if tested == session_service.UNKNOWN_RUN_PACKAGE:
        return True
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        return False
    return _approved_package_digest(poc) != tested


@router.post("/{session_id}/messages", response_model=SessionDetailResponse)
def append_messages(
    session_id: uuid.UUID,
    payload: MessageAppend,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    updated = session_service.append_messages(
        db,
        session,
        payload.user_content,
        payload.assistant_content,
    )
    return session_service.session_detail(db, updated)


@router.post("/{session_id}/chat")
async def chat(
    session_id: uuid.UUID,
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Send a user message to the live V1 wizard agent and stream its reply as
    SSE (UI chat contract). On turn end the exchange is persisted to the
    session's ``metadata["messages"]`` so a reload shows the full transcript.

    The turn runs as its own task (``agent_service.Turn``), not inside this
    response: a page that reloads or closes mid-reply does not stop it, and
    ``GET /chat/stream`` joins it again.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Limits count per session owner: the ownership dependency has already
    # checked that the requesting user (X-Wizard-User-Id) is this owner.
    owner = session.user_id
    try:
        # Before the agent is woken: a refused message must not start one.
        agent_service.check_chat_rate(owner)
    except agent_service.ChatRateLimitError as exc:
        raise _chat_rate_limited(exc) from exc

    # Before the agent is asked for: a live agent whose interface language
    # changed is told so in a turn of its own, which must not run into the
    # reply still on its way.
    if agent_service.running_turn(str(session_id)) is not None:
        raise HTTPException(status_code=409, detail="The wizard is still responding.")

    metadata = dict(session.session_metadata)
    try:
        agent = await agent_service.get_or_create_session(
            str(session_id),
            session.output_dir,
            payload.locale,
            resume_id=_resume_id(metadata, session_id),
            transcript=metadata.get("messages"),
            user_id=owner,
        )
    except agent_service.AgentUserLimitError as exc:
        raise _agent_busy(exc) from exc
    except agent_service.AgentCapacityError as exc:
        raise api_error(503, "agent_capacity", str(exc)) from exc
    except agent_service.AgentNotConfiguredError as exc:
        raise internal_error(
            503, "agent_unavailable", "The wizard is not available right now.", exc
        ) from exc

    if agent["lock"].locked() or agent_service.running_turn(str(session_id)) is not None:
        raise HTTPException(status_code=409, detail="The wizard is still responding.")
    agent_service.record_chat_turn(owner)
    # Registered before the next await, so a second message that arrives while
    # this one is being prepared is refused instead of starting beside it.
    turn = agent_service.begin_turn(str(session_id), payload.message)

    try:
        # The agent was started above, which takes a while: a gate reopened or
        # approved in the panel meanwhile is what this turn is told.
        await asyncio.to_thread(db.refresh, session)
        user_message = payload.message
        # The agent gets the UI's gate state with every message; the transcript
        # keeps what the user wrote (#173).
        run_note, seen_run = await asyncio.to_thread(_latest_run_note, session)
        view_note = None
        blueprint_note = None
        user_changed = artifact_sync.user_changed_blueprint(db, session)
        if session.step >= artifact_sync.STEP_BPMN or user_changed:
            blueprint = session_service.session_detail(db, session).blueprint.model_dump()
            view_written = await asyncio.to_thread(
                _write_ui_view, blueprint, str(session_id), session.output_dir
            )
            if view_written and session.step >= artifact_sync.STEP_BPMN:
                view_note = _UI_VIEW_NOTE
            if user_changed:
                blueprint_note = _user_blueprint_note(session.active_version, view_written)
        package_note = await asyncio.to_thread(_package_note, session)
        lang = (payload.locale or "fi").split("-")[0].lower()
        reopened_note = _reopened_gate_note(session, lang)
        gate1_note = await asyncio.to_thread(_gate1_missing_note, session)
        notes = [
            note
            for note in (
                reopened_note,
                gate1_note,
                run_note,
                package_note,
                view_note,
                blueprint_note,
            )
            if note
        ]
        agent_message = agent_service.with_gate_context(
            user_message, session.step, session.gate_statuses, notes or None
        )

        notice_text = agent_service.RESTART_NOTICE.get(lang, agent_service.RESTART_NOTICE["en"])
        output_dir = session.output_dir
        # One wizard.turn span per message, with the turn's model usage under it.
        # Numbers, statuses and the session id only: no text and no user identity.
        turn_attributes = {
            "gaik.session.id": str(session_id),
            "gaik.step": session.step,
            "gaik.gate_statuses": ",".join(
                f"{key}={value}" for key, value in sorted(session.gate_statuses.items())
            ),
        }
        # This request's own database session is not needed while the reply
        # streams: ending its transaction gives its connection back to the
        # pool. Before the turn's task exists, which opens a session of its own.
        await asyncio.to_thread(db.commit)
    except BaseException:
        await agent_service.end_turn(str(session_id), turn)
        raise

    first = agent  # frames() may restart the agent; both clients' usage counts

    def turn_agents():
        # A restart means the first agent's failed query was answered by the new one.
        return [(first, False)] if agent is first else [(first, True), (agent, False)]

    async def frames(turn_db: Session, turn_session):
        """The turn's frames; what the turn leaves behind is stored once they are through."""
        nonlocal agent
        parts: list[str] = []
        if agent.get("notice_pending"):
            # The agent had to be re-bootstrapped from the stored transcript:
            # say so once, in the chat, instead of silently starting over (#174).
            agent["notice_pending"] = False
            parts.append(notice_text)
            yield agent_service.sse({"delta": notice_text})
        replied = False
        async for frame in agent_service.stream_turn_for(agent, agent_message, parts):
            if (
                agent.get("resumed") == "sdk"
                and not agent.get("resume_verified")
                and not replied
                and agent_service.frame_is_error(frame)
                and not agent_service.frame_is_turn_limit(frame)
            ):
                # The resumed CLI session was not there after all (its file is
                # gone): drop the id, start again from the stored transcript,
                # say so, and give this message a second go (#174). A session
                # that already replied, or stopped at the turn limit, was there.
                await agent_service.end_session(str(session_id))
                try:
                    agent = await agent_service.get_or_create_session(
                        str(session_id),
                        output_dir,
                        payload.locale,
                        resume_id=None,
                        transcript=metadata.get("messages") or [],
                        user_id=owner,
                    )
                except agent_service.AgentUserLimitError as exc:
                    yield agent_service.sse(stream_error("agent_busy", str(exc)))
                    return
                except agent_service.AgentCapacityError as exc:
                    yield agent_service.sse(stream_error("agent_capacity", str(exc)))
                    return
                except agent_service.AgentNotConfiguredError as exc:
                    log_cause("agent_unavailable", exc)
                    yield agent_service.sse(
                        stream_error("agent_unavailable", "The wizard is not available right now.")
                    )
                    return
                agent["notice_pending"] = False
                parts.clear()
                parts.append(notice_text)
                yield agent_service.sse({"delta": notice_text})
                async for retry_frame in agent_service.stream_turn_for(agent, agent_message, parts):
                    yield retry_frame
                break
            if '"delta"' in frame:
                replied = True
            yield frame
        agent["resume_verified"] = True
        sdk_id = agent.get("sdk_session_id")
        if sdk_id and sdk_id != metadata.get("agent_sdk_session_id"):
            # Remembered so the next process can resume this CLI session. A
            # server write: update_session, not the PATCH route that refuses it.
            await asyncio.to_thread(
                session_service.update_session,
                turn_db,
                turn_session,
                SessionUpdate(metadata={"agent_sdk_session_id": sdk_id}),
            )
        assistant_text = "".join(parts).strip()
        # Before the exchange is stored: a change that reopened a gate is said
        # in the reply itself, so the chat and the panel tell the same story.
        reopened = await asyncio.to_thread(_gate_reopened_by_turn, turn_db, turn_session)
        if reopened and assistant_text:
            reopened_text = agent_service.reopened_notice(lang, reopened)
            assistant_text = f"{assistant_text}\n\n{reopened_text}"
            yield agent_service.sse({"delta": f"\n\n{reopened_text}"})
        if assistant_text:
            # Persist off the event loop (sync SQLAlchemy commit).
            await asyncio.to_thread(
                session_service.append_messages,
                turn_db,
                turn_session,
                user_message,
                assistant_text,
            )
            if seen_run:
                # Told once: the next message does not repeat the same run.
                await asyncio.to_thread(
                    session_service.update_session,
                    turn_db,
                    turn_session,
                    SessionUpdate(metadata={"agent_seen_run": seen_run}),
                )
        # The agent writes its artifacts to disk as the conversation moves;
        # pull them into the session so the workspace keeps up (#141).
        # Best-effort, as it always was: the reply is whole and stored by now,
        # and must not end in an error because a file could not be read.
        try:
            await asyncio.to_thread(_sync_artifacts_and_advance, turn_db, turn_session)
        except Exception:  # noqa: BLE001
            logger.warning(
                "artifacts of session %s could not be adopted", session_id, exc_info=True
            )
            await asyncio.to_thread(turn_db.rollback)

    # The request's database session closes with the request and the turn can
    # outlive it, so the turn opens its own, the way the request got its one.
    open_db = request.app.dependency_overrides.get(get_db, get_db)

    def open_turn_session(turn_db: Session):
        """The session row for the turn, with no transaction left open behind it.

        The agent works for minutes before the turn writes anything. A
        transaction held idle for that long keeps a pooled connection per turn,
        and the pool is smaller than the number of agents that may be live.
        Every write re-reads the row under a lock, so nothing is lost by
        letting the connection go.
        """
        row = session_service.get_session(turn_db, session_id)
        turn_db.commit()
        return row

    async def run_turn() -> None:
        opened = open_db()
        try:
            turn_db = next(opened)
            turn_session = await asyncio.to_thread(open_turn_session, turn_db)
            if turn_session is None:  # deleted between the request and here
                return
            # A turn that will never finish must not hold the session for good:
            # nothing else can end it now that it does not live in a response.
            async with asyncio.timeout(config.turn_timeout_seconds()):
                async for frame in telemetry.traced_turn(
                    frames(turn_db, turn_session),
                    turn_attributes,
                    turn_agents,
                    agent_service._model(),
                    _turn_failed,
                ):
                    # Each reader keeps its own connection alive (Turn.subscribe).
                    if not agent_service.is_heartbeat(frame):
                        await turn.publish(frame)
        except TimeoutError:
            logger.error("chat turn of session %s ended at the time limit", session_id)
            # The agent's process is in an unknown state: the next message
            # starts a new one, which resumes the conversation.
            await agent_service.end_session(str(session_id))
            await turn.publish(
                agent_service.sse(
                    {
                        "error": True,
                        "message": "The wizard took too long over this reply and was stopped. "
                        "What it wrote so far is kept; send your message again to go on.",
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001 - the chat is told; the cause is in the log
            reference = uuid.uuid4().hex[:8]
            logger.error("chat turn failed [%s]", reference, exc_info=exc)
            await turn.publish(
                agent_service.sse(
                    {
                        "error": True,
                        "message": "The wizard could not finish its reply "
                        f"(reference {reference}). Please try again.",
                    }
                )
            )
        finally:
            # Whatever closing the database session does, the turn is taken
            # away: one left registered would refuse every later message.
            try:
                opened.close()
            except Exception:  # noqa: BLE001
                logger.warning("the turn's database session did not close", exc_info=True)
            finally:
                await agent_service.end_turn(str(session_id), turn)

    # Kept on the turn: a task nothing refers to can be collected mid-run.
    turn.task = asyncio.create_task(run_turn())
    return StreamingResponse(
        turn.subscribe(),
        media_type="text/event-stream",
        headers=agent_service.sse_headers(),
    )


@router.post("/{session_id}/agent/end")
async def end_agent(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Release the agent held for this session; the conversation stays.

    A live agent is a process in the api pod, and they are few
    (WIZARD_MAX_LIVE_AGENTS). It was released only after 30 idle minutes or
    when its place was needed, so a user who had finished kept one from the
    next. The session, its files and the stored conversation are untouched:
    the next message starts the agent again from where it left off.
    """
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if agent_service.is_busy(str(session_id)):
        raise api_error(409, "agent_busy", "The wizard is still replying; wait for it to finish.")
    ended = await agent_service.end_session(str(session_id))
    if ended:
        logger.info("session %s: agent ended by the user", session_id)
    return {"ended": ended}


@router.get("/{session_id}/chat/stream")
async def chat_stream(session_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Join the reply that is on its way for this session, from its first frame.

    For a page loaded in the middle of a turn: the session detail names the
    message being answered (``pending_turn``) and this stream brings the reply
    so far and the rest of it. 204 when no turn is running; the stored
    transcript then has everything.
    """
    turn = agent_service.running_turn(str(session_id))
    if turn is None:
        return Response(status_code=204)
    # The ownership check read the session through this request's database
    # session; its connection is not held for as long as the reply streams.
    await asyncio.to_thread(db.commit)
    return StreamingResponse(
        turn.subscribe(),
        media_type="text/event-stream",
        headers=agent_service.sse_headers(),
    )


_UI_VIEW_NOTE = (
    "[The diagram the user sees in the Workflow tab is "
    f"{artifact_sync.UI_VIEW_BPMN_FILE} in the output directory, "
    "generated by the server from the current blueprint; it is not your workflow.bpmn. "
    f"{artifact_sync.UI_VIEW_MAPPING_FILE} gives each element id the blueprint field it "
    f"came from, as a path into {artifact_sync.UI_VIEW_BLUEPRINT_FILE}.]"
)


def _write_ui_view(blueprint: dict[str, Any], session_id: str, output_dir: str) -> bool:
    """Write the diagram the user sees, and the blueprint behind it, for the agent.

    The Workflow tab renders BPMN generated from the session blueprint, and the
    agent only knew its own workflow.bpmn, so asked why a node or lane was there
    it explained a different diagram or found nothing. Best-effort: a chat turn
    must not fail because the diagram could not be generated or written.
    """
    from wizard_api.services import bpmn_service

    try:
        xml, mapping, v1 = bpmn_service.generate_bpmn_view(
            blueprint,
            session_id=session_id,
            agent_draft=artifact_sync.read_draft_blueprint(output_dir),
        )
    except Exception:  # noqa: BLE001 - see the docstring
        logger.warning("UI diagram for the agent could not be generated", exc_info=True)
        return False
    return artifact_sync.write_ui_view(output_dir, xml, mapping, v1)


def _user_blueprint_note(version: int, view_written: bool) -> str:
    """The line telling the agent that the blueprint is the user's, not its draft.

    A save in the Blueprint form or the diagram changes the session blueprint
    only, so the agent went on from its own use_case.blueprint.json as if the
    user had changed nothing. Told with every message while it holds, like the
    package's state: it stays true until the agent's draft catches up.
    """
    draft = artifact_sync.DRAFT_BLUEPRINT_FILE
    if not view_written:
        return (
            f"[The user changed the blueprint in the workspace after your {draft} was last "
            f"adopted; the current blueprint is version {version}, and your {draft} is not "
            "current. Ask the user what they changed before you rewrite it.]"
        )
    return (
        f"[The user changed the blueprint in the workspace after your {draft} was last "
        f"adopted; the current blueprint is version {version}. Its name, description, "
        f"workflow steps and integration targets as the user saved them are in "
        f"{artifact_sync.UI_VIEW_BLUEPRINT_FILE}, written by the server; the rest of that file "
        f"is filled in by the server for the diagram. Take the user's changes from it into "
        f"{draft} when you next write that file, and keep your own specification for "
        "everything else.]"
    )


def _latest_run_note(session) -> tuple[str | None, str | None]:
    """The line about the latest PoC run the agent has not heard about, and that run's id.

    The id comes back only for a finished run, which the caller marks as told
    once the turn is through; a run still going is mentioned and told again
    later. Best-effort: a chat message never fails because the run cannot be
    read (no sandbox, the Job already cleaned up).
    """
    from wizard_api.services import run_context, sandbox_runner

    metadata = session.session_metadata or {}
    run_id = metadata.get("latest_run")
    if not run_id or run_id == metadata.get("agent_seen_run") or not session.output_dir:
        return None, None
    try:
        # Saved when the run ended (stream_poc_run); the Job may be gone by now.
        summary = run_context.saved(session.output_dir, run_id)
        if summary is not None:
            return run_context.line(summary), run_id
        runner = sandbox_runner.SandboxRunner()
        status = runner.status(run_id, session_id=str(session.id))
        if not status.finished:
            return run_context.running_line(run_id), None
        log = runner.read_log(run_id)
        spec = _run_output_spec(session.id)
        return run_context.collect(session.output_dir, run_id, status, log, spec), run_id
    except Exception:  # noqa: BLE001 - see the docstring
        logger.warning("latest run %s could not be read for the agent", run_id, exc_info=True)
        return None, None


def _gate1_missing_note(session) -> str | None:
    """The line saying what keeps Gate 1's approve button disabled, while something does.

    The panel will not approve Gate 1 until the draft has the current process
    and the expected value, and a placeholder such as "unknown" counts as
    missing. The agent cannot see the panel: in a UC05 run it had written
    expected_value "unknown", kept asking the user to press a button that was
    disabled, and the session stood still. Told with every message while the
    draft is there and Gate 1 waits, like the package's state.
    """
    if session.gate_statuses.get("gate_1") == "approved" or not session.output_dir:
        return None
    try:
        draft = artifact_sync.read_draft_blueprint(session.output_dir)
        if draft is None:
            return None
        missing = session_service.gate1_missing_from_draft(draft)
    except Exception:  # noqa: BLE001 - best-effort, like the package's line
        logger.warning("Gate 1 fields could not be read for the agent", exc_info=True)
        return None
    if not missing:
        return None
    fields = " and ".join(missing)
    return (
        f"[Gate 1 cannot be approved yet: the page keeps its Approve button disabled and "
        f"shows {fields} in use_case.blueprint.json as missing. An empty value or a "
        'placeholder such as "unknown" or "n/a" counts as missing. If the conversation '
        "has answered it, write the answer there; if you infer it, write it and record "
        "a clearly labelled assumption; otherwise ask the user for it. Do not ask the "
        "user to approve Gate 1 until it is filled in.]"
    )


def _package_note(session) -> str | None:
    """The line about what stops this session's package, while something does.

    Unlike a run, this is told with every message: it is the package's state, and
    it stays true until the package changes. The check parses the package and runs
    none of it. Best-effort, like the run's line.
    """
    from wizard_api.services import poc_service, run_context

    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        return None
    try:
        problems = poc_service.package_problems(poc)
        if problems:
            return run_context.package_line(problems)
        return run_context.check_line(session.output_dir, poc_service.package_version(poc))
    except Exception:  # noqa: BLE001 - see the docstring
        logger.warning("package check could not be read for the agent", exc_info=True)
        return None


def _sync_artifacts_and_advance(db: Session, session) -> None:
    """After a chat turn: adopt the agent's draft blueprint, then let the step
    follow the agent as far as the gates allow.

    The wizard writes ``use_case.blueprint.json`` at Phase 3 (spec generation),
    right before Gate 1. Its appearance means gathering is complete → advance to
    Gate 1 so the user cannot skip it. Its *content* is the blueprint the
    workspace shows, and BPMN is generated from that, so reading it here is what
    makes blueprint, schema and diagram follow the conversation (#141) instead
    of staying on the seed blueprint.

    After Gate 1 the step used to stay at 4 for the rest of the conversation
    (#169). Now the artifacts the agent writes (schema, components, BPMN,
    package) say which phase it has reached, and the session moves there, but
    never past a gate the user has not approved: it stops on the gate step and
    waits. The move happens only when the artifacts show a *new* phase since
    the last turn, so a user who stepped back to review something is not pushed
    forward again by every message.

    Best-effort by design: the files are written mid-conversation and a chat
    turn must not fail because one was missing or half-written.
    """
    # The turn can have changed the row behind this copy: the agent's
    # reopen_gate tool moves the step and the gates in a session of its own.
    db.refresh(session)
    draft = artifact_sync.read_draft_blueprint(session.output_dir)
    if draft is not None:
        artifact_sync.sync_blueprint_from_draft(db, session, draft)
    if _reopen_if_approved_content_changed(db, session):
        # The session now waits on the reopened gate; the step is not moved on.
        return
    reached = artifact_sync.step_reached(session.output_dir)
    if reached is None:
        return
    seen = session.session_metadata.get("agent_step")
    # After a gate was reopened the later phases' artifacts are on disk
    # already, so "a new phase since the last turn" never comes: the session
    # follows them as far as the gates allow until it is back where they are.
    replaying = bool(session.session_metadata.get(session_service.REPLAY_KEY))
    if isinstance(seen, int) and reached <= seen and not replaying:
        return
    target = furthest_step_before_pending_gate(session.step, reached, session.gate_statuses)
    metadata: dict[str, Any] = {"agent_step": reached}
    if replaying and target >= reached:
        metadata[session_service.REPLAY_KEY] = False
    payload = SessionUpdate(metadata=metadata)
    if target > session.step:
        payload.step = target
    session_service.update_session(db, session, payload)


@router.post("/{session_id}/versions", response_model=SessionDetailResponse)
def create_blueprint_version(
    session_id: uuid.UUID,
    payload: VersionCreate,
    db: Session = Depends(get_db),
) -> SessionDetailResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    blueprint_service.add_version(
        db,
        session,
        note=payload.note or f"Vaihe {session.step}",
        content=payload.content,
    )
    db.commit()
    db.refresh(session)
    return session_service.session_detail(db, session)


# ---------------------------------------------------------------------------
# Sandbox PoC runs (#91 SandboxRunner, #92 SSE log stream)
# ---------------------------------------------------------------------------


def _settled_status(runner: Any, run_id: str) -> Any:
    """The run's terminal status if the Job has settled, else None (#228).

    Used when the log stream fails: the stream is a view of the run, not the run.
    A short wait covers the controller lag between the container's exit and the
    Job's status; a run still going, or a Job that cannot be read, is None.
    """
    try:
        status = runner.final_status(run_id, wait_seconds=5.0)
    except Exception:  # noqa: BLE001 - the stream error is reported instead
        return None
    return status if status.finished else None


def _run_output_spec(session_id: uuid.UUID) -> dict[str, Any] | None:
    """The session's output spec, for the checks of a run's output; in its own session scope.

    None when it cannot be read: the checks that need no spec are still made.
    """
    from wizard_api.db import SessionLocal
    from wizard_api.routers.cases import output_spec

    try:
        with SessionLocal() as db:
            session = session_service.get_session(db, session_id)
            if session is None or not session.output_dir:
                return None
            return output_spec(db, session)
    except Exception:  # noqa: BLE001 - a run is saved and told whatever happens here
        logger.warning("output spec of session %s could not be read", session_id, exc_info=True)
        return None


def _save_run_for_agent(
    runner: Any, output_dir: str, run_id: str, status: Any, spec: dict[str, Any] | None = None
) -> bool:
    """Save a finished run where the agent reads it. Best-effort: never breaks the stream.

    True once the session holds the run; the Job can go then.
    """
    from wizard_api.services import run_context

    if not os.path.isdir(output_dir):  # the session was deleted during the run
        return False
    try:
        run_context.save(output_dir, run_id, status, runner.read_log(run_id), spec)
    except Exception:  # noqa: BLE001
        logger.warning("run %s could not be saved for the agent", run_id, exc_info=True)
        return False
    return True


def _save_check_for_agent(runner: Any, output_dir: str, run_id: str, status: Any) -> bool:
    """Keep a finished preflight's result for the agent. Best-effort, like a run's."""
    from wizard_api.services import run_context

    if not os.path.isdir(output_dir):  # the session was deleted during the check
        return False
    try:
        version = runner.check_version(run_id)
        if version:
            run_context.save_check(output_dir, version, status, runner.read_log(run_id))
    except Exception:  # noqa: BLE001
        logger.warning("preflight %s could not be saved for the agent", run_id, exc_info=True)
        return False
    return True


def _remove_run_quietly(runner: Any, run_id: str) -> None:
    """Remove a Job whose result the session holds. The TTL reaps it otherwise."""
    try:
        runner.delete_run(run_id)
    except Exception:  # noqa: BLE001 - the Job may be gone already
        logger.info("run %s was not removed after saving", run_id, exc_info=True)


def _record_successful_run(session_id: uuid.UUID, run_id: str) -> None:
    """Note a run that succeeded, in its own session scope."""
    from wizard_api.db import SessionLocal

    with SessionLocal() as db:
        session = session_service.get_session(db, session_id)
        if session is None:
            return
        # A gate reopened while the run was going takes the run's place as the
        # session's latest (reopen_gate): the run tested the solution as it was
        # before the change, so it proves nothing about the one being approved.
        if run_id in (session.session_metadata.get(session_service.VOIDED_RUNS_KEY) or []):
            logger.info("run %s of session %s was voided by a reopened gate", run_id, session_id)
            return
        latest = session.session_metadata.get("latest_run")
        if latest is not None and latest != run_id:
            logger.info(
                "run %s of session %s ended after a newer one; not recorded", run_id, session_id
            )
            return
        if latest is None and session.session_metadata.get(session_service.REOPENED_KEY):
            logger.info("run %s of session %s ended after a gate was reopened", run_id, session_id)
            return
        # Only the keys this writes: update_session merges them into the row as it is now.
        metadata: dict[str, Any] = {"last_successful_run": run_id}
        # The package this run was started on, kept when it was (create_poc_run).
        tested = (
            session.session_metadata.get(session_service.RUN_PACKAGE_KEY)
            if latest == run_id
            else None
        )
        if tested:
            metadata[session_service.SUCCESSFUL_RUN_PACKAGE_KEY] = tested
        elif session_service.SUCCESSFUL_RUN_PACKAGE_KEY in session.session_metadata:
            # The session keeps digests and this run has none. Writing None here
            # read as "recorded before the digest was kept" and opened Gate 3
            # without comparing. The older digest is not this run's, and the
            # package on disk may have changed while the run was going, so
            # neither is written: the gate stays closed until a run with a
            # known package succeeds.
            metadata[session_service.SUCCESSFUL_RUN_PACKAGE_KEY] = (
                session_service.UNKNOWN_RUN_PACKAGE
            )
        session_service.update_session(db, session, SessionUpdate(metadata=metadata))


@router.post("/{session_id}/runs", status_code=201)
@telemetry.sandbox_start_span("run")
def create_poc_run(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Start a sandbox run of this session's generated PoC package.

    The package must be complete — an unwired one downloads and does nothing,
    and starting a ten-minute Job to prove that helps nobody. Gate 3 is where
    the run belongs, so the gate below it has to be approved first.
    """
    from wizard_api.services import poc_service, sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    if session.gate_statuses.get("gate_2") != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "gate_not_approved",
                "gate": "gate_2",
                "message": "approve Gate 2 before running the PoC",
            },
        )

    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=409, detail="no PoC package to run yet")
    problems = poc_service.package_problems(poc)
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "poc_package_incomplete",
                "problems": problems,
                "message": "the package is not complete: " + "; ".join(problems),
            },
        )

    # Before the run is created: a change made while it starts then reads as a
    # change after the run, never as part of what it tested.
    package = _approved_package_digest(poc)
    try:
        runner = sandbox_runner.SandboxRunner()
        run_id = runner.create_run(str(session_id), user_id=session.user_id)
    except sandbox_runner.RunLimitError as exc:
        raise _busy(exc) from exc
    except sandbox_runner.SandboxNotConfiguredError as exc:
        # 503, not 500: the deployment is missing a piece. Which one is for the
        # operator, in the log under the trace id; the user hears it is unavailable.
        raise _sandbox_unavailable(exc) from exc

    # The agent hears about this run with the next chat message (run_context, #96).
    # The digest says which package the run tested, for Gate 3 (_check_gate_readiness).
    session_service.update_session(
        db,
        session,
        SessionUpdate(metadata={"latest_run": run_id, session_service.RUN_PACKAGE_KEY: package}),
    )
    return {"run_id": run_id, "session_id": str(session_id), "phase": "pending"}


@router.post("/{session_id}/poc/check", status_code=201)
@telemetry.sandbox_start_span("check")
def create_poc_check(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Start a preflight of this session's package in the sandbox (#252).

    It imports what the entrypoint imports, builds each stage's model config and
    loads the approved schema, all in the runner image, and calls no model. So it
    needs no input and no approved gate, and a pass is never recorded as the
    successful run that opens the deployable download. Follow it on the run
    stream like any other run.
    """
    from wizard_api.services import poc_service, sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=409, detail="no PoC package to check yet")
    problems = poc_service.package_problems(poc)
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "poc_package_incomplete",
                "problems": problems,
                "message": "the package is not complete: " + "; ".join(problems),
            },
        )
    version = poc_service.package_version(poc)
    try:
        # A page load asks again for the package it already checked: answer
        # with that preflight while it is going or has passed. A preflight of an
        # older version of this session's package is stopped first.
        started = sandbox_runner.SandboxRunner().start_check(
            str(session_id), version, user_id=session.user_id
        )
    except sandbox_runner.RunLimitError as exc:
        raise _busy(exc) from exc
    except sandbox_runner.SandboxNotConfiguredError as exc:
        raise _sandbox_unavailable(exc) from exc
    answer = {
        "run_id": started["run_id"],
        "session_id": str(session_id),
        "phase": started["phase"],
        "version": version,
    }
    if started["reused"]:
        answer["reused"] = True
    return answer


@router.get("/{session_id}/runs/{run_id}")
def get_poc_run(session_id: uuid.UUID, run_id: str, db: Session = Depends(get_db)) -> dict:
    """Where the run got to, for a client that is not following the stream."""
    from wizard_api.services import sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        status = sandbox_runner.SandboxRunner().status(run_id, session_id=str(session_id))
    except sandbox_runner.SandboxNotConfiguredError as exc:
        raise _sandbox_unavailable(exc) from exc
    except sandbox_runner.RunNotFoundError as exc:
        # The Job is reaped an hour after the run; the copy saved when it ended
        # still says how it went, so a reloaded PoC tab can show it.
        summary = _saved_run(session, run_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="run not found") from exc
        return {
            "run_id": run_id,
            "phase": summary.get("phase", "unknown"),
            "exit_code": summary.get("exit_code"),
            "message": summary.get("failure_reason"),
            "reason": summary.get("failure_reason"),
            "finished": True,
        }
    # A finished run is saved with the failure reason read from its log, which
    # says more than the Job's own message ("BackoffLimitExceeded").
    summary = _saved_run(session, run_id) if status.finished else None
    return {
        "run_id": status.run_id,
        "phase": status.phase,
        "exit_code": status.exit_code,
        "message": public_run_message(status),
        "reason": (summary or {}).get("failure_reason"),
        "finished": status.finished,
    }


@router.get("/{session_id}/runs/{run_id}/output")
def get_poc_run_output(session_id: uuid.UUID, run_id: str, db: Session = Depends(get_db)) -> dict:
    """What the run wrote to ``output/``, read from its log, for the PoC tab.

    The run prints each top-level json/txt/md file of ``output/`` between the
    output markers (sandbox-job.yaml). The tab showed only the raw log, with
    the result somewhere in it; this is the same reading a case gets
    (``case_service.parse_run_output``): the record, the grounding check, the
    transcript and the document, plus every file as printed. A run that wrote
    nothing, or has not finished, answers with no files. ``warnings`` lists what
    looks wrong in the record (``case_service.output_warnings``).
    """
    from wizard_api.routers.cases import output_spec
    from wizard_api.services import case_service, sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    spec = output_spec(db, session) if session.output_dir else None
    try:
        runner = sandbox_runner.SandboxRunner()
        runner.check_run_of_session(run_id, str(session_id))
        log = runner.read_log(run_id)
    except sandbox_runner.SandboxNotConfiguredError as exc:
        raise _sandbox_unavailable(exc) from exc
    except sandbox_runner.RunNotFoundError as exc:
        # Reaped Job: read the output files saved when the run ended.
        kept = _saved_run_output(session, run_id)
        if kept is None:
            raise HTTPException(status_code=404, detail="run not found") from exc
        log = ""
        files, downloads = kept
        skipped = (_saved_run(session, run_id) or {}).get("skipped") or []
    else:
        files = case_service.output_files(log, run_id)
        downloads, skipped = case_service.output_downloads(log, run_id)
    result = case_service.parse_run_output(log, spec, run_id=run_id, files=files)
    return {
        "run_id": run_id,
        # What looks wrong in the result (an empty record, an answer that says it
        # got no input). The run's phase stays what it was: these inform.
        "warnings": case_service.output_warnings(result, spec),
        "record": result["record"],
        "validation": result["validation"],
        "transcript": result["transcript"],
        "document": result["document"],
        "files": [{"name": name, "body": body.strip()} for name, body in sorted(files.items())],
        # Every file of output/ as the run wrote it, a PDF included, for download.
        "downloads": [
            {"name": name, "size": len(data)} for name, data in sorted(downloads.items())
        ],
        "skipped": skipped,
    }


@router.get("/{session_id}/runs/{run_id}/files/{name}")
def download_poc_run_file(
    session_id: uuid.UUID, run_id: str, name: str, db: Session = Depends(get_db)
) -> Response:
    """One file the run wrote to ``output/``, as it wrote it.

    The run's output lives in an emptyDir that goes with its pod; the run prints
    each file base64 into its log (sandbox-job.yaml), and this decodes it. The
    tester could not get the PDF a PoC produced: the log said it was saved under
    ``/workspace/poc/output/``, which nobody outside the sandbox can reach
    (customer test feedback, October 2026).
    """
    import mimetypes

    from wizard_api.services import ai_marking, case_service, sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        runner = sandbox_runner.SandboxRunner()
        runner.check_run_of_session(run_id, str(session_id))
        log = runner.read_log(run_id)
    except sandbox_runner.SandboxNotConfiguredError as exc:
        raise _sandbox_unavailable(exc) from exc
    except sandbox_runner.RunNotFoundError as exc:
        kept = _saved_run_output(session, run_id)
        if kept is None:
            raise HTTPException(status_code=404, detail="run not found") from exc
        downloads = kept[1]
    else:
        downloads, _ = case_service.output_downloads(log, run_id)
    data = downloads.get(name)
    if data is None:
        raise HTTPException(status_code=404, detail="file not found")
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": _attachment(name), **ai_marking.headers()},
    )


def _attachment(name: str) -> str:
    from urllib.parse import quote

    ascii_name = name.encode("ascii", "ignore").decode() or "output"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _saved_run(session: Any, run_id: str) -> dict[str, Any] | None:
    """The summary run_context saved for this session's run, or None."""
    from wizard_api.services import run_context

    if not session.output_dir:
        return None
    try:
        return run_context.saved(session.output_dir, run_id)
    except ValueError:  # not a run id
        return None


def _saved_run_output(session: Any, run_id: str) -> tuple[dict[str, str], dict[str, bytes]] | None:
    """The output files run_context saved for this session's run, or None."""
    from wizard_api.services import run_context

    if not session.output_dir:
        return None
    try:
        return run_context.saved_output(session.output_dir, run_id)
    except ValueError:
        return None


@router.get("/{session_id}/runs/{run_id}/stream")
async def stream_poc_run(
    session_id: uuid.UUID, run_id: str, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Follow one run's output live, in the UI's own SSE contract (#92).

        data: {"log": "<line>"}      (repeated, as the run produces them)
        data: {"heartbeat": true}    (keep-alive during silent steps)
        data: {"done": true, "phase": "succeeded"}
        data: {"error": true, "message": "..."}

    A PoC can be quiet for minutes — a model call produces nothing until it
    answers — so the heartbeat is what keeps the connection from being dropped
    by a proxy in between.
    """
    from wizard_api.services import agent_service, sandbox_runner

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Before the stream opens: a run the session did not start is a 404, not an
    # event on a 200 stream, and nothing of it is read or recorded (B3, #143).
    try:
        await asyncio.to_thread(
            sandbox_runner.SandboxRunner().check_run_of_session, run_id, str(session_id)
        )
    except sandbox_runner.RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except sandbox_runner.SandboxNotConfiguredError:
        pass  # gen() reports it in the stream's own contract

    async def gen():
        try:
            runner = sandbox_runner.SandboxRunner()
        except sandbox_runner.SandboxNotConfiguredError as exc:
            log_cause("sandbox_unavailable", exc)
            yield agent_service.sse(
                stream_error("sandbox_unavailable", "The sandbox is not available right now.")
            )
            return

        queue: asyncio.Queue = asyncio.Queue()
        # The log's tail, for the reason a failed run gives in its last lines.
        tail: collections.deque[str] = collections.deque(maxlen=400)

        def pump() -> None:
            try:
                for line in runner.stream_logs(run_id):
                    tail.append(line)
                    queue.put_nowait(("log", line))
            except Exception as exc:  # noqa: BLE001 - reported to the client below
                queue.put_nowait(("error", exc))
            finally:
                queue.put_nowait(("eof", None))

        task = asyncio.create_task(asyncio.to_thread(pump))
        try:
            status = None
            while True:
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=20)
                except TimeoutError:
                    yield agent_service.sse({"heartbeat": True})
                    continue
                if kind == "log":
                    yield agent_service.sse({"log": payload})
                elif kind == "error":
                    # The log stream broke, not necessarily the run. A Job that
                    # has already settled is reported (and recorded) by its own
                    # phase; only a run still going is an interruption (#228).
                    status = await asyncio.to_thread(_settled_status, runner, run_id)
                    if status is None:
                        # The watch's own error (a Kubernetes API message) is
                        # for the log; the person hears the run was interrupted.
                        log_cause("run_stream_interrupted", payload)
                        yield agent_service.sse(
                            stream_error(
                                "run_stream_interrupted", "Following the run was interrupted."
                            )
                        )
                        return
                    break
                else:
                    break
            if status is None:
                status = await asyncio.to_thread(runner.final_status, run_id)
            kind = await asyncio.to_thread(runner.run_kind, run_id)
            with telemetry.tracer.start_as_current_span("wizard.sandbox.result") as span:
                span.set_attributes(
                    {
                        "gaik.session.id": str(session_id),
                        "gaik.sandbox.run_id": run_id,
                        "gaik.sandbox.kind": kind or "run",
                        "gaik.sandbox.phase": status.phase,
                    }
                )
                if status.exit_code is not None:
                    span.set_attribute("gaik.sandbox.exit_code", status.exit_code)
                if status.phase != "succeeded":
                    span.set_status(telemetry.Status(telemetry.StatusCode.ERROR))
            ops_metrics.sandbox_runs.add(1, {"kind": kind or "run", "phase": status.phase})
            # Only a run of the package itself: a preflight calls no model, and a
            # case run ran on one case's inputs, so neither proves the package.
            if status.phase == "succeeded" and kind is None:
                # Recorded rather than re-queried later: a finished Job is
                # reaped an hour after it ends (ttlSecondsAfterFinished), and
                # the deployable download must still know the run happened.
                await asyncio.to_thread(_record_successful_run, session_id, run_id)
            saved = False
            if status.finished and kind is None and session.output_dir:
                # For the same reason the run's log and files are saved for the
                # agent now, not when the user next writes in the chat (#96).
                # With what looks wrong in its output, read against the output spec.
                spec = await asyncio.to_thread(_run_output_spec, session_id)
                saved = await asyncio.to_thread(
                    _save_run_for_agent, runner, session.output_dir, run_id, status, spec
                )
            if status.finished and kind == sandbox_runner.CHECK_KIND and session.output_dir:
                saved = await asyncio.to_thread(
                    _save_check_for_agent, runner, session.output_dir, run_id, status
                )
            if saved:
                # The session now holds the result; the Job's log, which every
                # user of the project can read, has nothing left to give.
                await asyncio.to_thread(_remove_run_quietly, runner, run_id)
            public = public_run_message(status)
            done: dict[str, Any] = {"done": True, "phase": status.phase, "message": public}
            if status.phase != "succeeded":
                # The reason in the run's own words, so the tab need not send the
                # person into the traceback; the Job's message names no cause.
                from wizard_api.services import case_service

                done["reason"] = case_service.run_failure_message(
                    status.phase, "\n".join(tail), public
                )
            yield agent_service.sse(done)
        finally:
            task.cancel()

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers=agent_service.sse_headers()
    )


# ---------------------------------------------------------------------------
# Sample input for a sandbox run (#95)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/poc/input", status_code=201)
async def upload_poc_input(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Add one sample input file to this session's PoC package.

    It lands in ``poc/sample_input/``, which the zip endpoint already serves and
    the Job's init container already unpacks — so the run reads it at
    ``/workspace/poc/sample_input`` with no change to the manifest. Regenerating
    the package keeps it.

    Only that directory: the package root holds ``run_poc.py``, the file the Job
    executes, and an upload must never be able to become it.
    """
    from wizard_api.services import input_content, malware_scan, poc_service
    from wizard_api.services.artifact_sync import read_draft_blueprint

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=409, detail="generate the PoC package first")

    try:
        data = await poc_service.read_upload(file)
        # Same check as a case input: what the file is, from its bytes, and
        # only the types the session's input contract asks for.
        allowed = input_content.allowed_kinds(read_draft_blueprint(session.output_dir))
        await asyncio.to_thread(input_content.check, file.filename or "", data, allowed)
        # Then the malware check; a file it reports, or one it could not
        # check, is never written.
        await malware_scan.check_upload(data)
        name = poc_service.save_sample_input(poc, file.filename or "", data)
    # Both name the user's own file and the limit it broke.
    except poc_service.InputTooLargeError as exc:
        raise api_error(413, "input_too_large", str(exc)) from exc
    except input_content.UnsupportedInputError as exc:
        raise api_error(415, "input_type_not_accepted", str(exc)) from exc
    except (malware_scan.UnsafeInputError, input_content.UnsafeContentError) as exc:
        raise api_error(422, "input_unsafe", str(exc)) from exc
    except malware_scan.ScannerUnavailableError as exc:
        raise api_error(503, "scanner_unavailable", malware_scan.UNAVAILABLE_MESSAGE) from exc
    except poc_service.InputRejectedError as exc:
        raise api_error(422, "input_rejected", str(exc)) from exc

    return {"name": name, "bytes": len(data), "path": f"sample_input/{name}", "uploaded": True}


@router.get("/{session_id}/poc/input")
def list_poc_inputs(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    from wizard_api.services import poc_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        return {"files": []}
    return {"files": poc_service.list_sample_inputs(poc)}


@router.delete("/{session_id}/poc/input/{filename}", status_code=204)
def delete_poc_input(
    session_id: uuid.UUID, filename: str, db: Session = Depends(get_db)
) -> Response:
    from wizard_api.services import poc_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=404, detail="no PoC package")
    try:
        removed = poc_service.delete_sample_input(poc, filename)
    except poc_service.InputRejectedError as exc:
        raise api_error(422, "input_rejected", str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="no such input file")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Gate 3 refinement (#96)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/runs/{run_id}/feedback", status_code=201)
def submit_run_feedback(
    session_id: uuid.UUID,
    run_id: str,
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """Record what was wrong with a run, and what kind of change it calls for.

    The classification comes from the agent, which has V1's table and the
    conversation; this records it and reports the rule that follows from it, so
    the user is told what will happen before it happens.
    """
    from wizard_api.services import blueprint_service, refinement

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        recorded = refinement.classify(
            payload.get("feedback", ""), payload.get("classification", "")
        )
    except refinement.RefinementRejectedError as exc:
        raise api_error(422, "refinement_rejected", str(exc)) from exc

    active = blueprint_service.get_active_version(db, session)
    version = active.version if active else 0

    # Kept on the session so the loop leaves a trail: what was asked for, after
    # which run, and against which blueprint version.
    session_service.lock_fresh(db, session)
    history = list(session.session_metadata.get("refinements") or [])
    history.append(
        {
            "run_id": run_id,
            "classification": recorded.classification,
            "feedback": recorded.feedback,
            "blueprint_version": version,
        }
    )
    session_service.update_session(
        db, session, SessionUpdate(metadata={"refinements": history[-50:]})
    )

    return {
        "run_id": run_id,
        "classification": recorded.classification,
        "rule": recorded.rule,
        "requires_blueprint_change": recorded.requires_blueprint_change,
        "blueprint_version": version,
    }


@router.get("/{session_id}/refinements")
def list_refinements(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"refinements": list(session.session_metadata.get("refinements") or [])}


@router.get("/{session_id}/poc/deployable")
def download_deployable_poc(session_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """The package as someone else receives it, after a run has proved it (#143).

    Two things separate this from the development zip. It is gated on a run that
    actually succeeded — handing over a package nobody has seen work is the
    thing the whole sandbox step exists to prevent — and it leaves behind what
    belongs to developing it: the sample input, the previous run's output, and
    the __pycache__ a package review found being shipped.
    """
    from wizard_api.services import ai_marking, poc_service

    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    run_id = session.session_metadata.get("last_successful_run")
    if not run_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_successful_run",
                "message": "run the PoC in the sandbox successfully before taking the package",
            },
        )

    poc = _poc_dir(session.output_dir)
    if not poc or not os.path.isdir(poc):
        raise HTTPException(status_code=404, detail="no PoC generated yet")
    problems = poc_service.package_problems(poc)
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "poc_package_incomplete",
                "problems": problems,
                "message": "the package is not complete: " + "; ".join(problems),
            },
        )

    package_config = poc_service.config_with_model_timeout(poc)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative in poc_service.deployable_files(poc):
            if relative == ai_marking.MARKER_FILE:
                continue
            if relative == poc_service.CONFIG_NAME and package_config is not None:
                zf.writestr(os.path.join("poc", relative), package_config)
            else:
                zf.write(os.path.join(poc, relative), os.path.join("poc", relative))
        zf.writestr(
            os.path.join("poc", ai_marking.MARKER_FILE),
            ai_marking.marker_json(session, "poc-package-deployable"),
        )
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="poc-{session_id}-deployable.zip"',
            "X-Wizard-Run-Id": str(run_id),
            "Cache-Control": "no-store",
            **ai_marking.headers(),
        },
    )
