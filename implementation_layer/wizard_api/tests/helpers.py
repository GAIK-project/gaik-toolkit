import pytest
from sqlalchemy import create_engine, text

from wizard_api.config import get_database_url


def postgres_available() -> bool:
    try:
        engine = create_engine(get_database_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(not postgres_available(), reason="Postgres not available")
