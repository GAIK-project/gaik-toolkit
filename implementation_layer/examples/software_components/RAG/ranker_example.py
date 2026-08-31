"""Example: fusing and reordering retrieval results with Ranker.

This script demonstrates how to:
1. Fuse a semantic and a keyword result list with Reciprocal Rank Fusion
2. Weight the arms so one signal counts more than the other
3. Inspect why a document ranked where it did (per-arm ranks)
4. Fuse a third, non-search signal (recency) into the same ranking
5. Reorder by a metadata field with asc / desc
6. Rerank with a cross-encoder, and degrade safely when it is unavailable
7. Flatten results to plain documents carrying their relevance score

Prerequisites:
    # Install dependencies -- pure Python, nothing to download
    pip install gaik[ranker]

    # Optional, only for step 6's cross-encoder:
    pip install gaik[ranker-rerank]

    No database, no API key and no model download are required to run this
    example. The two "search results" below are hand-written so the ranking
    maths is visible.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.ranker import Ranker
from langchain_core.documents import Document


def make_results(*entries: tuple[int, str, float]) -> list[tuple[Document, float]]:
    """Build (Document, score) pairs the way a vector store would return them."""
    return [
        (Document(page_content=text, metadata={"id": doc_id}), score)
        for doc_id, text, score in entries
    ]


def show(title: str, results: list[tuple[Document, float]]) -> None:
    print(f"--- {title} ---")
    for position, (doc, score) in enumerate(results, start=1):
        ranks = {key: value for key, value in doc.metadata.items() if key.startswith("rank_")}
        provenance = f"   {ranks}" if ranks else ""
        print(f"  {position}. [{score:.6f}] {doc.page_content}{provenance}")
    print()


def main() -> None:
    # These are what `store.search_semantic(...)` and `store.search_keyword(...)`
    # would hand you. Note the scores are on completely different scales:
    # cosine similarity in [0, 1] versus an unbounded ts_rank_cd score. Adding
    # them directly would let the keyword arm dominate arbitrarily -- which is
    # exactly why RRF fuses by rank instead.
    semantic = make_results(
        (1, "Dental implants replace a missing tooth root", 0.91),
        (2, "Root canal treatment saves an infected tooth", 0.83),
        (3, "Implant surgery recovery takes a few weeks", 0.77),
    )
    keyword = make_results(
        (3, "Implant surgery recovery takes a few weeks", 4.2),
        (1, "Dental implants replace a missing tooth root", 3.1),
        (4, "Bridge vs implant: cost comparison", 2.8),
    )

    show("Semantic search (cosine similarity)", semantic)
    show("Keyword search (ts_rank_cd)", keyword)

    ranker = Ranker(rrf_k=60)

    # 1. Balanced fusion. Documents found by both arms rise to the top.
    show("Fused, balanced weights", ranker.fuse(semantic, keyword))

    # 2. Weighted fusion. Leaning on the keyword arm reorders the head of the
    #    list -- worth measuring on your own eval set before adopting, since a
    #    badly weighted hybrid can score *worse* than either arm alone.
    show(
        "Fused, keyword-weighted (0.2 / 0.8)",
        ranker.fuse(semantic, keyword, weights=(0.2, 0.8)),
    )

    # 3. Provenance: which arm found what, and at which rank. A document with no
    #    `rank_keyword` was never returned by the keyword arm at all.
    show(
        "Fused, with per-arm ranks",
        ranker.fuse(
            semantic,
            keyword,
            names=("semantic", "keyword"),
            expose_ranks=True,
        ),
    )

    # 4. RRF is not limited to two search arms -- any ranked signal works. Here
    #    a recency ordering is fused in as a third, independently weighted arm.
    recency = make_results(
        (4, "Bridge vs implant: cost comparison", 1.0),
        (2, "Root canal treatment saves an infected tooth", 0.5),
    )
    show(
        "Fused with a recency signal (3 arms)",
        ranker.fuse(
            semantic,
            keyword,
            recency,
            weights=(0.5, 0.3, 0.2),
            names=("semantic", "keyword", "recency"),
            expose_ranks=True,
        ),
    )

    # 5. Reordering by a business field rather than by relevance.
    dated = [
        (Document(page_content="March article", metadata={"date": "2026-03-01"}), 0.5),
        (Document(page_content="January article", metadata={"date": "2026-01-05"}), 0.9),
        (Document(page_content="Undated article", metadata={}), 0.7),
    ]
    show("Ordered by relevance (desc)", ranker.order_by(dated))
    show(
        "Ordered by date, oldest first, undated last",
        ranker.order_by(dated, field="date", direction="asc", missing="last"),
    )
    show(
        "Ordered by date, newest first, undated dropped",
        ranker.order_by(dated, field="date", direction="desc", missing="drop"),
    )

    # 6. Cross-encoder reranking. Without `gaik[ranker-rerank]` installed this
    #    raises ImportError, so the example reports it instead of failing --
    #    a *runtime* failure (timeout, HTTP error) would instead be logged and
    #    the retrieval order returned unchanged.
    print("--- Cross-encoder reranking ---")
    fused = ranker.fuse(semantic, keyword)
    try:
        reranked = ranker.rerank("tooth implant recovery", fused, top_k=3)
        for position, (doc, score) in enumerate(reranked, start=1):
            print(f"  {position}. [{score:+.4f}] {doc.page_content}")
    except ImportError as exc:
        print(f"  Skipped: {exc}")
    print()

    # 7. Flatten to plain documents when a downstream component wants those.
    #    New Document objects are built, so nothing upstream is mutated.
    documents = Ranker.to_documents(ranker.fuse(semantic, keyword, top_k=2))
    print("--- Flattened to documents ---")
    for doc in documents:
        print(f"  {doc.metadata['relevance_score']:.6f}  {doc.page_content}")


if __name__ == "__main__":
    main()
