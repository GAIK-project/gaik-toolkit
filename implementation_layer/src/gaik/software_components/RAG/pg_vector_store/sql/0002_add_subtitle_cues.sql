-- Migration: Add individual subtitle cues for precise timestamp resolution
-- These are the raw, ungrouped subtitle lines from SRT files.
-- They enable precise seek within grouped segments and cue-level in-video search.

CREATE TABLE IF NOT EXISTS "s3_subtitle_cues" (
    "id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    "video_id" uuid NOT NULL REFERENCES "s3_videos"("id") ON DELETE CASCADE,
    "cue_index" integer NOT NULL,
    "start_seconds" real NOT NULL,
    "end_seconds" real NOT NULL,
    "text" text NOT NULL,
    "text_search" tsvector GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(text, ''))) STORED,
    CONSTRAINT "s3_subtitle_cues_video_cue_unique" UNIQUE("video_id", "cue_index")
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS "s3_subtitle_cues_video_id_idx"
ON "s3_subtitle_cues" USING btree ("video_id");

CREATE INDEX IF NOT EXISTS "s3_subtitle_cues_text_search_gin"
ON "s3_subtitle_cues" USING GIN ("text_search");

CREATE INDEX IF NOT EXISTS "s3_subtitle_cues_video_start_idx"
ON "s3_subtitle_cues" USING btree ("video_id", "start_seconds");

-- Comment
COMMENT ON TABLE s3_subtitle_cues IS 'Individual subtitle cues (raw SRT lines) for precise timestamp resolution and cue-level search. cue_index is the parser-assigned sequence number (1-based), not the original SRT sequence number.';
