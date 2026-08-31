"""Regression tests for Retriever ranking behaviour.

Each test here pins a defect that shipped: reranking that computed scores
without reordering, a cross-encoder reloaded per call, a candidate pool that
never widened, a reranker outage breaking search, and relevance scores leaking
into the vector store's own documents.

Uses hand-written fakes rather than MagicMock, per repo convention.
"""

import logging

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.retriever import Retriever  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class FakeEmbedder:
    def embed_query(self, query):
        return [0.1, 0.2, 0.3]


class FakeStore:
    """Records the top_k it was asked for and returns owned Document objects."""

    def __init__(self, documents=None):
        if documents is None:  # an explicit [] means "the store is empty"
            documents = [
                Document(page_content="d1", metadata={"source": "a"}),
                Document(page_content="d2", metadata={"source": "b"}),
                Document(page_content="d3", metadata={"source": "c"}),
            ]
        self.documents = documents
        self.requested_top_k = None

    def search(self, embedding, *, top_k=5, filters=None):
        self.requested_top_k = top_k
        scores = [0.91, 0.83, 0.77]
        # Return the stored objects, exactly as VectorStore's in-memory path does.
        return list(zip(self.documents, scores))[:top_k]


class FakeCrossEncoder:
    def __init__(self, scores):
        self.scores = list(scores)
        self.predict_calls = 0

    def predict(self, pairs):
        self.predict_calls += 1
        return self.scores[: len(pairs)]  # plain list, not numpy


class ExplodingCrossEncoder:
    def predict(self, pairs):
        raise RuntimeError("inference backend unavailable")


def make_retriever(store, cross_encoder=None, **kwargs):
    retriever = Retriever(embedder=FakeEmbedder(), vector_store=store, **kwargs)
    if cross_encoder is not None:
        retriever._cross_encoder = cross_encoder
    return retriever


def names_of(documents):
    return [d.page_content for d in documents]


# ----------------------------------------------------------------------
# Defect 1: reranking computed scores but never reordered
# ----------------------------------------------------------------------


def test_rerank_without_hybrid_reorders_results():
    store = FakeStore()
    # Retrieval order is d1, d2, d3. The cross-encoder says d2 is best.
    retriever = make_retriever(
        store, FakeCrossEncoder([0.1, 0.9, 0.5]), re_rank=True, top_k=3
    )

    assert names_of(retriever.search("query")) == ["d2", "d3", "d1"]


def test_rerank_with_hybrid_still_reorders():
    store = FakeStore()
    retriever = make_retriever(
        store,
        FakeCrossEncoder([0.1, 0.9, 0.5]),
        re_rank=True,
        hybrid_search=True,
        top_k=3,
    )

    assert names_of(retriever.search("query")) == ["d2", "d3", "d1"]


def test_reranked_scores_match_the_returned_order():
    store = FakeStore()
    retriever = make_retriever(
        store, FakeCrossEncoder([0.1, 0.9, 0.5]), re_rank=True, top_k=3
    )

    docs = retriever.search("query", include_scores=True)
    scores = [d.metadata["relevance_score"] for d in docs]
    assert scores == sorted(scores, reverse=True)
    assert scores == [0.9, 0.5, 0.1]


# ----------------------------------------------------------------------
# Defect 2: cross-encoder reconstructed on every call
# ----------------------------------------------------------------------


def test_cross_encoder_is_reused_across_searches():
    store = FakeStore()
    encoder = FakeCrossEncoder([0.1, 0.9, 0.5])
    retriever = make_retriever(store, encoder, re_rank=True, top_k=3)

    retriever.search("query")
    retriever.search("query")
    retriever.search("query")

    assert encoder.predict_calls == 3
    assert retriever._cross_encoder is encoder  # never replaced


# ----------------------------------------------------------------------
# Defect 3: candidate pool never widened
# ----------------------------------------------------------------------


def test_candidate_pool_widens_when_reranking():
    store = FakeStore()
    retriever = make_retriever(
        store, FakeCrossEncoder([0.1, 0.9, 0.5]), re_rank=True, top_k=5
    )
    docs = retriever.search("query")

    assert store.requested_top_k == 20  # 5 * candidate_multiplier
    assert len(docs) <= 5


def test_candidate_pool_widens_when_hybrid_scoring():
    store = FakeStore()
    retriever = make_retriever(store, hybrid_search=True, top_k=5)
    retriever.search("query")

    assert store.requested_top_k == 20


def test_plain_semantic_search_pool_is_unchanged():
    """Backwards compatibility: the default path must not fetch more rows."""
    store = FakeStore()
    retriever = make_retriever(store, top_k=5)
    retriever.search("query")

    assert store.requested_top_k == 5


def test_candidate_multiplier_is_configurable():
    store = FakeStore()
    retriever = make_retriever(
        store, FakeCrossEncoder([0.1, 0.9, 0.5]), re_rank=True, top_k=3,
        candidate_multiplier=10,
    )
    retriever.search("query")

    assert store.requested_top_k == 30


# ----------------------------------------------------------------------
# Defect 5: reranker failure broke search
# ----------------------------------------------------------------------


def test_rerank_failure_falls_back_to_retrieval_order(caplog):
    store = FakeStore()
    retriever = make_retriever(store, ExplodingCrossEncoder(), re_rank=True, top_k=3)

    with caplog.at_level(
        logging.WARNING, logger="gaik.software_components.RAG.retriever"
    ):
        docs = retriever.search("query")

    assert names_of(docs) == ["d1", "d2", "d3"]
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_rerank_with_no_candidates_does_not_call_the_model():
    store = FakeStore(documents=[])
    encoder = FakeCrossEncoder([])
    retriever = make_retriever(store, encoder, re_rank=True, top_k=3)

    assert retriever.search("query") == []
    assert encoder.predict_calls == 0


# ----------------------------------------------------------------------
# Defect 7: relevance scores leaked into the vector store's own documents
# ----------------------------------------------------------------------


def test_include_scores_does_not_mutate_the_stores_documents():
    store = FakeStore()
    retriever = make_retriever(store, top_k=3)

    retriever.search("query", include_scores=True)

    for stored_doc in store.documents:
        assert "relevance_score" not in stored_doc.metadata


def test_second_search_does_not_see_a_stale_score():
    store = FakeStore()
    retriever = make_retriever(store, top_k=3)

    retriever.search("query", include_scores=True)
    docs = retriever.search("query", include_scores=False)

    assert all("relevance_score" not in d.metadata for d in docs)


def test_include_scores_preserves_existing_metadata():
    store = FakeStore()
    retriever = make_retriever(store, top_k=3)

    docs = retriever.search("query", include_scores=True)

    assert docs[0].metadata["source"] == "a"
    assert docs[0].metadata["relevance_score"] == pytest.approx(0.91)


# ----------------------------------------------------------------------
# Unchanged behaviour
# ----------------------------------------------------------------------


def test_plain_semantic_search_preserves_store_order():
    store = FakeStore()
    retriever = make_retriever(store, top_k=3)
    assert names_of(retriever.search("query")) == ["d1", "d2", "d3"]


def test_top_k_truncates():
    store = FakeStore()
    retriever = make_retriever(store, top_k=2)
    assert len(retriever.search("query")) == 2


def test_score_threshold_filters():
    store = FakeStore()
    retriever = make_retriever(store, top_k=3, score_threshold=0.8)
    assert names_of(retriever.search("query")) == ["d1", "d2"]
