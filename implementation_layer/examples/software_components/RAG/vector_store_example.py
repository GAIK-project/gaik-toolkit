"""Minimal example for using VectorStore with embeddings."""

from __future__ import annotations

from langchain_core.documents import Document

from gaik.software_components.RAG.vector_store import VectorStore


def main() -> None:
    docs = [
        Document(page_content="First chunk", metadata={"page_number": 1}),
        Document(page_content="Second chunk", metadata={"page_number": 2}),
    ]
    embeddings = [
        [0.1, 0.2, 0.3],
        [0.2, 0.1, 0.4],
    ]

    store = VectorStore(persist=False)
    store.add(docs, embeddings)

    results = store.search([0.1, 0.2, 0.3], top_k=2)
    for doc, score in results:
        print(doc.metadata, score)


if __name__ == "__main__":
    main()
