import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from wizard_api.config import build_session_output_dir
from wizard_api.models import BlueprintVersion, WizardSession
from wizard_api.schemas.blueprint import (
    AssumptionItem,
    BusinessContext,
    PendingTurn,
    SessionDetailResponse,
)
from wizard_api.schemas.session import SessionCreate, SessionUpdate
from wizard_api.services import agent_service, artifact_sync, blueprint_service
from wizard_api.session_state import (
    GATE_KEY_TO_STEP,
    GATE_KEYS,
    MAX_STEP,
    check_gates_for_step_change,
    default_gate_statuses,
    merge_gate_statuses,
)
from wizard_api.storage import ensure_output_dir

# Metadata keys the server writes as a record of what happened: the chat
# transcript, the refinement history, the run the deployable package is gated
# on (#143), the agent conversation the next chat turn resumes, the agent draft
# last adopted as the blueprint. A PATCH that sets them would forge that record
# — "a successful run happened" with no run, a turn resuming a conversation of
# the caller's choosing, a stale draft adopted again — so they are refused,
# whoever the caller is.
SERVER_OWNED_METADATA_KEYS = frozenset(
    {
        "messages",
        "refinements",
        "last_successful_run",
        "latest_run",
        "latest_run_package",
        "latest_run_inputs",
        "last_successful_run_package",
        "agent_seen_run",
        "agent_sdk_session_id",
        "protected",
        artifact_sync.ADOPTED_DRAFT_KEY,
        "gate_reopened",
        "gate_replay",
        "voided_runs",
        "approved_content",
    }
)

#: Session metadata key: the gate whose approval was taken back for a change,
#: with who did it and why. Kept until that gate is approved again; the page
#: says so, and the agent is told with every message meanwhile.
REOPENED_KEY = "gate_reopened"
#: Session metadata key: set while a session walks its gates again after one
#: was reopened. The artifacts of the later phases are already on disk then,
#: so the step follows them at once instead of waiting for a new one to appear.
REPLAY_KEY = "gate_replay"
#: Runs that were the session's latest when a gate was reopened: they tested
#: the solution as it was, so they are never recorded as its successful run.
VOIDED_RUNS_KEY = "voided_runs"
#: Session metadata key: the digest of the package the latest run was started on
#: (the sessions router's ``_approved_package_digest``, which covers ``prompts/``).
RUN_PACKAGE_KEY = "latest_run_package"
#: Session metadata key: the names of the files in ``sample_input/`` when the
#: latest run was started, the material it ran on. The PoC tab tells a result
#: from other material than what is listed now, also after a reload.
RUN_INPUTS_KEY = "latest_run_inputs"
#: Session metadata key: that digest for the run recorded as ``last_successful_run``.
#: Gate 3 is refused while the package on disk differs from it: the run that
#: passed tested another package. Absent in a session whose run was recorded
#: before the digest was kept; such a session is approved as it was.
SUCCESSFUL_RUN_PACKAGE_KEY = "last_successful_run_package"
#: That key's value for a successful run recorded without a digest in a session
#: that keeps digests: nothing says which package the run tested, so Gate 3 is
#: refused until a run with a known package succeeds. Never a digest (16 hex).
UNKNOWN_RUN_PACKAGE = "unknown"
#: Session metadata key: digests of the solution and of the package as they were
#: when Gate 3 was approved. A chat turn that leaves either different has
#: changed what the gates approved, and the gate that covers it reopens.
APPROVED_CONTENT_KEY = "approved_content"


class ServerOwnedMetadataError(ValueError):
    def __init__(self, keys: list[str]):
        self.keys = keys
        super().__init__(f"metadata keys are set by the server, not the caller: {', '.join(keys)}")


def check_metadata_patch(metadata: dict) -> None:
    """For what an HTTP caller sends, on create and on PATCH: the server's own
    writes (feedback, artifact sync, a recorded run) go through update_session
    with these keys and must."""
    forbidden = sorted(SERVER_OWNED_METADATA_KEYS & set(metadata))
    if forbidden:
        raise ServerOwnedMetadataError(forbidden)


def _session_status(step: int, metadata: dict) -> str:
    if metadata.get("status") == "done" or step >= MAX_STEP:
        return "done"
    return "active"


def _session_title(metadata: dict) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "Nimetön sessio"


