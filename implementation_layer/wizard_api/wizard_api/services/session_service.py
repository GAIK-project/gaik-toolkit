import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizard_api.config import build_session_output_dir
from wizard_api.models import WizardSession
from wizard_api.schemas.session import SessionCreate, SessionUpdate
from wizard_api.session_state import merge_gate_statuses


def _to_response(session: WizardSession) -> dict:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "step": session.step,
        "gate_statuses": session.gate_statuses,
        "metadata": session.session_metadata,
        "output_dir": session.output_dir,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def create_session(db: Session, payload: SessionCreate) -> WizardSession:
    session_id = uuid.uuid4()
    output_dir = payload.output_dir or build_session_output_dir(
        payload.user_id, session_id
    )
    session = WizardSession(
        id=session_id,
        user_id=payload.user_id,
        output_dir=output_dir,
        session_metadata=dict(payload.metadata),
    )
    db.add(session)
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


def update_session(
    db: Session, session: WizardSession, payload: SessionUpdate
) -> WizardSession:
    if payload.step is not None:
        session.step = payload.step
    if payload.gate_statuses is not None:
        session.gate_statuses = merge_gate_statuses(
            session.gate_statuses, payload.gate_statuses
        )
    if payload.metadata is not None:
        session.session_metadata = {**session.session_metadata, **payload.metadata}
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


def session_response(session: WizardSession) -> dict:
    return _to_response(session)
