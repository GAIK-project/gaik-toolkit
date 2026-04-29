"""FinnishTextProcessor demo — lemmatization + compound splitting for Finnish RAG.

Shows how to use ``FinnishTextProcessor`` standalone and (optionally) plug it
into ``PgVectorStore`` so hybrid search matches inflected forms ("kissan",
"kissoilla" → "kissa") and compound parts ("kerrostalo" → "kerros" + "talo").

Standalone mode: backend=``"simple"`` runs without any extra deps so this
file can be smoke-tested in CI.

For real morphological lemmatization, install one of:

    pip install gaik[finnish-rag]                        # spaCy + UralicNLP
    python -m spacy download fi_core_news_md
    pip install gaik[finnish-rag-voikko]                 # libvoikko system lib

Then re-run with backend="auto" (or "voikko" / "spacy" / "uralic" explicitly)
to see real morphology in action.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure printed Unicode (ä/ö, arrows) survives on Windows cp1252 consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.finnish_text_processor import (  # noqa: E402
    FinnishTextProcessor,
)


def standalone_demo() -> None:
    """Lemmatize a few Finnish phrases without a database."""
    print("=== Standalone FinnishTextProcessor ===\n")

    # backend="auto" tries voikko → spacy → uralic → simple
    # (we use "simple" here so this script runs without extra installs)
    processor = FinnishTextProcessor(backend="simple")
    print(f"Active backend:           {processor.backend_name}")
    print(f"Compound splitting:       {processor.supports_compound_splitting}\n")

    samples = [
        "Kissoilla on neljä jalkaa.",
        "Kerrostalon ovi on kiinni.",
        "Ostin uuden kirjan kaupasta.",
    ]
    for text in samples:
        print(f"Original:   {text}")
        print(f"Lemmas:     {processor.lemmatize(text)}")
        print(f"FTS text:   {processor.to_tsvector_text(text)!r}")
        print(f"Query exp.: {processor.expand_query(text)!r}")
        print()


def pgvector_integration_demo() -> None:
    """Show how to wire the processor into PgVectorStore (no actual DB call here)."""
    print("=== PgVectorStore integration ===\n")
    print("Run this against a real Postgres (with pgvector + pg_trgm + unaccent):")
    print(
        """
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore
    from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

    processor = FinnishTextProcessor(backend="auto")  # uses voikko/spacy/uralic
    with PgVectorStore(
        "postgresql://postgres:postgres@localhost/mydb",
        text_processor=processor,
    ) as store:
        store.setup()

        # On ingest, the processor lemmatizes content into the
        # `content_lemmatized` column; the tsvector is built from that.
        store.add(documents, embeddings)

        # On query, the processor lemmatizes the search text BEFORE
        # `websearch_to_tsquery`, so an inflected query matches lemma-indexed
        # documents.
        results = store.search_hybrid(
            query_embedding=q_vec,
            query_text="kerrostalon kissoilla",   # → "kerros talo kissa"
            top_k=5,
        )
"""
    )


if __name__ == "__main__":
    standalone_demo()
    pgvector_integration_demo()
