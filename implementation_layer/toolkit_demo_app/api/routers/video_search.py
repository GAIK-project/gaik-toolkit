"""Semantic video search router - Hybrid search over transcribed video segments.

Every visitor searches the same index, so the API only reads it. The index is
seeded with ``api/scripts/seed_dental_demo.py``, which writes to the database
directly.

A video's playback and thumbnail routes hand out signed storage links. The
proxy (``proxy.ts``) forwards them for a signed-in user only and then sets
``x-gaik-signed-in``; a request without it gets no link.
"""

import logging
import os

try:
    from utils import generate_presigned_url
except ImportError:
    from api.utils import generate_presigned_url
from fastapi import APIRouter, Form, Header, HTTPException
from pydantic import BaseModel

try:
    from utils.errors import error_detail
except ImportError:
    from api.utils.errors import error_detail

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons (lazy-initialised)
_store = None
_embedder = None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
TABLE_NAME = "video_segments"
FTS_LANGUAGE = "simple"

# Set by the proxy, never by the browser, once it has found the user signed in.
SIGNED_IN_HEADER = "x-gaik-signed-in"


def _require_signed_in(signed_in: str | None) -> None:
    if signed_in != "1":
        raise HTTPException(status_code=401, detail="Sign in to use this feature.")


def _get_store():
    """Lazy-init PgVectorStore singleton."""
    global _store
    if _store is not None:
        return _store

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None

    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    _store = PgVectorStore(
        db_url,
        table_name=TABLE_NAME,
        embedding_dim=EMBEDDING_DIM,
        fts_language=FTS_LANGUAGE,
        # Users type questions; websearch mode ANDs every word, so a sentence
        # query got no keyword hits at all. Needs gaik >= 0.7.3 for hybrid.
        tsquery_mode="or",
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
    if not use_azure:
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
        raise HTTPException(status_code=500, detail=error_detail(e)) from e


@router.get("/videos/{video_id}/play")
async def get_playback_url(
    video_id: str,
    signed_in: str | None = Header(None, alias=SIGNED_IN_HEADER),
):
    """Generate a presigned Allas S3 URL for video playback (signed-in users)."""
    _require_signed_in(signed_in)
    return generate_presigned_url(video_id, "video.mp4", label="video")


@router.get("/videos/{video_id}/thumbnail")
async def get_thumbnail_url(
    video_id: str,
    signed_in: str | None = Header(None, alias=SIGNED_IN_HEADER),
):
    """Generate a presigned Allas S3 URL for video thumbnail (signed-in users)."""
    _require_signed_in(signed_in)
    return generate_presigned_url(video_id, "thumbnail.jpg", label="thumbnail")


@router.post("/search", response_model=SearchResponse)
async def search_videos(
    query: str = Form(...),
    top_k: int = Form(10, ge=1, le=100),
    video_id: str = Form(None),
    search_type: str = Form("hybrid"),
):
    """
    Search indexed video segments.

    - **query**: Natural language search query
    - **top_k**: Maximum results, 1 to 100 (default 10)
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
        raise HTTPException(status_code=500, detail=error_detail(e)) from e
