"""Session state survives wizard_api process restart (US-S1-01 / #11)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from helpers import requires_postgres
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from wizard_api.config import get_database_url
from wizard_api.db import get_db
from wizard_api.main import app
from wizard_api.models import Base, BlueprintVersion, WizardSession


@pytest.fixture
def persistence_engine():
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@contextmanager
def api_process(engine) -> Iterator[TestClient]:
    """Fresh TestClient + DB session — simulates a new wizard_api process."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    db.close()


def _delete_session(engine, session_id: str) -> None:
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    try:
        sid = uuid.UUID(session_id)
        db.query(BlueprintVersion).filter(BlueprintVersion.session_id == sid).delete()
        db.query(WizardSession).filter(WizardSession.id == sid).delete()
        db.commit()
    finally:
        db.close()


@requires_postgres
def test_session_survives_api_restart(persistence_engine) -> None:
    user_id = "restart-test-user"
    session_id: str | None = None

    try:
        # --- Process 1: create session, advance to step 2, append chat ---
        with api_process(persistence_engine) as client:
            create = client.post(
                "/sessions",
                json={"user_id": user_id, "title": "Restart persistence"},
            )
            assert create.status_code == 201
            body = create.json()
            session_id = body["id"]
            assert body["step"] == 1
            assert body["active_version"] == 1

            patched = client.patch(
                f"/sessions/{session_id}",
                json={"step": 2},
            )
            assert patched.status_code == 200
            assert patched.json()["step"] == 2

            messaged = client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "user_content": "Need voice reporting for maintenance",
                    "assistant_content": "Logged under step 2.",
                },
            )
            assert messaged.status_code == 200
            snapshot = messaged.json()

        expected_step = snapshot["step"]
        expected_messages = snapshot["messages"]
        expected_active_version = snapshot["active_version"]
        expected_blueprint = snapshot["blueprint"]

        # --- Process 2: new API instance, same Postgres ---
        with api_process(persistence_engine) as client:
            resumed = client.get(f"/sessions/{session_id}")
            assert resumed.status_code == 200
            body = resumed.json()

        assert body["step"] == expected_step == 2
        assert body["messages"] == expected_messages
        assert len(body["messages"]) == 2
        assert body["messages"][0]["content"] == "Need voice reporting for maintenance"
        assert body["messages"][1]["content"] == "Logged under step 2."
        assert body["active_version"] == expected_active_version
        assert body["blueprint"]["name"] == expected_blueprint["name"]
        assert body["blueprint"]["steps"] == expected_blueprint["steps"]
    finally:
        if session_id:
            _delete_session(persistence_engine, session_id)
