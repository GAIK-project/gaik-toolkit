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


class _WatchedLock:
    """A re-entrant lock that sets ``contended`` when a thread has to wait for it."""

    def __init__(self, contended: threading.Event) -> None:
        self._lock = threading.RLock()
        self._contended = contended

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if self._lock.acquire(blocking=False):
            return True
        self._contended.set()
        return self._lock.acquire(blocking, timeout) if blocking else False

    def release(self) -> None:
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def _watch_store_locks(monkeypatch, stores, contended: threading.Event) -> None:
    """Set ``contended`` when a writer of these stores waits for a lock."""
    from gaik.software_components.RAG.vector_store import vector_store as module

    for one in stores:
        if not one.persist:
            monkeypatch.setattr(one, "_lock", _WatchedLock(contended), raising=False)
    keyed_locks = getattr(module, "_KeyedLocks", None)
    if keyed_locks is not None:
        watched = keyed_locks()
        watched._new_lock = lambda: _WatchedLock(contended)
        monkeypatch.setattr(module, "_CHROMA_WRITES", watched)


def _overlap(monkeypatch, *stores, until: threading.Event | None = None) -> threading.Event:
    """Make the first prune of a replacement wait, so that two writers overlap.

    A replacement stores its chunks, then reads the document's chunks to delete the
    ones it did not store. The first such read waits for ``until``. By default that
    is set as soon as another writer has to wait for a store lock, or, where there is
    no lock to wait for, when that writer reaches its own read. Returns an event set
    once the first read waits.
    """
    go = until or threading.Event()
    waiting = threading.Event()
    guard = threading.Lock()
    calls = []

    def pausing(original):
        def paused(document_id, owner):
            with guard:
                calls.append(document_id)
                first = len(calls) == 1
            if first:
                waiting.set()
                go.wait(5)  # only a broken test waits this long
            elif until is None:
                go.set()
            return original(document_id, owner)

        return paused

    for one in stores:
        monkeypatch.setattr(one, "_ids_in_scope", pausing(one._ids_in_scope))
    if until is None:
        _watch_store_locks(monkeypatch, stores, go)
    return waiting


def test_two_overlapping_replacements_of_one_document_leave_one_version(store, monkeypatch):
    # Without a lock, each call deletes the chunks the other stored, and the document
    # has none left.
    _overlap(monkeypatch, store)

    _run(*(_replace(store, texts) for texts in VERSIONS))

    assert _texts(store) in [sorted(texts) for texts in VERSIONS]


