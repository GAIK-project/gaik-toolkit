import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from helpers import postgres_available
from wizard_api.config import get_database_url
from wizard_api.db import get_db
from wizard_api.main import app
from wizard_api.models import Base, WizardSession

requires_postgres = pytest.mark.skipif(not postgres_available(), reason="Postgres not available")


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
        session.query(WizardSession).delete()
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
