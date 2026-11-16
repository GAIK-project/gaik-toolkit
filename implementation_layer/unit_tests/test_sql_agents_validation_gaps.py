"""Valid queries the SQL validators used to refuse or render wrongly (issue #146).

Each accepted form is paired with a check that the read-only refusals still
hold inside it.
"""

import logging

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

import sqlglot.tokens  # noqa: E402
from gaik.software_components import _sql_parse  # noqa: E402
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
from sqlglot.dialects.dialect import Dialect  # noqa: E402

# sqlglot's compiled build (sqlglot[c]) skips the check for dropped arguments.
COMPILED = bool(getattr(sqlglot.tokens, "SQLGLOTC_INSTALLED", False))
needs_argument_check = pytest.mark.skipif(
    COMPILED, reason="sqlglot's compiled build skips the argument check"
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


# --- An argument sqlglot drops while parsing is refused ---------------------


@needs_argument_check
def test_duckdb_refuses_the_time_zone_date_trunc_drops():
    # sqlglot reads DuckDB's date_trunc with two arguments and drops the third while
    # parsing, so the render matches the tree and only the parse shows the loss.
    with pytest.raises(TabularUnsafeSQLError, match="loses one of its arguments"):
        validate_duckdb(
            "SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders",
            allowed_tables=["orders"],
        )


@needs_argument_check
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT array_agg(name, ', ') FROM orders",
        "SELECT epoch_ms(ms, 3) FROM orders",
        "SELECT encode(note, 'latin1') FROM orders",
    ],
)
def test_duckdb_refuses_other_dropped_arguments(sql):
    with pytest.raises(TabularUnsafeSQLError, match="loses one of its arguments"):
        validate_duckdb(sql, allowed_tables=["orders"])


@needs_argument_check
def test_postgres_refuses_a_dropped_argument():
    with pytest.raises(UnsafeSQLError, match="loses one of its arguments"):
        validate_pg("SELECT array_agg(name, ', ') FROM orders")


@pytest.mark.parametrize(
    "sql",
    [
        # Values sqlglot rewrites on the way in are still arguments it uses.
        "SELECT date_trunc('d', ts) FROM orders",
        "SELECT date_trunc(month, ts) FROM orders",
        "SELECT date_diff('day', ordered_on, shipped_on) FROM orders",
        "SELECT strftime(ts, '%-d.%-m.%Y') FROM orders",
        "SELECT json_extract_string(doc, 'a'), doc ->> '$.b' FROM orders",
        "SELECT list_sort(tags, 'DESC'), list_sort(tags, 'ASC', 'NULLS FIRST') FROM orders",
        "SELECT log10(amount), epoch_ms(ms) FROM orders",
    ],
)
def test_duckdb_keeps_arguments_sqlglot_rewrites(sql):
    validate_duckdb(sql, allowed_tables=["orders"])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT to_char(ts, 'YYYY-MM'), date_trunc('month', ts) FROM orders",
        "SELECT json_extract_path(doc, 'a', 'b') FROM orders",
        "SELECT date_bin('15 minutes', ts, TIMESTAMP '2001-01-01') FROM orders",
    ],
)
def test_postgres_keeps_arguments_sqlglot_rewrites(sql):
    validate_pg(sql)


# --- sqlglot's compiled build (sqlglot[c]) ----------------------------------
#
# Its parser classes are native: an instance attribute cannot be set on them and a
# Python class cannot derive from them. Where the pure-Python build is installed, a
# parser that refuses the attribute the same way stands in for it; where sqlglotc
# is installed, the installed build is the compiled one.


def _read_only_functions(parser_class):
    class ReadOnlyFunctions(parser_class):
        def __setattr__(self, name, value):
            if name == "FUNCTIONS":
                raise AttributeError(
                    f"'{parser_class.__name__}' object attribute 'FUNCTIONS' is read-only"
                )
            super().__setattr__(name, value)

    return ReadOnlyFunctions


def _use_read_only_parsers(monkeypatch):
    for name in ("duckdb", "postgres"):
        dialect = type(Dialect.get_or_raise(name))
        monkeypatch.setattr(dialect, "parser_class", _read_only_functions(dialect.parser_class))


@pytest.fixture(params=["installed build", "compiled build"])
def sqlglot_build(request, monkeypatch):
    if request.param == "compiled build":
        if COMPILED:
            pytest.skip("the installed build is the compiled one")
        _use_read_only_parsers(monkeypatch)
    return request.param


