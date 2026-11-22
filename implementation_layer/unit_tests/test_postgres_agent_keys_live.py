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


@pytest.fixture
def partitioned_url():
    suffix = uuid.uuid4().hex[:8]
    schema, role = f"gaik_test_parts_{suffix}", f"gaik_test_ro_{suffix}"
    password = uuid.uuid4().hex
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(
            f"CREATE TABLE {schema}.customers (id int, region text, PRIMARY KEY (id, region)) "
            "PARTITION BY LIST (region)"
        )
        # A partition attached later, whose columns have other numbers than the
        # table's: PostgreSQL's copy of a key into it has another confkey.
        conn.execute(
            f"CREATE TABLE {schema}.customers_eu (dropped int, region text NOT NULL, "
            "id int NOT NULL)"
        )
        conn.execute(f"ALTER TABLE {schema}.customers_eu DROP COLUMN dropped")
        conn.execute(
            f"ALTER TABLE {schema}.customers ATTACH PARTITION {schema}.customers_eu "
            "FOR VALUES IN ('eu')"
        )
        # A partition that is partitioned again.
        conn.execute(
            f"CREATE TABLE {schema}.customers_us PARTITION OF {schema}.customers "
            "FOR VALUES IN ('us') PARTITION BY RANGE (id)"
        )
        conn.execute(
            f"CREATE TABLE {schema}.customers_us_low PARTITION OF {schema}.customers_us "
            "FOR VALUES FROM (0) TO (1000)"
        )
        # A key declared against one partition.
        conn.execute(
            f"CREATE TABLE {schema}.eu_notes (customer_id int, region text, "
            f"FOREIGN KEY (customer_id, region) REFERENCES {schema}.customers_eu (id, region))"
        )
        # A plain table and a partitioned one, both referencing the partitioned table.
        conn.execute(
            f"CREATE TABLE {schema}.invoices (id int, customer_id int, region text, "
            f"FOREIGN KEY (customer_id, region) REFERENCES {schema}.customers (id, region))"
        )
        conn.execute(
            f"CREATE TABLE {schema}.orders (id int, customer_id int, region text, "
            f"FOREIGN KEY (customer_id, region) REFERENCES {schema}.customers (id, region)) "
            "PARTITION BY RANGE (id)"
        )
        conn.execute(
            f"CREATE TABLE {schema}.orders_early PARTITION OF {schema}.orders "
            "FOR VALUES FROM (0) TO (1000)"
        )
        conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'")
        conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
        conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}")
    params = conninfo_to_dict(PG_URL)
    params.update(user=role, password=password)
    yield make_conninfo(**params), schema
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.execute(f"DROP ROLE {role}")


_PARTITIONED_TABLES = [
    "customers",
    "customers_eu",
    "customers_us",
    "customers_us_low",
    "eu_notes",
    "invoices",
    "orders",
    "orders_early",
]


def _references(url, schema, allowlist):
    with PostgresAgent(url, schema_name=schema, table_allowlist=allowlist) as agent:
        return {
            t.name: {c.name: c.references for c in t.columns} for t in agent.get_schema().tables
        }


def test_a_key_into_a_partitioned_table_names_the_table_not_a_partition(partitioned_url):
    url, schema = partitioned_url
    tables = _references(url, schema, _PARTITIONED_TABLES)
    for table in ("invoices", "orders"):
        assert tables[table]["customer_id"] == "customers.id"
        assert tables[table]["region"] == "customers.region"
    # The key PostgreSQL copies onto a partition of the referencing table is kept.
    assert tables["orders_early"]["customer_id"] == "customers.id"
    # A key declared against one partition names that partition.
    assert tables["eu_notes"]["customer_id"] == "customers_eu.id"
    assert tables["eu_notes"]["region"] == "customers_eu.region"
    # PostgreSQL's copies into customers_eu (attached with other column numbers),
    # customers_us and its own partition customers_us_low name no column.
    named = {ref.split(".")[0] for columns in tables.values() for ref in columns.values() if ref}
    assert named == {"customers", "customers_eu"}
    assert all(
        ref is None or ref.startswith("customers_eu.") for ref in tables["eu_notes"].values()
    )


def test_a_key_into_a_partitioned_table_the_agent_may_not_read_names_no_partition(
    partitioned_url,
):
    url, schema = partitioned_url
    # The keys point at customers, which is not listed; one of its partitions holds
    # only some of the rows a key may name, so it is not given in its place.
    tables = _references(url, schema, [t for t in _PARTITIONED_TABLES if t != "customers"])
    assert tables["invoices"] == {"id": None, "customer_id": None, "region": None}
    assert tables["eu_notes"]["customer_id"] == "customers_eu.id"
