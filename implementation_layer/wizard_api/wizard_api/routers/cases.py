"""Cases: run the generated solution as a process, with roles, on real input.

See ``wizard_api.services.case_service``. Same owner rule as every other
``/sessions/{session_id}/...`` route: the router carries the dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wizard_api import telemetry
from wizard_api.db import get_db
from wizard_api.errors import api_error, internal_error, public_run_message
from wizard_api.ownership import requesting_user, session_belongs_to_requester
from wizard_api.services import (
    case_service,
    input_content,
    malware_scan,
    poc_service,
    session_service,
)
from wizard_api.services.artifact_sync import (
    DRAFT_BLUEPRINT_FILE,
    WORKFLOW_BPMN_FILE,
    read_draft_blueprint,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sessions",
    tags=["cases"],
    dependencies=[Depends(session_belongs_to_requester)],
)


class SubmitRequest(BaseModel):
    role: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=2000)
    task: str | None = Field(default=None, max_length=200)


class StepRequest(BaseModel):
    task: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=2000)


class ReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|return|rerun|reject)$")
    role: str = Field(default="", max_length=200)
    comment: str = Field(default="", max_length=2000)
    record: dict[str, Any] | list[dict[str, Any]] | None = None
    return_to: str | None = Field(default=None, max_length=200)


def _session(db: Session, session_id: uuid.UUID):
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.output_dir:
        raise HTTPException(status_code=409, detail="session has no output directory")
    return session


def _draft(output_dir: str) -> dict[str, Any]:
    path = Path(output_dir) / DRAFT_BLUEPRINT_FILE
    if not poc_service.regular_file(path, output_dir):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def output_spec(db: Session, session) -> dict[str, Any] | None:
    """The output fields: the agent's draft first, as the PoC was built from it."""
    spec = _draft(session.output_dir).get("target_output_spec")
    if isinstance(spec, dict) and spec.get("fields"):
        return case_service.normalize_spec(spec)
    detail = session_service.session_detail(db, session)
    return detail.target_output_spec.model_dump() if detail.target_output_spec else None


def _bpmn(db: Session, session, session_id: uuid.UUID) -> str | None:
    """The diagram the user sees in the Workflow tab and approves at Gate 2.

    Cases used to read the agent's own workflow.bpmn first, so a case was routed
    to the roles of a diagram the user never saw. That file is now only the
    fallback for when the diagram cannot be generated.
    """
    from wizard_api.services import bpmn_service

    detail = session_service.session_detail(db, session)
    try:
        return bpmn_service.generate_bpmn_xml(
            detail.blueprint.model_dump(),
            session_id=str(session_id),
            agent_draft=read_draft_blueprint(session.output_dir),
        )
    except Exception:  # noqa: BLE001 - fall back to the agent's diagram, see the docstring
        logger.warning("diagram for session %s could not be generated", session_id, exc_info=True)
    path = Path(session.output_dir) / WORKFLOW_BPMN_FILE
    if poc_service.regular_file(path, session.output_dir):
        return path.read_text(encoding="utf-8")
    return None


def _review_needed(db: Session, session, session_id: uuid.UUID) -> bool:
    """Whether someone reviews the result: the process names a reviewer (#296).

    Without a BPMN, or with one that does not parse, someone does: a result
    nobody looked at must not complete a case on its own (#295).
    """
    xml = _bpmn(db, session, session_id)
    if not xml:
        return True
    try:
        process = case_service.process_from_bpmn(xml)
    except case_service.BpmnParseError:
        return True
    if case_service.process_problem(process):
        # Nobody can be named from a process that cannot be walked, so someone reviews.
        return True
    return case_service.reviewer_task(process) is not None


def _case(output_dir: str, case_id: str) -> dict[str, Any]:
    try:
        return case_service.get_case(output_dir, case_id)
    except case_service.CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


def _sandbox_unavailable(exc: Exception) -> HTTPException:
    """503 for a deployment missing a piece of the sandbox; the piece is in the log."""
    return internal_error(
        503, "sandbox_unavailable", "The sandbox is not available right now.", exc
    )


