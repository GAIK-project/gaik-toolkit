"""The Postgres agent's model-written SQL runs on a role that can only read the demo tables."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from api.routers import postgres_agent as route
from fastapi import HTTPException

READ_ONLY = (False, False, False, False, False, False, 0, 0)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(route, "_role_checked", None)
    monkeypatch.setattr(route, "_warned_fallback", False)
    monkeypatch.setattr(route, "_seeded", True)
    monkeypatch.delenv(route.AGENT_DATABASE_ENV, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_a_read_only_role_has_no_problems():
    assert route._role_problems(READ_ONLY) == []


@pytest.mark.parametrize(
    ("facts", "problem"),
    [
        ((True, False, False, False, False, False, 0, 0), "superuser"),
        ((False, True, False, False, False, False, 0, 0), "create roles"),
        ((False, False, False, True, False, False, 0, 0), "bypass row security"),
        ((False, False, False, False, True, False, 0, 0), "create schemas"),
        ((False, False, False, False, False, True, 0, 0), "create schemas"),
        ((False, False, False, False, False, False, 2, 0), "change 2 demo table(s)"),
        ((False, False, False, False, False, False, 0, 3), "read 3 table(s) outside"),
        (None, "not found"),
    ],
)
def test_a_role_that_can_do_more_than_read_is_named(facts, problem):
    assert any(problem in p for p in route._role_problems(facts))


def test_the_agent_uses_its_own_connection_when_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin@db/demo")
    monkeypatch.setenv(route.AGENT_DATABASE_ENV, "postgresql://agent@db/demo")

    assert route._agent_database_url() == ("postgresql://agent@db/demo", True)


def test_without_its_own_connection_the_agent_falls_back_and_says_so(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin@db/demo")

    assert route._agent_database_url() == ("postgresql://admin@db/demo", False)
    assert route.AGENT_DATABASE_ENV in caplog.text


def test_a_role_that_can_write_stops_the_agent(monkeypatch):
    monkeypatch.setenv(route.AGENT_DATABASE_ENV, "postgresql://agent@db/demo")
    monkeypatch.setattr(route, "_check_agent_role", lambda url: ["it is a superuser"])
    built = []
    monkeypatch.setattr(
        "gaik.software_components.postgres_agent.PostgresAgent",
        lambda *a, **k: built.append(a),
        raising=False,
    )

    with pytest.raises(HTTPException) as refused:
        route._resolve_agent()

    assert refused.value.status_code == 503
    assert "superuser" not in refused.value.detail  # the reasons stay in the log
    assert built == []


def test_the_role_is_checked_once_per_process(monkeypatch):
    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            calls.append(params)

            class Cursor:
                @staticmethod
                def fetchone():
                    return READ_ONLY

            return Cursor()

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda url: Conn())

    assert route._check_agent_role("postgresql://agent@db/demo") == []
    assert route._check_agent_role("postgresql://agent@db/demo") == []
    assert calls == [{"schema": route.DEMO_SCHEMA}]


def test_status_tells_whether_the_agent_has_its_own_role(monkeypatch):
    import asyncio

    monkeypatch.setenv("DATABASE_URL", "postgresql://admin@db/demo")
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is False
    monkeypatch.setenv(route.AGENT_DATABASE_ENV, "postgresql://agent@db/demo")
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is True


ADMIN_URL = os.getenv("GAIK_DEMO_TEST_POSTGRES_URL")


@pytest.mark.skipif(not ADMIN_URL, reason="set GAIK_DEMO_TEST_POSTGRES_URL to a throwaway database")
def test_the_role_script_makes_a_role_the_check_accepts(monkeypatch):
    """Against a real, throwaway PostgreSQL: the script's role passes, the owner does not."""
    import subprocess
    from urllib.parse import urlsplit, urlunsplit

    import psycopg

    route._seed_demo_schema.__globals__["_seeded"] = False
    route._seed_demo_schema(ADMIN_URL)
    script = Path(route.__file__).parents[1] / "scripts" / "postgres_agent_role.sql"
    subprocess.run(
        ["psql", ADMIN_URL, "-q", "-v", "agent_password=pw-test", "-f", str(script)],
        check=True,
    )
    parts = urlsplit(ADMIN_URL)
    host = parts.netloc.split("@", 1)[1]
    agent_url = urlunsplit(parts._replace(netloc=f"gaik_sql_agent:pw-test@{host}"))

    def facts(url):
        with psycopg.connect(url) as conn:
            return conn.execute(route._ROLE_FACTS_SQL, {"schema": route.DEMO_SCHEMA}).fetchone()

    assert route._role_problems(facts(agent_url)) == []
    assert "it is a superuser" in route._role_problems(facts(ADMIN_URL))
    with psycopg.connect(agent_url) as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute(f"DELETE FROM {route.DEMO_SCHEMA}.orders")
