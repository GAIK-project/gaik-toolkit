"""Example: hybrid search over your own documents with PostgreSQL and pgvector.

This script demonstrates how to:
1. Create the table, indexes and search functions
2. Index documents with their embeddings
3. Search in three modes - hybrid, vector and keyword - and compare them
4. Check that both arms of the hybrid search are alive
5. Decide whether a query found anything relevant at all

Prerequisites:
    # Start a pgvector database
    docker run -d --name pgvector-test -p 5432:5432 \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=vector_test \
        pgvector/pgvector:pg17

    # Install dependencies
    pip install "gaik[pg-vector-store,embedder,ranker]"

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

import psycopg
from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from gaik.software_components.RAG.ranker import Ranker
from gaik.software_components.RAG.relevance_gate import RelevanceGate
from langchain_core.documents import Document

# Connection string (override with DATABASE_URL environment variable)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/vector_test",
)

# The model's output size must equal EMBEDDING_DIM, and pgvector's HNSW index
# takes at most 2,000 dimensions. On Azure, the model name is your deployment.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
TABLE = "handbook_chunks"

HANDBOOK = [
    (
        "Holiday pay",
        "pay",
        "Holiday pay is paid before the annual leave begins. It amounts to 50 percent "
        "of the salary for the leave period.",
    ),
    (
        "Night work",
        "pay",
        "A night work supplement is paid for hours worked between 11 pm and 6 am. "
        "The rate is set in section 12 of the collective agreement.",
    ),
    (
        "Overtime",
        "pay",
        "The first two hours of overtime are paid at a 50 percent premium. Overtime "
        "always requires the employer's initiative.",
    ),
    (
        "Travel expenses",
        "finance",
        "Travel expense claims are filed within two months of the trip. Mileage is "
        "claimed on form ML-204.",
    ),
    (
        "Annual accounts",
        "finance",
        "The annual accounts are prepared within four months of the end of the "
        "financial year and approved by the general meeting.",
    ),
    (
        "Probation",
        "employment",
        "A probationary period can last up to six months. During it either party can "
        "end the contract without a notice period.",
    ),
    (
        "Notice period",
        "employment",
        "The employer's notice period is 14 days when the employment has lasted at most one year.",
    ),
    (
        "Sick leave",
        "employment",
        "Report a sickness absence to your supervisor without delay. A medical "
        "certificate is required for absences longer than three days.",
    ),
    (
        "Remote work",
        "employment",
        "Remote work is agreed in writing with your supervisor. The employer provides "
        "the equipment needed for it.",
    ),
    (
        "Onboarding",
        "employment",
        "Onboarding starts on the first working day and is the responsibility of the "
        "new employee's supervisor.",
    ),
]


def show(label: str, results: list[tuple[Document, float]]) -> None:
    titles = ", ".join(doc.metadata["title"] for doc, _ in results) or "(nothing)"
    print(f"  {label:<8} {titles}")


def main() -> None:
    embedder = Embedder(get_openai_config(use_azure=True), model=EMBEDDING_MODEL)

    with PgVectorStore(
        DATABASE_URL,
        table_name=TABLE,
        embedding_dim=EMBEDDING_DIM,
        fts_language="english",  # the Postgres text search configuration
        tsquery_mode="or",  # a full question still matches; ts_rank_cd ranks
        hnsw_ef_search=100,
    ) as store:
        # 1. Table, HNSW + GIN indexes and SQL functions. Safe to call again.
        store.setup()

        # 2. Index
        docs = [
            Document(page_content=text, metadata={"title": title, "category": category})
            for title, category, text in HANDBOOK
        ]
        embeddings, docs = embedder.embed(docs)
        ids = store.add(docs, embeddings)
        print(f"Indexed {len(ids)} chunks\n")

        # 3. Three modes over the same data. Keep all three reachable in your
        # application: comparing them is how you see what each arm contributes.
        def search(query: str, mode: str = "hybrid", top_k: int = 3, filters: dict | None = None):
            if mode == "keyword":
                return store.search_keyword(query, top_k=top_k, filters=filters)
            vector = embedder.embed_query(query)
            if mode == "vector":
                return store.search_semantic(vector, top_k=top_k, threshold=0.0, filters=filters)
            return store.search_hybrid(vector, query, top_k=top_k, filters=filters)

        for query in ("When do I get my holiday pay?", "ML-204", "working from home"):
            print(f'"{query}"')
            for mode in ("hybrid", "vector", "keyword"):
                show(mode, search(query, mode))
            print()

        print('"extra pay", only category "pay"')
        show("hybrid", search("extra pay", filters={"category": "pay"}))
        print()

        # Per-result provenance: fuse the two lists yourself and every hit says
        # which arm found it and at what rank.
        query = "form for mileage claims"
        vector = embedder.embed_query(query)
        semantic = store.search_semantic(vector, top_k=20, threshold=0.0)
        keyword = store.search_keyword(query, top_k=20)
        fused = Ranker(expose_ranks=True).fuse(
            semantic, keyword, names=("semantic", "keyword"), weights=(1.0, 1.0), top_k=3
        )
        print(f'"{query}" with ranks per arm')
        for doc, _ in fused:
            ranks = {k: v for k, v in doc.metadata.items() if k.startswith("rank_")}
            print(f"  {doc.metadata['title']:<16} {ranks}")
        print()

        # 4. Health checks. Either arm can stop contributing without an error,
        # because the other one keeps filling the page.
        with psycopg.connect(DATABASE_URL) as conn:
            unindexed = conn.execute(
                f"SELECT count(*) FROM {TABLE} "
                "WHERE text_search IS NULL OR text_search = ''::tsvector"
            ).fetchone()[0]
        print(f"Rows the keyword arm cannot see: {unindexed}")
        print(f"Keyword arm finds a stored word: {bool(search('probationary', 'keyword'))}")
        # On a query with literal matches the two lists should differ. If they
        # never do, across many queries, the keyword arm is contributing nothing.
        probe = "working from home"
        differs = [d.metadata["id"] for d, _ in search(probe, "hybrid")] != [
            d.metadata["id"] for d, _ in search(probe, "vector")
        ]
        print(f"Keyword arm changes the hybrid result: {differs}\n")

        # 5. A result count is not evidence: the vector arm returns its nearest
        # neighbours for any input. What separates an answerable question from
        # an unanswerable one is the similarity of the closest chunk.
        def best_similarity(query: str) -> float:
            hits = store.search_semantic(embedder.embed_query(query), top_k=1, threshold=0.0)
            return hits[0][1]

        answerable = [
            best_similarity(q)
            for q in (
                "When do I get my holiday pay?",
                "How long can a probationary period be?",
                "Who pays for remote work equipment?",
                "How is overtime compensated?",
            )
        ]
        unanswerable = [
            best_similarity(q)
            for q in (
                "asdf qwer zxcv",
                "How do I bake cinnamon rolls?",
                "What is the capital of France?",
                "Best ski resorts in the Alps",
            )
        ]
        reading = RelevanceGate.calibrate(answerable, unanswerable, lower_is_better=False)
        print(reading)
        if reading.separated:
            gate = RelevanceGate(reading.floor, lower_is_better=False)
            for query in ("Who approves the annual accounts?", "Best ski resorts in the Alps"):
                hits = store.search_semantic(embedder.embed_query(query), top_k=3, threshold=0.0)
                answerable_now = gate.is_answerable(hits, key=lambda hit: hit[1])
                print(f'  "{query}" -> {"search" if answerable_now else "nothing relevant"}')

        # 6. Cleanup
        store.delete(ids)


if __name__ == "__main__":
    main()
