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


# ── CTE names are allowed only where the CTE is in scope ─────────────

ALLOWED = ["customers", "orders"]


@pytest.mark.parametrize(
    "bad_sql",
    [
        # Inside its own body a non-recursive CTE name is the real table.
        "WITH secrets AS (SELECT * FROM secrets) SELECT * FROM secrets",
        # An earlier CTE cannot see a later one.
        "WITH a AS (SELECT * FROM secrets), secrets AS (SELECT 1) SELECT * FROM a",
        # A CTE of a subquery is not visible in the outer query.
        "SELECT * FROM secrets WHERE EXISTS (WITH secrets AS (SELECT 1) SELECT 1 FROM secrets)",
        # Nor in the other branch of a set operation.
        "(WITH secrets AS (SELECT 1) SELECT * FROM secrets) UNION SELECT * FROM secrets",
        # A quoted CTE name is another name than the unquoted table.
        'WITH "Secrets" AS (SELECT 1) SELECT * FROM secrets',
    ],
)
def test_cte_name_out_of_scope_is_checked_as_a_table(bad_sql):
    with pytest.raises(UnsafeSQLError, match="not in the allowed table list"):
        validate_read_only(bad_sql, allowlist=ALLOWED)


@pytest.mark.parametrize(
    "good_sql",
    [
        "WITH a AS (SELECT * FROM orders), b AS (SELECT * FROM a) "
        "SELECT * FROM b JOIN a USING (id)",
        "WITH a AS (SELECT id FROM orders) SELECT * FROM a UNION SELECT * FROM a",
        "WITH RECURSIVE r AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM r WHERE n < 3) "
        "SELECT * FROM r",
        "SELECT * FROM orders WHERE EXISTS (WITH t AS (SELECT 1) SELECT * FROM t)",
    ],
)
def test_cte_name_in_scope_is_allowed(good_sql):
    validate_read_only(good_sql, allowlist=ALLOWED)


# ── Functions and row locks ──────────────────────────────────────────


@pytest.mark.parametrize(
    "call",
    [
        "set_config('default_transaction_read_only', 'off', false)",
        "current_setting('server_version')",
        "query_to_xml('select 1', true, true, '')",
        "dblink('dbname=other', 'select 1')",
        "pg_read_file('postgresql.conf')",
        "lo_import('/tmp/x')",
        "nextval('orders_id_seq')",
        "setval('orders_id_seq', 1)",
        "pg_sleep(5)",
        "pg_terminate_backend(1)",
        "pg_advisory_lock(1)",
        "ts_stat('select 1')",
        "some_extension_function(1)",
        "pg_catalog.set_config('a', 'b', false)",
        '"pg_sleep"(5)',
    ],
)
def test_rejects_function_outside_the_allowlist(call):
    for sql in (
        f"SELECT {call}",
        f"SELECT * FROM orders WHERE id = (SELECT {call})",
        f"SELECT 1 FROM orders ORDER BY {call}",
    ):
        with pytest.raises(UnsafeSQLError, match="is not allowed"):
            validate_read_only(sql)


def test_rejects_function_in_from():
    with pytest.raises(UnsafeSQLError, match="is not allowed"):
        validate_read_only("SELECT * FROM pg_ls_dir('.')")


@pytest.mark.parametrize(
    "sql",
    ["SELECT public.lower(name) FROM customers", "SELECT * FROM public.generate_series(1, 3)"],
)
def test_rejects_schema_qualified_function(sql):
    with pytest.raises(UnsafeSQLError, match="Schema-qualified function"):
        validate_read_only(sql)


@pytest.mark.parametrize("lock", ["UPDATE", "NO KEY UPDATE", "SHARE", "KEY SHARE"])
def test_rejects_row_locks(lock):
    with pytest.raises(UnsafeSQLError, match="Row locks"):
        validate_read_only(f"SELECT * FROM customers FOR {lock}")


def test_ordinary_analytical_functions_still_work():
    """The function allowlist must not break everyday reporting SQL."""
    validate_read_only(
        "SELECT c.city, date_trunc('month', o.ordered_on) AS month, count(*), "
        "round(avg(o.amount), 2), string_agg(DISTINCT o.product, ', '), "
        "coalesce(max(o.amount), 0), extract(year FROM now()), age(min(o.ordered_on)), "
        "to_char(sum(o.amount), 'FM999990.00'), split_part(c.name, ' ', 1), "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY o.amount), "
        "row_number() OVER (PARTITION BY c.city ORDER BY count(*) DESC), "
        "json_build_object('city', c.city), upper(left(c.city, 1)), cast(count(*) AS text) "
        "FROM customers c JOIN orders o ON o.customer_id = c.id "
        "CROSS JOIN generate_series(1, 2) AS g "
        "WHERE lower(c.name) LIKE 'a%' AND o.ordered_on >= current_date - interval '1 year' "
        "GROUP BY c.city, c.name, 2 HAVING count(*) > 0",
        allowlist=ALLOWED,
    )


# ── Identifiers resolve as PostgreSQL resolves them ──────────────────


def test_quoted_mixed_case_table_is_not_the_lower_case_one():
    with pytest.raises(UnsafeSQLError, match="not in the allowed table list"):
        validate_read_only('SELECT * FROM "Users"', allowlist=["users"])


def test_allowlist_entry_names_the_table_exactly():
    validate_read_only('SELECT * FROM "Users"', allowlist=["Users"])
    validate_read_only("SELECT * FROM Users", allowlist=["users"])
    with pytest.raises(UnsafeSQLError, match="not in the allowed table list"):
        validate_read_only("SELECT * FROM users", allowlist=["Users"])


def test_unqualified_table_is_pinned_to_the_schema():
    """An unqualified name must not reach another schema on the search path."""
    out = validate_read_only("SELECT * FROM pg_user", schema_name="sales")
    assert '"sales".pg_user' in out
    out = validate_read_only(
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent r JOIN customers c ON true",
        schema_name="sales",
    )
    assert '"sales".orders' in out
    assert '"sales".customers' in out
    assert "FROM recent" in out


def test_quoted_schema_must_match_exactly():
    with pytest.raises(UnsafeSQLError, match="Cross-schema"):
        validate_read_only('SELECT * FROM "Public".customers', schema_name="public")
    validate_read_only("SELECT * FROM PUBLIC.customers", schema_name="public")
