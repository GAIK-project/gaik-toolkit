-- Consolidated schema for semantic video search (S3-based)
-- PostgreSQL 17 + pgvector extension
-- This replaces all previous migrations with a clean, single migration

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create video status enum
CREATE TYPE "public"."video_status" AS ENUM('pending', 'ready', 'ready_no_subs', 'failed');

-- S3 Videos Table
-- Stores metadata for videos uploaded to S3-compatible storage (CSC Allas)
CREATE TABLE "s3_videos" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"title" text,
	"s3_key" text NOT NULL,
	"srt_key" text,
	"thumb_key" text,
	"duration_seconds" integer,
	"status" "video_status" DEFAULT 'pending' NOT NULL,
	"size_bytes" bigint,
	"checksum" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"metadata" jsonb,
	CONSTRAINT "s3_videos_s3_key_unique" UNIQUE("s3_key")
);

-- S3 Video Segments Table
-- Stores subtitle segments with vector embeddings for semantic search
CREATE TABLE "s3_segments" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "s3_segments_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"video_id" uuid NOT NULL,
	"srt_index" integer NOT NULL,
	"start_seconds" real NOT NULL,
	"end_seconds" real NOT NULL,
	"text" text NOT NULL,
	"embedding" vector(1536),
	CONSTRAINT "s3_segments_video_id_srt_index_unique" UNIQUE("video_id","srt_index")
);

-- Foreign key constraint for segments -> videos
ALTER TABLE "s3_segments" ADD CONSTRAINT "s3_segments_video_id_s3_videos_id_fk" 
FOREIGN KEY ("video_id") REFERENCES "public"."s3_videos"("id") ON DELETE cascade ON UPDATE no action;

-- Indexes for performance
CREATE INDEX "s3_videos_status_idx" ON "s3_videos" USING btree ("status");
CREATE INDEX "s3_videos_created_at_idx" ON "s3_videos" USING btree ("created_at");
CREATE INDEX "s3_segments_video_id_idx" ON "s3_segments" USING btree ("video_id");

-- HNSW index for vector similarity search (pgvector)
-- This enables fast cosine similarity searches on embeddings
CREATE INDEX "s3_segments_embedding_hnsw" ON "s3_segments" USING hnsw ("embedding" vector_cosine_ops);
