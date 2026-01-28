"""Vector store with in-memory and Chroma-backed persistence."""

from __future__ import annotations

import math
from collections.abc import Iterable

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "VectorStore requires 'langchain-core'. Install extras with 'pip install gaik[vector-store]'"
    ) from exc


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _iter_indices(n: int) -> Iterable[int]:
    return range(n)


class VectorStore:
    """Store embeddings with metadata and provide similarity search."""

    def __init__(
        self,
        *,
        persist: bool = False,
        persist_path: str = "chroma_store",
        collection_name: str = "gaik_rag",
    ) -> None:
        self.persist = persist
        self.persist_path = persist_path
        self.collection_name = collection_name

        self._embeddings: list[list[float]] = []
        self._documents: list[Document] = []

        self._collection = None
        if self.persist:
            try:
                import chromadb
            except ImportError as exc:
                raise ImportError(
                    "Chroma persistence requires 'chromadb'. "
                    "Install extras with 'pip install gaik[vector-store]'"
                ) from exc

            client = chromadb.PersistentClient(path=self.persist_path)
            self._collection = client.get_or_create_collection(self.collection_name)

    def add(self, documents: list[Document], embeddings: list[list[float]]) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have the same length")

        if not self.persist:
            self._documents.extend(documents)
            self._embeddings.extend(embeddings)
            return

        ids = [f"{self.collection_name}_{i}" for i in _iter_indices(len(embeddings))]
        self._collection.add(  # type: ignore[union-attr]
            ids=ids,
            embeddings=embeddings,
            documents=[doc.page_content for doc in documents],
            metadatas=[doc.metadata for doc in documents],
        )

    def count(self) -> int:
        """Return the number of documents in the vector store."""
        if not self.persist:
            return len(self._documents)

        if self._collection is None:
            return 0

        return self._collection.count()

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[tuple[Document, float]]:
        if not self.persist:
            scored = []
            for idx, embedding in enumerate(self._embeddings):
                doc = self._documents[idx]
                if filters and not _match_filters(doc.metadata, filters):
                    continue
                score = _cosine_similarity(query_embedding, embedding)
                scored.append((doc, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            return scored[:top_k]

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            query_kwargs["where"] = filters

        results = self._collection.query(  # type: ignore[union-attr]
            **query_kwargs
        )

        docs: list[Document] = []
        scores: list[float] = []
        for doc_text, meta, dist in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
        ):
            docs.append(Document(page_content=doc_text, metadata=meta or {}))
            scores.append(1.0 - float(dist))

        return list(zip(docs, scores))


def _match_filters(metadata: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if metadata.get(key) != value:
            return False
    return True
