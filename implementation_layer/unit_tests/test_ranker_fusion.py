"""Unit tests for Ranker reciprocal rank fusion.

Pure arithmetic and list manipulation -- no database, no embedding API, no
model download.
"""

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.ranker import (  # noqa: E402
    Ranker,
    reciprocal_rank_fusion,
)
from langchain_core.documents import Document  # noqa: E402

# RRF scores below are hand-computed with k=60 and asserted exactly, so that a
# refactor of the fusion loop cannot quietly change the maths.
K = 60


def doc(name: str, *, doc_id=None, **metadata) -> Document:
    if doc_id is not None:
        metadata["id"] = doc_id
    return Document(page_content=name, metadata=metadata)


D1, D2, D3, D4 = doc("d1"), doc("d2"), doc("d3"), doc("d4")

# Two arms that overlap partially: d1 and d3 appear in both, d2 and d4 in one.
SEMANTIC = [(D1, 0.91), (D2, 0.83), (D3, 0.77)]
KEYWORD = [(D3, 4.2), (D1, 3.1), (D4, 2.8)]


def names_of(results):
    return [d.page_content for d, _ in results]


def scores_of(results):
    return [score for _, score in results]


def test_rrf_scores_match_hand_computed_values():
    fused = reciprocal_rank_fusion([SEMANTIC, KEYWORD], k=K)
    by_name = {d.page_content: score for d, score in fused}

    assert by_name["d1"] == pytest.approx(1 / 61 + 1 / 62)  # 0.03252247
    assert by_name["d3"] == pytest.approx(1 / 63 + 1 / 61)  # 0.03226646
    assert by_name["d2"] == pytest.approx(1 / 62)  # 0.01612903
    assert by_name["d4"] == pytest.approx(1 / 63)  # 0.01587302


def test_rrf_orders_by_fused_score():
    fused = reciprocal_rank_fusion([SEMANTIC, KEYWORD], k=K)
    assert names_of(fused) == ["d1", "d3", "d2", "d4"]


def test_weighting_changes_the_order():
    """Weights chosen so that two independent swaps happen.

    (0.7, 0.3) leaves the unweighted order intact and would prove nothing;
    (0.2, 0.8) flips d1<->d3 *and* lifts d4 above d2.
    """
    fused = reciprocal_rank_fusion([SEMANTIC, KEYWORD], weights=(0.2, 0.8), k=K)
    assert names_of(fused) == ["d3", "d1", "d4", "d2"]

    by_name = {d.page_content: score for d, score in fused}
    assert by_name["d3"] == pytest.approx(0.2 / 63 + 0.8 / 61)
    assert by_name["d4"] == pytest.approx(0.8 / 63)


def test_three_way_fusion_lets_a_third_signal_promote_a_document():
    """A non-search signal (recency) is just another arm."""
    recency = [(D4, 1.0), (D2, 0.5)]

    without = reciprocal_rank_fusion([SEMANTIC, KEYWORD], k=K)
    with_recency = reciprocal_rank_fusion([SEMANTIC, KEYWORD, recency], k=K)

    assert names_of(without) == ["d1", "d3", "d2", "d4"]
    # d4 was last; the recency arm ranks it first and lifts it above d2.
    assert names_of(with_recency) == ["d1", "d3", "d4", "d2"]


def test_dedups_on_metadata_id_even_when_content_differs():
    """PgVectorStore surfaces the row id; the same row must fuse as one entry."""
    from_semantic = doc("chunk text", doc_id=7)
    from_keyword = doc("chunk text with a highlight marker", doc_id=7)

    fused = reciprocal_rank_fusion([[(from_semantic, 0.9)], [(from_keyword, 3.0)]], k=K)

    assert len(fused) == 1
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 61)


def test_dedups_on_content_when_no_id_is_present():
    a = Document(page_content="same text", metadata={"source": "a"})
    b = Document(page_content="same text", metadata={"source": "b"})

    fused = reciprocal_rank_fusion([[(a, 0.9)], [(b, 3.0)]], k=K)

    assert len(fused) == 1
    # First arm wins the Document instance.
    assert fused[0][0].metadata["source"] == "a"


