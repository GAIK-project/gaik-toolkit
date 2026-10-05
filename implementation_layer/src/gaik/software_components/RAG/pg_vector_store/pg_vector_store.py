"""PostgreSQL-backed vector store with semantic, keyword, and hybrid search via pgvector."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:
    raise ImportError(
        "PgVectorStore requires 'psycopg[binary]'. "
        "Install extras with 'pip install gaik[pg-vector-store]'"
    ) from exc

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "PgVectorStore requires 'langchain-core'. "
        "Install extras with 'pip install gaik[pg-vector-store]'"
    ) from exc

if TYPE_CHECKING:
    from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

logger = logging.getLogger(__name__)

# How a natural-language query becomes a tsquery. See `gaik_tsquery` in SQL.
_TSQUERY_MODES = frozenset({"websearch", "or", "prefix"})

# pgvector column types and the most dimensions an HNSW index takes for each.
# `halfvec` stores 16-bit floats: half the space, and room for the 3,072
# dimensions of the large embedding models.
_VECTOR_TYPES = {"vector": 2000, "halfvec": 4000}

_ITERATIVE_SCAN_MODES = frozenset({"off", "relaxed_order", "strict_order"})

# One shared SQL helper rather than the same expression inlined at five call
# sites, so the three modes cannot drift apart between the keyword arm and the
# two hybrid functions.
_TSQUERY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION gaik_tsquery(
    search_language regconfig,
    query_text TEXT,
    mode TEXT DEFAULT 'websearch'
)
RETURNS tsquery
LANGUAGE sql IMMUTABLE
AS $$
    SELECT CASE
        -- Postgres' own parser, which conjoins every term. Correct for short
        -- keyword input and wrong for a sentence: a nine-word question only
        -- matches a passage containing all nine stems, so on real prose the
        -- keyword arm contributes nothing at all and does so silently.
        WHEN mode = 'websearch' THEN
            websearch_to_tsquery(search_language, query_text)

        -- The same parse with the AND operators rewritten to OR, which keeps
        -- stemming, stop-word removal and quoted phrases while letting partial
        -- matches through. ts_rank_cd then discriminates: it already scores by
        -- how many distinct terms matched and how close together they are.
        --
        -- A leading '-' is dropped first. websearch reads it as NOT, also in a
        -- spaced dash ('Kela - asumistuki'), and '!x' OR-ed with the rest
        -- matches nearly every row that lacks x. A dash inside a word is kept.
        WHEN mode = 'or' THEN
            NULLIF(
                replace(
                    websearch_to_tsquery(
                        search_language,
                        regexp_replace(query_text, '(^|\\s)-+', '\\1', 'g')
                    )::text,
                    ' & ', ' | '
                ),
                ''
            )::tsquery

        -- Prefix match on each term, OR-ed. Suits agglutinative suffixing on an
        -- UNSTEMMED index. It is a poor fit for a stemmed Finnish index, where
        -- consonant gradation means a lemma is often not a prefix of its own
        -- inflected forms -- 'kolmikantakauppa' does not reach
        -- 'kolmikantakaupassa'. Lemmatize both sides instead.
        WHEN mode = 'prefix' THEN
            NULLIF(
                replace(
                    regexp_replace(
                        websearch_to_tsquery(
                            search_language,
                            regexp_replace(query_text, '(^|\\s)-+', '\\1', 'g')
                        )::text,
                        '''(\\s|$)', ''':*\\1', 'g'
                    ),
                    ' & ', ' | '
                ),
                ''
            )::tsquery

        ELSE websearch_to_tsquery(search_language, query_text)
    END
$$
"""


def _format_vector(embedding: list[float]) -> str:
    """Format a Python list of floats as a pgvector literal string."""
    return "[" + ",".join(str(v) for v in embedding) + "]"


def _build_filter_clause(filters: dict | None) -> tuple[str, list[Any]]:
    """Build a SQL WHERE clause fragment for JSONB metadata containment.

    Returns (clause_str, params) where clause_str is empty when no filters.
    """
    if not filters:
        return "", []
    return "AND metadata @> %s::jsonb", [json.dumps(filters)]


@dataclass(frozen=True)
class HealthReport:
    """What :meth:`PgVectorStore.health` found.

    ``ok`` is ``True`` when ``problems`` is empty. Each problem is one sentence
    naming what is wrong and what it costs. ``details`` holds the raw readings
    (row counts, column types, versions) for logging or a status endpoint.
    """

    ok: bool
    problems: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.ok:
            return "ok"
        return "\n".join(f"- {problem}" for problem in self.problems)