def test_two_chroma_stores_on_one_folder_share_a_documents_lock(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore

    # One store per request on the same folder and collection, say.
    first, second = (
        VectorStore(persist=True, persist_path=str(tmp_path / "chroma")) for _ in range(2)
    )
    _overlap(monkeypatch, first, second)

    _run(_replace(first, VERSIONS[0]), _replace(second, VERSIONS[1]))

    assert _texts(first) in [sorted(texts) for texts in VERSIONS]


def test_chroma_writes_of_other_documents_do_not_wait(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore
    from gaik.software_components.RAG.vector_store import vector_store as module

    store = VectorStore(persist=True, persist_path=str(tmp_path / "chroma"))
    other_done = threading.Event()
    replacing = _overlap(monkeypatch, store, until=other_done)
    waited = []

    def replace_report():
        _replace(store, VERSIONS[0])()
        waited.append(other_done.is_set())

    def add_minutes():
        assert replacing.wait(5), "the replacement never reached its prune"
        VectorStore(persist=True, persist_path=str(tmp_path / "chroma")).add(
            _chunks("minutes", ["other"]), [A1]
        )
        other_done.set()

    _run(replace_report, add_minutes)

    assert waited == [True], "the write of another document waited for the replacement"
    assert module._CHROMA_WRITES._entries == {}, "a lock outlived its writers"


def test_a_chroma_store_keeps_the_folder_it_opened_after_a_chdir(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore

    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path)
    relative = VectorStore(persist=True, persist_path="chroma")
    monkeypatch.chdir(tmp_path / "elsewhere")
    absolute = VectorStore(persist=True, persist_path=str(tmp_path / "chroma"))

    assert relative._chroma_scope == absolute._chroma_scope


def test_a_folder_key_ignores_case_on_macos(monkeypatch):
    from gaik.software_components.RAG.vector_store import vector_store as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    assert module._folder_key("/Data/Chroma") == module._folder_key("/data/chroma")


def test_a_shallow_copy_shares_the_lock_and_a_deep_copy_has_its_own():
    import copy

    from gaik.software_components.RAG.vector_store import VectorStore

    store = VectorStore()
    store.add(_chunks("report", ["alpha"]), [A1])

    assert copy.copy(store)._lock is store._lock  # it shares the lists the lock guards
    deep = copy.deepcopy(store)
    assert deep._lock is not store._lock
    deep.add(_chunks("report", ["beta"]), [B1], replace=True)
    assert _texts(store) == ["alpha"] and _texts(deep) == ["beta"]


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

    def fetchall(self):
        return []

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
def test_pg_threads_sharing_a_store_do_not_run_inside_each_others_transaction(
    second_call, monkeypatch
):
    store, conn = _pg_store()
    # The first thread stays inside its transaction until the second has to wait for
    # the store's lock; with no lock, the second runs inside it.
    monkeypatch.setattr(store, "_lock", _WatchedLock(conn.release), raising=False)
    calls = {
        "replace": _replace(store, ["beta", "gamma"]),
        "count": store.count,
        "close": store.close,
    }

    def second():
        assert conn.inserting.wait(5), "the first thread never inserted"
        calls[second_call]()

    _run(_replace(store, ["alpha", "delta"]), second, names=("first", "second"))

    names = [name for name, _ in conn.log]
    assert "second" in names, "the second call ran no statement, so the test checks nothing"
    # Without the store's lock, the second thread's statements (its commit would store
    # the first's half-done replacement) land inside the first's transaction.
    assert "second" not in names[: conn.log.index(("first", "COMMIT")) + 1], conn.log


def test_pg_close_waits_a_bounded_time_for_a_call_in_another_thread():
    import time

    store, conn = _pg_store()
    holding, done = threading.Event(), threading.Event()

    def long_call():  # a relemmatize() of a big table, say
        with store._lock:
            holding.set()
            done.wait(10)

    worker = threading.Thread(target=long_call, daemon=True)
    worker.start()
    assert holding.wait(5)
    started = time.monotonic()
    store.close(timeout=0.2)
    elapsed = time.monotonic() - started
    done.set()
    worker.join(5)

    assert conn.closed and store._conn is None
    assert 0.15 <= elapsed < 3, elapsed


def _held_by_caller(lock) -> bool:
    """Whether the calling thread holds ``lock``: another thread cannot take it."""
    taken = []

    def try_it():
        got = lock.acquire(timeout=0)
        if got:
            lock.release()
        taken.append(got)

    thread = threading.Thread(target=try_it)
    thread.start()
    thread.join(5)
    return not taken[0]


def test_pg_the_text_processor_runs_outside_the_stores_lock():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    class _SlowProcessor:  # a Finnish lemmatizer, say
        def __init__(self) -> None:
            self.held: list[bool] = []

        def to_tsvector_text(self, text):
            self.held.append(_held_by_caller(store._lock))
            return text

        def expand_query(self, text):
            self.held.append(_held_by_caller(store._lock))
            return text

    processor = _SlowProcessor()
    store = PgVectorStore("postgresql://unused", embedding_dim=3, text_processor=processor)
    store._conn = conn = _SharedPg()
    conn.release.set()

    store.add(_chunks("report", ["alpha"]), [A1])
    store.search_keyword("roof")
    store.search_hybrid(A1, "roof")
    store.search_hybrid_weighted(A1, "roof")

    assert processor.held == [False] * 4


def test_pg_a_shallow_copy_shares_the_connections_lock():
    import copy

    store, _ = _pg_store()
    assert copy.copy(store)._lock is store._lock


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
