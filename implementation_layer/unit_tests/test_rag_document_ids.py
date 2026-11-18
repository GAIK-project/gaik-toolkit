"""A chunk's id comes from its document and its text, in every RAG store.

Indexing the same document again updates its chunks instead of storing a second
copy; ``replace=True`` also drops the chunks the document no longer has; and
``delete_document`` removes one document's chunks and leaves the others.

The PgVectorStore tests against a database are skipped unless ``GAIK_TEST_PG_URL``
points at a pgvector database (see ``test_pg_vector_store_sql.py``).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from langchain_core.documents import Document  # noqa: E402

A1 = [1.0, 0.0, 0.0]
B1 = [0.0, 1.0, 0.0]
C1 = [0.0, 0.0, 1.0]


def _chunks(document: str, texts: list[str]) -> list[Document]:
    return [
        Document(page_content=text, metadata={"document_name": document, "page": i})
        for i, text in enumerate(texts)
    ]


def _add_as(store, owner: str | None, chunks, embeddings, **kwargs) -> None:
    """``store.add`` as a store with ``owner`` that shares this store's chunks."""
    store.owner = owner
    try:
        store.add(chunks, embeddings, **kwargs)
    finally:
        store.owner = None


def _texts(store, document: str) -> list[str]:
    found = store.search(A1, top_k=50, filters={"document_id": document})
    return sorted(doc.page_content for doc, _ in found)


# ── VectorStore, in memory and in Chroma ─────────────────────────────


@pytest.fixture(params=[False, True], ids=["memory", "chroma"])
def store(request, tmp_path):
    if request.param:
        pytest.importorskip("chromadb")
    from gaik.software_components.RAG.vector_store import VectorStore

    return VectorStore(persist=request.param, persist_path=str(tmp_path / "chroma"))


def test_indexing_the_same_document_twice_stores_its_chunks_once(store):
    chunks = _chunks("report", ["alpha", "beta"])
    store.add(chunks, [A1, B1])
    store.add(_chunks("report", ["alpha", "beta"]), [A1, B1])

    assert store.count() == 2
    assert _texts(store, "report") == ["alpha", "beta"]


def test_replace_drops_the_chunks_a_changed_document_no_longer_has(store):
    store.add(_chunks("report", ["alpha", "beta", "gamma"]), [A1, B1, C1])
    store.add(_chunks("report", ["alpha", "delta"]), [A1, B1], replace=True)

    assert _texts(store, "report") == ["alpha", "delta"]
    assert store.count() == 2


def test_delete_document_leaves_the_other_documents(store):
    store.add(_chunks("report", ["alpha", "beta"]), [A1, B1])
    store.add(_chunks("minutes", ["gamma"]), [C1])

    assert store.delete_document("report") == 2

    assert store.count() == 1
    assert _texts(store, "report") == []
    assert _texts(store, "minutes") == ["gamma"]


def test_a_text_repeated_in_one_document_keeps_each_occurrence(store):
    store.add(_chunks("report", ["Page header", "body", "Page header"]), [A1, B1, A1])

    assert store.count() == 3


def test_the_same_text_in_two_documents_is_two_chunks(store):
    store.add(_chunks("report", ["shared text"]), [A1])
    store.add(_chunks("minutes", ["shared text"]), [A1])

    assert store.count() == 2


def test_chunks_that_name_no_document_are_added_as_before(store):
    store.add([Document(page_content="bare")], [A1])
    store.add([Document(page_content="bare")], [A1])

    assert store.count() == 2
    [(doc, _), _second] = store.search(A1, top_k=2)
    assert doc.metadata == {}


def test_the_document_id_comes_from_the_source_when_set(store):
    store.add([Document(page_content="x", metadata={"source": "a/report.pdf"})], [A1])

    [(doc, _)] = store.search(A1, top_k=1)
    assert doc.metadata["document_id"] == "a/report.pdf"
    assert store.delete_document("a/report.pdf") == 1


