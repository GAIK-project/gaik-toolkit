"""Chroma-backed VectorStore scores like the in-memory one and stores large adds."""

import warnings

import pytest

chromadb = pytest.importorskip("chromadb")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.vector_store.vector_store import VectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def _scores(store):
    store.add(
        [Document(page_content="unit"), Document(page_content="scaled")],
        [[0.6, 0.8], [1.8, 2.4]],
    )
    return {doc.page_content: score for doc, score in store.search([1.0, 0.0], top_k=2)}


def test_persisted_scores_are_cosine_similarities_like_in_memory(tmp_path):
    memory = _scores(VectorStore())
    persisted = _scores(VectorStore(persist=True, persist_path=str(tmp_path / "c")))

    for key in ("unit", "scaled"):
        assert persisted[key] == pytest.approx(memory[key], abs=1e-5)
        assert persisted[key] == pytest.approx(0.6, abs=1e-5)


def test_an_existing_l2_collection_still_reports_cosine_scores(tmp_path):
    path = str(tmp_path / "c")
    chromadb.PersistentClient(path=path).get_or_create_collection("gaik_rag")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store = VectorStore(persist=True, persist_path=path)
    assert any("l2" in str(w.message) for w in caught)

    scores = _scores(store)
    assert scores["unit"] == pytest.approx(0.6, abs=1e-5)
    assert scores["scaled"] == pytest.approx(0.6, abs=1e-5)


def test_an_add_above_the_chroma_batch_limit_stores_every_chunk(tmp_path):
    store = VectorStore(persist=True, persist_path=str(tmp_path / "c"))
    client = chromadb.PersistentClient(path=str(tmp_path / "c"))
    size = client.get_max_batch_size() + 1
    docs = [Document(page_content=f"c{i}") for i in range(size)]

    store.add(docs, [[1.0, float(i)] for i in range(size)])

    assert store.count() == size
