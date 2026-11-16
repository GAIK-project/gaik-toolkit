"""Valid queries the SQL validators used to refuse or render wrongly (issue #146).

Each accepted form is paired with a check that the read-only refusals still
hold inside it.
"""

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent.sql_safety import (  # noqa: E402
    UnsafeSQLError,
)
from gaik.software_components.postgres_agent.sql_safety import (  # noqa: E402
    validate_read_only as validate_pg,
)
from gaik.software_components.tabular_agent.sql_safety import (  # noqa: E402
    UnsafeSQLError as TabularUnsafeSQLError,
)
from gaik.software_components.tabular_agent.sql_safety import (  # noqa: E402
    validate_read_only as validate_duckdb,
)

# --- ALL, SOME and ROW are syntax, not functions (Postgres) -----------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders WHERE status <> ALL (ARRAY['x', 'y'])",
        "SELECT id FROM orders WHERE amount > SOME (ARRAY[1, 2])",
        "SELECT id FROM orders WHERE (id, amount) = ROW(1, 2)",
    ],
)
def test_postgres_accepts_all_some_and_row(sql):
    validate_pg(sql, allowlist=["orders"])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders WHERE id <> ALL (SELECT pg_read_file('x'))",
        "SELECT id FROM orders WHERE id > SOME (ARRAY[set_config('a', 'b', false)])",
        "SELECT ROW(pg_sleep(1))",
        "SELECT id FROM orders WHERE id = ALL (SELECT id FROM other.secrets)",
        "SELECT id FROM orders WHERE id = ROW((SELECT id FROM secrets))",
    ],
)
def test_postgres_still_checks_inside_all_some_and_row(sql):
    with pytest.raises(UnsafeSQLError):
        validate_pg(sql, allowlist=["orders"])


# --- EXCEPT and INTERSECT at the top level ----------------------------------


@pytest.mark.parametrize("op", ["EXCEPT", "INTERSECT"])
def test_postgres_accepts_except_and_intersect(op):
    out = validate_pg(f"SELECT id FROM orders {op} SELECT id FROM customers")
    assert op in out.upper()


@pytest.mark.parametrize("op", ["EXCEPT", "INTERSECT"])
def test_duckdb_accepts_except_and_intersect(op):
    out = validate_duckdb(
        f"SELECT region FROM sales {op} SELECT region FROM headcount",
        allowed_tables=["sales", "headcount"],
    )
    assert op in out.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders EXCEPT SELECT id FROM other.secrets",
        "SELECT id FROM orders INTERSECT SELECT set_config('a', 'b', false)",
        "SELECT id FROM orders EXCEPT SELECT id FROM secrets",
        "SELECT id FROM orders EXCEPT SELECT id FROM orders FOR UPDATE",
    ],
)
def test_postgres_set_operations_are_still_checked(sql):
    with pytest.raises(UnsafeSQLError):
        validate_pg(sql, allowlist=["orders"])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT region FROM sales EXCEPT SELECT * FROM read_csv('/etc/passwd')",
        "SELECT region FROM sales INTERSECT SELECT region FROM other_db.main.sales",
        "SELECT region FROM sales EXCEPT SELECT region FROM secrets",
    ],
)
def test_duckdb_set_operations_are_still_checked(sql):
    with pytest.raises(TabularUnsafeSQLError):
        validate_duckdb(sql, allowed_tables=["sales"])


# --- WITH RECURSIVE: every CTE is in scope in every body (Postgres) ---------

_FORWARD = "WITH RECURSIVE a AS (SELECT * FROM b), b AS (SELECT 1 AS x) SELECT * FROM a"


def test_postgres_recursive_cte_may_reference_a_later_cte():
    validate_pg(_FORWARD, allowlist=["orders"])


def test_postgres_recursive_cte_name_is_not_schema_qualified():
    out = validate_pg(_FORWARD)
    assert '"public".' not in out


def test_postgres_plain_with_keeps_forward_references_as_tables():
    out = validate_pg("WITH a AS (SELECT * FROM b), b AS (SELECT 1 AS x) SELECT * FROM a")
    assert '"public".b' in out


@pytest.mark.parametrize(
    "sql",
    [
        "WITH RECURSIVE a AS (SELECT * FROM secrets), b AS (SELECT 1) SELECT * FROM a",
        "WITH RECURSIVE a AS (SELECT * FROM other.b), b AS (SELECT 1) SELECT * FROM a",
        "WITH RECURSIVE a AS (SELECT pg_read_file('x')) SELECT * FROM a",
    ],
)
def test_postgres_recursive_ctes_are_still_checked(sql):
    with pytest.raises(UnsafeSQLError):
        validate_pg(sql, allowlist=["orders"])


# --- A render that would drop part of the query is refused ------------------


def test_duckdb_refuses_a_query_the_render_would_change():
    # sqlglot renders this as CAST(ordered_on AS TEXT), dropping the format.
    with pytest.raises(TabularUnsafeSQLError, match="cannot be checked as written"):
        validate_duckdb(
            "SELECT TO_CHAR(ordered_on, 'YYYY-MM') AS m FROM orders",
            allowed_tables=["orders"],
        )


def test_duckdb_strftime_still_renders_as_written():
    out = validate_duckdb(
        "SELECT strftime(ordered_on, '%Y-%m') AS m FROM orders", allowed_tables=["orders"]
    )
    assert "'%Y-%m'" in out


def test_postgres_date_trunc_keeps_its_time_zone():
    out = validate_pg("SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders")
    assert "Europe/Helsinki" in out
