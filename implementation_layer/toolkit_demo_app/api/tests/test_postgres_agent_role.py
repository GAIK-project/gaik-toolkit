"""The Postgres agent's model-written SQL runs on a role that can only read the demo tables."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from api.routers import postgres_agent as route
from fastapi import HTTPException

READ_ONLY = (False, False, False, False, False, False, False, 0, 0, 0, 0, 0, False, False, 0, False)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(route, "_role_checked", None)
    monkeypatch.setattr(route, "_role_checked_at", 0.0)
    monkeypatch.setattr(route, "_warned_fallback", False)
    monkeypatch.setattr(route, "_seeded", True)
    monkeypatch.delenv(route.AGENT_DATABASE_ENV, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_a_read_only_role_has_no_problems():
    assert route._role_problems(READ_ONLY) == []


def _with(**changes):
    names = [
        "superuser",
        "createrole",
        "createdb",
        "bypassrls",
        "replication",
        "db_create",
        "schema_create",
        "memberships",
        "writable",
        "elsewhere",
        "definer",
        "server_files",
        "switched",
        "large_objects",
        "extensions",
        "default_grants",
    ]
    facts = dict(zip(names, READ_ONLY))
    facts.update(changes)
    return tuple(facts[n] for n in names)


@pytest.mark.parametrize(
    ("facts", "problem"),
    [
        (_with(superuser=True), "superuser"),
        (_with(createrole=True), "create roles"),
        (_with(bypassrls=True), "bypass row security"),
        (_with(db_create=True), "create schemas"),
        (_with(schema_create=True), "create schemas"),
        (_with(memberships=1), "member of 1 other role"),
        (_with(writable=2), "change or maintain 2 table(s) or view(s)"),
        (_with(elsewhere=3), "read or use 3 relation(s) or sequence(s) besides the demo tables"),
        (_with(definer=1), "SECURITY DEFINER"),
        (_with(replication=True), "replication attribute"),
        (_with(server_files=2), "2 function(s) that read or list server files"),
        (_with(switched=True), "switches to another role"),
        (_with(large_objects=True), "large objects"),
        (_with(extensions=1), "reaches other hosts or files"),
        (_with(default_grants=True), "default privileges"),
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


def test_a_second_check_within_ten_minutes_reuses_the_result(monkeypatch):
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

    monkeypatch.setattr(psycopg, "connect", lambda url, **kwargs: Conn())
    assert route._check_agent_role("postgresql://agent@db/demo") == []
    assert route._check_agent_role("postgresql://agent@db/demo") == []
    assert len(calls) == 1
    assert calls[0]["schema"] == route.DEMO_SCHEMA
    assert calls[0]["tables"] == route.DEMO_TABLES
    assert {"pg_read_file", "pg_ls_dir", "lo_import"} <= set(calls[0]["server_file_functions"])


def test_the_role_script_turns_replication_off():
    script = Path(route.__file__).parents[1] / "scripts" / "postgres_agent_role.sql"
    alter = " ".join(
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if not line.startswith("--")
    )
    assert "NOREPLICATION" in alter


def test_two_first_requests_seed_the_demo_schema_once(monkeypatch):
    import threading
    import time as real_time

    import psycopg

    monkeypatch.setattr(route, "_seeded", False)
    connects = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, *params):
            real_time.sleep(0.05)  # the second request arrives while the first seeds

            class Cursor:
                @staticmethod
                def fetchone():
                    return (0,)

            return Cursor()

    def connect(url, **kwargs):
        connects.append(url)
        return Conn()

    monkeypatch.setattr(psycopg, "connect", connect)
    threads = [
        threading.Thread(target=route._seed_demo_schema, args=("postgresql://admin@db/demo",))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert connects == ["postgresql://admin@db/demo"]
    assert route._seeded is True


def test_status_reports_the_last_check_and_never_connects(monkeypatch):
    import asyncio

    import psycopg

    def no_connect(*args, **kwargs):
        pytest.fail("/status must not connect")

    monkeypatch.setattr(psycopg, "connect", no_connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin@db/demo")
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is False
    monkeypatch.setenv(route.AGENT_DATABASE_ENV, "postgresql://agent@db/demo")
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is False  # not checked
    monkeypatch.setattr(route, "_role_checked", ["it is a superuser"])
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is False
    monkeypatch.setattr(route, "_role_checked", [])
    assert asyncio.run(route.postgres_agent_status()).own_read_only_role is True


def test_a_passing_check_is_repeated_after_ten_minutes(monkeypatch):
    import psycopg

    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            calls.append(1)

            class Cursor:
                @staticmethod
                def fetchone():
                    return READ_ONLY

            return Cursor()

    monkeypatch.setattr(psycopg, "connect", lambda url, **kwargs: Conn())
    now = [1000.0]
    monkeypatch.setattr(route.time, "monotonic", lambda: now[0])

    route._check_agent_role("postgresql://agent@db/demo")
    now[0] += 60
    route._check_agent_role("postgresql://agent@db/demo")
    now[0] += route._ROLE_RECHECK_SECONDS
    route._check_agent_role("postgresql://agent@db/demo")

    assert len(calls) == 2


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
        ["psql", ADMIN_URL, "-q", "-f", str(script)],
        check=True,
    )
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        # the script sets no password; a test sets one the way \\password would not
        conn.execute("ALTER ROLE gaik_sql_agent PASSWORD 'pw-test'")
    parts = urlsplit(ADMIN_URL)
    host = parts.netloc.split("@", 1)[1]
    agent_url = urlunsplit(parts._replace(netloc=f"gaik_sql_agent:pw-test@{host}"))

    def facts(url):
        with psycopg.connect(url) as conn:
            return conn.execute(route._ROLE_FACTS_SQL, route._ROLE_FACTS_PARAMS).fetchone()

    assert route._role_problems(facts(agent_url)) == []
    assert "it is a superuser" in route._role_problems(facts(ADMIN_URL))

    # Each grant below makes the role more than read-only; the check names each one.
    cases = {
        "member of": "GRANT pg_read_server_files TO gaik_sql_agent",
        "change": "GRANT INSERT ON public.gaik_review_index TO gaik_sql_agent",
        "read or use": "GRANT SELECT ON public.gaik_review_view TO gaik_sql_agent",
        "read or use ": "GRANT SELECT (secret) ON public.gaik_review_index TO gaik_sql_agent",
        "SECURITY DEFINER": "GRANT EXECUTE ON FUNCTION public.gaik_review_wipe() TO gaik_sql_agent",
        "server files": "GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_file(text) TO gaik_sql_agent",
        "besides the demo tables": f"GRANT SELECT ON {route.DEMO_SCHEMA}.gaik_review_peek "
        "TO gaik_sql_agent",
    }
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"DROP VIEW IF EXISTS {route.DEMO_SCHEMA}.gaik_review_peek")
        conn.execute("DROP VIEW IF EXISTS public.gaik_review_view")
        conn.execute("DROP TABLE IF EXISTS public.gaik_review_index")
        conn.execute("CREATE TABLE public.gaik_review_index (id int, secret text)")
        conn.execute(
            "CREATE VIEW public.gaik_review_view AS SELECT id FROM public.gaik_review_index"
        )
        conn.execute(
            f"CREATE VIEW {route.DEMO_SCHEMA}.gaik_review_peek AS "
            "SELECT secret FROM public.gaik_review_index"
        )
        conn.execute(
            "CREATE OR REPLACE FUNCTION public.gaik_review_wipe() RETURNS void "
            "LANGUAGE sql SECURITY DEFINER AS 'DELETE FROM public.gaik_review_index'"
        )
        conn.execute("REVOKE EXECUTE ON FUNCTION public.gaik_review_wipe() FROM PUBLIC")
        assert route._role_problems(facts(agent_url)) == []
        for problem, grant in cases.items():
            conn.execute(grant)
            found = route._role_problems(facts(agent_url))
            assert any(problem.strip() in p for p in found), (grant, found)
            conn.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
        assert route._role_problems(facts(agent_url)) == []
        conn.execute("ALTER ROLE gaik_sql_agent REPLICATION")
        assert "it has the replication attribute" in route._role_problems(facts(agent_url))
    # Running the script again turns the attribute off.
    subprocess.run(["psql", ADMIN_URL, "-q", "-f", str(script)], check=True)
    assert route._role_problems(facts(agent_url)) == []

    with psycopg.connect(agent_url) as conn:
        assert conn.execute(f"SELECT count(*) FROM {route.DEMO_SCHEMA}.orders").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM public.gaik_review_index")


@pytest.mark.skipif(not ADMIN_URL, reason="set GAIK_DEMO_TEST_POSTGRES_URL to a throwaway database")
def test_a_role_switched_through_the_url_options_is_refused():
    from urllib.parse import urlsplit, urlunsplit

    import psycopg

    # The login role is the owner; a role set through the URL's options does not change it.
    parts = urlsplit(ADMIN_URL)
    switched = urlunsplit(parts._replace(query="options=-crole%3Dgaik_sql_agent"))
    with psycopg.connect(switched) as conn:
        facts = conn.execute(route._ROLE_FACTS_SQL, route._ROLE_FACTS_PARAMS).fetchone()
    problems = route._role_problems(facts)
    assert "it is a superuser" in problems
    assert any("switches to another role" in p for p in problems)
