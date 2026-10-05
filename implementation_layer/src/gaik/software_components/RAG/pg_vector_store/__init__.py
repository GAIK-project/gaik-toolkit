"""PostgreSQL vector store building block with semantic, keyword, and hybrid search."""

from .pg_vector_store import HealthReport, PgVectorStore
from .video_search_helpers import format_search_results, ingest_video_segments

__all__ = [
    "HealthReport",
    "PgVectorStore",
    "ingest_video_segments",
    "format_search_results",
]

__version__ = "0.1.0"
