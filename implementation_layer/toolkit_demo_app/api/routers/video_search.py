"""Semantic dental video search router - Hybrid search over transcribed video segments."""

import logging
import os
from collections.abc import AsyncGenerator

try:
    from utils import sse_event
except ImportError:
    from api.utils import sse_event
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons (lazy-initialised)
_store = None
_embedder = None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
TABLE_NAME = "video_segments"
FTS_LANGUAGE = "simple"


def _get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def _get_store():
    """Lazy-init PgVectorStore singleton."""
    global _store
    if _store is not None:
        return _store

    db_url = _get_database_url()
    if not db_url:
        return None

    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    _store = PgVectorStore(
        db_url,
        table_name=TABLE_NAME,
        embedding_dim=EMBEDDING_DIM,
        fts_language=FTS_LANGUAGE,
    )
    _store.setup()
    logger.info("PgVectorStore initialised for table '%s'", TABLE_NAME)
    return _store


def _get_embedder():
    """Lazy-init Embedder singleton."""
    global _embedder
    if _embedder is not None:
        return _embedder

    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        return None

    from gaik.software_components.config import get_openai_config
    from gaik.software_components.RAG.embedder import Embedder

    config = get_openai_config(use_azure=use_azure)
    _embedder = Embedder(config=config, model=EMBEDDING_MODEL)
    logger.info("Embedder initialised with model '%s'", EMBEDDING_MODEL)
    return _embedder


# ---------- Models ----------

class VideoInfo(BaseModel):
    video_id: str
    video_title: str
    segment_count: int


class SearchResult(BaseModel):
    text: str
    video_title: str
    video_id: str
    start_seconds: float
    end_seconds: float
    timestamp: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    total_results: int


class StatusResponse(BaseModel):
    database_connected: bool
    total_segments: int
    total_videos: int
    embedding_model: str


# ---------- Endpoints ----------

@router.get("/status", response_model=StatusResponse)
async def video_search_status():
    """Check database connectivity and indexed content stats."""
    store = _get_store()
    if store is None:
        return StatusResponse(
            database_connected=False,
            total_segments=0,
            total_videos=0,
            embedding_model=EMBEDDING_MODEL,
        )

    try:
        total = store.count()
        # Count distinct video_ids via raw query
        conn = store._get_conn()
        row = conn.execute(
            f"SELECT COUNT(DISTINCT metadata->>'video_id') AS cnt FROM {TABLE_NAME}"
        ).fetchone()
        video_count = row["cnt"] if row else 0

        return StatusResponse(
            database_connected=True,
            total_segments=total,
            total_videos=video_count,
            embedding_model=EMBEDDING_MODEL,
        )
    except Exception as e:
        logger.error("Database status check failed: %s", e)
        return StatusResponse(
            database_connected=False,
            total_segments=0,
            total_videos=0,
            embedding_model=EMBEDDING_MODEL,
        )