def test_an_own_document_id_is_kept(store):
    store.add(
        [Document(page_content="x", metadata={"document_id": "doc-7", "source": "tmp/x.pdf"})],
        [A1],
    )

    assert store.delete_document("tmp/x.pdf") == 0
    assert store.delete_document("doc-7") == 1


def test_two_owners_with_the_same_document_keep_separate_chunks(store):
    _add_as(store, "user-a", _chunks("report", ["alpha", "beta"]), [A1, B1])
    _add_as(store, "user-b", _chunks("report", ["alpha", "beta"]), [A1, B1])

    assert store.count() == 4

    _add_as(store, "user-a", _chunks("report", ["gamma"]), [C1], replace=True)
    assert _texts(store, "report") == ["alpha", "beta", "gamma"]
    assert store.count() == 3


def test_delete_document_deletes_only_the_given_owners_chunks(store):
    _add_as(store, "user-a", _chunks("report", ["alpha"]), [A1])
    _add_as(store, "user-b", _chunks("report", ["beta"]), [B1])
    store.add(_chunks("report", ["gamma"]), [C1])

    assert store.delete_document("report") == 1
    assert _texts(store, "report") == ["alpha", "beta"]
    assert store.delete_document("report", owner="user-a") == 1
    assert _texts(store, "report") == ["beta"]


def test_replace_without_an_owner_leaves_the_owners_chunks(store):
    _add_as(store, "user-a", _chunks("report", ["alpha"]), [A1])
    store.add(_chunks("report", ["beta"]), [B1], replace=True)

    assert _texts(store, "report") == ["alpha", "beta"]


def test_a_store_with_an_owner_deletes_with_it(store):
    _add_as(store, "user-a", _chunks("report", ["alpha"]), [A1])
    _add_as(store, "user-b", _chunks("report", ["beta"]), [B1])
    store.owner = "user-a"

    with pytest.raises(ValueError):
        store.delete_document("report", owner="user-b")
    assert store.delete_document("report") == 1
    store.owner = None
    assert _texts(store, "report") == ["beta"]


@pytest.mark.parametrize("bad", [{"$ne": "x"}, {"$in": ["report"]}, ["report"], None, 1.5])
def test_delete_document_refuses_an_id_that_is_not_text(store, bad):
    store.add(_chunks("report", ["alpha"]), [A1])

    with pytest.raises(ValueError):
        store.delete_document(bad)
    assert store.count() == 1


def test_a_document_id_that_is_not_text_is_refused(store):
    with pytest.raises(ValueError):
        store.add([Document(page_content="x", metadata={"document_id": {"$ne": ""}})], [A1])
    assert store.count() == 0


def test_an_int_document_id_is_stored_and_deleted_as_its_string(store):
    store.add([Document(page_content="x", metadata={"document_id": 7})], [A1])

    [(doc, _)] = store.search(A1, top_k=1)
    assert doc.metadata["document_id"] == "7"
    assert store.delete_document(7) == 1


def test_replace_keeps_the_old_chunks_when_storing_fails(store, monkeypatch):
    store.add(_chunks("report", ["alpha", "beta"]), [A1, B1])

    def fail(*args, **kwargs):
        raise RuntimeError("store unavailable")

    if store.persist:
        monkeypatch.setattr(store._collection, "add", fail)
    else:
        monkeypatch.setattr(store, "_ids", _FailingList(store._ids))
    with pytest.raises(RuntimeError):
        store.add(_chunks("report", ["gamma"]), [C1], replace=True)
    monkeypatch.undo()

    assert _texts(store, "report") == ["alpha", "beta"]


class _FailingList(list):
    def append(self, item):
        raise RuntimeError("store unavailable")


def test_the_occurrence_is_counted_within_one_call(store):
    store.add(_chunks("report", ["header"]), [A1])
    store.add(_chunks("report", ["header"]), [A1])

    assert store.count() == 1


def test_indexing_again_drops_a_metadata_key_the_chunk_no_longer_has(store):
    [chunk] = _chunks("report", ["alpha"])
    chunk.metadata["heading"] = "Old heading"
    store.add([chunk], [A1])
    [chunk] = _chunks("report", ["alpha"])
    chunk.metadata["heading"] = None
    store.add([chunk], [A1])

    [(doc, _)] = store.search(A1, top_k=5)
    assert doc.metadata.get("heading") is None
    assert store.count() == 1


