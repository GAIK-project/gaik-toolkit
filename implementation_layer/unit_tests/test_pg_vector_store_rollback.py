"""PgVectorStore rolls back after a failure, so the connection stays usable.

No database: a fake connection behaves like psycopg without autocommit. A
failed statement aborts the transaction until a rollback, and rows inserted
before a commit stay pending.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class _FakePg:
    closed = False

    def __init__(self) -> None:
        self.pending: list[str] = []
        self.committed: list[str] = []
        self.aborted = False
        self.fail_next = False
        self._row = None

    @property
    def info(self):
        name = "INERROR" if self.aborted else ("INTRANS" if self.pending else "IDLE")
        return SimpleNamespace(transaction_status=SimpleNamespace(name=name))

    def execute(self, sql, params=()):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if self.fail_next:
            self.fail_next = False
            self.aborted = True
            raise RuntimeError("LIMIT must not be negative")
        if "INSERT" in sql:
            self.pending.append(params[1])
            self._row = {"id": len(self.committed) + len(self.pending)}
        elif "COUNT(*)" in sql:
            self._row = {"cnt": len(self.committed)}
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []

    def commit(self):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        self.committed += self.pending
        self.pending = []

    def rollback(self):
        self.pending = []
        self.aborted = False


def _store():
    store = PgVectorStore("postgresql://unused", embedding_dim=3)
    store._conn = _FakePg()
    return store, store._conn


def test_a_failed_search_does_not_break_the_next_call():
    store, conn = _store()
    conn.fail_next = True

    with pytest.raises(RuntimeError):
        store.search_semantic([0.1, 0.2, 0.3], top_k=-1)

    assert store.count() == 0
    assert store._conn is conn


def test_a_connection_left_aborted_is_rolled_back_before_reuse():
    store, conn = _store()
    conn.aborted = True

    assert store.count() == 0


def test_a_failed_add_leaves_nothing_pending_for_the_retry():
    store, conn = _store()
    docs = [
        Document(page_content="a"),
        Document(page_content="b"),
        Document(page_content="c", metadata={"bad": object()}),
    ]

    with pytest.raises(TypeError):
        store.add(docs, [[1.0, 0.0, 0.0]] * 3)

    store.add(docs[:2], [[1.0, 0.0, 0.0]] * 2)
    assert conn.committed == ["a", "b"]
