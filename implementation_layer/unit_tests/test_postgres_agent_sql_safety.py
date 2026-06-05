"""Unit tests for postgres_agent read-only SQL validation.

These exercise the security boundary (``validate_read_only``) without needing a
live database.
"""

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent.sql_safety import (  # noqa: E402
    UnsafeSQLError,
    validate_read_only,
)


def test_accepts_plain_select():
    out = validate_read_only("SELECT id, name FROM customers")
    assert "customers" in out.lower()


def test_accepts_cte():
    out = validate_read_only("WITH recent AS (SELECT * FROM orders) SELECT count(*) FROM recent")
    assert "recent" in out.lower()


def test_accepts_union():
    out = validate_read_only("SELECT id FROM customers UNION SELECT id FROM orders")
    assert "union" in out.lower()


def test_strips_trailing_semicolon():
    out = validate_read_only("SELECT 1;")
    assert ";" not in out


@pytest.mark.parametrize(
    "bad_sql",
    [
        "DROP TABLE customers",
        "INSERT INTO customers (id) VALUES (1)",
        "UPDATE customers SET name = 'x'",
        "DELETE FROM customers",
        "SELECT 1; DROP TABLE customers",
        "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
        "TRUNCATE customers",
        "SELECT * INTO backup FROM customers",
        "ALTER TABLE customers ADD COLUMN x INT",
    ],
)
def test_rejects_non_readonly(bad_sql):
    with pytest.raises(UnsafeSQLError):
        validate_read_only(bad_sql)


def test_rejects_empty():
    with pytest.raises(UnsafeSQLError):
        validate_read_only("   ")


def test_rejects_cross_schema_reference():
    with pytest.raises(UnsafeSQLError):
        validate_read_only("SELECT * FROM other_schema.secrets", schema_name="public")


def test_allows_same_schema_qualified():
    out = validate_read_only("SELECT * FROM public.customers", schema_name="public")
    assert "customers" in out.lower()


def test_rejects_table_outside_allowlist():
    with pytest.raises(UnsafeSQLError):
        validate_read_only("SELECT * FROM secrets", allowlist=["customers", "orders"])


def test_allows_table_in_allowlist():
    out = validate_read_only("SELECT * FROM customers", allowlist=["customers", "orders"])
    assert "customers" in out.lower()


def test_allowlist_ignores_cte_names():
    out = validate_read_only(
        "WITH summary AS (SELECT customer_id FROM orders) SELECT * FROM summary",
        allowlist=["customers", "orders"],
    )
    assert "summary" in out.lower()
