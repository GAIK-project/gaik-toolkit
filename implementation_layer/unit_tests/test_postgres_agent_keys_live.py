"""Primary and foreign keys as a SELECT-only role sees them, on a real PostgreSQL.

Skipped unless ``GAIK_TEST_PG_URL`` points at a database where the tests may
create a schema and a role (see ``test_postgres_agent_read_only_live.py``).
"""

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.postgres_agent import PostgresAgent  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a PostgreSQL database")


@pytest.fixture
def readonly_url():
    suffix = uuid.uuid4().hex[:8]
    schema, role = f"gaik_test_keys_{suffix}", f"gaik_test_ro_{suffix}"
    other = f"gaik_test_other_{suffix}"
    password = uuid.uuid4().hex
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE SCHEMA {other}")
        conn.execute(f"CREATE TABLE {schema}.customers (id int PRIMARY KEY)")
        # A table of the same name in another schema.
        conn.execute(f"CREATE TABLE {other}.customers (id int PRIMARY KEY)")
        conn.execute(f"CREATE TABLE {schema}.products (id int PRIMARY KEY)")
        conn.execute(
            f"CREATE TABLE {schema}.regions (country text, code text, PRIMARY KEY (country, code))"
        )
        # Two constraints with the same name on different tables, and a composite key.
        conn.execute(
            f"CREATE TABLE {schema}.orders (id int PRIMARY KEY, customer_id int, "
            f"CONSTRAINT ref FOREIGN KEY (customer_id) REFERENCES {schema}.customers (id), "
            f"other_customer_id int REFERENCES {other}.customers (id))"
        )
        conn.execute(
            f"CREATE TABLE {schema}.lines (product_id int, country text, code text, "
            f"CONSTRAINT ref FOREIGN KEY (product_id) REFERENCES {schema}.products (id), "
            f"FOREIGN KEY (code, country) REFERENCES {schema}.regions (code, country))"
        )
        conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'")
        conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
        conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}")
    params = conninfo_to_dict(PG_URL)
    params.update(user=role, password=password)
    yield make_conninfo(**params), schema
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.execute(f"DROP SCHEMA {other} CASCADE")
        conn.execute(f"DROP ROLE {role}")


def test_select_only_role_sees_primary_and_foreign_keys(readonly_url):
    url, schema = readonly_url
    with PostgresAgent(
        url,
        schema_name=schema,
        table_allowlist=["customers", "products", "regions", "orders", "lines"],
    ) as agent:
        tables = {t.name: {c.name: c for c in t.columns} for t in agent.get_schema().tables}
    assert tables["customers"]["id"].is_primary_key
    assert tables["regions"]["country"].is_primary_key
    assert tables["regions"]["code"].is_primary_key
    assert tables["orders"]["customer_id"].references == "customers.id"
    # A reference into another schema would read as this schema's customers table.
    assert tables["orders"]["other_customer_id"].references is None
    assert tables["lines"]["product_id"].references == "products.id"
    assert tables["lines"]["code"].references == "regions.code"
    assert tables["lines"]["country"].references == "regions.country"
