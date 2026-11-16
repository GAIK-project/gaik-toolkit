"""PgVectorStore search: websearch operators survive lemmatization, weighted
hybrid returns keyword-only matches, and the documented recipes pass a
threshold the semantic arm can use.

Offline tests use fakes. The live test runs only when ``GAIK_TEST_PG_URL``
points at a pgvector database (see test_pg_vector_store_sql.py).
"""

from __future__ import annotations

import contextlib
import os
import random
import re
import uuid
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

# The READMEs live in the repository, not in an installed wheel (CI installs gaik
# from a wheel), so read them from the source tree next to these tests.
RAG_DIR = Path(__file__).resolve().parents[1] / "src" / "gaik" / "software_components" / "RAG"

_LEMMAS = {"kissa": ["kissa"], "koiran": ["koira"], "mustan": ["musta"], "ja": []}
_LEMMAS["kerrostaloissa"] = ["kerros", "talo"]


class _Processor:
    def lemmatize(self, text):
        # Like the real processor: punctuation-only tokens give no lemma.
        words = [w.strip("()") for w in text.split() if any(c.isalnum() for c in w)]
        return [lemma for word in words for lemma in _LEMMAS.get(word.lower(), [word])]

    def expand_query(self, text):
        return " ".join(self.lemmatize(text))


def _store(mode):
    return PgVectorStore(
        "postgresql://unused", embedding_dim=3, tsquery_mode=mode, text_processor=_Processor()
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("kissa -koiran", "kissa -koira"),
        ('"mustan kissa"', '"musta kissa"'),
        ("kissa or koiran", "kissa or koira"),
        ("kissa -kerrostaloissa", 'kissa -"kerros talo"'),
        ("kissa ja koiran", "kissa koira"),
        ("ja or kissa", "kissa"),
        ("kissa or ja or koiran", "kissa or koira"),
        ('("mustan kissa")', '"musta kissa"'),
    ],
)
def test_websearch_mode_keeps_its_operators_after_lemmatizing(query, expected):
    assert _store("websearch")._lemmatize_query(query) == expected


def test_or_mode_still_joins_the_lemmas():
    assert _store("or")._lemmatize_query("kissa ja koiran") == "kissa koira"


class _ExpandOnly:
    """The documented minimum: to_tsvector_text and expand_query, no lemmatize."""

    def to_tsvector_text(self, text):
        return text

    def expand_query(self, text):
        return _Processor().expand_query(text)


@pytest.mark.parametrize(
    ("query", "expected"),
    [("kissa -koiran", "kissa -koira"), ('"mustan kissa"', '"musta kissa"'), ("kissa", "kissa")],
)
def test_websearch_mode_works_with_a_processor_that_only_expands(query, expected):
    store = PgVectorStore(
        "postgresql://unused",
        embedding_dim=3,
        tsquery_mode="websearch",
        text_processor=_ExpandOnly(),
    )
    assert store._lemmatize_query(query) == expected


class _Recorder:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        return self


def test_weighted_hybrid_joins_both_arms():
    store = PgVectorStore("postgresql://unused", embedding_dim=3)
    recorder = _Recorder()
    store._create_hybrid_weighted_function(recorder)

    body = recorder.sql[0]
    assert "FULL OUTER JOIN keyword k" in body
    assert "LEFT JOIN keyword_normalized" not in body


def _recipe_calls(text):
    return re.findall(r"search_semantic\([^)]*\)", text)


@pytest.mark.parametrize(
    "path", ["ranker/README.md", "ranker/ranker.py", "pg_vector_store/README.md"]
)
def test_documented_semantic_searches_pass_a_threshold(path):
    calls = _recipe_calls((RAG_DIR / path).read_text(encoding="utf-8"))
    examples = [c for c in calls if "top_k=" in c]
    assert examples
    assert all("threshold=" in c for c in examples)


def test_the_ranker_recipe_lets_the_index_return_every_row_it_asks_for():
    """An HNSW index scan returns at most hnsw.ef_search rows (40 by default),
    so the recipe's top_k=50 came back as 40 rows on an indexed table."""
    text = (RAG_DIR / "ranker/README.md").read_text(encoding="utf-8")
    recipe = text.split("## Quick Start", 1)[1].split("```python", 1)[1].split("```", 1)[0]
    asked = [int(n) for c in _recipe_calls(recipe) for n in re.findall(r"top_k=(\d+)", c)]
    ef_search = re.search(r"PgVectorStore\([^)]*hnsw_ef_search=(\d+)", recipe)

    assert asked
    assert ef_search, "the recipe's PgVectorStore(...) sets no hnsw_ef_search"
    assert int(ef_search.group(1)) >= max(asked)


# ── Against a real database ──────────────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
live = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")


@contextlib.contextmanager
def _live_store(**kwargs):
    table = f"gaik_test_weighted_{uuid.uuid4().hex[:8]}"
    options = {"embedding_dim": 3, "fts_language": "simple", "tsquery_mode": "or", **kwargs}
    store = PgVectorStore(PG_URL, table_name=table, **options)
    try:
        store.setup()
        yield store
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


@live
def test_weighted_hybrid_returns_a_match_only_the_keyword_arm_found():
    with _live_store() as store:
        texts = ["kela asumistuki", "vero alv", "junat helsinki", "sote uudistus", "kissa"]
        vectors = [[1, 0, 0], [0.9, 0.1, 0], [0.8, 0.2, 0], [0.7, 0.3, 0], [0, 0, 1]]
        store.add([Document(page_content=t) for t in texts], vectors)

        hits = store.search_hybrid_weighted(
            [1, 0, 0], "kissa", top_k=1, semantic_weight=0.0, keyword_weight=1.0
        )

        assert [doc.page_content for doc, _ in hits] == ["kissa"]


@live
def test_weighted_hybrid_keeps_the_keyword_score_of_a_row_below_the_keyword_cut():
    """The keyword arm keeps its best 3 * top_k rows. A row the semantic arm
    found that matches the keywords less well than those still has a keyword
    score, as it had before the keyword arm got its cut."""
    with _live_store() as store:
        texts = ["kissa talo auto vero"] + ["kissa kissa kissa"] * 4
        vectors = [[1, 0, 0]] + [[0.1, 0, 1]] * 4
        store.add([Document(page_content=t) for t in texts], vectors)

        hits = store.search_hybrid_weighted([1, 0, 0], "kissa", top_k=1)

        doc, score = hits[0]
        assert doc.page_content == "kissa talo auto vero"
        # One occurrence of the term against the best match's three.
        assert doc.metadata["keyword_score"] == pytest.approx(1 / 3)
        assert score == pytest.approx(0.5 * 1.0 + 0.5 / 3)


@live
@pytest.mark.parametrize(("ef_search", "expected"), [(None, 40), (100, 50)])
def test_an_index_scan_returns_at_most_ef_search_rows(ef_search, expected):
    """What the Ranker recipe's hnsw_ef_search=100 is for: at pgvector's
    default of 40, a top_k=50 search through the HNSW index returns 40 rows."""
    rows = random.Random(0)
    with _live_store(embedding_dim=8, hnsw_ef_search=ef_search) as store:
        vectors = [[rows.gauss(0, 1) for _ in range(8)] for _ in range(120)]
        store.add([Document(page_content=f"rivi {i}") for i in range(120)], vectors)
        # A table this small is scanned, not indexed, unless the planner is told.
        store._get_conn().execute("SET enable_seqscan = off")

        hits = store.search_semantic([1.0] * 8, top_k=50, threshold=-1.0)

        assert len(hits) == expected
