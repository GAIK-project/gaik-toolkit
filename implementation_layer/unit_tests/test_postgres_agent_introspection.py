"""PostgresAgent introspection and result rows, with fake connections (issue #146)."""

import logging

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent import PostgresAgent  # noqa: E402
from gaik.software_components.postgres_agent.introspection import (  # noqa: E402
    introspect_schema,
)
from gaik.software_components.postgres_agent.models import (  # noqa: E402
    ColumnInfo,
    SchemaInfo,
    TableInfo,
)

URL = "postgresql://user:pass@localhost/db"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeIntrospectionConn:
    """Answers the introspection queries for tables ``customers`` and ``orders``."""

    def __init__(self, schema="public"):
        self.schema = schema
        self.queries = []

    def execute(self, query, params=None):
        text = str(query)
        self.queries.append(text)
        if params != (self.schema,):
            return _Result([])
        if "information_schema.tables" in text:
            return _Result([{"table_name": "customers"}, {"table_name": "orders"}])
        if "information_schema.columns" in text:
            return _Result(
                [
                    {
                        "table_name": table,
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                    }
                    for table in ("customers", "orders")
                ]
            )
        return _Result([])


def test_allowlist_entry_that_matches_no_table_is_reported(caplog):
    with caplog.at_level(logging.WARNING):
        schema = introspect_schema(FakeIntrospectionConn(), allowlist=["Customers", "orders"])
    assert [t.name for t in schema.tables] == ["orders"]
    assert "'Customers' matches no table" in caplog.text
    assert "did you mean 'customers'" in caplog.text
    assert "'orders' matches" not in caplog.text


def test_allowlist_that_matches_every_table_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        introspect_schema(FakeIntrospectionConn(), allowlist=["customers", "orders"])
    assert caplog.text == ""


def test_keys_are_read_from_pg_catalog():
    conn = FakeIntrospectionConn()
    introspect_schema(conn)
    assert not any("table_constraints" in q or "key_column_usage" in q for q in conn.queries)
    assert sum("pg_catalog.pg_constraint" in q for q in conn.queries) == 2


def test_mixed_case_schema_name_is_folded_for_introspection():
    agent = PostgresAgent(URL, schema_name="Sales", table_allowlist=["customers", "orders"])
    conn = FakeIntrospectionConn(schema="sales")
    agent._get_conn = lambda: conn
    assert agent.schema_name == "sales"
    assert [t.name for t in agent.get_schema().tables] == ["customers", "orders"]


class _Column:
    def __init__(self, name):
        self.name = name


class _Cursor:
    """Rows as dicts until ``row_factory`` is changed, like a dict_row cursor."""

    def __init__(self, names, rows):
        self.description = [_Column(n) for n in names]
        self._rows = rows
        self.row_factory = "dict_row"

    def fetchall(self):
        if self.row_factory == "dict_row":
            return [dict(zip([c.name for c in self.description], r)) for r in self._rows]
        return self._rows


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeQueryConn:
    def __init__(self, names, rows):
        self._cursor = _Cursor(names, rows)

    def transaction(self, **_):
        return _Transaction()

    def execute(self, query):
        return self._cursor


def _agent_returning(names, rows):
    agent = PostgresAgent(URL, table_allowlist=["customers", "orders"])
    agent._get_conn = lambda: FakeQueryConn(names, rows)
    return agent


def test_result_columns_with_the_same_name_keep_every_value():
    agent = _agent_returning(["count", "count"], [(10, 7)])
    rows = agent.run_sql("SELECT count(*), count(DISTINCT id) FROM orders")
    assert rows == [{"count": 10, "count_2": 7}]


def test_renamed_repeat_does_not_take_a_real_column_name():
    agent = _agent_returning(["count", "count", "count_2"], [(1, 2, 3)])
    assert agent.run_sql("SELECT 1") == [{"count": 1, "count_3": 2, "count_2": 3}]


def test_cached_sample_rows_are_not_sent_with_later_questions(monkeypatch):
    agent = PostgresAgent(URL, table_allowlist=["customers", "orders"])
    agent._schema = SchemaInfo(
        schema_name="public",
        tables=[
            TableInfo(
                name="customers",
                columns=[ColumnInfo(name="email", data_type="text", nullable=True)],
                sample_rows=[{"email": "secret@example.com"}],
            )
        ],
    )
    agent._schema_has_samples = True
    sent = []

    class Completions:
        @staticmethod
        def parse(**kwargs):
            sent.append(kwargs["messages"])
            raise RuntimeError("stop here")

    class Client:
        class beta:  # noqa: N801
            class chat:  # noqa: N801
                completions = Completions

    agent._model = "gpt-4o"
    monkeypatch.setattr(agent, "_get_llm_client", lambda: Client())
    with pytest.raises(RuntimeError, match="stop here"):
        agent.generate_sql("How many customers?")
    prompt = sent[0][1]["content"]
    assert "TABLE customers" in prompt
    assert "secret@example.com" not in prompt
    # The schema the caller asked for keeps its samples.
    assert agent.get_schema().tables[0].sample_rows == [{"email": "secret@example.com"}]
