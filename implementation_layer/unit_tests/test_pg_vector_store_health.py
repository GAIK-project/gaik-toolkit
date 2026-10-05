"""PgVectorStore: column type, session settings, similarity in hybrid results, health().

The first group needs no database. The second runs against a real pgvector
database and is skipped unless ``GAIK_TEST_PG_URL`` points at one (see
``test_pg_vector_store_sql.py``).
"""

from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("langchain_core")

import psycopg  # noqa: E402
from gaik.software_components.RAG.pg_vector_store import HealthReport, PgVectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class _Recorder:
    """Stands in for a psycopg connection and remembers every call."""

    closed = False

    def __init__(self, reject: str | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.rollbacks = 0
        self._reject = reject

    def execute(self, sql, params=()):
        if self._reject and self._reject in sql:
            raise RuntimeError("unrecognized configuration parameter")
        self.calls.append((sql, tuple(params)))
        return self

    def fetchall(self):
        return []

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"embedding_dim": 3072}, 'vector_type="halfvec"'),
        ({"embedding_dim": 4001, "vector_type": "halfvec"}, "4,000"),
        ({"vector_type": "bit"}, "Invalid vector_type"),
        ({"hnsw_iterative_scan": "relaxed"}, "Invalid hnsw_iterative_scan"),
    ],
)
def test_a_configuration_pgvector_cannot_index_is_refused_up_front(kwargs, message):
    """A 3,072-dimension ``vector`` column used to fail inside setup() with a
    Postgres error about the HNSW index; the constructor now says what to do."""
    with pytest.raises(ValueError, match=message):
        PgVectorStore("postgresql://unused", **kwargs)


def test_halfvec_reaches_every_statement():
    store = PgVectorStore("postgresql://unused", embedding_dim=3072, vector_type="halfvec")
    store._conn = recorder = _Recorder()
    vector = [0.0] * 3072

    store.search_semantic(vector)
    store.search_hybrid(vector, "kissa")
    store.search_hybrid_weighted(vector, "kissa")

    for sql, params in recorder.calls:
        assert "halfvec(3072)" in sql and "::vector(" not in sql
        assert sql.count("%s") == len(params)


def test_session_settings_are_applied_and_a_rejected_one_is_skipped():
    store = PgVectorStore(
        "postgresql://unused", hnsw_ef_search=100, hnsw_iterative_scan="relaxed_order"
    )
    accepted = _Recorder()
    store._apply_session_settings(accepted)
    assert [sql for sql, _ in accepted.calls] == [
        "SET hnsw.ef_search = 100",
        "SET hnsw.iterative_scan = relaxed_order",
    ]

    # pgvector before 0.8 has no iterative scan. The failed SET aborts the
    # transaction, so without a rollback every later statement would fail too.
    old_pgvector = _Recorder(reject="iterative_scan")
    store._apply_session_settings(old_pgvector)
    assert [sql for sql, _ in old_pgvector.calls] == ["SET hnsw.ef_search = 100"]
    assert old_pgvector.rollbacks == 1


def test_health_report_reads_as_a_list():
    assert str(HealthReport(True)) == "ok"
    assert str(HealthReport(False, ["one", "two"])) == "- one\n- two"


# ── Against a real database ──────────────────────────────────────────

PG_URL = os.environ.get("GAIK_TEST_PG_URL")
live = pytest.mark.skipif(not PG_URL, reason="set GAIK_TEST_PG_URL to a pgvector database")

TEXTS = ["kela asumistuki hakeminen", "vero alv laskelma", "kissa koira", "junat helsinki"]
VECTORS = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]]


def _drop(table: str) -> None:
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        signatures = conn.execute(
            "SELECT oid::regprocedure::text FROM pg_proc WHERE proname LIKE %s",
            (f"%\\_{table}",),
        ).fetchall()
        for (signature,) in signatures:
            conn.execute(f"DROP FUNCTION IF EXISTS {signature}")


@pytest.fixture
def table():
    name = f"gaik_test_health_{uuid.uuid4().hex[:8]}"
    yield name
    _drop(name)


def _filled(table: str, **kwargs) -> PgVectorStore:
    store = PgVectorStore(PG_URL, table_name=table, embedding_dim=3, **kwargs)
    store.setup()
    store.add([Document(page_content=text) for text in TEXTS], VECTORS)
    return store


@live
def test_a_healthy_store_reports_ok(table):
    with _filled(table, fts_language="finnish", hnsw_ef_search=100) as store:
        report = store.health()

    assert report.ok, str(report)
    assert report.details["rows"] == len(TEXTS)
    assert report.details["embedding_type"] == "vector(3)"
    assert report.details["fts_language"] == "finnish"
    assert report.details["hnsw_ef_search"] == "100"


