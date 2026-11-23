"""Removing a whole session: everything the wizard keeps for it.

The session's row and blueprint versions, its folder (uploads, cases, the PoC
package, saved runs), its sandbox Jobs and the agent's conversation files.
The row goes last, so a removal that stops halfway can be repeated: until then
the session is still listed and every step below finds what is left.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from wizard_api.config import get_session_output_root
from wizard_api.models import WizardSession
from wizard_api.services import agent_service, sandbox_runner, usage_caps

logger = logging.getLogger(__name__)

#: Set in session metadata by an operator: the session stays until it is cleared.
PROTECTED_KEY = "protected"


class ProtectedSessionError(RuntimeError):
    """An operator has marked this session to be kept."""


class SessionFolderError(RuntimeError):
    """The stored folder is not this session's folder under the output root."""


def is_protected(session: WizardSession) -> bool:
    return session.session_metadata.get(PROTECTED_KEY) is True


def session_folder(session: WizardSession) -> Path:
    """The session's own folder, checked before anything under it is removed."""
    root = get_session_output_root().resolve()
    folder = Path(session.output_dir).resolve()
    if folder.name != str(session.id) or root not in folder.parents:
        raise SessionFolderError(f"session {session.id} has a folder outside the output root")
    return folder


def _stop_runs(session: WizardSession) -> None:
    if not sandbox_runner.kubernetes_available():
        return
    try:
        sandbox_runner.SandboxRunner().delete_session_runs(str(session.id))
    except sandbox_runner.SandboxNotConfiguredError:
        return


#: Every agent conversation the session has had. The chat route adds each new one
#: beside ``agent_sdk_session_id``, which holds only the latest.
CONVERSATIONS_KEY = "agent_sdk_session_ids"


def stored_conversation_ids(metadata: dict) -> set[str]:
    """The conversation ids a session stored itself, in the shape the CLI gives them."""
    listed = metadata.get(CONVERSATIONS_KEY)
    candidates = [
        metadata.get("agent_sdk_session_id"),
        *(listed if isinstance(listed, list) else []),
    ]
    return {
        value
        for value in candidates
        if isinstance(value, str) and agent_service.SDK_SESSION_ID.fullmatch(value)
    }


def conversation_ids(
    state_dir: Path, session: WizardSession, claimed: frozenset[str] = frozenset()
) -> set[str]:
    """The agent conversations of this session.

    All sessions share one project folder, so a conversation is known by its id,
    and the ids the session stored are its own. A session from before the list
    was kept stored only its latest id; a conversation it replaced is found by the
    session's own folder, which the server names in the agent's first message.
    Not by the session id alone: a transcript that only mentions it, such as
    another session's where the id was pasted, would be taken for this one's.
    ``claimed`` are the ids other sessions stored; they are never this one's.
    """
    ids = stored_conversation_ids(session.session_metadata) - claimed
    folder = getattr(session, "output_dir", None)
    if not folder:
        return ids
    needle = str(folder).encode()
    for transcript in (state_dir / "projects").glob("*/*.jsonl"):
        stem = transcript.stem
        if stem in ids or stem in claimed or not agent_service.SDK_SESSION_ID.fullmatch(stem):
            continue
        if needle in transcript.read_bytes():
            ids.add(stem)
    return ids


def _claimed_elsewhere(db: Session, session: WizardSession) -> frozenset[str]:
    """The conversation ids the other sessions stored, read without their messages."""
    rows = (
        db.query(
            WizardSession.session_metadata["agent_sdk_session_id"],
            WizardSession.session_metadata[CONVERSATIONS_KEY],
        )
        .filter(WizardSession.id != session.id)
        .all()
    )
    return frozenset(
        conversation
        for latest, listed in rows
        for conversation in stored_conversation_ids(
            {"agent_sdk_session_id": latest, CONVERSATIONS_KEY: listed}
        )
    )


def _remove_conversations(db: Session, session: WizardSession) -> None:
    state_dir = agent_service.agent_state_dir()
    if state_dir is None:
        return
    for conversation in conversation_ids(state_dir, session, _claimed_elsewhere(db, session)):
        for project in (state_dir / "projects").glob("*"):
            (project / f"{conversation}.jsonl").unlink(missing_ok=True)
            if (project / conversation).is_dir():
                shutil.rmtree(project / conversation)
        env = state_dir / "session-env" / conversation
        if env.is_dir():
            shutil.rmtree(env)


def remove(db: Session, session: WizardSession) -> None:
    """Remove the session. The caller has ended its live agent."""
    if is_protected(session):
        raise ProtectedSessionError(str(session.id))
    folder = session_folder(session)
    _stop_runs(session)
    _remove_conversations(db, session)
    if folder.exists():
        shutil.rmtree(folder)
    db.delete(session)
    # Its place under WIZARD_MAX_SESSIONS_PER_USER goes back with it; its spend stays.
    usage_caps.release_session(db, session.user_id)
    db.commit()
