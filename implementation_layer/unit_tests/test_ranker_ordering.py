"""Unit tests for Ranker.order_by / rank / to_documents.

This is the asc/desc surface: ordering by relevance score or by an arbitrary
metadata field (date, price, priority).
"""

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.ranker import Ranker  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def result(name: str, score: float, **metadata):
    return (Document(page_content=name, metadata=metadata), score)


RESULTS = [
    result("a", 0.9, date="2026-01-05", price=30),
    result("b", 0.5, date="2026-03-01", price=10),
    result("c", 0.7, date="2026-02-10", price=20),
]


def names_of(results):
    return [d.page_content for d, _ in results]


# ----------------------------------------------------------------------
# Ordering by relevance score
# ----------------------------------------------------------------------


def test_order_by_score_desc_is_the_default():
    assert names_of(Ranker().order_by(RESULTS)) == ["a", "c", "b"]


def test_order_by_score_asc():
    assert names_of(Ranker().order_by(RESULTS, direction="asc")) == ["b", "c", "a"]


def test_order_by_score_keeps_scores_untouched():
    ordered = Ranker().order_by(RESULTS, direction="asc")
    assert [s for _, s in ordered] == [0.5, 0.7, 0.9]


# ----------------------------------------------------------------------
# Ordering by a metadata field
# ----------------------------------------------------------------------


def test_order_by_metadata_field_asc():
    assert names_of(Ranker().order_by(RESULTS, field="date", direction="asc")) == [
        "a",
        "c",
        "b",
    ]


def test_order_by_metadata_field_desc():
    assert names_of(Ranker().order_by(RESULTS, field="date", direction="desc")) == [
        "b",
        "c",
        "a",
    ]


def test_order_by_numeric_field():
    assert names_of(Ranker().order_by(RESULTS, field="price", direction="asc")) == [
        "b",
        "c",
        "a",
    ]


def test_order_by_field_does_not_reorder_by_score():
    """Ordering by a field must ignore relevance entirely."""
    ordered = Ranker().order_by(RESULTS, field="price", direction="asc")
    assert [s for _, s in ordered] == [0.5, 0.7, 0.9]


# ----------------------------------------------------------------------
# Missing-field handling
# ----------------------------------------------------------------------

MIXED = [
    result("has", 0.9, date="2026-01-05"),
    result("missing", 0.8),
    result("also-has", 0.7, date="2026-02-10"),
]


def test_missing_field_goes_last_by_default():
    assert names_of(Ranker().order_by(MIXED, field="date", direction="asc")) == [
        "has",
        "also-has",
        "missing",
    ]


def test_missing_field_first():
    ordered = Ranker().order_by(MIXED, field="date", direction="asc", missing="first")
    assert names_of(ordered) == ["missing", "has", "also-has"]


def test_missing_field_drop():
    ordered = Ranker().order_by(MIXED, field="date", direction="asc", missing="drop")
    assert names_of(ordered) == ["has", "also-has"]


def test_all_rows_missing_the_field_preserves_input_order():
    ordered = Ranker().order_by(RESULTS, field="nonexistent")
    assert names_of(ordered) == ["a", "b", "c"]


def test_none_valued_field_counts_as_missing():
    """A None never reaches a `<` comparison."""
    rows = [result("x", 0.9, date=None), result("y", 0.8, date="2026-01-01")]
    ordered = Ranker().order_by(rows, field="date", direction="asc")
    assert names_of(ordered) == ["y", "x"]


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


def test_invalid_direction_raises_and_names_both_valid_values():
    with pytest.raises(ValueError, match="direction must be 'asc' or 'desc'"):
        Ranker().order_by(RESULTS, direction="ascending")


def test_invalid_missing_raises():
    with pytest.raises(ValueError, match="missing must be"):
        Ranker().order_by(RESULTS, field="date", missing="ignore")


def test_non_comparable_field_values_raise_typeerror_naming_the_field():
    rows = [result("x", 0.9, priority=1), result("y", 0.8, priority="high")]
    with pytest.raises(TypeError, match="'priority'"):
        Ranker().order_by(rows, field="priority")


# ----------------------------------------------------------------------
# Stability and truncation
# ----------------------------------------------------------------------


def test_ties_keep_input_order():
    """Asserted explicitly so a future rewrite cannot silently lose stability."""
    tied = [result("first", 0.5), result("second", 0.5), result("third", 0.5)]
    assert names_of(Ranker().order_by(tied)) == ["first", "second", "third"]
    assert names_of(Ranker().order_by(tied, direction="asc")) == [
        "first",
        "second",
        "third",
    ]


def test_top_k_truncates():
    assert names_of(Ranker().order_by(RESULTS, top_k=2)) == ["a", "c"]


def test_instance_top_k_is_the_default():
    assert names_of(Ranker(top_k=1).order_by(RESULTS)) == ["a"]


def test_empty_input_returns_empty():
    assert Ranker().order_by([]) == []
    assert Ranker().order_by([], field="date") == []


# ----------------------------------------------------------------------
# rank() facade
# ----------------------------------------------------------------------


def test_rank_score_strategy():
    assert names_of(Ranker().rank(RESULTS, strategy="score")) == ["a", "c", "b"]


def test_rank_field_strategy():
    ordered = Ranker().rank(RESULTS, strategy="field", field="price", direction="asc")
    assert names_of(ordered) == ["b", "c", "a"]


def test_rank_field_strategy_without_field_raises():
    with pytest.raises(ValueError, match="requires a field name"):
        Ranker().rank(RESULTS, strategy="field")


def test_rank_rerank_strategy_without_query_raises():
    with pytest.raises(ValueError, match="requires a query"):
        Ranker().rank(RESULTS, strategy="rerank")


def test_rank_unknown_strategy_raises():
    with pytest.raises(ValueError, match="strategy must be"):
        Ranker().rank(RESULTS, strategy="magic")


# ----------------------------------------------------------------------
# to_documents
# ----------------------------------------------------------------------


def test_to_documents_attaches_scores():
    docs = Ranker.to_documents(Ranker().order_by(RESULTS))
    assert [d.metadata["relevance_score"] for d in docs] == [0.9, 0.7, 0.5]


def test_to_documents_can_omit_scores():
    docs = Ranker.to_documents(RESULTS, include_scores=False)
    assert all("relevance_score" not in d.metadata for d in docs)


def test_to_documents_custom_score_key():
    docs = Ranker.to_documents(RESULTS, score_key="rrf_score")
    assert docs[0].metadata["rrf_score"] == 0.9


def test_to_documents_does_not_mutate_input_documents():
    """Guards the Retriever defect where scores leaked into the vector store."""
    source_doc = RESULTS[0][0]
    Ranker.to_documents(RESULTS)
    assert "relevance_score" not in source_doc.metadata