def _to_response(session: WizardSession) -> dict:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "step": session.step,
        "gate_statuses": session.gate_statuses,
        "metadata": session.session_metadata,
        "output_dir": session.output_dir,
        "active_version": session.active_version,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _business_context_from_draft(data: dict | None) -> BusinessContext | None:
    """The business-facing framing from the agent's V1 draft blueprint, read for
    us by ``artifact_sync``. ``None`` when there is no draft yet, or no business
    framing in it."""
    if not data:
        return None
    business = data.get("business_spec") or {}
    use_case = data.get("use_case") or {}

    def _str(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _list(value: object) -> list[str]:
        # The template says list, but the agent sometimes writes one sentence
        # as a plain string. Dropping it left Gate 1 reporting the field as
        # missing while the conversation had answered it.
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    ctx = BusinessContext(
        current_process=_str(business.get("current_process")),
        pain_points=_list(business.get("pain_points")),
        intended_users=_list(business.get("intended_users")),
        reviewers=_list(business.get("reviewers")),
        expected_value=_list(business.get("expected_value")),
        knowledge_processes=_list(use_case.get("knowledge_processes")),
        domain=_str(use_case.get("domain")),
    )
    # Nothing worth surfacing if the file had no business framing at all.
    if not any(
        [
            ctx.current_process,
            ctx.pain_points,
            ctx.intended_users,
            ctx.reviewers,
            ctx.expected_value,
            ctx.knowledge_processes,
            ctx.domain,
        ]
    ):
        return None
    return ctx


#: What the agent writes for something it has not learned yet. The same rule as
#: the panel's (solution_wizard_v2/lib/known-values.ts): such a value is shown
#: as missing and does not count towards approving Gate 1.
_NOT_KNOWN = re.compile(
    r"^(unknown|n/?a|none|tbd|-|tuntematon|ei (vielä )?tiedossa|not known( yet)?)\.?$",
    re.IGNORECASE,
)


def _known(value: str) -> bool:
    return bool(value.strip()) and not _NOT_KNOWN.match(value.strip())


def gate1_missing(ctx: BusinessContext | None) -> list[str]:
    """The draft fields Gate 1 still lacks, as the panel decides it
    (components/gate1-review.tsx ``gate1Missing``): its approve button stays
    disabled until both are there. Field paths in use_case.blueprint.json."""
    missing = []
    if ctx is None or not _known(ctx.current_process):
        missing.append("business_spec.current_process")
    if ctx is None or not any(_known(v) for v in ctx.expected_value):
        missing.append("business_spec.expected_value")
    return missing


def gate1_missing_from_draft(data: dict | None) -> list[str]:
    return gate1_missing(_business_context_from_draft(data))


def _assumptions_from_draft(data: dict | None) -> list[AssumptionItem]:
    """The draft blueprint's ``assumptions[]``, or an empty list when there is
    no draft yet."""
    raw = data.get("assumptions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[AssumptionItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        out.append(
            AssumptionItem(
                id=str(item.get("id") or ""),
                text=text.strip(),
                status=str(item.get("status") or "unconfirmed"),
                impact=str(item.get("impact") or ""),
            )
        )
    return out


def _pending_turn(session: WizardSession) -> PendingTurn | None:
    """The chat turn in progress for this session, for a page loaded mid-reply."""
    turn = agent_service.running_turn(str(session.id))
    if turn is None:
        return None
    return PendingTurn(
        user_message=turn.user_message,
        started_at=datetime.fromtimestamp(turn.started_at, UTC),
    )


def session_detail(
    db: Session,
    session: WizardSession,
    versions: list[BlueprintVersion] | None = None,
    active: BlueprintVersion | None = None,
) -> SessionDetailResponse:
    if versions is None:
        versions = blueprint_service.list_versions(db, session.id)
    if active is None:
        active = blueprint_service.get_active_version(db, session)
    metadata = session.session_metadata
    # One read of the agent's draft for every field derived from it.
    draft = artifact_sync.read_draft_blueprint(session.output_dir)
    messages = metadata.get("messages")
    if not isinstance(messages, list):
        messages = []
    blueprint = (
        active.content
        if active
        else blueprint_service.default_blueprint_content(_session_title(metadata))
    )
    return SessionDetailResponse(
        id=str(session.id),
        user_id=session.user_id,
        title=_session_title(metadata),
        step=session.step,
        status=_session_status(session.step, metadata),
        gate_statuses=session.gate_statuses,
        metadata=metadata,
        output_dir=session.output_dir,
        active_version=session.active_version,
        versions=[
            {"version": v.version, "note": v.note, "created_at": v.created_at} for v in versions
        ],
        blueprint=blueprint,
        business_context=_business_context_from_draft(draft),
        target_output_spec=artifact_sync.target_output_spec_from_draft(draft) if draft else None,
        assumptions=_assumptions_from_draft(draft),
        messages=messages,
        pending_turn=_pending_turn(session),
        agent_live=agent_service.is_live(str(session.id)),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def create_session(db: Session, payload: SessionCreate) -> WizardSession:
    session_id = uuid.uuid4()
    output_dir = build_session_output_dir(payload.user_id, session_id)
    ensure_output_dir(output_dir)

    title = (payload.title or "").strip() or "Nimetön sessio"
    metadata = dict(payload.metadata)
    metadata.setdefault("title", title)
    metadata.setdefault("status", "active")
    metadata.setdefault("messages", [])

    session = WizardSession(
        id=session_id,
        user_id=payload.user_id,
        output_dir=output_dir,
        session_metadata=metadata,
    )
    db.add(session)
    db.flush()
    blueprint_service.create_initial_version(db, session, title=title)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: uuid.UUID) -> WizardSession | None:
    return db.get(WizardSession, session_id)


def list_sessions(db: Session, user_id: str) -> list[WizardSession]:
    stmt = (
        select(WizardSession)
        .where(WizardSession.user_id == user_id)
        .order_by(WizardSession.updated_at.desc())
    )
    return list(db.scalars(stmt).all())


def move_owner(db: Session, legacy_user_id: str, owner: str) -> int:
    """Move the sessions saved under ``legacy_user_id`` (an e-mail address, from
    before owner ids) to ``owner``; how many moved.

    ``updated_at`` stays as it was, so the move does not restart the retention
    period. The folders keep their paths: a session made before owner ids keeps
    its files where they are until it is removed.
    """
    result = db.execute(
        update(WizardSession)
        .where(WizardSession.user_id == legacy_user_id)
        .values(user_id=owner, updated_at=WizardSession.updated_at)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount or 0


def lock_fresh(db: Session, session: WizardSession) -> WizardSession:
    """Re-read the row from the database and hold it until the next commit.

    ``metadata`` is one JSONB object, and every writer builds the *whole* new
    object from the copy it holds. A chat turn holds its copy for minutes while
    the agent works; a sandbox run recorded in the meantime (``last_successful_run``)
    was then written over by the turn's own ``append_messages``, so the run the
    UI had reported as succeeded was unknown to the api and the deployable
    package answered 409 (#253). Reading the row again under ``FOR UPDATE``
    makes each read–modify–write start from what is stored now and keeps a
    second writer waiting until the first has committed.
    """
    db.refresh(session, with_for_update=True)
    return session


def update_session(db: Session, session: WizardSession, payload: SessionUpdate) -> WizardSession:
    lock_fresh(db, session)
    # Gates are checked against what the session looks like *after* this patch,
    # so a request that approves a gate and advances in one go is allowed, while
    # one that only advances is not. Raises GateNotApprovedError, which the
    # router turns into a 409.
    effective_gates = (
        merge_gate_statuses(session.gate_statuses, payload.gate_statuses)
        if payload.gate_statuses is not None
        else session.gate_statuses
    )
    if payload.step is not None:
        check_gates_for_step_change(session.step, payload.step, effective_gates)
        session.step = payload.step
        metadata = dict(session.session_metadata)
        metadata["status"] = _session_status(session.step, metadata)
        session.session_metadata = metadata
    if payload.gate_statuses is not None:
        session.gate_statuses = effective_gates
    if payload.metadata is not None:
        session.session_metadata = {**session.session_metadata, **payload.metadata}
    reopened = session.session_metadata.get(REOPENED_KEY)
    if isinstance(reopened, dict) and effective_gates.get(reopened.get("gate")) == "approved":
        # The reopened gate has its approval again: nothing is left to say about it.
        session.session_metadata = {
            key: value for key, value in session.session_metadata.items() if key != REOPENED_KEY
        }
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


class GateNotReopenableError(ValueError):
    """Only an approved gate can be reopened."""

    def __init__(self, gate_key: str, status: str) -> None:
        self.gate_key = gate_key
        self.status = status
        super().__init__(f"{gate_key} is {status}, not approved; there is nothing to reopen")


def reopen_gate(
    db: Session,
    session: WizardSession,
    gate_key: str,
    *,
    reason: str = "",
    by: str = "user",
) -> WizardSession:
    """Take back the approval of ``gate_key`` and of every gate after it.

    An approval was final: a user who asked in the chat for another field after
    Gate 3 got "ok" from the agent and changed files, while every gate stayed
    approved, the step stayed where it was and the package the session offered
    was the old one. The agent, asked to reopen a gate, could only answer "if
    the panel has a way to reopen it, do that" - it had none.

    Reopening puts the session back on the gate's step with that gate and the
    later ones pending, so the change is reviewed and approved the way the
    first version was. A run that passed before tested the old solution, so
    unless only the handover is reopened it no longer opens Gate 3 or the
    deployable package. ``by`` is "user" (the panel), "agent" (its tool) or
    "change" (a chat turn changed what was approved; see the sessions router).
    """
    if gate_key not in GATE_KEYS:
        raise ValueError(f"unknown gate: {gate_key!r}")
    lock_fresh(db, session)
    status = session.gate_statuses.get(gate_key, "pending")
    if status != "approved":
        db.commit()  # releases the row
        raise GateNotReopenableError(gate_key, status)
    index = GATE_KEYS.index(gate_key)
    gates = {**default_gate_statuses(), **session.gate_statuses}
    for key in GATE_KEYS[index:]:
        gates[key] = "pending"
    session.gate_statuses = gates
    # Onto the reopened gate, or onto an earlier one that is not approved (only
    # a direct PATCH leaves one behind): never onto a step past a pending gate.
    earlier_open = [key for key in GATE_KEYS[:index] if gates.get(key) != "approved"]
    session.step = GATE_KEY_TO_STEP[earlier_open[0] if earlier_open else gate_key]
    metadata = dict(session.session_metadata)
    metadata["status"] = "active"
    metadata["status"] = _session_status(session.step, metadata)
    metadata[REOPENED_KEY] = {
        "gate": gate_key,
        "by": by,
        "reason": reason.strip()[:500],
        "at": datetime.now(UTC).isoformat(),
    }
    metadata[REPLAY_KEY] = True
    if gate_key != GATE_KEYS[-1]:
        metadata["last_successful_run"] = None
        # The digests and the inputs go with the runs they describe; only
        # where one was kept.
        for key in (RUN_PACKAGE_KEY, SUCCESSFUL_RUN_PACKAGE_KEY, RUN_INPUTS_KEY):
            if key in metadata:
                metadata[key] = None
        # A run still going tests the solution as it was: when it ends it is
        # no longer the session's latest, and is not recorded as its proof. It
        # is also remembered by name: the note of the reopening goes when the
        # gate is approved again, which can happen before that run ends.
        if metadata.get("latest_run"):
            voided = [r for r in metadata.get(VOIDED_RUNS_KEY) or [] if isinstance(r, str)]
            metadata[VOIDED_RUNS_KEY] = [*voided, metadata["latest_run"]][-20:]
        metadata["latest_run"] = None
        # Kept again when Gate 3 is next approved.
        metadata.pop(APPROVED_CONTENT_KEY, None)
    session.session_metadata = metadata
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


def append_messages(
    db: Session,
    session: WizardSession,
    user_content: str,
    assistant_content: str,
) -> WizardSession:
    lock_fresh(db, session)
    metadata = dict(session.session_metadata)
    messages = list(metadata.get("messages") or [])
    ts = datetime.now(UTC).isoformat()
    messages.append(
        {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "role": "user",
            "content": user_content,
            "createdAt": ts,
        }
    )
    messages.append(
        {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "role": "assistant",
            "content": assistant_content,
            "createdAt": ts,
        }
    )
    metadata["messages"] = messages
    session.session_metadata = metadata
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


def session_response(session: WizardSession) -> dict:
    return _to_response(session)
