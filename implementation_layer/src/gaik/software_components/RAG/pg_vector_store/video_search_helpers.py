"""Video search helpers built on PgVectorStore.

Thin convenience layer for ingesting video transcription segments
and formatting search results with timestamps. Keeps PgVectorStore
itself generic for any document RAG use case.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gaik.software_components.RAG.embedder import Embedder

    from .pg_vector_store import PgVectorStore

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "video_search_helpers requires 'langchain-core'. "
        "Install with 'pip install gaik[pg-vector-store]'"
    ) from exc


def format_timestamp(seconds: float) -> str:
    """Format seconds as ``MM:SS``."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def ingest_video_segments(
    store: PgVectorStore,
    embedder: Embedder,
    *,
    video_title: str,
    video_id: str | None = None,
    segments: list[dict[str, Any]],
    extra_metadata: dict[str, Any] | None = None,
) -> list[int]:
    """Embed and store video transcription segments.

    Each segment dict must have ``start`` (float), ``end`` (float),
    ``text`` (str), and optionally ``srt_index`` (int).

    Args:
        store: Initialised PgVectorStore (``setup()`` already called).
        embedder: Embedder instance for generating embeddings.
        video_title: Human-readable video title.
        video_id: Unique video identifier (auto-generated if omitted).
        segments: Chunked transcription segments.
        extra_metadata: Additional metadata merged into every segment.

    Returns:
        List of inserted row IDs.
    """
    if not segments:
        return []

    video_id = video_id or uuid.uuid4().hex[:12]

    documents: list[Document] = []
    for seg in segments:
        meta: dict[str, Any] = {
            "video_title": video_title,
            "video_id": video_id,
            "start_seconds": seg["start"],
            "end_seconds": seg["end"],
            "srt_index": seg.get("srt_index", 0),
            "title": video_title,
        }
        if extra_metadata:
            meta.update(extra_metadata)

        documents.append(Document(page_content=seg["text"], metadata=meta))

    texts = [doc.page_content for doc in documents]
    embeddings, _ = embedder.embed(texts)

    return store.add(documents, embeddings)


def format_search_results(
    results: list[tuple[Document, float]],
) -> list[dict[str, Any]]:
    """Convert PgVectorStore search results to video-search-friendly dicts.

    Returns:
        List of dicts with ``text``, ``video_title``, ``video_id``,
        ``start_seconds``, ``end_seconds``, ``timestamp``, ``score``.
    """
    formatted: list[dict[str, Any]] = []
    for doc, score in results:
        meta = doc.metadata or {}
        start = meta.get("start_seconds", 0)
        end = meta.get("end_seconds", 0)
        formatted.append({
            "text": doc.page_content,
            "video_title": meta.get("video_title", ""),
            "video_id": meta.get("video_id", ""),
            "start_seconds": start,
            "end_seconds": end,
            "timestamp": f"{format_timestamp(start)} - {format_timestamp(end)}",
            "score": round(score, 4),
        })
    return formatted
