"""Seed a small demo database for the postgres_agent example.

Creates an isolated ``gaik_postgres_agent_demo`` schema with two tables
(``customers`` and ``orders``) and a handful of rows. Safe to re-run.

For safety this refuses to touch a database that is not on localhost unless
``--force`` is given -- so you cannot accidentally seed a production database.

Run standalone:
    python seed_demo_db.py
    python seed_demo_db.py --force   # allow a non-localhost DATABASE_URL
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

try:
    import psycopg
except ImportError:
    print("This example needs psycopg. Install it with: pip install 'gaik[postgres-agent]'")
    raise SystemExit(1) from None

DEMO_SCHEMA = "gaik_postgres_agent_demo"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "", None}


def seed_demo_db(database_url: str, *, force: bool = False) -> None:
    """Create and populate the demo schema.

    Args:
        database_url: PostgreSQL connection URI.
        force: Allow seeding a database that is not on localhost.

    Raises:
        RuntimeError: If the database is not local and ``force`` is False.
    """
    host = urlparse(database_url).hostname
    if host not in _LOCAL_HOSTS and not force:
        raise RuntimeError(
            f"Refusing to seed a non-localhost database (host={host!r}). "
            f"Pass force=True (or --force on the command line) to override."
        )

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {DEMO_SCHEMA}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEMO_SCHEMA}.customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT,
                joined_on DATE
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEMO_SCHEMA}.orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES {DEMO_SCHEMA}.customers (id),
                product TEXT NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                ordered_on DATE
            )
            """
        )
        conn.execute(f"TRUNCATE {DEMO_SCHEMA}.orders, {DEMO_SCHEMA}.customers")
        conn.execute(
            f"""
            INSERT INTO {DEMO_SCHEMA}.customers (id, name, city, joined_on) VALUES
                (1, 'Aino Virtanen', 'Helsinki', '2024-01-15'),
                (2, 'Bo Lindholm', 'Turku', '2024-03-02'),
                (3, 'Carlos Mendez', 'Tampere', '2025-06-20'),
                (4, 'Diana Korhonen', 'Helsinki', '2025-09-11')
            """
        )
        conn.execute(
            f"""
            INSERT INTO {DEMO_SCHEMA}.orders
                (id, customer_id, product, amount, ordered_on) VALUES
                (1, 1, 'Mechanical keyboard', 79.90, '2025-02-01'),
                (2, 1, 'Monitor 27 inch', 249.00, '2025-02-15'),
                (3, 2, 'Wireless mouse', 25.50, '2025-04-10'),
                (4, 3, 'Laptop', 1299.00, '2025-07-01'),
                (5, 3, 'Headphones', 149.00, '2025-07-03'),
                (6, 4, 'Webcam HD', 89.00, '2025-10-05')
            """
        )
    print(f"Seeded schema '{DEMO_SCHEMA}': 4 customers, 6 orders.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the postgres_agent demo database.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow seeding a database that is not on localhost.",
    )
    args = parser.parse_args()

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    seed_demo_db(url, force=args.force)
