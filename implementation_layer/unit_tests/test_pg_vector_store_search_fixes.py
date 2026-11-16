"""PgVectorStore search: websearch operators survive lemmatization, weighted
hybrid returns keyword-only matches, and the documented recipes pass a
threshold the semantic arm can use.

Offline tests use fakes. The live test runs only when ``GAIK_TEST_PG_URL``
points at a pgvector database (see test_pg_vector_store_sql.py).
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG import ranker as ranker_module  # noqa: E402
from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

RAG_DIR = Path(ranker_module.__file__).resolve().parent.parent

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
    assert "FULL OUTER JOIN keyword_normalized" in body
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


# ── Against a real database ──────────────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")


@pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")
def test_weighted_hybrid_returns_a_match_only_the_keyword_arm_found():
    table = f"gaik_test_weighted_{uuid.uuid4().hex[:8]}"
    store = PgVectorStore(
        PG_URL, table_name=table, embedding_dim=3, fts_language="simple", tsquery_mode="or"
    )
    try:
        store.setup()
        texts = ["kela asumistuki", "vero alv", "junat helsinki", "sote uudistus", "kissa"]
        vectors = [[1, 0, 0], [0.9, 0.1, 0], [0.8, 0.2, 0], [0.7, 0.3, 0], [0, 0, 1]]
        store.add([Document(page_content=t) for t in texts], vectors)

        hits = store.search_hybrid_weighted(
            [1, 0, 0], "kissa", top_k=1, semantic_weight=0.0, keyword_weight=1.0
        )

        assert [doc.page_content for doc, _ in hits] == ["kissa"]
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