@pytest.fixture
def compiled_build(monkeypatch):
    if not COMPILED:
        _use_read_only_parsers(monkeypatch)


def test_both_builds_validate_a_plain_query(sqlglot_build):
    out = validate_duckdb(
        "SELECT region, sum(amount) FROM sales GROUP BY region", allowed_tables=["sales"]
    )
    assert out == "SELECT region, SUM(amount) FROM sales GROUP BY region"
    out = validate_pg("SELECT id, name FROM customers WHERE id = 1", allowlist=["customers"])
    assert out == 'SELECT id, name FROM "public".customers WHERE id = 1'


_NOT_A_SELECT = "Only read-only SELECT queries are allowed"
_ONE_STATEMENT = "Expected exactly one SQL statement"
_NOT_ALLOWED = "not in the allowed table list"


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("INSERT INTO sales VALUES (1)", _NOT_A_SELECT),
        ("UPDATE sales SET units = 0", _NOT_A_SELECT),
        ("DELETE FROM sales", _NOT_A_SELECT),
        ("DROP TABLE sales", _NOT_A_SELECT),
        ("CREATE TABLE x AS SELECT 1", _NOT_A_SELECT),
        ("ALTER TABLE sales ADD COLUMN x INT", _NOT_A_SELECT),
        ("ATTACH 'evil.db'", _NOT_A_SELECT),
        ("COPY sales TO 'leak.csv'", _NOT_A_SELECT),
        ("SET enable_external_access = true", _NOT_A_SELECT),
        ("SELECT 1; DROP TABLE sales", _ONE_STATEMENT),
        ("SELECT * FROM sales; SELECT * FROM sales", _ONE_STATEMENT),
        ("SELECT * FROM secrets", _NOT_ALLOWED),
        ("WITH s AS (SELECT * FROM secrets) SELECT * FROM s", _NOT_ALLOWED),
        ("SELECT * FROM other_db.main.sales", "Cross-database references"),
        ("SELECT * FROM read_csv('/etc/passwd')", "Reading external files"),
        ("SELECT read_text('/etc/passwd')", "'read_text' is not allowed"),
    ],
)
def test_duckdb_refusals_hold_on_both_builds(sqlglot_build, sql, reason):
    with pytest.raises(TabularUnsafeSQLError, match=reason):
        validate_duckdb(sql, allowed_tables=["sales"])


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("INSERT INTO customers (id) VALUES (1)", _NOT_A_SELECT),
        ("UPDATE customers SET name = 'x'", _NOT_A_SELECT),
        ("DELETE FROM customers", _NOT_A_SELECT),
        ("TRUNCATE customers", _NOT_A_SELECT),
        ("DROP TABLE customers", _NOT_A_SELECT),
        ("CREATE TABLE x AS SELECT 1", _NOT_A_SELECT),
        ("ALTER TABLE customers ADD COLUMN x INT", _NOT_A_SELECT),
        ("WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x", "forbidden operation"),
        ("SELECT * INTO backup FROM customers", "forbidden operation"),
        ("SELECT 1; DROP TABLE customers", _ONE_STATEMENT),
        ("SELECT * FROM secrets", _NOT_ALLOWED),
        ("SELECT * FROM other.secrets", "Cross-schema reference"),
        ("SELECT pg_read_file('x')", "'pg_read_file' is not allowed"),
        ("SELECT set_config('a', 'b', false)", "'set_config' is not allowed"),
        ("SELECT * FROM customers FOR UPDATE", "Row locks"),
    ],
)
def test_postgres_refusals_hold_on_both_builds(sqlglot_build, sql, reason):
    with pytest.raises(UnsafeSQLError, match=reason):
        validate_pg(sql, allowlist=["customers", "orders"])


def test_compiled_build_skips_only_the_argument_check(compiled_build, caplog):
    _sql_parse._warn_unchecked.cache_clear()
    with caplog.at_level(logging.WARNING, logger=_sql_parse.__name__):
        # Not refused: without the check, this lossy call passes as plain sqlglot reads it.
        for _ in range(2):
            validate_duckdb(
                "SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders",
                allowed_tables=["orders"],
            )
        with pytest.raises(TabularUnsafeSQLError, match="cannot be checked as written"):
            validate_duckdb("SELECT TO_CHAR(ordered_on, 'YYYY-MM') FROM orders")
    warnings = [r for r in caplog.records if "compiled build" in r.getMessage()]
    assert len(warnings) == 1
    assert "duckdb" in warnings[0].getMessage()
