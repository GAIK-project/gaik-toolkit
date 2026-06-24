import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)
from wizard_api.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(
    payload: SessionCreate, db: Session = Depends(get_db)
) -> SessionResponse:
    session = session_service.create_session(db, payload)
    return SessionResponse(**session_service.session_response(session))


@router.get("", response_model=SessionListResponse)
def list_sessions(
    user_id: str = Query(min_length=1, max_length=255),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    sessions = session_service.list_sessions(db, user_id)
    return SessionListResponse(
        sessions=[
            SessionResponse(**session_service.session_response(s)) for s in sessions
        ]
    )


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> SessionResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionResponse(**session_service.session_response(session))


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
) -> SessionResponse:
    session = session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    updated = session_service.update_session(db, session, payload)
    return SessionResponse(**session_service.session_response(updated))
