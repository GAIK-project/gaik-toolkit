"""Valid queries the SQL validators used to refuse or render wrongly (issue #146),
and calls whose arguments sqlglot drops while parsing (issues #146 and #219).

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

# Whether the installed sqlglot is its compiled build (sqlglot[c]).
COMPILED = bool(getattr(sqlglot.tokens, "SQLGLOTC_INSTALLED", False))

# --- sqlglot's compiled build (sqlglot[c]) ----------------------------------
#
# Its parser classes are native: an instance attribute cannot be set on them and a
# Python class cannot derive from them. Where the pure-Python build is installed, a
# parser that refuses the attribute the same way stands in for it; where sqlglotc
# is installed, the installed build is the compiled one. The stand-in does not show
# that the native tokens and nodes carry the positions the written-call check reads
# (Token.start and .end, FUNC_TOKENS, meta["start"]), so run this file on the real
# build too, with sqlglotc at the installed sqlglot's version:
#   uv run --with sqlglotc==<sqlglot version> pytest <this file>
# (passed with sqlglot and sqlglotc 30.33.0).


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


_LOSES = "loses one of its arguments"


def test_duckdb_refuses_the_time_zone_date_trunc_drops(sqlglot_build):
    # sqlglot reads DuckDB's date_trunc with two arguments and drops the third while
    # parsing, so the render matches the tree and only the parse shows the loss.
    with pytest.raises(TabularUnsafeSQLError, match=_LOSES):
        validate_duckdb(
            "SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders",
            allowed_tables=["orders"],
        )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT array_agg(name, ', ') FROM orders",
        "SELECT epoch_ms(ms, 3) FROM orders",
        "SELECT encode(note, 'latin1') FROM orders",
    ],
)
def test_duckdb_refuses_other_dropped_arguments(sqlglot_build, sql):
    with pytest.raises(TabularUnsafeSQLError, match=_LOSES):
        validate_duckdb(sql, allowed_tables=["orders"])


def test_postgres_refuses_a_dropped_argument(sqlglot_build):
    with pytest.raises(UnsafeSQLError, match=_LOSES):
        validate_pg("SELECT array_agg(name, ', ') FROM orders")


# Functions sqlglot reads with a parser of its own rather than from a list of
# written arguments (issue #219).
_SHARED_PARSER_CALLS = [
    ("SELECT arg_max(name, amount, 2, 9) FROM orders", "ARG_MAX(name, amount, 2)"),
    ("SELECT argmax(name, amount, 2, 9) FROM orders", "ARG_MAX(name, amount, 2)"),
    ("SELECT arg_min(name, amount, 2, 9) FROM orders", "ARG_MIN(name, amount, 2)"),
    ("SELECT max_by(name, amount, 2, 9) FROM orders", "ARG_MAX(name, amount, 2)"),
    ("SELECT min_by(name, amount, 2, 9) FROM orders", "ARG_MIN(name, amount, 2)"),
    ("SELECT ceil(amount, 1, 2) FROM orders", None),
    ("SELECT floor(amount, 1, 2) FROM orders", None),
    ("SELECT initcap(name, ' ', '-') FROM orders", None),
    ("SELECT region, sum(amount) FILTER (WHERE ceil(amount, 1, 2) > 0) FROM orders", None),
]


@pytest.mark.parametrize(
    ("sql", "runs_as"),
    _SHARED_PARSER_CALLS
    + [
        ("SELECT quantile(amount, 0.5, 9) FROM orders", "QUANTILE(amount, 0.5)"),
        ("SELECT quantile_cont(amount, 0.5, 9) FROM orders", "QUANTILE_CONT(amount, 0.5)"),
        ("SELECT quantile_disc(amount, 0.5, 9) FROM orders", "QUANTILE_DISC(amount, 0.5)"),
        ("SELECT map(keys, vals, extra) FROM orders", "MAP(keys, vals)"),
        ("SELECT upper(map(keys, vals, extra)[1]) FROM orders", "MAP(keys, vals)"),
    ],
)
def test_duckdb_refuses_an_argument_a_function_parser_drops(sqlglot_build, sql, runs_as):
    with pytest.raises(TabularUnsafeSQLError, match=_LOSES) as refused:
        validate_duckdb(sql, allowed_tables=["orders"])
    if runs_as:
        assert f"would run as {runs_as}." in str(refused.value)


@pytest.mark.parametrize(("sql", "runs_as"), _SHARED_PARSER_CALLS)
def test_postgres_refuses_an_argument_a_function_parser_drops(sqlglot_build, sql, runs_as):
    with pytest.raises(UnsafeSQLError, match=_LOSES) as refused:
        validate_pg(sql)
    if runs_as:
        assert f"would run as {runs_as}." in str(refused.value)


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
        # Function parsers, with every argument they read.
        "SELECT arg_max(name, amount), arg_max(name, amount, 2), max_by(name, amount) FROM orders",
        "SELECT quantile(amount, 0.5), quantile_cont(amount, [0.25, 0.5]) FROM orders",
        "SELECT quantile_disc(DISTINCT amount, 0.5), approx_quantile(amount, 0.5) FROM orders",
        "SELECT ceil(amount), floor(amount), max(amount), min(amount), max(amount, 2) FROM orders",
        "SELECT map([1], [2]), map(), initcap(name) FROM orders",
        "SELECT string_agg(name, ',' ORDER BY ts), listagg(name, ','), group_concat(name, ',') "
        "FROM orders",
        "SELECT cast(amount AS INT), try_cast(name AS INT), trim(both 'x' from name) FROM orders",
        "SELECT substring(name, 1, 2), position('a' in name), extract(year FROM ts) FROM orders",
        # Arguments that leave no trace of their own in the tree.
        "SELECT coalesce(amount, NULL), if(amount > 1, NULL, TRUE), count(*) FROM orders",
        "SELECT extract(year FROM CURRENT_DATE), coalesce(NULL, CURRENT_DATE) FROM orders",
        # Parentheses that are not calls, and calls with nested brackets.
        "SELECT list_transform(tags, x -> x || ','), {'a': 1, 'b': [1, 2]} FROM orders",
        "SELECT sum(amount) OVER (PARTITION BY region, name ORDER BY ts) FROM orders AS o(a, b)",
        "SELECT CAST(amount AS DECIMAL(10, 2)), amount::VARCHAR(20) FROM orders",
        "SELECT name FROM orders WHERE EXISTS (SELECT name, ts FROM orders) AND id IN (1, 2)",
    ],
)
def test_duckdb_keeps_arguments_sqlglot_rewrites(sqlglot_build, sql):
    validate_duckdb(sql, allowed_tables=["orders"])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT to_char(ts, 'YYYY-MM'), date_trunc('month', ts) FROM orders",
        "SELECT json_extract_path(doc, 'a', 'b') FROM orders",
        "SELECT date_bin('15 minutes', ts, TIMESTAMP '2001-01-01') FROM orders",
        "SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders",
        "SELECT ceil(amount), floor(amount), initcap(name), date_part('year', ts) FROM orders",
        "SELECT position('a' in name), overlay(name placing 'b' from 1 for 2) FROM orders",
        "SELECT substring(name from 1 for 2), trim(both 'x' from name) FROM orders",
        "SELECT string_agg(name, ',' ORDER BY ts), json_agg(name), json_object('a', 1) FROM orders",
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY amount) FROM orders",
        "SELECT coalesce(amount, NULL), amount::numeric(10, 2), round(amount, 2) FROM orders",
        "SELECT id FROM orders WHERE id = ANY (ARRAY[1, 2]) AND EXISTS (SELECT id, ts FROM orders)",
    ],
)
def test_postgres_keeps_arguments_sqlglot_rewrites(sqlglot_build, sql):
    validate_pg(sql)


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


def test_compiled_build_checks_arguments_from_the_written_calls(compiled_build, caplog):
    with caplog.at_level(logging.WARNING, logger=_sql_parse.__name__):
        with pytest.raises(TabularUnsafeSQLError, match=_LOSES) as refused:
            validate_duckdb(
                "SELECT date_trunc('month', ts, 'Europe/Helsinki') FROM orders",
                allowed_tables=["orders"],
            )
        assert "would run as DATE_TRUNC('MONTH', ts)." in str(refused.value)
        with pytest.raises(UnsafeSQLError, match=_LOSES):
            validate_pg("SELECT array_agg(name, ', ') FROM orders")
        with pytest.raises(TabularUnsafeSQLError, match="cannot be checked as written"):
            validate_duckdb("SELECT TO_CHAR(ordered_on, 'YYYY-MM') FROM orders")
    assert not caplog.records
