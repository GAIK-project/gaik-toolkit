"""Example: Semantic video search with pgvector.

Demonstrates:
1. Ingest video transcript segments into PgVectorStore
2. Search segments with hybrid (semantic + keyword) search
3. Format results with timestamps

Prerequisites:
    # Start a pgvector database
    docker run -d --name pgvector-test -p 5432:5432 \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=vector_test \
        pgvector/pgvector:pg17

    # Install dependencies
    pip install gaik[pg-vector-store,embedder]

    # Set environment variables (or use .env file)
    AZURE_API_KEY=your-key
    AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from gaik.software_components.RAG.pg_vector_store.video_search_helpers import (
    format_search_results,
    ingest_video_segments,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/vector_test",
)


def main() -> None:
    # 1. Set up embedder and vector store
    config = get_openai_config(use_azure=True)
    embedder = Embedder(config=config, model="text-embedding-3-small")

    with PgVectorStore(
        DATABASE_URL,
        table_name="video_segments",
        embedding_dim=1536,
        fts_language="simple",
    ) as store:
        store.setup()
        print("Database schema ready.\n")

        # 2. Prepare sample segments (normally from Whisper transcription)
        sample_segments = [
            {
                "start": 0.0,
                "end": 45.0,
                "text": "Today we will discuss dental implant placement. "
                "The procedure begins with a thorough examination "
                "and 3D imaging to plan the implant position.",
            },
            {
                "start": 45.0,
                "end": 90.0,
                "text": "After local anesthesia, a small incision is made "
                "in the gum tissue. The implant is then carefully "
                "placed into the jawbone at the planned angle.",
            },
            {
                "start": 90.0,
                "end": 135.0,
                "text": "Osseointegration takes several months. During this "
                "healing period, the titanium implant fuses with the "
                "surrounding bone tissue to create a stable foundation.",
            },
            {
                "start": 135.0,
                "end": 180.0,
                "text": "Finally, the abutment and crown are attached. "
                "The prosthetic tooth is custom-made to match the "
                "patient's existing teeth in color and shape.",
            },
        ]

        # 3. Ingest segments
        print("Ingesting video segments...")
        ids = ingest_video_segments(
            store,
            embedder,
            video_title="Dental Implant Procedure Overview",
            video_id="demo_implant_01",
            segments=sample_segments,
            extra_metadata={"source": "example"},
        )
        print(f"Stored {len(ids)} segments (IDs: {ids})\n")

        # 4. Hybrid search
        query = "how long does implant healing take"
        print(f'--- Hybrid Search: "{query}" ---')
        query_embedding = embedder.embed_query(query)

        results = store.search_hybrid(
            query_embedding,
            query,
            top_k=3,
            semantic_weight=0.6,
            keyword_weight=0.4,
        )

        formatted = format_search_results(results)
        for r in formatted:
            print(f"  [{r['score']:.4f}] {r['timestamp']}")
            print(f"    {r['video_title']}: {r['text'][:80]}...")
        print()

        # 5. Keyword search
        keyword = "titanium bone"
        print(f'--- Keyword Search: "{keyword}" ---')
        results = store.search_keyword(keyword, top_k=3)
        formatted = format_search_results(results)
        for r in formatted:
            print(f"  [{r['score']:.4f}] {r['timestamp']}: {r['text'][:80]}...")
        print()

        # 6. Semantic search with metadata filter
        print("--- Semantic Search (filtered by video_id) ---")
        results = store.search_semantic(
            query_embedding,
            top_k=3,
            threshold=0.0,
            filters={"video_id": "demo_implant_01"},
        )
        formatted = format_search_results(results)
        for r in formatted:
            print(f"  [{r['score']:.4f}] {r['timestamp']}: {r['text'][:80]}...")
        print()

        # 7. Cleanup
        deleted = store.delete(ids)
        print(f"Cleaned up: deleted {deleted} documents")


if __name__ == "__main__":
    main()
