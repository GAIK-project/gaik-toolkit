-- Migration: prefix_tsquery for Finnish (agglutinative language) support
--
-- Problem: 'simple' text search config does no stemming, so
-- 'xylitol' won't match 'xylitolin' (Finnish genitive).
-- Solution: Replace websearch_to_tsquery with prefix-based matching.
--
-- Adds a helper function to convert query text into prefix tsquery,
-- and updates hybrid_search() to use it.

-- 1. Helper: Convert space-separated words to prefix tsquery
-- e.g., 'fluoridi ksylitoli' → 'fluoridi:* & ksylitoli:*'
-- Supports quoted phrases by falling back to websearch_to_tsquery
-- when the input contains quotes.
-- Special characters are stripped to prevent tsquery syntax errors.
CREATE OR REPLACE FUNCTION prefix_tsquery(p_config regconfig, p_text TEXT)
RETURNS tsquery
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    v_words TEXT[];
    v_parts TEXT[];
    v_word TEXT;
BEGIN
    -- If query contains quotes, fall back to websearch_to_tsquery
    -- (prefix matching doesn't help with exact phrases)
    IF p_text LIKE '%"%' THEN
        RETURN websearch_to_tsquery(p_config, p_text);
    END IF;

    -- Split on whitespace, filter empty strings, add :* prefix operator
    -- Strip tsquery-special characters: ( ) ? ! & | < > : \ '
    v_words := string_to_array(trim(regexp_replace(p_text, '\s+', ' ', 'g')), ' ');
    v_parts := ARRAY[]::TEXT[];

    FOREACH v_word IN ARRAY v_words LOOP
        v_word := regexp_replace(v_word, '[()!&|<>:?\\''"]', '', 'g');
        IF length(v_word) > 0 THEN
            v_parts := array_append(v_parts, v_word || ':*');
        END IF;
    END LOOP;

    IF array_length(v_parts, 1) IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN to_tsquery(p_config, array_to_string(v_parts, ' & '));
END;
$$;

COMMENT ON FUNCTION prefix_tsquery IS 'Convert query text to prefix tsquery for Finnish/agglutinative languages. Each word becomes a prefix match (e.g., xylitol → xylitol:*) joined with AND. Special characters are stripped to prevent tsquery syntax errors.';

-- 2. Update hybrid_search() to use prefix matching instead of websearch_to_tsquery
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
    IF NOT v_has_embedding AND NOT v_has_text THEN
        RETURN;
    END IF;

    -- Use prefix matching for Finnish agglutinative forms
    IF v_has_text THEN
        v_tsquery := prefix_tsquery('simple', p_query_text);
    END IF;

    RETURN QUERY
    WITH semantic AS (
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
