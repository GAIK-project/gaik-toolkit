"""Vector store with in-memory and Chroma-backed persistence."""

from __future__ import annotations

import math
import uuid
import warnings

from gaik.software_components.RAG._chunk_ids import chunk_ids, with_document_id

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "VectorStore requires 'langchain-core'. "
        "Install extras with 'pip install gaik[vector-store]'"
    ) from exc


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


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
        self._ids: list[str] = []

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

    def add(
        self,
        documents: list[Document],
        embeddings: list[list[float]],
        *,
        replace: bool = False,
    ) -> None:
        """Store chunks with their embeddings.

        Each chunk's id comes from its document and its text (see
        ``_chunk_ids``): the document is ``metadata["document_id"]``, else
        ``source``, else ``document_name``, and is stored as ``document_id``.
        Adding a chunk that is already stored updates it instead of storing a
        second copy. A chunk whose metadata names no document is stored as a new
        one each time.

        Args:
            documents: The chunks.
            embeddings: Their embeddings, in the same order.
            replace: First delete every stored chunk of each document in
                ``documents``, so chunks the document no longer has do not stay
                behind. Pass all of a document's chunks in one call. For a
                persisted store, a failure after the delete leaves the document
                out until it is added again.
        """
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have the same length")
        if not documents:
            return

        # A chunk that names no document gets a new id, as before.
        keyed = [
            (doc_id, chunk_id or uuid.uuid4().hex) for doc_id, chunk_id in chunk_ids(documents)
        ]
        stored = [
            Document(page_content=doc.page_content, metadata=with_document_id(doc.metadata, doc_id))
            for doc, (doc_id, _) in zip(documents, keyed)
        ]
        if replace:
            for doc_id in dict.fromkeys(
                doc.metadata["document_id"] for doc in stored if "document_id" in doc.metadata
            ):
                self.delete_document(doc_id)

        if not self.persist:
            position = {chunk_id: index for index, chunk_id in enumerate(self._ids)}
            for doc, embedding, (_, chunk_id) in zip(stored, embeddings, keyed):
                if chunk_id in position:
                    self._documents[position[chunk_id]] = doc
                    self._embeddings[position[chunk_id]] = embedding
                else:
                    position[chunk_id] = len(self._ids)
                    self._ids.append(chunk_id)
                    self._documents.append(doc)
                    self._embeddings.append(embedding)
            return

        ids = [f"{self.collection_name}_{chunk_id}" for _, chunk_id in keyed]
        texts = [doc.page_content for doc in stored]
        metadatas = [_chroma_metadata(doc.metadata) for doc in stored]
        # Chroma rejects a single call above its maximum batch size, so send
        # slices. If one fails, the slices before it stay stored.
        batch = _max_batch_size(self._client) or len(ids)
        for start in range(0, len(ids), batch):
            end = start + batch
            self._collection.upsert(  # type: ignore[union-attr]
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )

    def delete_document(self, document_id) -> int:
        """Delete every chunk whose ``document_id`` is ``document_id``.

        ``add()`` stores ``document_id`` with each chunk (the chunk's own
        ``document_id``, else its ``source``, else its ``document_name``).
        Chunks stored by a gaik release before that have none and are not
        found: index them again into a new collection.

        Returns:
            The number of chunks deleted.
        """
        if not self.persist:
            keep = [
                index
                for index, doc in enumerate(self._documents)
                if doc.metadata.get("document_id") != document_id
            ]
            deleted = len(self._documents) - len(keep)
            if deleted:
                self._documents = [self._documents[i] for i in keep]
                self._embeddings = [self._embeddings[i] for i in keep]
                self._ids = [self._ids[i] for i in keep]
            return deleted

        where = {"document_id": document_id}
        found = self._collection.get(where=where, include=[])  # type: ignore[union-attr]
        ids = list(found.get("ids") or [])
        if ids:
            self._collection.delete(where=where)  # type: ignore[union-attr]
        return len(ids)

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
        if self._space != "cosine":
            query_kwargs["include"].append("embeddings")
        if filters:
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
