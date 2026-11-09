"""PostgresAgent.run_sql against a real PostgreSQL database.

The validator is tested without a database in ``test_postgres_agent_sql_safety.py``.
These tests cover what only PostgreSQL can show: that each query runs in a
transaction started read-only, that nothing a query does to the session
outlives it, and that names resolve inside the agent's schema.

Skipped unless ``GAIK_TEST_PG_URL`` points at a database the tests may create
a schema in, e.g. ``docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432
postgres:17`` and
``GAIK_TEST_PG_URL=postgresql://postgres:postgres@localhost:5432/postgres``.
"""

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent import PostgresAgent, UnsafeSQLError  # noqa: E402
from gaik.software_components.postgres_agent import agent as agent_module  # noqa: E402

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a PostgreSQL database")


@pytest.fixture
def schema():
    name = f"gaik_test_agent_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {name}")
        conn.execute(f"CREATE TABLE {name}.orders (id int PRIMARY KEY, amount numeric)")
        conn.execute(f"INSERT INTO {name}.orders VALUES (1, 10), (2, 20)")
        conn.execute(f"CREATE TABLE {name}.users (id int)")
        conn.execute(f'CREATE TABLE {name}."Users" (id int)')
        conn.execute(f'INSERT INTO {name}."Users" VALUES (7)')
        conn.execute(f"CREATE SEQUENCE {name}.counter")
    yield name
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {name} CASCADE")


@pytest.fixture
def unvalidated(monkeypatch):
    """Let any SQL reach the database, to test what the database itself refuses."""
    monkeypatch.setattr(agent_module, "validate_read_only", lambda sql, **_: sql)


def test_runs_a_query_in_the_schema(schema):
    with PostgresAgent(PG_URL, schema_name=schema) as agent:
        rows = agent.run_sql("SELECT count(*) AS n, sum(amount) AS total FROM orders")
    assert rows == [{"n": 2, "total": 30}]


def test_cte_and_join_still_run_after_schema_qualification(schema):
    with PostgresAgent(PG_URL, schema_name=schema, table_allowlist=["orders"]) as agent:
        rows = agent.run_sql(
            "WITH big AS (SELECT * FROM orders WHERE amount > 10) "
            "SELECT o.id FROM orders o JOIN big ON big.id = o.id"
        )
    assert rows == [{"id": 2}]


def test_query_runs_in_a_read_only_transaction(schema, unvalidated):
    with PostgresAgent(PG_URL, schema_name=schema) as agent:
        rows = agent.run_sql("SELECT current_setting('transaction_read_only') AS read_only")
        assert rows == [{"read_only": "on"}]
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            agent.run_sql("SELECT nextval('counter')")


def test_transaction_is_read_only_whatever_the_session_default(schema, unvalidated):
    with PostgresAgent(PG_URL, schema_name=schema) as agent:
        agent._get_conn().execute("SET default_transaction_read_only = off")
        rows = agent.run_sql("SELECT current_setting('transaction_read_only') AS read_only")
        assert rows == [{"read_only": "on"}]
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            agent.run_sql("SELECT nextval('counter')")


def test_session_settings_changed_by_a_query_do_not_outlive_it(schema, unvalidated):
    with PostgresAgent(PG_URL, schema_name=schema, statement_timeout_ms=4321) as agent:
        agent.run_sql(
            "SELECT set_config('statement_timeout', '0', false), "
            "set_config('default_transaction_read_only', 'off', false), "
            "set_config('search_path', 'pg_catalog', false)"
        )
        conn = agent._get_conn()
        assert conn.execute("SHOW statement_timeout").fetchone() == {"statement_timeout": "4321ms"}
        assert conn.execute("SHOW default_transaction_read_only").fetchone() == {
            "default_transaction_read_only": "on"
        }
        assert conn.execute("SHOW search_path").fetchone() == {"search_path": schema}


def test_connection_is_usable_after_a_failed_query(schema):
    with PostgresAgent(PG_URL, schema_name=schema) as agent:
        with pytest.raises(psycopg.errors.UndefinedColumn):
            agent.run_sql("SELECT no_such_column FROM orders")
        assert agent.run_sql("SELECT id FROM orders ORDER BY id") == [{"id": 1}, {"id": 2}]


def test_unqualified_system_relation_does_not_resolve(schema):
    """Without the schema pin this would read pg_catalog through the search path."""
    with PostgresAgent(PG_URL, schema_name=schema) as agent:
        with pytest.raises(psycopg.errors.UndefinedTable):
            agent.run_sql("SELECT * FROM pg_user")


def test_allowlist_tells_mixed_case_tables_apart(schema):
    with PostgresAgent(PG_URL, schema_name=schema, table_allowlist=["users"]) as agent:
        assert [t.name for t in agent.get_schema().tables] == ["users"]
        assert agent.run_sql("SELECT * FROM users") == []
        with pytest.raises(UnsafeSQLError):
            agent.run_sql('SELECT * FROM "Users"')
    with PostgresAgent(PG_URL, schema_name=schema, table_allowlist=["Users"]) as agent:
        assert [t.name for t in agent.get_schema().tables] == ["Users"]
        assert agent.run_sql('SELECT * FROM "Users"') == [{"id": 7}]


def test_cte_named_after_a_table_outside_the_allowlist_is_rejected(schema):
    with PostgresAgent(PG_URL, schema_name=schema, table_allowlist=["orders"]) as agent:
        with pytest.raises(UnsafeSQLError):
            agent.run_sql("WITH users AS (SELECT * FROM users) SELECT * FROM users")
