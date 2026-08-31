"""Unit tests for PgVectorStore row -> (Document, score) conversion.

``_rows_to_results`` is a staticmethod, so the whole conversion contract is
testable with hand-built row dicts and no database.
"""

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402

convert = PgVectorStore._rows_to_results


def row(**overrides):
    base = {
        "id": 1,
        "title": None,
        "content": "chunk text",
        "metadata": {},
        "similarity": 0.87,
    }
    base.update(overrides)
    return base


def test_id_is_surfaced_into_metadata():
    """Without a stable id, Ranker cannot match the same row across two lists."""
    results = convert([row(id=42)], score_key="similarity")
    doc, score = results[0]

    assert doc.metadata["id"] == 42
    assert score == pytest.approx(0.87)


def test_title_column_still_wins_over_metadata():
    results = convert(
        [row(title="Column Title", metadata={"title": "JSONB Title"})],
        score_key="similarity",
    )
    assert results[0][0].metadata["title"] == "Column Title"


def test_jsonb_string_metadata_is_parsed():
    results = convert([row(metadata='{"source": "manual.pdf"}')], score_key="similarity")
    assert results[0][0].metadata["source"] == "manual.pdf"


def test_null_metadata_becomes_empty_dict():
    results = convert([row(metadata=None, id=None, title=None)], score_key="similarity")
    assert results[0][0].metadata == {}


def test_row_metadata_dict_is_not_aliased():
    """The Document must not share psycopg's row dict."""
    source_metadata = {"source": "a.pdf"}
    results = convert([row(metadata=source_metadata, id=7)], score_key="similarity")

    assert results[0][0].metadata["id"] == 7
    assert "id" not in source_metadata  # the caller's dict is untouched


def test_hybrid_extra_keys_surface_per_arm_ranks():
    rows = [
        {
            "id": 3,
            "title": None,
            "content": "found by both arms",
            "metadata": {},
            "rrf_score": 0.0325,
            "semantic_rank": 1,
            "keyword_rank": 2,
        }
    ]
    doc, _ = convert(rows, score_key="rrf_score", extra_keys=("semantic_rank", "keyword_rank"))[0]

    assert doc.metadata["semantic_rank"] == 1
    assert doc.metadata["keyword_rank"] == 2


def test_null_valued_extra_keys_are_omitted_not_none():
    """A keyword-only hit has no semantic rank; the key must be absent."""
    rows = [
        {
            "id": 4,
            "title": None,
            "content": "keyword-only hit",
            "metadata": {},
            "rrf_score": 0.0158,
            "semantic_rank": None,
            "keyword_rank": 1,
        }
    ]
    doc, _ = convert(rows, score_key="rrf_score", extra_keys=("semantic_rank", "keyword_rank"))[0]

    assert "semantic_rank" not in doc.metadata
    assert doc.metadata["keyword_rank"] == 1


def test_weighted_hybrid_extra_keys_surface_per_arm_scores():
    rows = [
        {
            "id": 5,
            "title": None,
            "content": "text",
            "metadata": {},
            "combined_score": 0.71,
            "semantic_score": 0.82,
            "keyword_score": 0.60,
        }
    ]
    doc, score = convert(
        rows, score_key="combined_score", extra_keys=("semantic_score", "keyword_score")
    )[0]

    assert score == pytest.approx(0.71)
    assert doc.metadata["semantic_score"] == pytest.approx(0.82)
    assert doc.metadata["keyword_score"] == pytest.approx(0.60)


def test_existing_content_and_score_behaviour_is_unchanged():
    results = convert(
        [row(content="body", metadata={"source": "a.pdf"}, similarity=0.5)],
        score_key="similarity",
    )
    doc, score = results[0]

    assert doc.page_content == "body"
    assert doc.metadata["source"] == "a.pdf"
    assert isinstance(score, float)


def test_empty_rows_return_empty():
    assert convert([], score_key="similarity") == []


def test_ids_let_ranker_fuse_two_lists_of_the_same_rows():
    """The point of surfacing id: fusion across arms that reformat content."""
    from gaik.software_components.RAG.ranker import Ranker

    semantic = convert([row(id=9, content="original chunk")], score_key="similarity")
    keyword_row = {
        "id": 9,
        "title": None,
        "content": "<b>original</b> chunk",
        "metadata": {},
        "score": 3.0,
    }
    keyword = convert([keyword_row], score_key="score")

    fused = Ranker().fuse(semantic, keyword)
    assert len(fused) == 1