@router.get("/videos", response_model=list[VideoInfo])
async def list_videos():
    """List all indexed videos with segment counts."""
    store = _get_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        conn = store._get_conn()
        rows = conn.execute(f"""
            SELECT
                metadata->>'video_id' AS video_id,
                metadata->>'video_title' AS video_title,
                COUNT(*) AS segment_count
            FROM {TABLE_NAME}
            WHERE metadata->>'video_id' IS NOT NULL
            GROUP BY metadata->>'video_id', metadata->>'video_title'
            ORDER BY video_title
        """).fetchall()

        return [
            VideoInfo(
                video_id=row["video_id"],
                video_title=row["video_title"] or "Untitled",
                segment_count=row["segment_count"],
            )
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/videos/{video_id}/play")
async def get_playback_url(video_id: str):
    """Generate a presigned Allas S3 URL for video playback."""
    bucket = os.getenv("ALLAS_BUCKET_NAME")
    endpoint = os.getenv("ALLAS_ENDPOINT_URL")
    access_key = os.getenv("ALLAS_ACCESS_KEY_ID")
    secret_key = os.getenv("ALLAS_SECRET_ACCESS_KEY")

    if not all([bucket, endpoint, access_key, secret_key]):
        raise HTTPException(status_code=503, detail="S3/Allas storage not configured")

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="regionOne",
            config=BotoConfig(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

        video_key = f"dental-demo/{video_id}/video.mp4"
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": video_key},
            ExpiresIn=900,  # 15 minutes
        )
        return {"url": url, "expires_in": 900}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate playback URL: {e}") from e


@router.get("/videos/{video_id}/thumbnail")
async def get_thumbnail_url(video_id: str):
    """Generate a presigned Allas S3 URL for video thumbnail."""
    bucket = os.getenv("ALLAS_BUCKET_NAME")
    endpoint = os.getenv("ALLAS_ENDPOINT_URL")
    access_key = os.getenv("ALLAS_ACCESS_KEY_ID")
    secret_key = os.getenv("ALLAS_SECRET_ACCESS_KEY")

    if not all([bucket, endpoint, access_key, secret_key]):
        raise HTTPException(status_code=503, detail="S3/Allas storage not configured")

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="regionOne",
            config=BotoConfig(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

        thumb_key = f"dental-demo/{video_id}/thumbnail.jpg"
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": thumb_key},
            ExpiresIn=900,
        )
        return {"url": url, "expires_in": 900}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail URL: {e}") from e


@router.post("/search", response_model=SearchResponse)
async def search_videos(
    query: str = Form(...),
    top_k: int = Form(10),
    video_id: str = Form(None),
    search_type: str = Form("hybrid"),
):
    """
    Search indexed video segments.

    - **query**: Natural language search query
    - **top_k**: Maximum results (default 10)
    - **video_id**: Optional filter to search within a specific video
    - **search_type**: hybrid, semantic, or keyword
    """
    store = _get_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    embedder = _get_embedder()
    if embedder is None and search_type != "keyword":
        raise HTTPException(status_code=503, detail="Embedder not configured")

    filters = {"video_id": video_id} if video_id else None

    try:
        from gaik.software_components.RAG.pg_vector_store.video_search_helpers import (
            format_search_results,
        )

        if search_type == "keyword":
            results = store.search_keyword(query, top_k=top_k, filters=filters)
        elif search_type == "semantic":
            query_embedding = embedder.embed_query(query)
            results = store.search_semantic(
                query_embedding, top_k=top_k, threshold=0.0, filters=filters
            )
        else:
            # Hybrid with adaptive weights
            query_embedding = embedder.embed_query(query)
            word_count = len(query.split())
            if word_count <= 2:
                sem_w, kw_w = 0.3, 0.7
            elif word_count <= 5:
                sem_w, kw_w = 0.5, 0.5
            else:
                sem_w, kw_w = 0.7, 0.3

            results = store.search_hybrid(
                query_embedding,
                query,
                top_k=top_k,
                semantic_weight=sem_w,
                keyword_weight=kw_w,
                filters=filters,
            )

        formatted = format_search_results(results)

        return SearchResponse(
            results=[SearchResult(**r) for r in formatted],
            query=query,
            total_results=len(formatted),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ingest/stream")
async def ingest_srt_stream(
    file: UploadFile = File(...),
    video_title: str = Form(...),
    video_id: str = Form(None),
):
    """
    Ingest an SRT subtitle file: parse, chunk, embed, and store segments.
    Returns SSE progress events.
    """
    store = _get_store()
    embedder = _get_embedder()

    if store is None:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": "Database not configured (DATABASE_URL missing)"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    if embedder is None:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": "Embedder not configured (API key missing)"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    if not file.filename:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": "No filename provided"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    srt_content = (await file.read()).decode("utf-8", errors="replace")

    import uuid as uuid_mod

    vid = video_id or uuid_mod.uuid4().hex[:12]

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Parse SRT", "status": "pending"},
            {"step": 2, "name": "Chunk Segments", "status": "pending"},
            {"step": 3, "name": "Generate Embeddings", "status": "pending"},
            {"step": 4, "name": "Store in Database", "status": "pending"},
        ]

        yield sse_event("steps", {"steps": steps})

        try:
            import asyncio

            from gaik.software_components.transcriber.srt_utils import chunk_segments, parse_srt

            # Step 1: Parse SRT
            steps[0]["status"] = "in_progress"
            steps[0]["message"] = "Parsing subtitle file..."
            yield sse_event("step_update", steps[0])

            segments = parse_srt(srt_content)

            steps[0]["status"] = "completed"
            steps[0]["message"] = f"Parsed {len(segments)} subtitle cues"
            yield sse_event("step_update", steps[0])

            # Step 2: Chunk
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Grouping into search chunks..."
            yield sse_event("step_update", steps[1])

            chunks = chunk_segments(segments, target_seconds=45)

            steps[1]["status"] = "completed"
            steps[1]["message"] = f"Created {len(chunks)} search chunks"
            yield sse_event("step_update", steps[1])

            # Step 3: Embed
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = f"Generating embeddings for {len(chunks)} chunks..."
            yield sse_event("step_update", steps[2])

            from gaik.software_components.RAG.pg_vector_store.video_search_helpers import (
                ingest_video_segments,
            )

            ids = await asyncio.to_thread(
                ingest_video_segments,
                store,
                embedder,
                video_title=video_title,
                video_id=vid,
                segments=chunks,
            )

            steps[2]["status"] = "completed"
            steps[2]["message"] = f"Generated {len(ids)} embeddings"
            yield sse_event("step_update", steps[2])

            # Step 4: Done (storage happened in ingest_video_segments)
            steps[3]["status"] = "completed"
            steps[3]["message"] = f"Stored {len(ids)} segments in database"
            yield sse_event("step_update", steps[3])

            yield sse_event(
                "result",
                {
                    "video_id": vid,
                    "video_title": video_title,
                    "segments_stored": len(ids),
                    "total_segments_in_db": store.count(),
                },
            )

        except Exception as e:
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/clear")
async def clear_all_segments():
    """Clear all indexed video segments from the database."""
    store = _get_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        conn = store._get_conn()
        result = conn.execute(f"DELETE FROM {TABLE_NAME}")
        conn.commit()
        return {"deleted": result.rowcount, "message": "All segments cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