def test_tagged_key_prevents_id_content_collision():
    """A document with id 'x' must not fuse with one whose content is 'x'."""
    with_id = doc("some body text", doc_id="x")
    content_is_x = Document(page_content="x", metadata={})

    fused = reciprocal_rank_fusion([[(with_id, 0.9)], [(content_is_x, 3.0)]], k=K)

    assert len(fused) == 2


def test_custom_key_callable():
    a = Document(page_content="alpha", metadata={"uid": "u1"})
    b = Document(page_content="beta", metadata={"uid": "u1"})

    fused = reciprocal_rank_fusion([[(a, 0.9)], [(b, 3.0)]], k=K, key=lambda d: d.metadata["uid"])

    assert len(fused) == 1


def test_empty_inputs_return_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []
    assert reciprocal_rank_fusion([[], []]) == []
    assert Ranker().fuse() == []
    assert Ranker().fuse([], []) == []


def test_single_list_preserves_its_order():
    fused = reciprocal_rank_fusion([SEMANTIC], k=K)
    assert names_of(fused) == ["d1", "d2", "d3"]


def test_weights_length_mismatch_raises():
    with pytest.raises(ValueError, match="weights has 3 entries but 2 result lists"):
        reciprocal_rank_fusion([SEMANTIC, KEYWORD], weights=(1.0, 1.0, 1.0))


def test_names_length_mismatch_raises():
    with pytest.raises(ValueError, match="names has 1 entries but 2 result lists"):
        reciprocal_rank_fusion([SEMANTIC, KEYWORD], names=("semantic",))


def test_top_k_truncates_after_fusion():
    fused = reciprocal_rank_fusion([SEMANTIC, KEYWORD], k=K, top_k=2)
    assert names_of(fused) == ["d1", "d3"]


def test_expose_ranks_writes_per_arm_metadata():
    fused = reciprocal_rank_fusion(
        [SEMANTIC, KEYWORD], k=K, names=("semantic", "keyword"), expose_ranks=True
    )
    by_name = {d.page_content: d.metadata for d, _ in fused}

    assert by_name["d1"]["rank_semantic"] == 1
    assert by_name["d1"]["rank_keyword"] == 2
    assert by_name["d1"]["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)

    # d2 was never returned by the keyword arm: the key is absent, not None, so
    # `"rank_keyword" in meta` cleanly answers "did this arm find it at all".
    assert by_name["d2"]["rank_semantic"] == 2
    assert "rank_keyword" not in by_name["d2"]


def test_expose_ranks_does_not_mutate_input_documents():
    reciprocal_rank_fusion(
        [SEMANTIC, KEYWORD], k=K, names=("semantic", "keyword"), expose_ranks=True
    )
    assert D1.metadata == {}
    assert "rank_semantic" not in D1.metadata


def test_ranker_fuse_uses_instance_defaults():
    ranker = Ranker(rrf_k=K, top_k=2, expose_ranks=True)
    fused = ranker.fuse(SEMANTIC, KEYWORD, names=("semantic", "keyword"))

    assert names_of(fused) == ["d1", "d3"]
    assert fused[0][0].metadata["rank_semantic"] == 1


def test_rrf_k_flattens_rank_differences():
    """Larger k compresses the gap between adjacent ranks."""
    small_k = reciprocal_rank_fusion([SEMANTIC], k=1)
    large_k = reciprocal_rank_fusion([SEMANTIC], k=1000)

    small_gap = scores_of(small_k)[0] - scores_of(small_k)[1]
    large_gap = scores_of(large_k)[0] - scores_of(large_k)[1]
    assert small_gap > large_gap


def test_duplicate_within_one_list_contributes_once():
    """A malformed arm that repeats a document must not double-count it."""
    dupe = [(D1, 0.9), (D2, 0.8), (D1, 0.7)]

    fused = reciprocal_rank_fusion([dupe], k=K)
    by_name = {d.page_content: score for d, score in fused}

    assert len(fused) == 2
    assert by_name["d1"] == pytest.approx(1 / 61)  # best rank only, counted once


def test_weights_are_validated_even_when_every_list_is_empty():
    with pytest.raises(ValueError, match="weights has 1 entries but 2 result lists"):
        reciprocal_rank_fusion([[], []], weights=(1.0,))
