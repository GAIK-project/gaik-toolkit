"""PgVectorStore's SQL: what the Python methods send, and what the SQL does.

The first group needs no database: a fake connection records each statement and
its parameters. The second runs against a real pgvector database and is skipped
unless ``GAIK_TEST_PG_URL`` points at one, e.g. ``docker run -e
POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg17`` and
``GAIK_TEST_PG_URL=postgresql://postgres:postgres@localhost:5432/postgres``.
"""

from __future__ import annotations

import os
import re
import uuid

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.pg_vector_store import PgVectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class _Recorder:
    """Stands in for a psycopg connection and remembers every call."""

    closed = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return self

    def fetchall(self):
        return []

    def commit(self):
        pass


def _store(tsquery_mode: str) -> tuple[PgVectorStore, _Recorder]:
    store = PgVectorStore("postgresql://unused", embedding_dim=3, tsquery_mode=tsquery_mode)
    recorder = _Recorder()
    store._conn = recorder
    return store, recorder


@pytest.mark.parametrize("method", ["search_hybrid", "search_hybrid_weighted"])
def test_hybrid_search_passes_the_tsquery_mode(method):
    """The SQL functions take the mode as their last argument; the Python
    wrappers used to leave it out, so hybrid search always parsed in websearch
    mode and ANDed every term of a sentence query whatever the store was built
    with."""
    store, recorder = _store("or")
    getattr(store, method)([0.1, 0.2, 0.3], "kissa ja tampere")

    sql, params = recorder.calls[-1]
    assert params[-1] == "or"
    assert sql.count("%s") == len(params)


def test_weighted_function_qualifies_the_id_column():
    """RETURNS TABLE makes `id` a PL/pgSQL variable, so a bare `id` in the
    function body made every search_hybrid_weighted() call fail as ambiguous."""
    store, recorder = _store("websearch")
    store._create_hybrid_weighted_function(recorder)

    body = next(sql for sql, _ in recorder.calls if "keyword_normalized AS" in sql)
    normalized = body[body.index("keyword_normalized AS") :]
    assert re.search(r"SELECT\s+kw\.id,", normalized)
    assert not re.search(r"SELECT\s+id,", normalized)


# ── Against a real database ──────────────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
live = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")

TEXTS = [
    "kela asumistuki hakeminen",
    "vero alv laskelma",
    "kissa koira",
    "junat helsinki tampere",
    "sote-uudistus eteni",
]
VECTORS = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [0, 1, 1]]


@pytest.fixture(scope="module")
def stores():
    made = {}
    for mode in ("websearch", "or", "prefix"):
        table = f"gaik_test_{mode}_{uuid.uuid4().hex[:8]}"
        store = PgVectorStore(
            PG_URL, table_name=table, embedding_dim=3, fts_language="simple", tsquery_mode=mode
        )
        store.setup()
        store.add([Document(page_content=t) for t in TEXTS], VECTORS)
        made[mode] = store
    yield made
    for store in made.values():
        conn = store._get_conn()
        conn.execute(f"DROP TABLE IF EXISTS {store.table_name} CASCADE")
        # By full signature: the hybrid functions have two overloads each.
        signatures = conn.execute(
            "SELECT oid::regprocedure::text AS sig FROM pg_proc WHERE proname LIKE %s",
            (f"%\\_{store.table_name}",),
        ).fetchall()
        for row in signatures:
            conn.execute(f"DROP FUNCTION IF EXISTS {row['sig']}")
        conn.commit()
        store.close()


def _first_words(results) -> list[str]:
    return sorted(doc.page_content.split()[0] for doc, _ in results)


@live
@pytest.mark.parametrize(
    ("mode", "query", "expected"),
    [
        # websearch reads '-' as NOT, also in a spaced dash; OR-ing '!alv' with the
        # rest used to match every row without 'alv'.
        ("or", "vero -alv", ["vero"]),
        ("or", "kela - asumistuki", ["kela"]),
        ("or", "-crab kissa", ["kissa"]),
        ("prefix", "kiss -koir", ["kissa"]),
        ("or", "sote-uudistus", ["sote-uudistus"]),  # a dash inside a word stays
        ("or", "kissa ja tampere", ["junat", "kissa"]),
        ("websearch", "kissa ja tampere", []),  # Postgres' own AND semantics
        ("websearch", "kissa -koira", []),
    ],
)
def test_keyword_search(stores, mode, query, expected):
    assert _first_words(stores[mode].search_keyword(query)) == expected


@live
def test_hybrid_keyword_arm_follows_the_mode(stores):
    query = "kissa ja tampere"
    or_hits = stores["or"].search_hybrid([1, 0, 0], query, top_k=10)
    websearch_hits = stores["websearch"].search_hybrid([1, 0, 0], query, top_k=10)

    keyword_found = [(d, s) for d, s in or_hits if "keyword_rank" in d.metadata]
    assert _first_words(keyword_found) == ["junat", "kissa"]
    assert not [d for d, _ in websearch_hits if "keyword_rank" in d.metadata]


@live
@pytest.mark.parametrize("fn", ["hybrid_search_fts", "hybrid_search_weighted"])
def test_an_older_gaik_sharing_the_database_is_never_ambiguous(stores, fn):
    """gaik before the tsquery_mode argument calls, and its setup() re-creates,
    the signature without it. A defaulted trailing argument made that call
    match two functions ("is not unique"): a rollback, or a second app on an
    older release, took hybrid search down."""
    store = stores["or"]
    conn = store._get_conn()
    name = f"{fn}_{store.table_name}"
    defaults = conn.execute(
        "SELECT pronargs, pronargdefaults FROM pg_proc WHERE proname = %s", (name,)
    ).fetchall()
    assert sorted((r["pronargs"], r["pronargdefaults"]) for r in defaults) == (
        [(8, 6), (9, 0)] if fn == "hybrid_search_fts" else [(7, 5), (8, 0)]
    )

    # What an older release sends: every legacy argument, positionally.
    legacy = (
        "%s::vector(3), %s, 10, 60, 0.5, 0.5, 'simple'::regconfig, NULL::jsonb"
        if fn == "hybrid_search_fts"
        else "%s::vector(3), %s, 10, 0.5, 0.5, 'simple'::regconfig, NULL::jsonb"
    )
    rows = conn.execute(f"SELECT * FROM {name}({legacy})", ("[1,0,0]", "kissa")).fetchall()
    conn.commit()
    assert rows


@live
def test_weighted_hybrid_runs_and_scores_keywords(stores):
    hits = stores["or"].search_hybrid_weighted([1, 0, 0], "kissa ja tampere", top_k=10)
    keyword_scored = [(d, s) for d, s in hits if d.metadata.get("keyword_score", 0) > 0]
    assert _first_words(keyword_scored) == ["junat", "kissa"]
