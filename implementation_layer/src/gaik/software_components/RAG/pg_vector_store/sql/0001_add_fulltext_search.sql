-- Migration: Add Full-Text Search for Hybrid Search
-- Combines semantic (vector) search with keyword (FTS) search using RRF

-- 1. Add tsvector column for full-text search (auto-generated from text)
ALTER TABLE s3_segments
ADD COLUMN text_search tsvector
GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(text, ''))) STORED;

-- 2. Create GIN index for fast full-text search
CREATE INDEX s3_segments_text_search_gin
ON s3_segments USING GIN (text_search);

-- 3. Create hybrid search function with RRF (Reciprocal Rank Fusion)
CREATE OR REPLACE FUNCTION hybrid_search(
    p_query_text TEXT,
    p_query_embedding vector(1536),
    p_limit INTEGER DEFAULT 20,
    p_semantic_weight FLOAT DEFAULT 0.5,
    p_keyword_weight FLOAT DEFAULT 0.5,
    p_rrf_k INTEGER DEFAULT 60
)
RETURNS TABLE (
    id BIGINT,
    video_id UUID,
    srt_index INTEGER,
    start_seconds REAL,
    end_seconds REAL,
    text TEXT,
    semantic_rank BIGINT,
    keyword_rank BIGINT,
    rrf_score FLOAT
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_has_embedding BOOLEAN := p_query_embedding IS NOT NULL;
    v_has_text BOOLEAN := p_query_text IS NOT NULL AND length(trim(p_query_text)) > 0;
    v_tsquery tsquery;
BEGIN
    -- If neither search method is provided, return empty set
    IF NOT v_has_embedding AND NOT v_has_text THEN
        RETURN;
    END IF;

    -- Build tsquery for keyword search (using 'simple' for multilingual support)
    IF v_has_text THEN
        v_tsquery := websearch_to_tsquery('simple', p_query_text);
    END IF;

    RETURN QUERY
    WITH semantic AS (
        -- Semantic (vector) search results with ranking
        SELECT
            s.id,
            s.video_id,
            s.srt_index,
            s.start_seconds,
            s.end_seconds,
            s.text,
            ROW_NUMBER() OVER (ORDER BY s.embedding <=> p_query_embedding)::BIGINT AS rank
        FROM s3_segments s
        WHERE v_has_embedding AND s.embedding IS NOT NULL
        ORDER BY s.embedding <=> p_query_embedding
        LIMIT p_limit * 3
    ),
    keyword AS (
        -- Full-text (keyword) search results with ranking
        SELECT
            s.id,
            s.video_id,
            s.srt_index,
            s.start_seconds,
            s.end_seconds,
            s.text,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(s.text_search, v_tsquery) DESC)::BIGINT AS rank
        FROM s3_segments s
        WHERE v_has_text AND s.text_search @@ v_tsquery
        ORDER BY ts_rank_cd(s.text_search, v_tsquery) DESC
        LIMIT p_limit * 3
    ),
    rrf AS (
        -- Combine results using Reciprocal Rank Fusion
        SELECT
            COALESCE(sem.id, kw.id) AS id,
            COALESCE(sem.video_id, kw.video_id) AS video_id,
            COALESCE(sem.srt_index, kw.srt_index) AS srt_index,
            COALESCE(sem.start_seconds, kw.start_seconds) AS start_seconds,
            COALESCE(sem.end_seconds, kw.end_seconds) AS end_seconds,
            COALESCE(sem.text, kw.text) AS text,
            sem.rank AS semantic_rank,
            kw.rank AS keyword_rank,
            (
                p_semantic_weight * COALESCE(1.0 / (p_rrf_k + sem.rank), 0) +
                p_keyword_weight * COALESCE(1.0 / (p_rrf_k + kw.rank), 0)
            )::FLOAT AS rrf_score
        FROM semantic sem
        FULL OUTER JOIN keyword kw ON sem.id = kw.id
    )
    SELECT r.id, r.video_id, r.srt_index, r.start_seconds, r.end_seconds,
           r.text, r.semantic_rank, r.keyword_rank, r.rrf_score
    FROM rrf r
    ORDER BY r.rrf_score DESC
    LIMIT p_limit;
END;
$$;

-- Add comment to function
COMMENT ON FUNCTION hybrid_search IS 'Hybrid search combining semantic (vector) and keyword (FTS) search using Reciprocal Rank Fusion (RRF). Returns segments ranked by combined relevance score.';
