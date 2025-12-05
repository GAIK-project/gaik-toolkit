/** SQL to install required PostgreSQL extensions */
export const EXTENSIONS_SQL = `
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE EXCEPTION 'pgvector extension is required but not installed';
  END IF;
END $$;
`;

/** SQL for hybrid search functions */
export const HYBRID_SEARCH_SQL = `
CREATE OR REPLACE FUNCTION gaik_hybrid_search(
    p_table_name TEXT,
    p_query_text TEXT,
    p_query_embedding vector,
    p_limit INTEGER DEFAULT 20,
    p_semantic_weight FLOAT DEFAULT 0.5,
    p_keyword_weight FLOAT DEFAULT 0.5,
    p_rrf_k INTEGER DEFAULT 60
)
RETURNS TABLE (
    id BIGINT,
    content TEXT,
    semantic_rank BIGINT,
    keyword_rank BIGINT,
    rrf_score FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql STABLE
AS $func$
DECLARE
    v_has_embedding BOOLEAN := p_query_embedding IS NOT NULL;
    v_has_text BOOLEAN := p_query_text IS NOT NULL AND length(trim(p_query_text)) > 0;
    v_tsquery tsquery;
BEGIN
    IF NOT v_has_embedding AND NOT v_has_text THEN
        RETURN;
    END IF;

    IF v_has_text THEN
        v_tsquery := websearch_to_tsquery('simple', p_query_text);
    END IF;

    RETURN QUERY EXECUTE format(
        $q$
        WITH semantic AS (
            SELECT t.id::BIGINT, t.content, t.metadata,
                   ROW_NUMBER() OVER (ORDER BY t.embedding <=> $1)::BIGINT AS rank
            FROM %I t
            WHERE $2 AND t.embedding IS NOT NULL
            ORDER BY t.embedding <=> $1
            LIMIT $3 * 3
        ),
        keyword AS (
            SELECT t.id::BIGINT, t.content, t.metadata,
                   ROW_NUMBER() OVER (ORDER BY ts_rank_cd(t.text_search, $4) DESC)::BIGINT AS rank
            FROM %I t
            WHERE $5 AND t.text_search @@ $4
            ORDER BY ts_rank_cd(t.text_search, $4) DESC
            LIMIT $3 * 3
        ),
        rrf AS (
            SELECT
                COALESCE(sem.id, kw.id) AS id,
                COALESCE(sem.content, kw.content) AS content,
                COALESCE(sem.metadata, kw.metadata) AS metadata,
                sem.rank AS semantic_rank,
                kw.rank AS keyword_rank,
                ($6 * COALESCE(1.0 / ($7 + sem.rank), 0) +
                 $8 * COALESCE(1.0 / ($7 + kw.rank), 0))::FLOAT AS rrf_score
            FROM semantic sem
            FULL OUTER JOIN keyword kw ON sem.id = kw.id
        )
        SELECT r.id, r.content, r.semantic_rank, r.keyword_rank, r.rrf_score, r.metadata
        FROM rrf r
        ORDER BY r.rrf_score DESC
        LIMIT $3
        $q$,
        p_table_name, p_table_name
    )
    USING p_query_embedding, v_has_embedding, p_limit, v_tsquery, v_has_text,
          p_semantic_weight, p_rrf_k, p_keyword_weight;
END;
$func$;

CREATE OR REPLACE FUNCTION gaik_semantic_search(
    p_table_name TEXT,
    p_query_embedding vector,
    p_limit INTEGER DEFAULT 20,
    p_min_similarity FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    id BIGINT,
    content TEXT,
    similarity FLOAT,
    distance FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql STABLE
AS $func$
BEGIN
    RETURN QUERY EXECUTE format(
        $q$
        SELECT
            t.id::BIGINT,
            t.content,
            (1 - (t.embedding <=> $1))::FLOAT AS similarity,
            (t.embedding <=> $1)::FLOAT AS distance,
            t.metadata
        FROM %I t
        WHERE t.embedding IS NOT NULL
          AND (1 - (t.embedding <=> $1)) >= $3
        ORDER BY t.embedding <=> $1
        LIMIT $2
        $q$,
        p_table_name
    )
    USING p_query_embedding, p_limit, p_min_similarity;
END;
$func$;
`;

/** SQL for example documents table */
export const EXAMPLE_TABLE_SQL = `
CREATE TABLE IF NOT EXISTS gaik_documents (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),
    text_search tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gaik_documents_embedding 
    ON gaik_documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_gaik_documents_text_search 
    ON gaik_documents USING gin (text_search);

CREATE INDEX IF NOT EXISTS idx_gaik_documents_metadata 
    ON gaik_documents USING gin (metadata);
`;

/** All migrations combined */
export const ALL_MIGRATIONS_SQL = `
${EXTENSIONS_SQL}
${HYBRID_SEARCH_SQL}
${EXAMPLE_TABLE_SQL}
`;
