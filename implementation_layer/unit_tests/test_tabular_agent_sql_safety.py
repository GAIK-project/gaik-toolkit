"""Unit tests for tabular_agent read-only SQL validation.

These exercise the security boundary (``validate_read_only``) without needing
DuckDB or an LLM. The DuckDB-specific cases matter most: unlike PostgreSQL,
DuckDB can reach the filesystem and the network from inside a plain ``SELECT``
via table functions, so a statement-type check alone is not enough.
"""

import pytest

pytest.importorskip("sqlglot")

from gaik.software_components.tabular_agent.sql_safety import (  # noqa: E402
    UnsafeSQLError,
    validate_read_only,
)

TABLES = ["sales", "headcount"]


def test_accepts_plain_select():
    out = validate_read_only("SELECT region, units FROM sales", allowed_tables=TABLES)
    assert "sales" in out.lower()


def test_accepts_cte():
    out = validate_read_only(
        "WITH totals AS (SELECT region, sum(units) AS u FROM sales GROUP BY region) "
        "SELECT * FROM totals",
        allowed_tables=TABLES,
    )
    assert "totals" in out.lower()


def test_accepts_join_across_allowed_tables():
    out = validate_read_only(
        "SELECT s.region FROM sales s JOIN headcount h ON s.region = h.region",
        allowed_tables=TABLES,
    )
    assert "headcount" in out.lower()


def test_accepts_union():
    out = validate_read_only(
        "SELECT region FROM sales UNION SELECT region FROM headcount", allowed_tables=TABLES
    )
    assert "union" in out.lower()


def test_strips_trailing_semicolon():
    out = validate_read_only("SELECT 1;", allowed_tables=TABLES)
    assert ";" not in out


def test_allows_any_table_when_no_allowlist_given():
    out = validate_read_only("SELECT * FROM anything")
    assert "anything" in out.lower()


@pytest.mark.parametrize(
    "bad_sql",
    [
        # Writes and DDL.
        "INSERT INTO sales VALUES (1)",
        "UPDATE sales SET units = 0",
        "DELETE FROM sales",
        "DROP TABLE sales",
        "CREATE TABLE x AS SELECT 1",
        "ALTER TABLE sales ADD COLUMN x INT",
        # DuckDB escape hatches that are not SELECTs.
        "ATTACH 'evil.db'",
        "DETACH other",
        "INSTALL httpfs",
        "LOAD httpfs",
        "PRAGMA database_list",
        "COPY sales TO '/tmp/leak.csv'",
        "SET enable_external_access = true",
        # Multi-statement smuggling.
        "SELECT 1; DROP TABLE sales",
        "SELECT * FROM sales; ATTACH 'evil.db'",
        # Empty input.
        "",
        "   ",
    ],
)
def test_rejects_non_read_only_statements(bad_sql):
    with pytest.raises(UnsafeSQLError):
        validate_read_only(bad_sql, allowed_tables=TABLES)


@pytest.mark.parametrize(
    "bad_sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT * FROM read_parquet('s3://bucket/secrets.parquet')",
        "SELECT * FROM read_json_auto('/etc/hosts')",
        "SELECT * FROM glob('/**')",
        "SELECT read_text('/etc/passwd')",
        "SELECT read_blob('/etc/passwd')",
        "SELECT * FROM parquet_scan('/data/x.parquet')",
        "SELECT * FROM sniff_csv('/etc/passwd')",
    ],
)
def test_rejects_reading_external_files(bad_sql):
    """DuckDB table functions reach the filesystem from inside a SELECT."""
    with pytest.raises(UnsafeSQLError):
        validate_read_only(bad_sql, allowed_tables=TABLES)


def test_rejects_table_outside_allowlist():
    with pytest.raises(UnsafeSQLError, match="not in the allowed table list"):
        validate_read_only("SELECT * FROM secrets", allowed_tables=TABLES)


def test_rejects_cross_database_reference():
    with pytest.raises(UnsafeSQLError, match="Cross-database"):
        validate_read_only("SELECT * FROM other.main.sales", allowed_tables=TABLES)


def test_rejects_unparsable_sql():
    with pytest.raises(UnsafeSQLError):
        validate_read_only("SELECT FROM WHERE ((", allowed_tables=TABLES)


def test_unknown_function_is_rejected_by_name():
    """An allowlist, not a denylist -- future extension functions are covered."""
    with pytest.raises(UnsafeSQLError, match="totally_new_extension_fn"):
        validate_read_only("SELECT totally_new_extension_fn('x') FROM sales", allowed_tables=TABLES)


def test_standard_aggregates_still_work():
    """The unknown-function rule must not break ordinary analytical SQL."""
    out = validate_read_only(
        "SELECT region, count(*), sum(units), avg(units), min(units), max(units), "
        "round(avg(units), 2) FROM sales GROUP BY region HAVING count(*) > 1",
        allowed_tables=TABLES,
    )
    assert "group by" in out.lower()
