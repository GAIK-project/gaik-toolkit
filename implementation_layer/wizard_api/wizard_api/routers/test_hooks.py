"""Dev/test-only hooks — never enable outside controlled E2E (WIZARD_TEST_HOOKS=1).

``main`` mounts this router only when ``WIZARD_TEST_HOOKS=1``, and every hook
answers 404 without it as well.
"""

import os
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.errors import api_error
from wizard_api.ownership import session_belongs_to_requester
from wizard_api.services import artifact_sync, draft_store, session_service

router = APIRouter(prefix="/test", tags=["test"])


def _require_hooks() -> None:
    if os.getenv("WIZARD_TEST_HOOKS") != "1":
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/shutdown")
def shutdown() -> dict[str, bool]:
    """Exit the API process so Docker restart policy brings up a fresh instance."""
    _require_hooks()
    os._exit(0)


def _session_dir(db: Session, session_id: uuid.UUID) -> str:
    session = session_service.get_session(db, session_id)
    if session is None or not session.output_dir:
        raise HTTPException(status_code=404, detail="session not found")
    return session.output_dir


@router.post(
    "/sessions/{session_id}/draft",
    status_code=204,
    dependencies=[Depends(_require_hooks), Depends(session_belongs_to_requester)],
)
def write_session_draft(
    session_id: uuid.UUID,
    blueprint: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> None:
    """Write ``blueprint`` as the session's agent draft, as the agent would.

    For the stack E2E, whose Playwright container cannot reach the API's
    session folder. Goes through ``draft_store.write_draft``: an invalid
    blueprint is refused with 422 and nothing is written; the file is the
    draft and nothing else.
    """
    output_dir = _session_dir(db, session_id)
    os.makedirs(output_dir, exist_ok=True)
    try:
        draft_store.write_draft(output_dir, blueprint)
    except ValidationError as exc:
        raise api_error(422, "invalid_draft", "The draft is not a valid blueprint.") from exc
    except ValueError as exc:
        raise api_error(422, "invalid_draft", str(exc)) from exc


@router.get(
    "/sessions/{session_id}/draft",
    dependencies=[Depends(_require_hooks), Depends(session_belongs_to_requester)],
)
def read_session_draft(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The session's agent draft as it is on disk; 404 while there is none."""
    draft = artifact_sync.read_draft_blueprint(_session_dir(db, session_id))
    if draft is None:
        raise HTTPException(status_code=404, detail="no draft")
    return draft