@live
def test_halfvec_stores_and_searches_above_two_thousand_dimensions(table):
    def unit(i: int) -> list[float]:
        return [1.0 if j == i else 0.0 for j in range(3072)]

    with PgVectorStore(
        PG_URL, table_name=table, embedding_dim=3072, vector_type="halfvec"
    ) as store:
        store.setup()
        store.setup()  # idempotent with the new column type too
        store.add([Document(page_content=text) for text in TEXTS], [unit(i) for i in range(4)])

        assert store.search_semantic(unit(2), top_k=1, threshold=0.0)[0][0].page_content == TEXTS[2]
        assert store.search_hybrid(unit(0), "kissa", top_k=4)
        assert store.search_hybrid_weighted(unit(0), "kissa", top_k=4)
        report = store.health()

    assert report.ok, str(report)
    assert report.details["vector_index"] == ["hnsw halfvec_cosine_ops"]


@live
def test_hybrid_results_carry_the_cosine_similarity(table):
    """RRF scores are built from rank positions, so they cannot tell a real
    match from the nearest neighbour of gibberish. The similarity can, and it
    is there for rows only the keyword arm found too."""
    with _filled(table) as store:
        hits = store.search_hybrid([1, 0, 0], "kissa", top_k=4)

    similarity = {doc.page_content: doc.metadata["semantic_similarity"] for doc, _ in hits}
    assert similarity["kela asumistuki hakeminen"] == pytest.approx(1.0)
    assert similarity["kissa koira"] == pytest.approx(0.0)
    keyword_only = [doc for doc, _ in hits if doc.page_content == "kissa koira"][0]
    assert "keyword_rank" in keyword_only.metadata
    assert [score for _, score in hits] == sorted((s for _, s in hits), reverse=True)


@live
def test_health_names_a_store_configured_differently_from_its_table(table):
    _filled(table, fts_language="finnish").close()

    with PgVectorStore(PG_URL, table_name=table, embedding_dim=8, fts_language="english") as other:
        report = other.health()

    assert not report.ok
    text = str(report)
    assert "the embedding column is vector(3)" in text
    assert "built with the 'finnish' configuration" in text


@live
def test_health_sees_a_keyword_column_nothing_fills(table):
    """The failure that ran unnoticed for months elsewhere: text_search declared
    as a plain column, every row NULL, and hybrid search silently vector-only."""
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, title TEXT, content TEXT NOT NULL, "
            "metadata JSONB DEFAULT '{}', embedding vector(3), text_search tsvector)"
        )
        conn.execute(f"INSERT INTO {table} (content, embedding) VALUES ('kissa', '[1,0,0]')")

    with PgVectorStore(PG_URL, table_name=table, embedding_dim=3) as store:
        report = store.health()

    text = str(report)
    assert "text_search is a plain column" in text
    assert "1 of 1 rows have an empty text_search" in text
    assert "there is no index on embedding" in text


@live
def test_health_of_a_missing_table_says_so():
    with PgVectorStore(PG_URL, table_name="gaik_test_never_created", embedding_dim=3) as store:
        report = store.health()
    assert not report.ok and "does not exist" in str(report)


@live
def test_lemmas_built_differently_are_found_and_rebuilt(table):
    pytest.importorskip("pyvoikko")
    from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

    documents = [
        Document(page_content="kerrostalon kissoilla on reviiri"),
        Document(page_content="arvonlisäveron ilmoitus annetaan kuukausittain"),
    ]
    whole = FinnishTextProcessor(backend="pyvoikko", decompound=False)
    split = FinnishTextProcessor(backend="pyvoikko", decompound=True)

    with PgVectorStore(PG_URL, table_name=table, embedding_dim=3, text_processor=whole) as store:
        store.setup()
        store.add(documents, VECTORS[:2])
        assert store.health().ok
        assert not store.search_keyword("talo")

    # The same table read through a processor that splits compounds: the index
    # holds "kerrostalo", the query asks for "kerros" and "talo".
    with PgVectorStore(PG_URL, table_name=table, embedding_dim=3, text_processor=split) as store:
        report = store.health()
        assert "lemmatize differently" in str(report)
        assert report.details["lemma_sample"] == {"rows": 2, "differing": 2}

        assert store.relemmatize() == 2
        assert store.health().ok
        assert store.search_keyword("talo")

    # And through no processor at all.
    with PgVectorStore(PG_URL, table_name=table, embedding_dim=3) as store:
        assert "has no text_processor" in str(store.health())
        with pytest.raises(ValueError, match="needs a text_processor"):
            store.relemmatize()


@live
def test_relemmatize_refuses_a_table_built_without_lemmas(table):
    pytest.importorskip("pyvoikko")
    from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

    _filled(table).close()
    processor = FinnishTextProcessor(backend="pyvoikko", decompound=False)
    with PgVectorStore(
        PG_URL, table_name=table, embedding_dim=3, text_processor=processor
    ) as store:
        assert "created without one" in str(store.health())
        with pytest.raises(ValueError, match="no content_lemmatized column"):
            store.relemmatize()
