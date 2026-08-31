"""Unit tests for Ranker cross-encoder reranking.

Exercises the whole rerank path without importing sentence-transformers and
without downloading a model, via the public ``model_loader`` seam. Explicit stub
classes rather than MagicMock, per repo convention.
"""

import logging

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.ranker import Ranker  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class FakeCrossEncoder:
    """Returns a fixed list of scores. A plain list, not a numpy array."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.predict_calls = 0
        self.last_batch_size = None

    def predict(self, pairs, batch_size=None):
        self.predict_calls += 1
        self.last_batch_size = batch_size
        return self.scores[: len(pairs)]


class CountingLoader:
    def __init__(self, model):
        self.model = model
        self.calls = 0

    def __call__(self, name):
        self.calls += 1
        return self.model


class ExplodingLoader:
    def __init__(self):
        self.calls = 0

    def __call__(self, name):
        self.calls += 1
        raise RuntimeError("model download failed")


class ExplodingPredictor:
    def predict(self, pairs, batch_size=None):
        raise RuntimeError("inference backend unavailable")


class WrongLengthPredictor:
    def predict(self, pairs, batch_size=None):
        return [0.1]


def result(name, score, **metadata):
    return (Document(page_content=name, metadata=metadata), score)


# Retrieval order is d1, d2, d3. The reranker disagrees: d2 is best, then d3.
CANDIDATES = [result("d1", 0.91), result("d2", 0.83), result("d3", 0.77)]
RERANK_SCORES = [0.1, 0.9, 0.5]


def names_of(results):
    return [d.page_content for d, _ in results]


def test_rerank_reorders_by_model_score():
    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder(RERANK_SCORES))
    assert names_of(ranker.rerank("q", CANDIDATES)) == ["d2", "d3", "d1"]


def test_rerank_returns_model_scores_not_retrieval_scores():
    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder(RERANK_SCORES))
    assert [s for _, s in ranker.rerank("q", CANDIDATES)] == [0.9, 0.5, 0.1]


def test_non_numpy_scores_are_accepted():
    """The stub returns a plain list; nothing may call .tolist() on it."""
    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder([3, 1, 2]))
    assert names_of(ranker.rerank("q", CANDIDATES)) == ["d1", "d3", "d2"]


def test_model_is_loaded_once_across_calls():
    loader = CountingLoader(FakeCrossEncoder(RERANK_SCORES))
    ranker = Ranker(model_loader=loader)

    ranker.rerank("q", CANDIDATES)
    ranker.rerank("q", CANDIDATES)
    ranker.rerank("q", CANDIDATES)

    assert loader.calls == 1


def test_batch_size_is_passed_through():
    model = FakeCrossEncoder(RERANK_SCORES)
    Ranker(model_loader=lambda _: model, rerank_batch_size=8).rerank("q", CANDIDATES)
    assert model.last_batch_size == 8


def test_loader_failure_falls_back_to_retrieval_order():
    ranker = Ranker(model_loader=ExplodingLoader())
    out = ranker.rerank("q", CANDIDATES)

    assert out == CANDIDATES  # documents *and* scores unchanged
    assert names_of(out) == ["d1", "d2", "d3"]


def test_predict_failure_falls_back_to_retrieval_order():
    ranker = Ranker(model_loader=lambda _: ExplodingPredictor())
    assert ranker.rerank("q", CANDIDATES) == CANDIDATES


def test_score_count_mismatch_falls_back():
    ranker = Ranker(model_loader=lambda _: WrongLengthPredictor())
    assert ranker.rerank("q", CANDIDATES) == CANDIDATES


def test_failure_logs_a_warning(caplog):
    ranker = Ranker(model_loader=ExplodingLoader())
    with caplog.at_level(logging.WARNING, logger="gaik.software_components.RAG.ranker"):
        ranker.rerank("q", CANDIDATES)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "falling back" in warnings[0].getMessage()


def test_on_error_raise_propagates():
    ranker = Ranker(model_loader=ExplodingLoader())
    with pytest.raises(RuntimeError, match="model download failed"):
        ranker.rerank("q", CANDIDATES, on_error="raise")


def test_empty_candidates_short_circuit_without_loading_the_model():
    loader = ExplodingLoader()
    ranker = Ranker(model_loader=loader)

    assert ranker.rerank("q", []) == []
    assert loader.calls == 0


def test_empty_query_short_circuits_without_loading_the_model():
    loader = ExplodingLoader()
    ranker = Ranker(model_loader=loader)

    assert ranker.rerank("", CANDIDATES) == CANDIDATES
    assert loader.calls == 0


def test_top_k_truncates_after_reranking():
    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder(RERANK_SCORES))
    assert names_of(ranker.rerank("q", CANDIDATES, top_k=2)) == ["d2", "d3"]


def test_top_k_applies_to_the_fallback_path_too():
    ranker = Ranker(model_loader=ExplodingLoader())
    assert names_of(ranker.rerank("q", CANDIDATES, top_k=2)) == ["d1", "d2"]


def test_rerank_does_not_mutate_input_documents():
    source_doc = CANDIDATES[0][0]
    before = dict(source_doc.metadata)

    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder(RERANK_SCORES))
    ranker.rerank("q", CANDIDATES)

    assert source_doc.metadata == before


def test_missing_sentence_transformers_raises_rather_than_falling_back(monkeypatch):
    """A missing dependency is a misconfiguration, not a runtime fault."""
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    ranker = Ranker()  # no model_loader -> real import path
    with pytest.raises(ImportError, match=r"gaik\[ranker-rerank\]"):
        ranker.rerank("q", CANDIDATES)


def test_rank_rerank_strategy_delegates():
    ranker = Ranker(model_loader=lambda _: FakeCrossEncoder(RERANK_SCORES))
    out = ranker.rank(CANDIDATES, strategy="rerank", query="q")
    assert names_of(out) == ["d2", "d3", "d1"]