def test_an_owner_is_part_of_the_chunk_id_when_set_by_the_store(store):
    _add_as(store, "user-a", _chunks("report", ["alpha"]), [A1])
    store.add(_chunks("report", ["alpha"]), [A1])

    assert store.count() == 2
    assert store.delete_document("report") == 1
    assert store.delete_document("report", owner="user-a") == 1


def test_a_store_without_an_owner_refuses_chunks_that_name_one(store):
    [chunk] = _chunks("report", ["alpha"])
    chunk.metadata["gaik_owner"] = "user-a"

    with pytest.raises(ValueError):
        store.add([chunk], [A1])
    assert store.count() == 0


# ── RAGWorkflow ──────────────────────────────────────────────────────


class _FakeEmbedder:
    def embed(self, documents):
        return [[1.0, float(len(doc.page_content)), 0.0] for doc in documents], documents


class _FakeParser:
    def __init__(self) -> None:
        self.texts: dict[str, list[str]] = {}

    def convert_doc_to_chunks(self, path, document_name=None):
        return [
            Document(page_content=text, metadata={"source": str(path), "document_name": "x"})
            for text in self.texts[Path(path).as_posix()]
        ]


@pytest.fixture
def workflow():
    pytest.importorskip("gaik.software_modules.RAG_workflow")
    from gaik.software_components.RAG.vector_store import VectorStore
    from gaik.software_modules.RAG_workflow import RAGWorkflow

    flow = RAGWorkflow.__new__(RAGWorkflow)
    flow.parser_kind = "text"
    flow.parser = _FakeParser()
    flow.embedder = _FakeEmbedder()
    flow.vector_store = VectorStore()
    return flow


def test_workflow_reindexing_a_changed_file_replaces_its_chunks(workflow):
    workflow.parser.texts = {"/in/a.pdf": ["one", "two", "three"], "/in/b.pdf": ["other"]}
    workflow.index_documents(["/in/a.pdf", "/in/b.pdf"], filenames=["a.pdf", "b.pdf"])
    workflow.parser.texts["/in/a.pdf"] = ["one", "four"]
    workflow.index_documents(["/in/a.pdf"], filenames=["a.pdf"])

    stored = sorted(d.page_content for d in workflow.vector_store._documents)
    assert stored == ["four", "one", "other"]


def test_workflow_two_files_with_the_same_name_are_two_documents(workflow):
    workflow.parser.texts = {"/in/1/a.pdf": ["one"], "/in/2/a.pdf": ["two"]}
    workflow.index_documents(["/in/1/a.pdf"], filenames=["a.pdf"])
    workflow.index_documents(["/in/2/a.pdf"], filenames=["a.pdf"])

    stored = sorted(d.page_content for d in workflow.vector_store._documents)
    assert stored == ["one", "two"]


def test_workflow_document_ids_identify_the_files(workflow):
    workflow.parser.texts = {"/tmp/x1.pdf": ["one", "two"], "/tmp/x2.pdf": ["three"]}
    workflow.index_documents(["/tmp/x1.pdf"], document_ids=["doc-7"])
    workflow.index_documents(["/tmp/x2.pdf"], document_ids=["doc-7"])

    assert [d.page_content for d in workflow.vector_store._documents] == ["three"]
    assert workflow.delete_document("doc-7") == 1
    with pytest.raises(ValueError):
        workflow.index_documents(["/tmp/x1.pdf"], document_ids=[])


def test_workflow_keeps_the_old_chunks_when_the_store_add_fails(workflow, monkeypatch):
    workflow.parser.texts = {"/in/a.pdf": ["one", "two"]}
    workflow.index_documents(["/in/a.pdf"])
    workflow.parser.texts["/in/a.pdf"] = ["three"]
    monkeypatch.setattr(workflow.vector_store, "_ids", _FailingList(workflow.vector_store._ids))

    with pytest.raises(RuntimeError):
        workflow.index_documents(["/in/a.pdf"])
    monkeypatch.undo()

    assert sorted(d.page_content for d in workflow.vector_store._documents) == ["one", "two"]


