"""PostgreSQL-backed vector store with semantic, keyword, and hybrid search via pgvector."""

from __future__ import annotations

import json
import logging
import re
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

    Example::

        from gaik.software_components.RAG.pg_vector_store import PgVectorStore
        from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

        processor = FinnishTextProcessor(backend="auto")  # voikko/spacy/uralic/simple
        with PgVectorStore(
            "postgresql://postgres:postgres@localhost/mydb",
            text_processor=processor,
        ) as store:
            store.setup()
            ids = store.add(documents, embeddings)
            results = store.search_hybrid(query_vec, "kerrostalon kissoilla", top_k=5)
    """

    def __init__(
        self,
        connection_string: str,
        *,
        table_name: str = "documents",
        embedding_dim: int = 1536,
        fts_language: str = "simple",
        text_processor: FinnishTextProcessor | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table_name):
            raise ValueError(
                f"Invalid table_name '{table_name}': "
                "must contain only letters, digits, and underscores"
            )
        self.connection_string = connection_string
        self.table_name = table_name
        self.embedding_dim = embedding_dim
        self.fts_language = fts_language
        self.text_processor = text_processor
        self._conn: psycopg.Connection | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> psycopg.Connection:
        """Return (and lazily create) the database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.connection_string, row_factory=dict_row)
        return self._conn

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
        dim = self.embedding_dim
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
                    embedding vector({dim}),
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
                    embedding vector({dim}),
                    text_search tsvector GENERATED ALWAYS AS (
                        to_tsvector('{lang}', COALESCE(content, ''))
                    ) STORED,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

        # 3. Indexes
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_embedding_hnsw_idx
            ON {table} USING hnsw (embedding vector_cosine_ops)
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
        self._create_match_function(conn)
        self._create_hybrid_fts_function(conn)
        self._create_hybrid_weighted_function(conn)

        conn.commit()
        logger.info("PgVectorStore setup complete for table '%s'", table)

    def _create_match_function(self, conn: psycopg.Connection) -> None:
        """Create the pure semantic search SQL function."""
        table = self.table_name
        dim = self.embedding_dim
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION match_{table}(
                query_embedding vector({dim}),
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
        dim = self.embedding_dim
        lang = self.fts_language
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_fts_{table}(
                query_embedding vector({dim}),
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
                    v_tsquery := websearch_to_tsquery(search_language, query_text);
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

    def _create_hybrid_weighted_function(self, conn: psycopg.Connection) -> None:
        """Create the weighted linear combination hybrid search SQL function."""
        table = self.table_name
        dim = self.embedding_dim
        lang = self.fts_language
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION hybrid_search_weighted_{table}(
                query_embedding vector({dim}),
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
                            websearch_to_tsquery(search_language, query_text)
                        )::FLOAT AS score
                    FROM {table} t
                    WHERE t.text_search @@ websearch_to_tsquery(search_language, query_text)
                      AND (filter_metadata IS NULL OR t.metadata @> filter_metadata)
                ),
                keyword_normalized AS (
                    SELECT
                        id,
                        CASE
                            WHEN MAX(score) OVER () > 0
                            THEN score / MAX(score) OVER ()
                            ELSE 0
                        END AS score
                    FROM keyword
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
                            %s, %s, %s, %s::jsonb, %s::vector({self.embedding_dim})
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
                        VALUES (%s, %s, %s::jsonb, %s::vector({self.embedding_dim}))
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
                %s::vector({self.embedding_dim}), %s, %s, %s::jsonb
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
                    websearch_to_tsquery('{self.fts_language}', %s)
                )::FLOAT AS score
            FROM {self.table_name} t
            WHERE t.text_search @@ websearch_to_tsquery('{self.fts_language}', %s)
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
            List of ``(Document, rrf_score)`` tuples, highest first.
        """
        conn = self._get_conn()
        vec_str = _format_vector(query_embedding)
        filter_json = json.dumps(filters) if filters else None
        effective_query = self._lemmatize_query(query_text)

        rows = conn.execute(
            f"""
            SELECT * FROM hybrid_search_fts_{self.table_name}(
                %s::vector({self.embedding_dim}),
                %s, %s, %s, %s, %s,
                '{self.fts_language}'::regconfig,
                %s::jsonb
            )
            """,
            (
                vec_str,
                effective_query,
                top_k,
                rrf_k,
                semantic_weight,
                keyword_weight,
                filter_json,
            ),
        ).fetchall()

        return self._rows_to_results(
            rows,
            score_key="rrf_score",
            extra_keys=("semantic_rank", "keyword_rank"),
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
                %s::vector({self.embedding_dim}),
                %s, %s, %s, %s,
                '{self.fts_language}'::regconfig,
                %s::jsonb
            )
            """,
            (
                vec_str,
                effective_query,
                top_k,
                semantic_weight,
                keyword_weight,
                filter_json,
            ),
        ).fetchall()

        return self._rows_to_results(
            rows,
            score_key="combined_score",
            extra_keys=("semantic_score", "keyword_score"),
        )

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
