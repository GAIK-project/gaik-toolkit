"""PgVectorStore.setup() from several sessions at once.

Every store shares the ``gaik_tsquery`` SQL function. Two sessions running
``CREATE OR REPLACE`` on it at the same moment fail with "tuple concurrently
updated", so workers that start together lost all but one ``setup()``.

The offline test records the SQL; the live one runs only when
``GAIK_TEST_PG_URL`` points at a pgvector database (see
test_pg_vector_store_sql.py).
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402


class _Recorder:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        return self

    def commit(self):
        self.sql.append("COMMIT")


def test_setup_takes_a_transaction_lock_before_its_first_statement():
    store = PgVectorStore("postgresql://unused", embedding_dim=3)
    recorder = _Recorder()
    store._get_conn = lambda: recorder

    store.setup()

    assert "pg_advisory_xact_lock" in recorder.sql[0]
    assert recorder.sql[-1] == "COMMIT"


PG_URL = os.environ.get("GAIK_TEST_PG_URL")


@pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")
def test_setups_started_together_all_succeed():
    tables = [f"gaik_test_setup_{uuid.uuid4().hex[:8]}" for _ in range(4)]
    errors: list[BaseException] = []

    def run(table, barrier):
        store = PgVectorStore(PG_URL, table_name=table, embedding_dim=3)
        try:
            store._get_conn()
            barrier.wait()
            store.setup()
        except BaseException as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)
        finally:
            store.close()

    try:
        for _ in range(3):
            barrier = threading.Barrier(len(tables))
            threads = [threading.Thread(target=run, args=(t, barrier)) for t in tables]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert errors == []
    finally:
        cleanup = PgVectorStore(PG_URL, table_name=tables[0], embedding_dim=3)
        conn = cleanup._get_conn()
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            for row in conn.execute(
                "SELECT oid::regprocedure::text AS sig FROM pg_proc WHERE proname LIKE %s",
                (f"%\\_{table}",),
            ).fetchall():
                conn.execute(f"DROP FUNCTION IF EXISTS {row['sig']}")
        conn.commit()
        cleanup.close()