def test_workflow_a_store_without_replace_gets_delete_then_add(workflow):
    calls = []

    class _Store:
        persist = False

        def add(self, documents, embeddings):
            calls.append(("add", [d.page_content for d in documents]))

        def delete_document(self, document_id):
            calls.append(("delete", document_id))
            return 0

    workflow.vector_store = _Store()
    workflow.parser.texts = {"/in/a.pdf": ["one"]}
    workflow.index_documents(["/in/a.pdf"])

    assert calls == [("delete", "/in/a.pdf"), ("add", ["one"])]


def test_workflow_delete_document_removes_one_file(workflow):
    workflow.parser.texts = {"/in/a.pdf": ["one", "two"], "/in/b.pdf": ["other"]}
    workflow.index_documents(["/in/a.pdf", "/in/b.pdf"])

    assert workflow.delete_document("/in/a.pdf") == 2
    assert [d.page_content for d in workflow.vector_store._documents] == ["other"]


# ── PgVectorStore without a database ─────────────────────────────────


class _Recorder:
    closed = False

    def __init__(self, *, has_chunk_key: bool = True) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.has_chunk_key = has_chunk_key
        self._row = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))
        if "pg_attribute" in sql:
            self._row = {"?column?": 1} if self.has_chunk_key else None
        else:
            self._row = {"id": len(self.calls)}
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
        pass


def _pg(has_chunk_key: bool = True, owner: str | None = None):
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    store = PgVectorStore("postgresql://unused", embedding_dim=3, owner=owner)
    store._conn = recorder = _Recorder(has_chunk_key=has_chunk_key)
    return store, recorder


def _inserts(recorder):
    return [(sql, params) for sql, params in recorder.calls if sql.startswith("INSERT")]


def test_pg_add_upserts_on_a_key_that_is_the_same_for_the_same_chunk():
    store, recorder = _pg()
    store.add(_chunks("report", ["alpha", "beta"]), [A1, B1])
    store.add(_chunks("report", ["alpha", "beta"]), [A1, B1])

    inserts = _inserts(recorder)
    assert all("ON CONFLICT (chunk_key) DO UPDATE" in sql for sql, _ in inserts)
    keys = [params[-1] for _, params in inserts]
    assert keys[:2] == keys[2:]
    assert keys[0] != keys[1]


PG_DELETE = (
    "DELETE FROM documents WHERE metadata @> %s::jsonb"
    " AND metadata->>'document_id' = %s AND metadata->>'gaik_owner' "
)


def test_pg_replace_deletes_the_documents_rows_before_inserting():
    store, recorder = _pg()
    store.add(_chunks("report", ["alpha"]), [A1], replace=True)

    calls = [(sql, params) for sql, params in recorder.calls if not sql.startswith("SELECT")]
    assert calls[0] == (PG_DELETE + "IS NULL", ('{"document_id": "report"}', "report"))
    assert calls[1][0].startswith("INSERT")


def test_pg_replace_deletes_only_the_rows_of_the_stores_owner():
    store, recorder = _pg(owner="user-a")
    store.add(_chunks("report", ["alpha"]), [A1], replace=True)

    sql, params = recorder.calls[1]
    assert sql == PG_DELETE + "= %s"
    assert params == ('{"document_id": "report"}', "report", "user-a")


def test_pg_delete_document_compares_the_document_id_exactly():
    store, recorder = _pg()
    store.delete_document("report")

    assert recorder.calls[-1] == (PG_DELETE + "IS NULL", ('{"document_id": "report"}', "report"))

    store.delete_document("report", owner="user-a")
    assert recorder.calls[-1] == (
        PG_DELETE + "= %s",
        ('{"document_id": "report"}', "report", "user-a"),
    )


@pytest.mark.parametrize("bad", [{"$ne": "x"}, ["report"], None, 1.5, True])
def test_pg_delete_document_refuses_an_id_that_is_not_text(bad):
    store, recorder = _pg()
    with pytest.raises(ValueError):
        store.delete_document(bad)
    assert recorder.calls == []


