"""Vector store with in-memory and Chroma-backed persistence."""

from __future__ import annotations

import math
import uuid
import warnings

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "VectorStore requires 'langchain-core'. "
        "Install extras with 'pip install gaik[vector-store]'"
    ) from exc


OWNER_KEY = "gaik_owner"
"""Metadata key under which a store with an ``owner`` records it on every chunk."""


def check_owner(owner: str | None) -> str | None:
    """``owner`` as given, or raise ``ValueError`` for a blank or non-string one."""
    if owner is None:
        return None
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner must be a non-blank string, such as a user or session id")
    return owner


def refuse_foreign_owner(documents) -> None:
    """Raise ``ValueError`` if a document's metadata already names an owner.

    A store without an owner would store such a chunk as it is, and it would then show
    up in that owner's searches: content planted into another user's view.
    """
    for doc in documents:
        if OWNER_KEY in (doc.metadata or {}):
            raise ValueError(
                f"metadata key {OWNER_KEY!r} is set by a store with an owner; "
                "add these documents through a store created with owner=..."
            )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """Store embeddings with metadata and provide similarity search.

    With ``owner`` (a user or session id), every chunk this store adds is recorded
    for that owner, and :meth:`search` and :meth:`count` see only that owner's
    chunks, whatever the caller's filters say. This is a filter in gaik, not access
    control: every process that can open the folder (a store without an owner, an
    older gaik, chromadb itself) still reads and writes every chunk, so it is trusted
    the same. Separate users who must not reach each other's data with separate
    collections or folders.
    """

    def __init__(
        self,
        *,
        persist: bool = False,
        persist_path: str = "chroma_store",
        collection_name: str = "gaik_rag",
        owner: str | None = None,
    ) -> None:
        self.persist = persist
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.owner = check_owner(owner)

        self._embeddings: list[list[float]] = []
        self._documents: list[Document] = []

        self._collection = None
        self._client = None
        self._space = "cosine"
        if self.persist:
            try:
                import chromadb
            except ImportError as exc:
                raise ImportError(
                    "Chroma persistence requires 'chromadb'. "
                    "Install extras with 'pip install gaik[vector-store]'"
                ) from exc

            self._client = chromadb.PersistentClient(path=self.persist_path)
            # Cosine space, so that ``1 - distance`` is the same cosine similarity
            # the in-memory store returns. Chroma's default space is l2.
            self._collection = self._client.get_or_create_collection(
                self.collection_name, metadata={"hnsw:space": "cosine"}
            )
            self._space = _collection_space(self._collection)
            if self._space != "cosine":
                warnings.warn(
                    f"Chroma collection {self.collection_name!r} uses the "
                    f"{self._space!r} space. Scores are cosine similarities "
                    "computed from the stored embeddings, but the candidates are "
                    "still chosen in that space. Re-index into a new collection "
                    "to search by cosine.",
                    stacklevel=2,
                )

    def add(self, documents: list[Document], embeddings: list[list[float]]) -> None:
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have the same length")
        documents = self._owned(documents)

        if not self.persist:
            self._documents.extend(documents)
            self._embeddings.extend(embeddings)
            return

        if not documents:
            return
        # A new id for every document: ids counted from zero on each call collided
        # with the ones already stored, and Chroma drops such a document silently.
        ids = [f"{self.collection_name}_{uuid.uuid4().hex}" for _ in documents]
        texts = [doc.page_content for doc in documents]
        metadatas = [_chroma_metadata(doc.metadata) for doc in documents]
        # Chroma rejects a single add above its maximum batch size, so send
        # slices. If one fails, the slices before it stay stored.
        batch = _max_batch_size(self._client) or len(ids)
        for start in range(0, len(ids), batch):
            end = start + batch
            self._collection.add(  # type: ignore[union-attr]
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )

    def _owned(self, documents: list[Document]) -> list[Document]:
        """``documents`` recorded for this store's owner (copies; the caller's are kept)."""
        if self.owner is None:
            refuse_foreign_owner(documents)
            return documents
        return [
            Document(
                page_content=doc.page_content,
                metadata={**(doc.metadata or {}), OWNER_KEY: self.owner},
            )
            for doc in documents
        ]

    def count(self) -> int:
        """Return the number of documents in the vector store (this owner's, with one)."""
        if not self.persist:
            if self.owner is None:
                return len(self._documents)
            return sum(1 for d in self._documents if d.metadata.get(OWNER_KEY) == self.owner)

        if self._collection is None:
            return 0

        if self.owner is not None:
            return len(self._collection.get(where={OWNER_KEY: self.owner}, include=[])["ids"])
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
                if self.owner is not None and doc.metadata.get(OWNER_KEY) != self.owner:
                    continue
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
        if self._space != "cosine":
            query_kwargs["include"].append("embeddings")
        if self.owner is not None:
            # The owner is always one of the conditions, so a filter cannot widen it.
            owner_where = {OWNER_KEY: self.owner}
            query_kwargs["where"] = (
                {"$and": [owner_where, _chroma_where(filters)]} if filters else owner_where
            )
        elif filters:
            query_kwargs["where"] = _chroma_where(filters)

        results = self._collection.query(  # type: ignore[union-attr]
            **query_kwargs
        )

        docs: list[Document] = []
        scores: list[float] = []
        stored = results.get("embeddings")
        for index, (doc_text, meta, dist) in enumerate(
            zip(
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
                results.get("distances", [[]])[0],
            )
        ):
            docs.append(Document(page_content=doc_text, metadata=meta or {}))
            if self._space == "cosine":
                scores.append(1.0 - float(dist))
            else:
                vector = [float(x) for x in stored[0][index]]  # type: ignore[index]
                scores.append(_cosine_similarity(query_embedding, vector))

        if self._space != "cosine":
            ranked = sorted(zip(docs, scores), key=lambda item: item[1], reverse=True)
            return ranked
        return list(zip(docs, scores))


def _collection_space(collection) -> str:
    """The distance space a Chroma collection was created with (default l2)."""
    configuration = getattr(collection, "configuration", None)
    if isinstance(configuration, dict):
        space = (configuration.get("hnsw") or {}).get("space")
        if space:
            return str(space)
    return str((collection.metadata or {}).get("hnsw:space", "l2"))


def _max_batch_size(client) -> int | None:
    getter = getattr(client, "get_max_batch_size", None)
    if getter is None:
        return None
    try:
        size = int(getter())
    except Exception:  # noqa: BLE001 - an older client may not report it
        return None
    return size if size > 0 else None


def _chroma_metadata(metadata: dict | None) -> dict | None:
    """Metadata as Chroma stores it: no ``None`` values, and ``None`` when empty.

    Chroma rejects a ``None`` value and an empty dict. A key left out reads back
    the same as one set to ``None``.
    """
    kept = {key: value for key, value in (metadata or {}).items() if value is not None}
    return kept or None


def _chroma_where(filters: dict) -> dict:
    """``filters`` as a Chroma ``where``: several keys must all match."""
    if len(filters) > 1 and not any(str(key).startswith("$") for key in filters):
        return {"$and": [{key: value} for key, value in filters.items()]}
    return filters


def _match_filters(metadata: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if metadata.get(key) != value:
            return False
    return True
