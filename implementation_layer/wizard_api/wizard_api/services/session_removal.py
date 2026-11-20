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


def conversation_ids(state_dir: Path, session: WizardSession) -> set[str]:
    """The agent conversations of this session.

    All sessions share one project folder, so a conversation is found by its id.
    The session stores only its latest id; a conversation it replaced is found
    by the session id, which the agent's prompt carries.
    """
    ids: set[str] = set()
    stored = session.session_metadata.get("agent_sdk_session_id")
    if isinstance(stored, str) and agent_service.SDK_SESSION_ID.fullmatch(stored):
        ids.add(stored)
    needle = str(session.id).encode()
    for transcript in (state_dir / "projects").glob("*/*.jsonl"):
        if transcript.stem in ids or not agent_service.SDK_SESSION_ID.fullmatch(transcript.stem):
            continue
        if needle in transcript.read_bytes():
            ids.add(transcript.stem)
    return ids


def _remove_conversations(session: WizardSession) -> None:
    state_dir = agent_service.agent_state_dir()
    if state_dir is None:
        return
    for conversation in conversation_ids(state_dir, session):
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
    _remove_conversations(session)
    if folder.exists():
        shutil.rmtree(folder)
    db.delete(session)
    # Its place under WIZARD_MAX_SESSIONS_PER_USER goes back with it; its spend stays.
    usage_caps.release_session(db, session.user_id, commit=False)
    db.commit()