class PgVectorStore:
    """PostgreSQL vector store with semantic, keyword, and hybrid search.

    Uses pgvector for vector similarity, tsvector/tsquery for full-text search,
    and Reciprocal Rank Fusion (RRF) for hybrid search combining both methods.

    Args:
        connection_string: PostgreSQL connection URI
            (e.g. ``postgresql://user:pass@host:5432/dbname``).
        table_name: Name of the documents table to create/use.
        embedding_dim: Dimension of the embedding vectors (must match your model).
        fts_language: PostgreSQL text search configuration
            (``'simple'``, ``'english'``, ``'finnish'``, etc.). When using a
            ``text_processor`` for lemmatization, ``'simple'`` is recommended
            so Postgres treats the lemmas as already-normalized tokens.
        text_processor: Optional ``FinnishTextProcessor``
            (from ``gaik.software_components.RAG.finnish_text_processor``)
            or any object with ``to_tsvector_text(str) -> str`` and
            ``expand_query(str) -> str`` methods). When supplied, ingestion
            lemmatizes content into a separate ``content_lemmatized`` column
            and the ``text_search`` tsvector is generated from those lemmas.
            Queries are lemmatized through the same processor before being
            handed to ``websearch_to_tsquery``. This dramatically improves
            recall on inflected / compound Finnish terms.
        tsquery_mode: How a query becomes a tsquery: ``"or"`` (default),
            ``"websearch"`` or ``"prefix"``. ``"or"`` lets a passage match on
            some of the query's words and leaves the ranking to ``ts_rank_cd``.
            ``"websearch"`` requires every word, which suits short keyword input
            and matches nothing for a full question.
        hnsw_ef_search: pgvector's ``hnsw.ef_search`` for this store's
            connection. ``None`` keeps the database's setting (pgvector's own
            default is 40).
        vector_type: ``"vector"`` (default, up to 2,000 dimensions) or
            ``"halfvec"`` (up to 4,000, half the storage, pgvector 0.7+). It is
            part of the table's schema: a table created with one cannot be
            searched with the other.
        hnsw_iterative_scan: pgvector's ``hnsw.iterative_scan`` for this store's
            connection: ``"relaxed_order"``, ``"strict_order"`` or ``"off"``.
            With a selective ``filters`` argument an HNSW scan otherwise returns
            fewer rows than asked, or none. Needs pgvector 0.8+. ``None`` keeps
            the database's setting.

    Example::

        from gaik.software_components.RAG.pg_vector_store import PgVectorStore
        from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

        # Name the backend and the decompound setting: the index and every
        # query must lemmatize the same way.
        processor = FinnishTextProcessor(backend="pyvoikko", decompound=False)
        with PgVectorStore(
            "postgresql://postgres:postgres@localhost/mydb",
            text_processor=processor,
        ) as store:
            store.setup()
            ids = store.add(documents, embeddings)
            results = store.search_hybrid(query_vec, "kerrostalon kissoilla", top_k=5)
            print(store.health())  # "ok", or what stops either arm from working
    """

    def __init__(
        self,
        connection_string: str,
        *,
        table_name: str = "documents",
        embedding_dim: int = 1536,
        fts_language: str = "simple",
        text_processor: FinnishTextProcessor | None = None,
        tsquery_mode: str = "or",
        hnsw_ef_search: int | None = None,
        vector_type: str = "vector",
        hnsw_iterative_scan: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table_name):
            raise ValueError(
                f"Invalid table_name '{table_name}': "
                "must contain only letters, digits, and underscores"
            )
        if tsquery_mode not in _TSQUERY_MODES:
            raise ValueError(
                f"Invalid tsquery_mode {tsquery_mode!r}: expected one of "
                f"{', '.join(sorted(_TSQUERY_MODES))}"
            )
        if vector_type not in _VECTOR_TYPES:
            raise ValueError(
                f"Invalid vector_type {vector_type!r}: expected one of "
                f"{', '.join(sorted(_VECTOR_TYPES))}"
            )
        if embedding_dim > _VECTOR_TYPES[vector_type]:
            hint = (
                ' Pass vector_type="halfvec", which indexes up to 4,000, or use'
                if vector_type == "vector" and embedding_dim <= _VECTOR_TYPES["halfvec"]
                else " Use"
            )
            raise ValueError(
                f"embedding_dim={embedding_dim} is more than the "
                f"{_VECTOR_TYPES[vector_type]:,} dimensions pgvector's HNSW index takes "
                f"for {vector_type!r}.{hint} an embedding model with a smaller output."
            )
        if hnsw_iterative_scan is not None and hnsw_iterative_scan not in _ITERATIVE_SCAN_MODES:
            raise ValueError(
                f"Invalid hnsw_iterative_scan {hnsw_iterative_scan!r}: expected one of "
                f"{', '.join(sorted(_ITERATIVE_SCAN_MODES))}"
            )
        self.connection_string = connection_string
        self.table_name = table_name
        self.embedding_dim = embedding_dim
        self.fts_language = fts_language
        self.text_processor = text_processor
        self.tsquery_mode = tsquery_mode
        self.hnsw_ef_search = hnsw_ef_search
        self.vector_type = vector_type
        self.hnsw_iterative_scan = hnsw_iterative_scan
        self._conn: psycopg.Connection | None = None

    @property
    def _vec(self) -> str:
        """The embedding column's SQL type, e.g. ``vector(1536)``."""
        return f"{self.vector_type}({self.embedding_dim})"

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> psycopg.Connection:
        """Return (and lazily create) the database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.connection_string, row_factory=dict_row)
            self._apply_session_settings(self._conn)
        return self._conn

    def _apply_session_settings(self, conn: psycopg.Connection) -> None:
        """Apply per-session GUCs: ``hnsw.ef_search`` and ``hnsw.iterative_scan``.

        pgvector defaults ``hnsw.ef_search`` to 40, which trades recall for a
        latency saving most RAG workloads would rather not take: measured on one
        1500-dimension corpus, raising it to 100 moved recall@20 against an exact
        scan from 96.2% to 99.2% for +0.7 ms median.

        A setting the server rejects is logged as a warning and skipped, with the
        transaction rolled back so the connection stays usable. That happens for
        ``hnsw.iterative_scan`` on pgvector before 0.8.
        """
        settings = (
            ("hnsw.ef_search", None if self.hnsw_ef_search is None else int(self.hnsw_ef_search)),
            ("hnsw.iterative_scan", self.hnsw_iterative_scan),
        )
        for name, value in settings:
            if value is None:
                continue
            try:
                conn.execute(f"SET {name} = {value}")
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.warning("Could not set %s = %s: %s", name, value, exc)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> PgVectorStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def setup(self, *, create_extensions: bool = True) -> None:
        """Create extensions, table, indexes, and SQL functions (idempotent).

        Safe to call multiple times -- uses ``IF NOT EXISTS`` and
        ``CREATE OR REPLACE`` throughout.

        Args:
            create_extensions: If ``True`` (default), create the required
                PostgreSQL extensions (vector, pg_trgm, unaccent). Set to
                ``False`` on managed databases where extensions are
                pre-installed and the user lacks superuser privileges.
        """
        conn = self._get_conn()
        table = self.table_name
        vec = self._vec
        lang = self.fts_language

        # 1. Extensions (skip on managed DBs where user lacks CREATE privileges)
        if create_extensions:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

        # 2. Documents table with generated tsvector column.
        # When a text_processor is wired in, an extra `content_lemmatized` column
        # holds the lemmatized text and the tsvector is generated from it; the
        # original content stays in `content` for display / re-embedding.
        if self.text_processor is not None:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    content TEXT NOT NULL,
                    content_lemmatized TEXT,
                    metadata JSONB DEFAULT '{{}}'::JSONB,
                    embedding {vec},
                    text_search tsvector GENERATED ALWAYS AS (
                        to_tsvector(
                            '{lang}',
                            COALESCE(content_lemmatized, content, '')
                        )
                    ) STORED,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        else:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}'::JSONB,
                    embedding {vec},
                    text_search tsvector GENERATED ALWAYS AS (
                        to_tsvector('{lang}', COALESCE(content, ''))
                    ) STORED,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

        # 3. Indexes
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_embedding_hnsw_idx
            ON {table} USING hnsw (embedding {self.vector_type}_cosine_ops)
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_text_search_gin_idx
            ON {table} USING gin (text_search)
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_content_trgm_gin_idx
            ON {table} USING gin (content gin_trgm_ops)
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_metadata_gin_idx
            ON {table} USING gin (metadata)
        """)

        # 4. SQL functions
        conn.execute(_TSQUERY_FUNCTION_SQL)
        # The two hybrid functions gained a trailing `tsquery_mode` argument.
        # Older gaik releases call, and their setup() re-creates, the signature
        # without it, and one database can meet both: a rollback, a rolling
        # update, two apps sharing a table. So the mode-aware function takes no
        # defaults and the old signature stays as a shim that forwards in
        # websearch mode. Were the new argument defaulted, an old call would
        # match both functions and fail as "not unique" -- and gaik 0.7.2 did
        # default it, so drop that version first: `CREATE OR REPLACE` cannot
        # remove a default.
        for name, mode_args in (
            (
                f"hybrid_search_fts_{table}",
                f"{vec}, TEXT, INTEGER, INTEGER, FLOAT, FLOAT, regconfig, JSONB, TEXT",
            ),
            (
                f"hybrid_search_weighted_{table}",
                f"{vec}, TEXT, INTEGER, FLOAT, FLOAT, regconfig, JSONB, TEXT",
            ),
        ):
            conn.execute(f"DROP FUNCTION IF EXISTS {name}({mode_args})")
        self._create_match_function(conn)
        self._create_hybrid_fts_function(conn)
        self._create_hybrid_weighted_function(conn)

        conn.commit()
        logger.info("PgVectorStore setup complete for table '%s'", table)

    def _create_match_function(self, conn: psycopg.Connection) -> None:
        """Create the pure semantic search SQL function."""
        table = self.table_name
        vec = self._vec
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION match_{table}(
                query_embedding {vec},
                match_threshold FLOAT DEFAULT 0.7,
                match_count INTEGER DEFAULT 10,
                filter_metadata JSONB DEFAULT NULL
            )
            RETURNS TABLE (
                id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                similarity FLOAT
            )
            LANGUAGE sql STABLE
            AS $$
                SELECT
                    t.id,
                    t.title,
                    t.content,
                    t.metadata,
                    (1 - (t.embedding <=> query_embedding))::FLOAT AS similarity
                FROM {table} t
                WHERE t.embedding IS NOT NULL
                  AND (1 - (t.embedding <=> query_embedding)) >= match_threshold
                  AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                ORDER BY t.embedding <=> query_embedding
                LIMIT match_count;
            $$
        """)

    def _create_hybrid_fts_function(self, conn: psycopg.Connection) -> None:
        """Create the RRF-based hybrid search SQL function."""
        table = self.table_name
        vec = self._vec
        lang = self.fts_language
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_fts_{table}(
                query_embedding {vec},
                query_text TEXT,
                result_limit INTEGER,
                rrf_k INTEGER,
                sem_weight FLOAT,
                kw_weight FLOAT,
                search_language regconfig,
                filter_metadata JSONB,
                tsquery_mode TEXT
            )
            RETURNS TABLE (
                id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                semantic_rank BIGINT,
                keyword_rank BIGINT,
                rrf_score FLOAT
            )
            LANGUAGE plpgsql STABLE
            AS $$
            DECLARE
                v_has_embedding BOOLEAN := query_embedding IS NOT NULL;
                v_has_text BOOLEAN := query_text IS NOT NULL AND length(trim(query_text)) > 0;
                v_tsquery tsquery;
            BEGIN
                IF NOT v_has_embedding AND NOT v_has_text THEN
                    RETURN;
                END IF;

                IF v_has_text THEN
                    v_tsquery := gaik_tsquery(search_language, query_text, tsquery_mode);
                END IF;

                RETURN QUERY
                WITH semantic AS (
                    SELECT
                        t.id, t.title, t.content, t.metadata,
                        ROW_NUMBER() OVER (
                            ORDER BY t.embedding <=> query_embedding
                        )::BIGINT AS rank
                    FROM {table} t
                    WHERE v_has_embedding
                      AND t.embedding IS NOT NULL
                      AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                    ORDER BY t.embedding <=> query_embedding
                    LIMIT result_limit * 3
                ),
                keyword AS (
                    SELECT
                        t.id, t.title, t.content, t.metadata,
                        ROW_NUMBER() OVER (
                            ORDER BY ts_rank_cd(t.text_search, v_tsquery) DESC
                        )::BIGINT AS rank
                    FROM {table} t
                    WHERE v_has_text
                      AND t.text_search @@ v_tsquery
                      AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                    ORDER BY ts_rank_cd(t.text_search, v_tsquery) DESC
                    LIMIT result_limit * 3
                ),
                rrf AS (
                    SELECT
                        COALESCE(sem.id, kw.id) AS id,
                        COALESCE(sem.title, kw.title) AS title,
                        COALESCE(sem.content, kw.content) AS content,
                        COALESCE(sem.metadata, kw.metadata) AS metadata,
                        sem.rank AS semantic_rank,
                        kw.rank AS keyword_rank,
                        (
                            sem_weight * COALESCE(1.0 / (rrf_k + sem.rank), 0) +
                            kw_weight  * COALESCE(1.0 / (rrf_k + kw.rank), 0)
                        )::FLOAT AS rrf_score
                    FROM semantic sem
                    FULL OUTER JOIN keyword kw ON sem.id = kw.id
                )
                SELECT r.id, r.title, r.content, r.metadata,
                       r.semantic_rank, r.keyword_rank, r.rrf_score
                FROM rrf r
                ORDER BY r.rrf_score DESC
                LIMIT result_limit;
            END;
            $$
        """)
        # The pre-tsquery_mode signature, for older gaik releases (see setup()).
        # Names, defaults and return columns must match theirs exactly, or their
        # setup() fails to `CREATE OR REPLACE` it.
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_fts_{table}(
                query_embedding {vec},
                query_text TEXT,
                result_limit INTEGER DEFAULT 20,
                rrf_k INTEGER DEFAULT 60,
                sem_weight FLOAT DEFAULT 0.5,
                kw_weight FLOAT DEFAULT 0.5,
                search_language regconfig DEFAULT '{lang}',
                filter_metadata JSONB DEFAULT NULL
            )
            RETURNS TABLE (
                id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                semantic_rank BIGINT,
                keyword_rank BIGINT,
                rrf_score FLOAT
            )
            LANGUAGE sql STABLE
            AS $$
                SELECT * FROM hybrid_search_fts_{table}(
                    query_embedding, query_text, result_limit, rrf_k,
                    sem_weight, kw_weight, search_language, filter_metadata,
                    'websearch'::TEXT
                );
            $$
        """)

    def _create_hybrid_weighted_function(self, conn: psycopg.Connection) -> None:
        """Create the weighted linear combination hybrid search SQL function."""
        table = self.table_name
        vec = self._vec
        lang = self.fts_language
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_weighted_{table}(
                query_embedding {vec},
                query_text TEXT,
                result_limit INTEGER,
                sem_weight FLOAT,
                kw_weight FLOAT,
                search_language regconfig,
                filter_metadata JSONB,
                tsquery_mode TEXT
            )
            RETURNS TABLE (
                id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                semantic_score FLOAT,
                keyword_score FLOAT,
                combined_score FLOAT
            )
            LANGUAGE plpgsql STABLE
            AS $$
            BEGIN
                RETURN QUERY
                WITH semantic AS (
                    SELECT
                        t.id, t.title, t.content, t.metadata,
                        (1 - (t.embedding <=> query_embedding))::FLOAT AS score
                    FROM {table} t
                    WHERE t.embedding IS NOT NULL
                      AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                    ORDER BY t.embedding <=> query_embedding
                    LIMIT result_limit * 3
                ),
                keyword AS (
                    SELECT
                        t.id,
                        ts_rank_cd(
                            t.text_search,
                            gaik_tsquery(search_language, query_text, tsquery_mode)
                        )::FLOAT AS score
                    FROM {table} t
                    WHERE t.text_search @@ gaik_tsquery(search_language, query_text, tsquery_mode)
                      AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                ),
                -- Qualified: RETURNS TABLE makes `id` a PL/pgSQL variable too, and
                -- a bare `id` here fails every call as ambiguous.
                keyword_normalized AS (
                    SELECT
                        kw.id,
                        CASE
                            WHEN MAX(kw.score) OVER () > 0
                            THEN kw.score / MAX(kw.score) OVER ()
                            ELSE 0
                        END AS score
                    FROM keyword kw
                )
                SELECT
                    s.id, s.title, s.content, s.metadata,
                    s.score AS semantic_score,
                    COALESCE(k.score, 0)::FLOAT AS keyword_score,
                    (sem_weight * s.score +
                     kw_weight * COALESCE(k.score, 0))::FLOAT AS combined_score
                FROM semantic s
                LEFT JOIN keyword_normalized k ON s.id = k.id
                ORDER BY (sem_weight * s.score + kw_weight * COALESCE(k.score, 0)) DESC
                LIMIT result_limit;
            END;
            $$
        """)
        # The pre-tsquery_mode signature, for older gaik releases (see setup()).
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_weighted_{table}(
                query_embedding {vec},
                query_text TEXT,
                result_limit INTEGER DEFAULT 20,
                sem_weight FLOAT DEFAULT 0.5,
                kw_weight FLOAT DEFAULT 0.5,
                search_language regconfig DEFAULT '{lang}',
                filter_metadata JSONB DEFAULT NULL
            )
            RETURNS TABLE (
                id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                semantic_score FLOAT,
                keyword_score FLOAT,
                combined_score FLOAT
            )
            LANGUAGE sql STABLE
            AS $$
                SELECT * FROM hybrid_search_weighted_{table}(
                    query_embedding, query_text, result_limit, sem_weight,
                    kw_weight, search_language, filter_metadata, 'websearch'::TEXT
                );
            $$
        """)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def add(
        self,
        documents: list[Document],
        embeddings: list[list[float]],
    ) -> list[int]:
        """Insert documents with their embeddings.

        The ``title`` field is taken from ``Document.metadata["title"]`` if present.

        Args:
            documents: List of langchain Documents to store.
            embeddings: Corresponding embedding vectors (same length as documents).

        Returns:
            List of inserted row IDs.

        Raises:
            ValueError: If documents and embeddings have different lengths.
        """
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have the same length")

        if not documents:
            return []

        conn = self._get_conn()
        ids: list[int] = []

        with conn.cursor() as cur:
            for doc, emb in zip(documents, embeddings):
                title = doc.metadata.get("title", "") if doc.metadata else ""
                metadata = doc.metadata or {}
                vec_str = _format_vector(emb)

                if self.text_processor is not None:
                    lemmatized = self.text_processor.to_tsvector_text(doc.page_content)
                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name}
                            (title, content, content_lemmatized, metadata, embedding)
                        VALUES (
                            %s, %s, %s, %s::jsonb, %s::{self._vec}
                        )
                        RETURNING id
                        """,
                        (
                            title,
                            doc.page_content,
                            lemmatized,
                            json.dumps(metadata),
                            vec_str,
                        ),
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (title, content, metadata, embedding)
                        VALUES (%s, %s, %s::jsonb, %s::{self._vec})
                        RETURNING id
                        """,
                        (title, doc.page_content, json.dumps(metadata), vec_str),
                    )
                row = cur.fetchone()
                ids.append(row["id"])

        conn.commit()
        logger.info("Inserted %d documents into '%s'", len(ids), self.table_name)
        return ids

    def count(self) -> int:
        """Return the total number of documents in the store."""
        conn = self._get_conn()
        row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {self.table_name}").fetchone()
        return row["cnt"] if row else 0

    def delete(self, document_ids: list[int]) -> int:
        """Delete documents by their IDs.

        Returns:
            Number of rows deleted.
        """
        if not document_ids:
            return 0

        conn = self._get_conn()
        result = conn.execute(
            f"DELETE FROM {self.table_name} WHERE id = ANY(%s)",
            (document_ids,),
        )
        conn.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Semantic search compatible with the existing VectorStore interface.

        This method provides a drop-in replacement for
        ``gaik.software_components.RAG.vector_store.VectorStore.search()``,
        allowing ``PgVectorStore`` to be used with the existing ``Retriever``.
        """
        return self.search_semantic(query_embedding, top_k=top_k, threshold=0.0, filters=filters)

    def search_semantic(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        threshold: float = 0.7,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Pure vector similarity search using cosine distance.

        Args:
            query_embedding: Query vector.
            top_k: Maximum number of results.
            threshold: Minimum cosine similarity (0.0 to 1.0).
            filters: Optional JSONB metadata filter (e.g. ``{"category": "news"}``).

        Returns:
            List of ``(Document, similarity_score)`` tuples, highest first.
        """
        conn = self._get_conn()
        vec_str = _format_vector(query_embedding)
        filter_json = json.dumps(filters) if filters else None

        rows = conn.execute(
            f"""
            SELECT * FROM match_{self.table_name}(
                %s::{self._vec}, %s, %s, %s::jsonb
            )
            """,
            (vec_str, threshold, top_k, filter_json),
        ).fetchall()

        return self._rows_to_results(rows, score_key="similarity")

    def search_keyword(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Full-text keyword search using tsvector/tsquery.

        Args:
            query_text: Natural language search query.
            top_k: Maximum number of results.
            filters: Optional JSONB metadata filter.

        Returns:
            List of ``(Document, ts_rank_score)`` tuples, highest first.
        """
        conn = self._get_conn()
        filter_clause, filter_params = _build_filter_clause(filters)
        effective_query = self._lemmatize_query(query_text)

        rows = conn.execute(
            f"""
            SELECT
                t.id, t.title, t.content, t.metadata,
                ts_rank_cd(
                    t.text_search,
                    gaik_tsquery('{self.fts_language}', %s, '{self.tsquery_mode}')
                )::FLOAT AS score
            FROM {self.table_name} t
            WHERE t.text_search @@ gaik_tsquery('{self.fts_language}', %s, '{self.tsquery_mode}')
              {filter_clause}
            ORDER BY score DESC
            LIMIT %s
            """,
            (effective_query, effective_query, *filter_params, top_k),
        ).fetchall()

        return self._rows_to_results(rows, score_key="score")

    def search_hybrid(
        self,
        query_embedding: list[float],
        query_text: str,
        *,
        top_k: int = 10,
        rrf_k: int = 60,
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Hybrid search using Reciprocal Rank Fusion (RRF).

        Combines vector similarity and full-text keyword rankings using
        the formula: ``score = sem_w / (k + sem_rank) + kw_w / (k + kw_rank)``.

        Args:
            query_embedding: Query vector for semantic search.
            query_text: Natural language query for keyword search.
            top_k: Maximum number of results.
            rrf_k: RRF smoothing constant (default 60).
            semantic_weight: Weight for semantic ranking (default 0.5).
            keyword_weight: Weight for keyword ranking (default 0.5).
            filters: Optional JSONB metadata filter.

        Returns:
            List of ``(Document, rrf_score)`` tuples, highest first. Each
            document's metadata carries ``semantic_rank`` and ``keyword_rank``
            (absent when that arm did not find the row) and
            ``semantic_similarity``, the row's cosine similarity to the query.
            The RRF score is built from rank positions and cannot tell a real
            match from the nearest neighbour of gibberish; the similarity can.
        """
        conn = self._get_conn()
        vec_str = _format_vector(query_embedding)
        filter_json = json.dumps(filters) if filters else None
        effective_query = self._lemmatize_query(query_text)

        rows = conn.execute(
            f"""
            SELECT
                h.*,
                (1 - (t.embedding <=> %s::{self._vec}))::FLOAT AS semantic_similarity
            FROM hybrid_search_fts_{self.table_name}(
                %s::{self._vec},
                %s, %s, %s, %s, %s,
                '{self.fts_language}'::regconfig,
                %s::jsonb,
                %s
            ) h
            JOIN {self.table_name} t ON t.id = h.id
            ORDER BY h.rrf_score DESC, h.id
            """,
            (
                vec_str,
                vec_str,
                effective_query,
                top_k,
                rrf_k,
                semantic_weight,
                keyword_weight,
                filter_json,
                self.tsquery_mode,
            ),
        ).fetchall()

        return self._rows_to_results(
            rows,
            score_key="rrf_score",
            extra_keys=("semantic_rank", "keyword_rank", "semantic_similarity"),
        )

    def search_hybrid_weighted(
        self,
        query_embedding: list[float],
        query_text: str,
        *,
        top_k: int = 10,
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """Weighted hybrid search using normalized linear combination.

        Semantic scores (cosine similarity) are in [0, 1]. Keyword scores
        (ts_rank_cd) are normalized to [0, 1] by dividing by the max score.

        Args:
            query_embedding: Query vector for semantic search.
            query_text: Natural language query for keyword search.
            top_k: Maximum number of results.
            semantic_weight: Weight for semantic score (default 0.5).
            keyword_weight: Weight for keyword score (default 0.5).
            filters: Optional JSONB metadata filter.

        Returns:
            List of ``(Document, combined_score)`` tuples, highest first.
        """
        conn = self._get_conn()
        vec_str = _format_vector(query_embedding)
        filter_json = json.dumps(filters) if filters else None
        effective_query = self._lemmatize_query(query_text)

        rows = conn.execute(
            f"""
            SELECT * FROM hybrid_search_weighted_{self.table_name}(
                %s::{self._vec},
                %s, %s, %s, %s,
                '{self.fts_language}'::regconfig,
                %s::jsonb,
                %s
            )
            """,
            (
                vec_str,
                effective_query,
                top_k,
                semantic_weight,
                keyword_weight,
                filter_json,
                self.tsquery_mode,
            ),
        ).fetchall()

        return self._rows_to_results(
            rows,
            score_key="combined_score",
            extra_keys=("semantic_score", "keyword_score"),
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self, *, sample_rows: int = 5) -> HealthReport:
        """Check, against the live database, that both search arms can work.

        Either arm of a hybrid search can stop contributing without an error,
        because the other keeps filling the page. This reads the table as it
        really is and compares it with how this store is configured:

        - the embedding column's type and dimension;
        - whether ``text_search`` is a generated column, and which text search
          configuration it was built with;
        - whether the index holds lemmas and this store lemmatizes queries the
          same way: the stored lemmas of a few rows are compared with what the
          current ``text_processor`` produces for the same text, which catches
          a changed backend, a changed ``decompound`` setting and a missing
          lemmatizer library alike;
        - rows without an embedding, an empty ``text_search`` or missing lemmas;
        - the vector and full-text indexes, and the vector index's operator class;
        - whether ``hnsw.ef_search`` and ``hnsw.iterative_scan`` took effect on
          this connection, which they do not behind a transaction pooler.

        Nothing is written. The row counts scan the table once, so call this at
        startup or from a status endpoint, not per request.

        Args:
            sample_rows: How many rows to take from each end of the table for the
                lemma comparison. ``0`` skips it.

        Returns:
            A :class:`HealthReport`; ``report.ok`` is ``True`` when nothing is
            wrong and ``str(report)`` lists the problems otherwise.
        """
        conn = self._get_conn()
        table = self.table_name
        problems: list[str] = []
        details: dict[str, Any] = {"table": table}

        columns = conn.execute(
            """
            SELECT
                a.attname AS name,
                format_type(a.atttypid, a.atttypmod) AS type,
                a.attgenerated AS generated,
                pg_get_expr(d.adbin, d.adrelid) AS expression
            FROM pg_attribute a
            LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = to_regclass(%s) AND a.attnum > 0 AND NOT a.attisdropped
            """,
            (table,),
        ).fetchall()
        if not columns:
            return HealthReport(
                False, [f"table {table!r} does not exist: call setup() first"], details
            )
        column = {row["name"]: row for row in columns}

        # Embedding column
        embedding_type = column["embedding"]["type"] if "embedding" in column else None
        details["embedding_type"] = embedding_type
        if embedding_type is None:
            problems.append("the table has no embedding column: the vector arm cannot work")
        elif embedding_type != self._vec:
            problems.append(
                f"the embedding column is {embedding_type}, this store is configured for "
                f"{self._vec}: inserts and vector searches fail"
            )

        # Full-text column
        text_search = column.get("text_search")
        index_holds_lemmas = False
        if text_search is None:
            problems.append("the table has no text_search column: the keyword arm cannot work")
        else:
            generated = text_search["generated"] == "s"
            details["text_search_generated"] = generated
            expression = text_search["expression"] or ""
            if not generated:
                problems.append(
                    "text_search is a plain column, not a generated one: nothing fills it "
                    "when a row is inserted or changed, so the keyword arm sees only what "
                    "was written to it by hand"
                )
            else:
                index_holds_lemmas = "content_lemmatized" in expression
                found = re.search(r"to_tsvector\('([^']+)'::regconfig", expression)
                details["fts_language"] = found.group(1) if found else None
                if found and found.group(1).lower() != self.fts_language.lower():
                    problems.append(
                        f"the full-text index was built with the {found.group(1)!r} "
                        f"configuration, queries are parsed with {self.fts_language!r}: "
                        "the two produce different word forms, so keyword matches are lost"
                    )

        # Lemmas: the index and the query must agree
        if self.text_processor is not None and not index_holds_lemmas:
            problems.append(
                "this store has a text_processor but the table was created without one: "
                "queries are lemmatized and the index is not, so the keyword arm misses"
            )
        if self.text_processor is not None and index_holds_lemmas:
            if getattr(self.text_processor, "backend_name", None) == "simple":
                problems.append(
                    "the text_processor's backend is 'simple', a tokenizer and not a "
                    "lemmatizer: inflected words are indexed and searched as typed"
                )
            if sample_rows > 0:
                sample = conn.execute(
                    f"""
                    (SELECT id, content, content_lemmatized FROM {table}
                     WHERE content_lemmatized IS NOT NULL ORDER BY id LIMIT %s)
                    UNION
                    (SELECT id, content, content_lemmatized FROM {table}
                     WHERE content_lemmatized IS NOT NULL ORDER BY id DESC LIMIT %s)
                    """,
                    (sample_rows, sample_rows),
                ).fetchall()
                differing = [
                    row["id"]
                    for row in sample
                    if self.text_processor.to_tsvector_text(row["content"])
                    != row["content_lemmatized"]
                ]
                details["lemma_sample"] = {"rows": len(sample), "differing": len(differing)}
                if differing:
                    problems.append(
                        f"{len(differing)} of {len(sample)} sampled rows hold lemmas that "
                        "differ from what this text_processor produces for the same text "
                        f"(for example id {differing[0]}): the index and the query "
                        "lemmatize differently, so the keyword arm misses. Restore the "
                        "backend and decompound setting the table was built with, or call "
                        "relemmatize()"
                    )

        # Rows either arm cannot see
        counted = ["count(*) AS total"]
        if embedding_type is not None:
            counted.append("count(*) FILTER (WHERE embedding IS NULL) AS without_embedding")
        if text_search is not None:
            counted.append(
                "count(*) FILTER (WHERE text_search IS NULL OR text_search = ''::tsvector) "
                "AS without_keywords"
            )
        if "content_lemmatized" in column:
            counted.append("count(content_lemmatized) AS with_lemmas")
        counts = conn.execute(f"SELECT {', '.join(counted)} FROM {table}").fetchone()
        total = counts["total"]
        details["rows"] = total
        for key in ("without_embedding", "without_keywords", "with_lemmas"):
            if key in counts:
                details[key] = counts[key]
        if counts.get("without_embedding"):
            problems.append(
                f"{counts['without_embedding']} of {total} rows have no embedding: "
                "the vector arm cannot return them"
            )
        if counts.get("without_keywords"):
            problems.append(
                f"{counts['without_keywords']} of {total} rows have an empty text_search: "
                "the keyword arm cannot return them"
            )
        with_lemmas = counts.get("with_lemmas", 0)
        if self.text_processor is not None and index_holds_lemmas and with_lemmas < total:
            problems.append(
                f"{total - with_lemmas} of {total} rows have no lemmas and are indexed as "
                "raw text: call relemmatize()"
            )
        if self.text_processor is None and index_holds_lemmas and with_lemmas:
            problems.append(
                f"{with_lemmas} of {total} rows are indexed as lemmas but this store has no "
                "text_processor: queries are not lemmatized, so inflected words miss"
            )

        # Indexes
        indexes = conn.execute(
            """
            SELECT a.attname AS column_name, am.amname AS method, opc.opcname AS opclass
            FROM pg_index x
            JOIN pg_class i ON i.oid = x.indexrelid
            JOIN pg_am am ON am.oid = i.relam
            JOIN pg_opclass opc ON opc.oid = x.indclass[0]
            JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = x.indkey[0]
            WHERE x.indrelid = to_regclass(%s) AND x.indisvalid
            """,
            (table,),
        ).fetchall()
        vector_indexes = [row for row in indexes if row["column_name"] == "embedding"]
        details["vector_index"] = [f"{row['method']} {row['opclass']}" for row in vector_indexes]
        wanted = f"{self.vector_type}_cosine_ops"
        if embedding_type is not None and not vector_indexes:
            problems.append("there is no index on embedding: every vector search scans the table")
        elif (
            vector_indexes
            and embedding_type == self._vec
            and not any(row["opclass"] == wanted for row in vector_indexes)
        ):
            problems.append(
                f"the vector index uses {vector_indexes[0]['opclass']}, searches use cosine "
                f"distance ({wanted}): the index is ignored and every search scans the table"
            )
        if text_search is not None and not any(
            row["column_name"] == "text_search" and row["method"] == "gin" for row in indexes
        ):
            problems.append("there is no GIN index on text_search: keyword search scans the table")

        # pgvector and the session settings this store asked for
        settings = conn.execute(
            """
            SELECT
                (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS pgvector,
                current_setting('hnsw.ef_search', true) AS ef_search,
                current_setting('hnsw.iterative_scan', true) AS iterative_scan
            """
        ).fetchone()
        details["pgvector"] = settings["pgvector"]
        details["hnsw_ef_search"] = settings["ef_search"]
        details["hnsw_iterative_scan"] = settings["iterative_scan"]
        if self.hnsw_ef_search is not None and settings["ef_search"] != str(self.hnsw_ef_search):
            problems.append(
                f"hnsw.ef_search is {settings['ef_search'] or 'unset'} on this connection, "
                f"the store asked for {self.hnsw_ef_search}: a transaction pooler drops "
                "session settings, so set it as a database default instead"
            )
        if (
            self.hnsw_iterative_scan is not None
            and settings["iterative_scan"] != self.hnsw_iterative_scan
        ):
            problems.append(
                f"hnsw.iterative_scan is {settings['iterative_scan'] or 'unset'} on this "
                f"connection, the store asked for {self.hnsw_iterative_scan}: it needs "
                "pgvector 0.8 or newer, and a transaction pooler drops session settings"
            )

        return HealthReport(not problems, problems, details)

    def relemmatize(self, *, batch_size: int = 500) -> int:
        """Recompute the lemma column for every row with the current ``text_processor``.

        Use it after changing the processor's backend or its ``decompound``
        setting, or to fill rows whose lemmas are missing. The index and the
        query must lemmatize the same way, and this is what brings an existing
        table back in step. Embeddings are not touched; the generated
        ``text_search`` column follows the new lemmas by itself.

        Args:
            batch_size: Rows read and committed at a time.

        Returns:
            Number of rows updated.

        Raises:
            ValueError: If the store has no ``text_processor``, or the table was
                created without one and so has no lemma column.
        """
        if self.text_processor is None:
            raise ValueError("relemmatize() needs a text_processor")
        conn = self._get_conn()
        table = self.table_name
        has_column = conn.execute(
            """
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(%s)
              AND attname = 'content_lemmatized'
              AND NOT attisdropped
            """,
            (table,),
        ).fetchone()
        if has_column is None:
            raise ValueError(
                f"table {table!r} was created without a text_processor and has no "
                "content_lemmatized column; create a new table with one"
            )

        last_id, updated = 0, 0
        while True:
            rows = conn.execute(
                f"SELECT id, content FROM {table} WHERE id > %s ORDER BY id LIMIT %s",
                (last_id, batch_size),
            ).fetchall()
            if not rows:
                break
            with conn.cursor() as cur:
                cur.executemany(
                    f"UPDATE {table} SET content_lemmatized = %s WHERE id = %s",
                    [
                        (self.text_processor.to_tsvector_text(row["content"]), row["id"])
                        for row in rows
                    ],
                )
            conn.commit()
            last_id = rows[-1]["id"]
            updated += len(rows)

        logger.info("Relemmatized %d rows in '%s'", updated, table)
        return updated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lemmatize_query(self, query_text: str) -> str:
        """Run the query through the configured ``text_processor`` (no-op when not set)."""
        if not query_text or self.text_processor is None:
            return query_text
        expanded = self.text_processor.expand_query(query_text)
        return expanded if expanded else query_text

    @staticmethod
    def _rows_to_results(
        rows: list[dict[str, Any]],
        *,
        score_key: str,
        extra_keys: tuple[str, ...] = (),
    ) -> list[tuple[Document, float]]:
        """Convert database rows to (Document, score) pairs.

        ``id`` and ``title`` are reserved metadata keys: they are taken from the
        table columns and overwrite any same-named key in the row's JSONB
        metadata. ``id`` gives callers a stable identity, which is what lets
        ``Ranker`` fuse two result lists that returned the same row.

        ``extra_keys`` surfaces per-arm columns the hybrid SQL functions already
        return (ranks and per-branch scores). Keys whose value is NULL are
        omitted rather than set to ``None``, so ``"semantic_rank" in metadata``
        answers "did the semantic arm find this row at all".
        """
        results: list[tuple[Document, float]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            else:
                metadata = dict(metadata)  # never alias the caller's row dict
            if row.get("title"):
                metadata["title"] = row["title"]
            if row.get("id") is not None:
                metadata["id"] = row["id"]
            for extra_key in extra_keys:
                value = row.get(extra_key)
                if value is not None:
                    metadata[extra_key] = value

            doc = Document(page_content=row["content"], metadata=metadata)
            score = float(row[score_key])
            results.append((doc, score))
        return results
