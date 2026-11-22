"""Writers that share a RAG store wait for each other.

Two overlapping ``add(..., replace=True)`` calls for one document leave one of the two
versions, not nothing. Threads sharing one PgVectorStore share its connection and its
transaction, so each call runs its transaction to the end before another starts.

The PgVectorStore test against a database is skipped unless ``GAIK_TEST_PG_URL``
points at a pgvector database (see ``test_pg_vector_store_sql.py``).
"""

from __future__ import annotations

import os
import pickle
import threading
import uuid

import pytest

pytest.importorskip("langchain_core")

from langchain_core.documents import Document  # noqa: E402

A1 = [1.0, 0.0, 0.0]
B1 = [0.0, 1.0, 0.0]
VERSIONS = (["alpha", "beta"], ["gamma", "delta"])


def _chunks(document: str, texts: list[str]) -> list[Document]:
    return [
        Document(page_content=text, metadata={"document_name": document, "page": i})
        for i, text in enumerate(texts)
    ]


def _run(*targets, names: tuple[str, ...] = ()) -> None:
    """Run each target in its own thread and raise what any of them raised."""
    errors: list[BaseException] = []

    def guarded(target):
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [
        threading.Thread(
            target=guarded, args=(target,), name=names[i] if names else None, daemon=True
        )
        for i, target in enumerate(targets)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(thread.is_alive() for thread in threads), "a writer did not finish"
    assert not errors, errors


def _replace(store, texts):
    return lambda: store.add(_chunks("report", texts), [A1, B1], replace=True)


def _texts(store) -> list[str]:
    return sorted(doc.page_content for doc, _ in store.search(A1, top_k=50))


@pytest.fixture(params=[False, True], ids=["memory", "chroma"])
def store(request, tmp_path):
    if request.param:
        pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore

    return VectorStore(persist=request.param, persist_path=str(tmp_path / "chroma"))


def _pause_first_prune(monkeypatch, *stores, until: threading.Event, timeout: float):
    """Make the first prune of a replacement wait until another prune starts.

    A replacement stores its chunks, then reads the document's chunks to delete the
    ones it did not store. The first such read waits for ``until``, which the second
    read sets (or for ``timeout``).
    """
    guard = threading.Lock()
    calls = []

    def pausing(original):
        def paused(document_id, owner):
            with guard:
                calls.append(document_id)
                first = len(calls) == 1
            if first:
                until.wait(timeout)
            else:
                until.set()
            return original(document_id, owner)

        return paused

    for one in stores:
        monkeypatch.setattr(one, "_ids_in_scope", pausing(one._ids_in_scope))


def test_two_overlapping_replacements_of_one_document_leave_one_version(store, monkeypatch):
    # Without a lock, each call deletes the chunks the other stored, and the document
    # has none left.
    _pause_first_prune(monkeypatch, store, until=threading.Event(), timeout=1.0)

    _run(*(_replace(store, texts) for texts in VERSIONS))

    assert _texts(store) in [sorted(texts) for texts in VERSIONS]


def test_two_chroma_stores_on_one_folder_share_a_documents_lock(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore

    # One store per request on the same folder and collection, say.
    first, second = (
        VectorStore(persist=True, persist_path=str(tmp_path / "chroma")) for _ in range(2)
    )
    _pause_first_prune(monkeypatch, first, second, until=threading.Event(), timeout=1.0)

    _run(_replace(first, VERSIONS[0]), _replace(second, VERSIONS[1]))

    assert _texts(first) in [sorted(texts) for texts in VERSIONS]


def test_chroma_writes_of_other_documents_do_not_wait(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore
    from gaik.software_components.RAG.vector_store import vector_store as module

    store = VectorStore(persist=True, persist_path=str(tmp_path / "chroma"))
    other_done = threading.Event()
    _pause_first_prune(monkeypatch, store, until=other_done, timeout=5.0)
    waited = []

    def replace_report():
        _replace(store, VERSIONS[0])()
        waited.append(other_done.is_set())

    def add_minutes():
        for _ in range(500):  # until the replacement holds its lock
            if module._CHROMA_WRITES._entries:
                break
            threading.Event().wait(0.01)
        VectorStore(persist=True, persist_path=str(tmp_path / "chroma")).add(
            _chunks("minutes", ["other"]), [A1]
        )
        other_done.set()

    _run(replace_report, add_minutes)

    assert waited == [True], "the write of another document waited for the replacement"
    assert module._CHROMA_WRITES._entries == {}, "a lock outlived its writers"


def test_an_in_memory_store_can_still_be_pickled():
    from gaik.software_components.RAG.vector_store import VectorStore

    store = VectorStore()
    store.add(_chunks("report", ["alpha"]), [A1])
    copy = pickle.loads(pickle.dumps(store))
    copy.add(_chunks("report", ["beta"]), [B1], replace=True)

    assert [doc.page_content for doc, _ in copy.search(B1, top_k=5)] == ["beta"]
    assert store.count() == 1


# ── PgVectorStore without a database ─────────────────────────────────


class _SharedPg:
    """A fake connection that records each thread's statements; one INSERT waits."""

    closed = False

    def __init__(self) -> None:
        self.log: list[tuple[str, str]] = []
        self.inserting = threading.Event()
        self.release = threading.Event()
        self._row = None

    def _record(self, statement: str) -> None:
        self.log.append((threading.current_thread().name, statement))

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        self._record(text.split()[0])
        if "pg_attribute" in text:
            self._row = {"?column?": 1}
        elif "COUNT(*)" in text:
            self._row = {"cnt": 0}
        else:
            self._row = {"id": len(self.log)}
        if text.startswith("INSERT") and threading.current_thread().name == "first":
            self.inserting.set()
            self.release.wait(5)
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetchone(self):
        return self._row

    def commit(self):
        self._record("COMMIT")

    def rollback(self):
        self._record("ROLLBACK")

    def close(self):
        self._record("CLOSE")
        self.closed = True


def _pg_store():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    store = PgVectorStore("postgresql://unused", embedding_dim=3)
    store._conn = conn = _SharedPg()
    return store, conn


@pytest.mark.parametrize("second_call", ["replace", "count", "close"])
def test_pg_threads_sharing_a_store_do_not_run_inside_each_others_transaction(second_call):
    store, conn = _pg_store()
    calls = {
        "replace": _replace(store, ["beta", "gamma"]),
        "count": store.count,
        "close": store.close,
    }

    def second():
        conn.inserting.wait(5)
        # The first thread is inside its transaction; it goes on in 0.3 s.
        threading.Timer(0.3, conn.release.set).start()
        calls[second_call]()

    _run(_replace(store, ["alpha", "delta"]), second, names=("first", "second"))

    names = [name for name, _ in conn.log]
    assert "second" in names, "the second call ran no statement, so the test checks nothing"
    # Without the store's lock, the second thread's statements (its commit would store
    # the first's half-done replacement) land inside the first's transaction.
    assert "second" not in names[: conn.log.index(("first", "COMMIT")) + 1], conn.log


def test_pg_a_store_not_yet_connected_can_still_be_pickled():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    store = pickle.loads(pickle.dumps(PgVectorStore("postgresql://unused", embedding_dim=3)))
    store._conn = _SharedPg()
    assert store.count() == 0


# ── PgVectorStore against a database ─────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")


@pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")
def test_pg_threads_replacing_one_document_through_one_store_leave_one_version():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    table = f"gaik_test_threads_{uuid.uuid4().hex[:8]}"
    store = PgVectorStore(PG_URL, table_name=table, embedding_dim=3)
    try:
        store.setup()
        for _ in range(5):
            _run(*(_replace(store, texts) for texts in VERSIONS))
            assert _texts(store) in [sorted(texts) for texts in VERSIONS]
    finally:
        conn = store._get_conn()
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        for row in conn.execute(
            "SELECT oid::regprocedure::text AS sig FROM pg_proc WHERE proname LIKE %s",
            (f"%\\_{table}",),
        ).fetchall():
            conn.execute(f"DROP FUNCTION IF EXISTS {row['sig']}")
        conn.commit()
        store.close()
