"""Minimal example for running Retriever with vector store."""

from __future__ import annotations

from langchain_core.documents import Document

from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.retriever import Retriever
from gaik.software_components.RAG.vector_store import VectorStore
from gaik.software_components.config import get_openai_config


def main() -> None:
    config = get_openai_config(use_azure=True)
    embedder = Embedder(config=config)
    store = VectorStore(persist=False)

    docs = [
        Document(page_content="Invoice total is 1500 USD", metadata={"page_number": 1}),
        Document(page_content="Budget is 2.5M EUR", metadata={"page_number": 2}),
    ]
    embeddings, documents = embedder.embed(docs)
    store.add(documents, embeddings)

    retriever = Retriever(embedder=embedder, vector_store=store, hybrid_search=True)
    results = retriever.search("What is the total?", include_scores=True)

    for doc in results:
        print(doc.metadata)


if __name__ == "__main__":
    main()