def _state_error(exc: Exception) -> HTTPException:
    # CaseStateError's messages are written for the user: what the case is
    # waiting for, or which required field a review left empty.
    return api_error(409, "case_state", str(exc))


@router.get("/{session_id}/cases/model")
def case_model(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """What the case UI is built from: the process (BPMN) and the output fields."""
    session = _session(db, session_id)
    xml = _bpmn(db, session, session_id)
    if not xml:
        raise HTTPException(status_code=409, detail="the session has no BPMN yet")
    spec = output_spec(db, session)
    if not spec:
        raise HTTPException(status_code=409, detail="the session has no output fields yet")
    try:
        process = case_service.process_from_bpmn(xml)
    except case_service.BpmnParseError as exc:
        # The parser's own words (line, column, token) go to the log.
        raise internal_error(
            409,
            "bpmn_invalid",
            "The session's BPMN diagram does not parse; fix it in the BPMN editor.",
            exc,
        ) from exc
    problem = case_service.process_problem(process)
    if problem:
        # What the process lacks ("no start event"), in case_service's words.
        raise api_error(409, "bpmn_not_runnable", problem)
    poc = os.path.join(session.output_dir, "poc")
    problems = poc_service.package_problems(poc) if os.path.isdir(poc) else ["no PoC package"]
    draft = _draft(session.output_dir)
    title = (draft.get("use_case") or {}).get("name") or spec.get("schema_name", "")
    return {
        "title": title,
        "spec": spec,
        "process": process,
        # The types an input upload accepts, so the form can say so before a
        # file is picked: the same set upload_case_input checks against.
        "accepted_inputs": input_content.accepted(input_content.allowed_kinds(draft)),
        # The reviewer, decided here and nowhere else (#296).
        "reviewer": case_service.reviewer_task(process),
        "package_ready": not problems,
        "package_problems": problems,
    }


@router.get("/{session_id}/cases")
def list_cases(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    session = _session(db, session_id)
    return {"cases": case_service.list_cases(session.output_dir)}


@router.post("/{session_id}/cases", status_code=201)
def create_case(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str | None = Depends(requesting_user),
) -> dict:
    session = _session(db, session_id)
    try:
        return case_service.create_case(session.output_dir, created_by=user_id or session.user_id)
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc


@router.get("/{session_id}/cases/{case_id}")
async def get_case(session_id: uuid.UUID, case_id: str, db: Session = Depends(get_db)) -> dict:
    """The case. A running case is settled here once its run has finished."""
    session = _session(db, session_id)
    case = _case(session.output_dir, case_id)
    if case["status"] == "running" and not case.get("run_id"):
        # Claimed for a run that never started (#294): given back once stale.
        # Takes the case's file lock: off the event loop, like finish_run below.
        return await asyncio.to_thread(
            case_service.release_stale_claim, session.output_dir, case_id
        )
    if case["status"] != "running":
        return case
    from wizard_api.services import sandbox_runner

    try:
        runner = sandbox_runner.SandboxRunner()
        status = await asyncio.to_thread(runner.status, case["run_id"], session_id=str(session_id))
    except sandbox_runner.RunNotFoundError:
        return await asyncio.to_thread(
            case_service.finish_run,
            session.output_dir,
            case_id,
            phase="failed",
            log=None,
            message="the run is no longer on the cluster",
            spec=None,
        )
    except sandbox_runner.SandboxNotConfiguredError as exc:
        raise _sandbox_unavailable(exc) from exc
    if not status.finished:
        return {**case, "run_phase": status.phase}
    # Read for a failed run too (#29): its reason is in its own log, and the
    # Job's own words ("reached the specified backoff limit") name no cause.
    log = None
    try:
        log = await asyncio.to_thread(runner.read_log, case["run_id"])
    except sandbox_runner.RunNotFoundError:
        log = None
    except Exception:  # noqa: BLE001 - a failed run still settles, with the Job's words
        if status.phase == "succeeded":
            raise
        logger.warning("log of failed case run %s could not be read", case["run_id"], exc_info=True)
    if log is not None and status.phase != "succeeded":
        # Only the end is read for the reason, as the PoC tab does (run_context).
        log = case_service.failure_log_tail(log)
    settled = await asyncio.to_thread(
        case_service.finish_run,
        session.output_dir,
        case_id,
        phase=status.phase,
        log=log,
        message=public_run_message(status),
        spec=output_spec(db, session),
        review_needed=_review_needed(db, session, session_id),
    )
    if log is not None:
        # The case holds what the log said; the Job's log, which every user of
        # the project can read, has nothing left to give. An unread log stays
        # for the hour the TTL gives it.
        await asyncio.to_thread(_delete_quietly, runner, case["run_id"])
    return settled


@router.delete("/{session_id}/cases/{case_id}", status_code=204)
def delete_case(session_id: uuid.UUID, case_id: str, db: Session = Depends(get_db)) -> Response:
    """Remove a case that was never sent for processing, with its input."""
    session = _session(db, session_id)
    try:
        case_service.delete_case(session.output_dir, case_id)
    except case_service.CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc
    return Response(status_code=204)


@router.post("/{session_id}/cases/{case_id}/inputs", status_code=201)
async def upload_case_input(
    session_id: uuid.UUID,
    case_id: str,
    file: UploadFile = File(...),
    task: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    try:
        data = await poc_service.read_upload(file)
        # What the file is, from its bytes, before anything is written: only
        # the types the session's input contract asks for.
        await asyncio.to_thread(
            input_content.check,
            file.filename or "",
            data,
            input_content.allowed_kinds(_draft(session.output_dir)),
        )
        # Then the malware check; a file it reports, or one it could not
        # check, is never written.
        await malware_scan.check_upload(data)
        # Waits on the session's and the case's file locks and writes the file:
        # off the event loop, so one session's uploads do not stall the worker.
        name = await asyncio.to_thread(
            case_service.save_input,
            session.output_dir,
            case_id,
            file.filename or "",
            data,
            task=task,
        )
    # All three name the user's own file and the rule it broke.
    except case_service.InputExistsError as exc:
        raise api_error(409, "input_exists", str(exc)) from exc
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
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc
    return {"name": name, "bytes": len(data), "task": task}


@router.get("/{session_id}/cases/{case_id}/inputs/{filename}")
def get_case_input(
    session_id: uuid.UUID, case_id: str, filename: str, db: Session = Depends(get_db)
) -> FileResponse:
    """One input file, for the reviewer to listen to or open beside the record."""
    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    try:
        path = case_service.input_path(session.output_dir, case_id, filename)
    except poc_service.InputRejectedError as exc:
        raise api_error(422, "input_rejected", str(exc)) from exc
    if path is None:
        raise HTTPException(status_code=404, detail="no such input file")
    # Uploaded by anyone with the session, so never rendered as a page (#292):
    # an .html or .svg would run in the web app's origin. Recordings, PDFs and
    # pictures stay viewable in place with a type we set; everything else is a
    # download, and nosniff stops the browser guessing otherwise.
    inline_type = _INLINE_TYPES.get(path.suffix.lower())
    return FileResponse(
        path,
        media_type=inline_type or "application/octet-stream",
        content_disposition_type="inline" if inline_type else "attachment",
        filename=path.name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


#: The input types shown in place: the review listens to recordings, opens a
#: cited PDF beside the report, and may show a photo. Not text or markup.
_INLINE_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@router.delete("/{session_id}/cases/{case_id}/inputs/{filename}", status_code=204)
def delete_case_input(
    session_id: uuid.UUID, case_id: str, filename: str, db: Session = Depends(get_db)
) -> Response:
    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    try:
        removed = case_service.delete_input(session.output_dir, case_id, filename)
    except poc_service.InputRejectedError as exc:
        raise api_error(422, "input_rejected", str(exc)) from exc
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="no such input file")
    return Response(status_code=204)


@router.post("/{session_id}/cases/{case_id}/submit")
@telemetry.sandbox_start_span("case")
def submit_case(
    session_id: uuid.UUID, case_id: str, payload: SubmitRequest, db: Session = Depends(get_db)
) -> dict:
    """Send the case's input to the sandbox: the package runs on this case's files."""
    from wizard_api.services import sandbox_runner

    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    # The same gate as a run of the package (create_poc_run): a case runs the
    # generated code, which only an approved blueprint may produce.
    if session.gate_statuses.get("gate_2") != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "gate_not_approved",
                "gate": "gate_2",
                "message": "approve Gate 2 before running a case",
            },
        )
    poc = os.path.join(session.output_dir, "poc")
    problems = poc_service.package_problems(poc) if os.path.isdir(poc) else ["no PoC package"]
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "poc_package_incomplete",
                "problems": problems,
                "message": "the package is not complete: " + "; ".join(problems),
            },
        )
    # Refused here, before a Job exists, rather than when the run fetches the package.
    try:
        case_service.case_package_inputs(
            poc_service.sample_input_dir(poc), case_service.inputs_dir(session.output_dir, case_id)
        )
    except case_service.InputClashError as exc:
        raise api_error(409, "input_clash", str(exc)) from exc
    # The case is taken before the Job exists, so two submits at once cannot
    # both start one (#294); it is given back when no Job could be started.
    try:
        case_service.claim_submission(session.output_dir, case_id)
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc
    runner = sandbox_runner.SandboxRunner()
    run_id = sandbox_runner.new_run_id(str(session_id))
    try:
        run_id = runner.create_run(
            str(session_id), run_id=run_id, case_id=case_id, user_id=session.user_id
        )
    except sandbox_runner.RunLimitError as exc:
        from wizard_api.routers.sessions import _busy

        case_service.release_submission(session.output_dir, case_id)
        raise _busy(exc) from exc
    except sandbox_runner.SandboxNotConfiguredError as exc:
        case_service.release_submission(session.output_dir, case_id)
        raise _sandbox_unavailable(exc) from exc
    except Exception:
        # A create that timed out may still have made the Job: remove it, so
        # nothing runs for a case that is given back.
        _delete_quietly(runner, run_id)
        case_service.release_submission(session.output_dir, case_id)
        raise
    try:
        return case_service.mark_submitted(
            session.output_dir,
            case_id,
            run_id=run_id,
            role=payload.role,
            note=payload.note,
            task=payload.task,
        )
    except case_service.CaseStateError as exc:
        # The claim was given back while the Job was being made (it went stale):
        # the case is no longer this request's, so its Job must not run.
        _delete_quietly(runner, run_id)
        raise _state_error(exc) from exc


def _delete_quietly(runner, run_id: str) -> None:
    try:
        runner.delete_run(run_id)
    except Exception:  # noqa: BLE001 - best effort; the Job may not exist
        pass


@router.post("/{session_id}/cases/{case_id}/step")
def complete_case_step(
    session_id: uuid.UUID, case_id: str, payload: StepRequest, db: Session = Depends(get_db)
) -> dict:
    """One person's part of the input is done; the next input task is up."""
    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    try:
        return case_service.complete_step(
            session.output_dir, case_id, task=payload.task, role=payload.role, note=payload.note
        )
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc


@router.post("/{session_id}/cases/{case_id}/review")
def review_case(
    session_id: uuid.UUID, case_id: str, payload: ReviewRequest, db: Session = Depends(get_db)
) -> dict:
    session = _session(db, session_id)
    _case(session.output_dir, case_id)
    try:
        return case_service.review(
            session.output_dir,
            case_id,
            action=payload.action,
            role=payload.role,
            record=payload.record,
            comment=payload.comment,
            spec=output_spec(db, session),
            return_to=payload.return_to,
        )
    except case_service.CaseStateError as exc:
        raise _state_error(exc) from exc
