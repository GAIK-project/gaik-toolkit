"""PostgresAgent reads only the tables named in its required table_allowlist."""

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent import (  # noqa: E402
    PostgresAgent,
    UnsafeSQLError,
)
from gaik.software_components.postgres_agent.introspection import (  # noqa: E402
    introspect_schema,
)

URL = "postgresql://user:pass@localhost:1/db"


def test_agent_without_table_allowlist_is_not_constructed():
    with pytest.raises(TypeError, match="table_allowlist"):
        PostgresAgent(URL)


@pytest.mark.parametrize("value", [None, [], ()])
def test_agent_with_no_tables_named_is_not_constructed(value):
    with pytest.raises(ValueError, match="table_allowlist"):
        PostgresAgent(URL, table_allowlist=value)


@pytest.mark.parametrize("value", ["orders", ["orders", ""], ["orders", None]])
def test_table_allowlist_must_be_a_list_of_names(value):
    with pytest.raises(ValueError, match="table_allowlist"):
        PostgresAgent(URL, table_allowlist=value)


@pytest.mark.parametrize("schema", ["information_schema", "pg_catalog", "PG_CATALOG", "pg_toast"])
def test_system_schema_is_not_accepted_as_schema_name(schema):
    with pytest.raises(ValueError, match="system schema"):
        PostgresAgent(URL, table_allowlist=["tables"], schema_name=schema)


def test_agent_keeps_the_tables_it_was_given():
    agent = PostgresAgent(URL, table_allowlist=("customers", "orders"))
    assert agent.table_allowlist == ["customers", "orders"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM secrets",
        "SELECT * FROM public.secrets",
        "TABLE secrets",
        "WITH s AS (SELECT * FROM secrets) SELECT * FROM s",
        "WITH orders AS (SELECT * FROM secrets) SELECT * FROM orders",
        "SELECT * FROM orders WHERE customer_id IN (SELECT id FROM secrets)",
        "SELECT (SELECT count(*) FROM secrets) AS n",
        "SELECT * FROM orders WHERE EXISTS (SELECT 1 FROM secrets)",
        "SELECT * FROM orders o JOIN secrets s ON s.id = o.id",
        "SELECT * FROM orders, LATERAL (SELECT * FROM secrets) s",
        "SELECT id FROM orders UNION SELECT id FROM secrets",
        "SELECT id FROM orders EXCEPT SELECT id FROM secrets",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM information_schema.columns",
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT * FROM pg_tables",
        'SELECT * FROM "Orders"',
    ],
)
def test_query_touching_a_table_off_the_list_is_refused_before_it_runs(sql):
    agent = PostgresAgent(URL, table_allowlist=["orders"])

    def no_connection():
        raise AssertionError("the query reached the database")

    agent._get_conn = no_connection
    with pytest.raises(UnsafeSQLError):
        agent.run_sql(sql)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _KeysConn:
    """orders.customer_id references customers.id; orders.owner_id references secrets.id."""

    def execute(self, query, params=None):
        text = str(query)
        if "information_schema.tables" in text:
            names = ("customers", "orders", "secrets")
            return _Result([{"table_name": n} for n in names])
        if "information_schema.columns" in text:
            columns = [("customers", "id"), ("orders", "customer_id"), ("orders", "owner_id")]
            return _Result(
                [
                    {"table_name": t, "column_name": c, "data_type": "int", "is_nullable": "NO"}
                    for t, c in columns
                ]
            )
        if "contype = 'f'" in text:
            return _Result(
                [
                    {
                        "table_name": "orders",
                        "column_name": "customer_id",
                        "foreign_table": "customers",
                        "foreign_column": "id",
                    },
                    {
                        "table_name": "orders",
                        "column_name": "owner_id",
                        "foreign_table": "secrets",
                        "foreign_column": "id",
                    },
                ]
            )
        return _Result([])


def test_schema_shown_to_the_model_names_no_table_off_the_list():
    schema = introspect_schema(_KeysConn(), allowlist=["customers", "orders"])
    columns = {c.name: c for t in schema.tables for c in t.columns}
    assert [t.name for t in schema.tables] == ["customers", "orders"]
    assert columns["customer_id"].references == "customers.id"
    assert columns["owner_id"].references is None
    assert "secrets" not in schema.to_prompt_text()


def test_empty_allowlist_introspects_no_table():
    schema = introspect_schema(_KeysConn(), allowlist=[])
    assert schema.tables == []
