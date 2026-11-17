"""A RAG store with an owner sees only that owner's chunks (G28)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.vector_store.vector_store import (  # noqa: E402
    OWNER_KEY,
    VectorStore,
)
from langchain_core.documents import Document  # noqa: E402

E = [1.0, 0.0]


def _doc(text, **meta):
    return Document(page_content=text, metadata={"source": "a.pdf", **meta})


def test_in_memory_owner_sees_only_its_chunks():
    store = VectorStore(owner="alice")
    store.add([_doc("alice's fact")], [E])
    store._documents.append(_doc("bob's fact", **{OWNER_KEY: "bob"}))
    store._embeddings.append(E)

    found = [d.page_content for d, _ in store.search(E, top_k=5)]

    assert found == ["alice's fact"]
    assert store.count() == 1


def test_the_callers_documents_are_not_changed():
    doc = _doc("fact")
    VectorStore(owner="alice").add([doc], [E])

    assert OWNER_KEY not in doc.metadata


def test_without_an_owner_nothing_changes():
    store = VectorStore()
    store.add([_doc("fact")], [E])

    ((doc, _),) = store.search(E)
    assert OWNER_KEY not in doc.metadata


@pytest.mark.parametrize("owner", ["", "  ", 5])
def test_a_blank_owner_is_refused(owner):
    with pytest.raises(ValueError, match="owner"):
        VectorStore(owner=owner)


def test_chroma_owners_share_a_collection_without_reading_each_other(tmp_path):
    pytest.importorskip("chromadb")
    kwargs = {"persist": True, "persist_path": str(tmp_path), "collection_name": "shared"}
    alice = VectorStore(owner="alice", **kwargs)
    bob = VectorStore(owner="bob", **kwargs)
    alice.add([_doc("alice's fact")], [E])
    bob.add([_doc("bob's fact")], [E])

    assert [d.page_content for d, _ in alice.search(E, top_k=5)] == ["alice's fact"]
    assert [d.page_content for d, _ in bob.search(E, top_k=5)] == ["bob's fact"]
    # a filter naming another owner cannot widen the search
    widened = alice.search(E, top_k=5, filters={OWNER_KEY: "bob"})
    assert widened == []
    either = alice.search(E, top_k=5, filters={"$or": [{"source": "a.pdf"}, {"x": 1}]})
    assert [d.page_content for d, _ in either] == ["alice's fact"]
    assert (alice.count(), bob.count()) == (1, 1)
    assert VectorStore(**kwargs).count() == 2  # no owner: the whole collection


# PgVectorStore: the owner goes into every statement that reads, counts or deletes.


class _Conn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))

        class _R:
            rowcount = 0

            @staticmethod
            def fetchall():
                return []

            @staticmethod
            def fetchone():
                return {"cnt": 0}

        return _R()

    def commit(self):
        pass


@pytest.fixture
def pg():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store.pg_vector_store import PgVectorStore

    store = PgVectorStore("postgresql://stub@localhost:1/stub", embedding_dim=2, owner="alice")
    conn = _Conn()
    store._get_conn = lambda: conn
    store._lemmatize_query = lambda q: q
    return store, conn


def _owner_in(params) -> bool:
    for p in params:
        if isinstance(p, str) and p.startswith("{"):
            if json.loads(p).get(OWNER_KEY) == "alice":
                return True
    return False


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.search_semantic(E, filters={OWNER_KEY: "bob"}),
        lambda s: s.search_keyword("roof", filters={OWNER_KEY: "bob"}),
        lambda s: s.search_hybrid(E, "roof"),
        lambda s: s.search_hybrid_weighted(E, "roof"),
        lambda s: s.search(E),
        lambda s: s.count(),
        lambda s: s.delete([1, 2]),
    ],
    ids=["semantic", "keyword", "hybrid", "weighted", "search", "count", "delete"],
)
def test_pg_every_search_count_and_delete_is_scoped_to_the_owner(pg, call):
    store, conn = pg

    call(store)

    (sql, params) = conn.calls[-1]
    assert _owner_in(params), (sql, params)
    assert not any(isinstance(p, str) and '"bob"' in p for p in params)


def test_pg_add_records_the_owner(pg):
    store, conn = pg

    class _Cur:
        def __init__(self):
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            self.params = params

        def fetchone(self):
            return {"id": 1}

    cur = _Cur()
    conn.cursor = lambda: cur

    store.add([_doc("fact", **{OWNER_KEY: "bob"})], [E])

    metadata = json.loads(next(p for p in cur.params if isinstance(p, str) and p.startswith("{")))
    assert metadata[OWNER_KEY] == "alice"


def test_rag_workflow_passes_its_owner_to_the_store(monkeypatch):
    pytest.importorskip("langchain_core")
    from gaik.software_modules.RAG_workflow import pipeline

    seen = {}

    class Store:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(pipeline, "VectorStore", Store)
    monkeypatch.setattr(pipeline, "Embedder", lambda **k: None)
    monkeypatch.setattr(pipeline, "Retriever", lambda **k: None)
    monkeypatch.setattr(pipeline, "AnswerGenerator", lambda **k: None)

    pipeline.RAGWorkflow(
        api_config={"provider": "openai", "model": "m"}, parser="text", owner="alice"
    )

    assert seen["owner"] == "alice"


def test_an_unowned_store_refuses_a_chunk_that_names_an_owner():
    store = VectorStore()

    with pytest.raises(ValueError, match=OWNER_KEY):
        store.add([_doc("planted", **{OWNER_KEY: "alice"})], [E])
    assert store.count() == 0


def test_an_unowned_chroma_store_refuses_a_planted_owner(tmp_path):
    pytest.importorskip("chromadb")
    kwargs = {"persist": True, "persist_path": str(tmp_path), "collection_name": "shared"}
    VectorStore(owner="alice", **kwargs).add([_doc("alice's fact")], [E])

    with pytest.raises(ValueError, match=OWNER_KEY):
        VectorStore(**kwargs).add([_doc("planted", **{OWNER_KEY: "alice"})], [E])

    found = VectorStore(owner="alice", **kwargs).search(E, top_k=5)
    assert [d.page_content for d, _ in found] == ["alice's fact"]


def test_pg_unowned_add_refuses_a_planted_owner():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store.pg_vector_store import PgVectorStore

    store = PgVectorStore("postgresql://stub@localhost:1/stub", embedding_dim=2)
    store._get_conn = lambda: pytest.fail("no statement may run")

    with pytest.raises(ValueError, match=OWNER_KEY):
        store.add([_doc("planted", **{OWNER_KEY: "alice"})], [E])


def test_pg_owner_turns_on_iterative_scans_unless_told_otherwise():
    pytest.importorskip("psycopg")
    from gaik.software_components.RAG.pg_vector_store.pg_vector_store import PgVectorStore

    dsn = "postgresql://stub@localhost:1/stub"
    assert PgVectorStore(dsn, owner="alice").hnsw_iterative_scan == "relaxed_order"
    assert PgVectorStore(dsn, owner="alice", hnsw_iterative_scan="off").hnsw_iterative_scan == (
        "off"
    )
    assert PgVectorStore(dsn).hnsw_iterative_scan is None