def test_pg_add_refuses_a_document_id_that_is_not_text():
    store, recorder = _pg()
    doc = Document(page_content="x", metadata={"document_id": {"$gt": ""}})
    with pytest.raises(ValueError):
        store.add([doc], [A1], replace=True)
    assert not [sql for sql, _ in recorder.calls if sql.startswith(("DELETE", "INSERT"))]


def test_pg_two_owners_get_different_keys_for_the_same_chunk():
    keys = []
    for owner in ("user-a", "user-b", None):
        store, recorder = _pg(owner=owner)
        store.add(_chunks("report", ["alpha"]), [A1])
        keys += [params[-1] for _, params in _inserts(recorder)]
    assert len(set(keys)) == 3


def test_pg_a_store_without_an_owner_refuses_chunks_that_name_one():
    store, recorder = _pg()
    [chunk] = _chunks("report", ["alpha"])
    chunk.metadata["gaik_owner"] = "user-a"

    with pytest.raises(ValueError):
        store.add([chunk], [A1])
    assert not _inserts(recorder)


@pytest.mark.parametrize("has_chunk_key", [True, False])
def test_pg_setup_alters_the_table_only_when_chunk_key_is_missing(has_chunk_key):
    store, recorder = _pg(has_chunk_key=has_chunk_key)
    store.setup()

    altered = [sql for sql, _ in recorder.calls if sql.startswith("ALTER TABLE")]
    assert bool(altered) is not has_chunk_key


def test_pg_a_table_without_chunk_key_is_inserted_into_as_before():
    store, recorder = _pg(has_chunk_key=False)
    store.add(_chunks("report", ["alpha"]), [A1])

    [(sql, _)] = _inserts(recorder)
    assert "chunk_key" not in sql
    assert "ON CONFLICT" not in sql


# ── PgVectorStore against a database ─────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
live = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")


@pytest.fixture
def pg_store():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    table = f"gaik_test_ids_{uuid.uuid4().hex[:8]}"
    store = PgVectorStore(PG_URL, table_name=table, embedding_dim=3)
    yield store
    conn = store._get_conn()
    conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    signatures = conn.execute(
        "SELECT oid::regprocedure::text AS sig FROM pg_proc WHERE proname LIKE %s",
        (f"%\\_{table}",),
    ).fetchall()
    for row in signatures:
        conn.execute(f"DROP FUNCTION IF EXISTS {row['sig']}")
    conn.commit()
    store.close()


@live
def test_pg_reindexing_stores_once_replace_drops_old_chunks_and_delete_leaves_others(pg_store):
    pg_store.setup()
    pg_store.add(_chunks("report", ["alpha", "beta", "gamma"]), [A1, B1, C1])
    pg_store.add(_chunks("report", ["alpha", "beta", "gamma"]), [A1, B1, C1])
    pg_store.add(_chunks("minutes", ["other"]), [A1])
    assert pg_store.count() == 4

    pg_store.add(_chunks("report", ["alpha", "delta"]), [A1, B1], replace=True)
    assert pg_store.count() == 3

    assert pg_store.delete_document("report") == 2
    assert pg_store.count() == 1


@live
def test_pg_setup_adds_chunk_key_to_a_table_made_without_it(pg_store):
    conn = pg_store._get_conn()
    conn.execute(
        f"CREATE TABLE {pg_store.table_name} (id SERIAL PRIMARY KEY, title TEXT, "
        "content TEXT NOT NULL, metadata JSONB DEFAULT '{}'::JSONB, embedding vector(3), "
        "text_search tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED, "
        "created_at TIMESTAMPTZ DEFAULT NOW())"
    )
    conn.execute(
        f"INSERT INTO {pg_store.table_name} (content, embedding) VALUES ('old', '[1,0,0]')"
    )
    conn.commit()

    pg_store.setup()
    pg_store.add(_chunks("report", ["alpha"]), [A1])
    pg_store.add(_chunks("report", ["alpha"]), [A1])

    assert pg_store.count() == 2
