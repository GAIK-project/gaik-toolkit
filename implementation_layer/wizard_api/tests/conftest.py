import sys
from pathlib import Path

# solution_wizard src (BPMN generation) — not a pip package in this repo layout
_SOLUTION_WIZARD_SRC = Path(__file__).resolve().parents[2] / "solution_wizard" / "src"
if _SOLUTION_WIZARD_SRC.is_dir():
    sys.path.insert(0, str(_SOLUTION_WIZARD_SRC))

import pytest
from fastapi.testclient import TestClient
from helpers import postgres_available
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from wizard_api import config
from wizard_api.config import get_database_url
from wizard_api.db import get_db
from wizard_api.main import app
from wizard_api.models import Base, BlueprintVersion, UsageTotal, WizardSession

requires_postgres = pytest.mark.skipif(not postgres_available(), reason="Postgres not available")


@pytest.fixture(autouse=True)
def _service_token_comes_from_this_test_only():
    """Each test sets (or leaves unset) the service token via monkeypatch.

    ``config`` consumes the variable out of the environment on first read and
    caches it, so without this a token set by one test would still be in force
    for the next one after monkeypatch has restored the environment.
    """
    config.forget_consumed_secret("WIZARD_API_TOKEN")
    yield
    config.forget_consumed_secret("WIZARD_API_TOKEN")


@pytest.fixture(autouse=True)
def _usage_caps_off_unless_a_test_sets_them(monkeypatch):
    """The usage caps are on by default (config); most tests create many sessions
    for one user and are about something else. tests/test_usage_caps.py sets them."""
    for name in (
        "WIZARD_SESSION_MAX_COST_USD",
        "WIZARD_USER_MAX_COST_USD",
        "WIZARD_DEPLOYMENT_MAX_COST_USD",
        "WIZARD_MAX_SESSIONS_PER_USER",
    ):
        monkeypatch.setenv(name, "0")
    monkeypatch.delenv("WIZARD_COST_WARN_RATIO", raising=False)


@pytest.fixture
def db_engine():
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.query(BlueprintVersion).delete()
        session.query(WizardSession).delete()
        session.query(UsageTotal).delete()
        session.commit()
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def api_client():
    with TestClient(app) as test_client:
        yield test_client
