"""Example: PostgreSQL vector store with semantic, keyword, and hybrid search.

This script demonstrates how to:
1. Connect to a PostgreSQL database with pgvector
2. Set up the schema (table, indexes, search functions)
3. Store documents with embeddings
4. Run semantic, keyword, hybrid (RRF), and weighted hybrid search
5. Filter results by metadata

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

# Load environment variables from .env file BEFORE importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from langchain_core.documents import Document

# Connection string (override with DATABASE_URL environment variable)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/vector_test",
)


def main() -> None:
    # 1. Set up the embedder (uses Azure OpenAI by default)
    config = get_openai_config(use_azure=True)
    embedder = Embedder(config=config)

    # 2. Connect to PostgreSQL and set up schema
    with PgVectorStore(DATABASE_URL) as store:
        store.setup()
        print("Database schema created successfully.\n")

        # 3. Prepare sample documents
        docs = [
            Document(
                page_content="Dental implants are titanium posts surgically placed into "
                "the jawbone to replace missing teeth. The procedure requires careful "
                "planning with 3D imaging and typically takes several months to complete.",
                metadata={"title": "Dental Implants", "category": "implants"},
            ),
            Document(
                page_content="Root canal treatment involves removing infected or damaged "
                "pulp from inside a tooth. The tooth is then cleaned, disinfected, "
                "filled, and sealed to prevent further infection.",
                metadata={"title": "Root Canal Treatment", "category": "endodontics"},
            ),
            Document(
                page_content="Fluoride varnish is applied to teeth to help prevent tooth "
                "decay. It strengthens enamel and is especially recommended for children "
                "and patients with high cavity risk.",
                metadata={"title": "Fluoride Treatment", "category": "prevention"},
            ),
            Document(
                page_content="Orthodontic braces gradually move teeth into proper alignment "
                "using brackets and wires. Modern options include clear aligners that are "
                "nearly invisible and can be removed for eating.",
                metadata={"title": "Orthodontic Treatment", "category": "orthodontics"},
            ),
            Document(
                page_content="Regular dental checkups include professional cleaning, "
                "examination for cavities, gum disease assessment, and oral cancer "
                "screening. Checkups are recommended every six months.",
                metadata={"title": "Dental Checkups", "category": "prevention"},
            ),
        ]

        # 4. Generate embeddings and store documents
        embeddings, documents = embedder.embed(docs)
        ids = store.add(documents, embeddings)
        print(f"Stored {len(ids)} documents (IDs: {ids})")
        print(f"Total documents in store: {store.count()}\n")

        # 5. Semantic search - finds conceptually similar results
        query = "tooth replacement surgery"
        query_embedding = embedder.embed_query(query)
        print(f'--- Semantic Search: "{query}" ---')
        results = store.search_semantic(query_embedding, top_k=3, threshold=0.3)
        for doc, score in results:
            print(f"  [{score:.3f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        print()

        # 6. Keyword search - finds exact term matches
        keyword = "fluoride enamel"
        print(f'--- Keyword Search: "{keyword}" ---')
        results = store.search_keyword(keyword, top_k=3)
        for doc, score in results:
            print(f"  [{score:.4f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        if not results:
            print("  (no keyword matches - try simpler terms)")
        print()

        # 7. Hybrid search (RRF) - combines semantic understanding with keyword matching
        hybrid_query = "prevent cavities"
        query_embedding = embedder.embed_query(hybrid_query)
        print(f'--- Hybrid Search (RRF): "{hybrid_query}" ---')
        results = store.search_hybrid(
            query_embedding,
            hybrid_query,
            top_k=3,
            semantic_weight=0.6,
            keyword_weight=0.4,
        )
        for doc, score in results:
            print(f"  [{score:.4f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        print()

        # 8. Weighted hybrid search - linear score combination
        print(f'--- Weighted Hybrid Search: "{hybrid_query}" (70% semantic, 30% keyword) ---')
        results = store.search_hybrid_weighted(
            query_embedding,
            hybrid_query,
            top_k=3,
            semantic_weight=0.7,
            keyword_weight=0.3,
        )
        for doc, score in results:
            print(f"  [{score:.4f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        print()

        # 9. Metadata filtering - restrict results by category
        print('--- Semantic Search with filter: category="prevention" ---')
        results = store.search_semantic(
            query_embedding,
            top_k=3,
            threshold=0.0,
            filters={"category": "prevention"},
        )
        for doc, score in results:
            print(f"  [{score:.3f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        print()

        # 10. VectorStore-compatible search (works with existing Retriever)
        print("--- VectorStore-compatible search() ---")
        results = store.search(query_embedding, top_k=2)
        for doc, score in results:
            print(f"  [{score:.3f}] {doc.metadata.get('title')}: {doc.page_content[:70]}...")
        print()

        # 11. Cleanup
        deleted = store.delete(ids)
        print(f"Cleaned up: deleted {deleted} documents")
        print(f"Remaining: {store.count()} documents")


if __name__ == "__main__":
    main()
