-- Migration: Add trigram similarity and unaccent for fuzzy keyword search
-- pg_trgm and unaccent are standard PostgreSQL contrib extensions.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Immutable wrapper for unaccent (required for index expressions)
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text AS $$
  SELECT public.unaccent($1);
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;

-- GIN trigram index on segment text for similarity queries
CREATE INDEX IF NOT EXISTS "s3_segments_text_trgm_gin"
ON s3_segments USING GIN (text gin_trgm_ops);

-- GIN trigram index on cue text for in-video fuzzy search
CREATE INDEX IF NOT EXISTS "s3_subtitle_cues_text_trgm_gin"
ON s3_subtitle_cues USING GIN (text gin_trgm_ops);
