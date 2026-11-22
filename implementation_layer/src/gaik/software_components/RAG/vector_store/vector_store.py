"""Vector store with in-memory and Chroma-backed persistence."""

from __future__ import annotations

import math
import os
import sys
import threading
import uuid
import warnings
from collections.abc import Hashable, Iterable, Iterator
from contextlib import contextmanager

from gaik.software_components.RAG._chunk_ids import (
    DOCUMENT_KEY,
    chunk_ids,
    delete_scope,
    document_scopes,
    in_scope,
    with_document_id,
)

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


class _KeyedLocks:
    """One lock per key, for the writers of that key in this process.

    A key's lock exists while a thread holds it or waits for it, so a process that
    writes many documents keeps no lock per document.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._entries: dict[Hashable, list] = {}  # key -> [lock, threads using it]

    @staticmethod
    def _new_lock():
        return threading.RLock()

    @contextmanager
    def hold(self, keys: Iterable[Hashable]) -> Iterator[None]:
        # Every caller takes its locks in the same order, so two callers that
        # share several keys cannot wait for each other.
        ordered = sorted(set(keys), key=repr)
        with self._guard:
            entries = []
            for key in ordered:
                entry = self._entries.get(key)
                if entry is None:
                    entry = self._entries[key] = [self._new_lock(), 0]
                entry[1] += 1
                entries.append((key, entry))
        acquired = []
        try:
            for _, entry in entries:
                entry[0].acquire()
                acquired.append(entry[0])
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()
            with self._guard:
                for key, entry in entries:
                    entry[1] -= 1
                    if entry[1] == 0:
                        del self._entries[key]


# Shared by every Chroma store in the process, so two stores on one folder and
# collection (one per request, say) also wait for each other.
_CHROMA_WRITES = _KeyedLocks()


class VectorStore:
    """Store embeddings with metadata and provide similarity search.

    With ``owner`` (a user or session id), every chunk this store adds is recorded
    for that owner, and :meth:`search` and :meth:`count` see only that owner's
    chunks, whatever the caller's filters say. This is a filter in gaik, not access
    control: every process that can open the folder (a store without an owner, an
    older gaik, chromadb itself) still reads and writes every chunk, so it is trusted
    the same. Separate users who must not reach each other's data with separate
    collections or folders.

    Threads can share a store. Writes of one document and owner (``add`` and
    :meth:`delete_document`) run one at a time: in memory every call does, and in
    Chroma the calls of every store in the process on the same folder and
    collection. Other processes writing to the same Chroma folder are not covered.
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
        self._ids: list[str] = []
        # Guards the three lists above, which every in-memory call reads or rebuilds.
        self._lock = threading.RLock()

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

            # The folder Chroma opens now, so a later chdir does not change the lock.
            self._chroma_scope = (_folder_key(self.persist_path), self.collection_name)
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

    def __getstate__(self) -> dict:
        # A lock cannot be pickled or deep-copied; an in-memory store could be.
        # The copy made from this state has lists of its own, and its own lock.
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._lock = threading.RLock()

    def __copy__(self) -> VectorStore:
        # A shallow copy shares the lists, so it shares the lock that guards them.
        clone = type(self).__new__(type(self))
        clone.__dict__.update(self.__dict__)
        return clone

    def add(
        self,
        documents: list[Document],
        embeddings: list[list[float]],
        *,
        replace: bool = False,
    ) -> None:
        """Store chunks with their embeddings.

        Each chunk's id comes from its document, its owner and its text (see
        ``_chunk_ids``): the document is ``metadata["document_id"]``, else
        ``source``, else ``document_name``. A ``document_id`` the caller set is
        stored as given; without one it is set to the document. The document
        is also stored as a string under ``gaik_document_key``, which
        ``replace`` and :meth:`delete_document` match on. The owner is the
        store's ``owner``. Adding a chunk that is already stored replaces it,
        metadata included, instead of storing a second copy. A chunk whose
        metadata names no document is stored as a new one each time.

        Args:
            documents: The chunks. A ``document_id`` in the metadata must be a
                string or an int; other types raise ``ValueError``.
            embeddings: Their embeddings, in the same order.
            replace: After storing, delete the other chunks of each document in
                ``documents``, so chunks the document no longer has do not stay
                behind. Only chunks with the same owner as the ones added (or,
                without one, chunks that name no owner) are deleted, and only
                chunks this release stored (with ``gaik_document_key``). Pass
                all of a document's chunks in one call. If storing fails, no
                stored chunk is deleted: in Chroma the chunks of the failed
                slice are put back as they were, and slices stored before it
                keep their new version.
        """
        if len(documents) != len(embeddings):
            raise ValueError("documents and embeddings must have the same length")
        documents = self._owned(documents)

        if not documents:
            return

        # A chunk that names no document gets a new id, as before.
        keys = chunk_ids(documents)
        keyed = [key.chunk_id or uuid.uuid4().hex for key in keys]
        stored = [
            Document(
                id=doc.id,  # a caller's own id stays on the in-memory copy, as before
                page_content=doc.page_content,
                metadata=with_document_id(doc.metadata, key.document_id),
            )
            for doc, key in zip(documents, keys)
        ]

        # Storing and pruning run under one lock: two overlapping replacements of
        # one document would otherwise each delete the chunks the other stored.
        with self._writing(document_scopes(keys)):
            if not self.persist:
                position = {chunk_id: index for index, chunk_id in enumerate(self._ids)}
                for doc, embedding, chunk_id in zip(stored, embeddings, keyed):
                    if chunk_id in position:
                        self._documents[position[chunk_id]] = doc
                        self._embeddings[position[chunk_id]] = embedding
                    else:
                        position[chunk_id] = len(self._ids)
                        self._ids.append(chunk_id)
                        self._documents.append(doc)
                        self._embeddings.append(embedding)
            else:
                ids = [f"{self.collection_name}_{chunk_id}" for chunk_id in keyed]
                texts = [doc.page_content for doc in stored]
                metadatas = [_chroma_metadata(doc.metadata) for doc in stored]
                # Chroma rejects a single call above its maximum batch size, so send
                # slices. If one fails, the slices before it stay stored.
                batch = _max_batch_size(self._client) or len(ids)
                for start in range(0, len(ids), batch):
                    end = start + batch
                    self._replace_slice(
                        ids[start:end],
                        embeddings[start:end],
                        texts[start:end],
                        metadatas[start:end],
                    )
                keyed = ids

            if replace:
                kept = set(keyed)
                for doc_id, owner in document_scopes(keys):
                    self._delete_ids(
                        [i for i in self._ids_in_scope(doc_id, owner) if i not in kept]
                    )

    @contextmanager
    def _writing(self, scopes: list[tuple[str, str | None]]) -> Iterator[None]:
        """Hold the lock that writes of these ``(document_id, owner)`` scopes share.

        In memory that is the store's own lock, which every call takes. In Chroma it
        is one lock per document and owner of this folder and collection, shared by
        every store in the process, so writes of other documents run alongside.
        """
        if not self.persist:
            with self._lock:
                yield
            return
        where = self._chroma_scope
        with _CHROMA_WRITES.hold((*where, doc_id, owner) for doc_id, owner in scopes):
            yield

    def _replace_slice(self, ids, embeddings, texts, metadatas) -> None:
        """Store one slice in Chroma in place of the chunks stored with the same ids.

        The slice is upserted, so each chunk is replaced where it is: a call that
        is interrupted leaves a chunk old or new, never gone. An upsert merges the
        new metadata into the stored one, so a key the stored chunk has and the
        new one lacks (a heading it no longer has) is sent as ``None``, which
        Chroma 1.x removes. If the upsert fails, the chunks read are put back as
        they were and the error is raised.

        Chroma before 1.0 refuses a ``None`` value. There the stored chunks are
        deleted and the slice added anew, which loses a chunk if the process stops
        between the two calls.
        """
        collection = self._collection
        old = collection.get(  # type: ignore[union-attr]
            ids=ids, include=["embeddings", "documents", "metadatas"]
        )
        old_ids = list(old.get("ids") or [])
        if not _chroma_removes_none_values():
            self._delete_then_add(old, ids, embeddings, texts, metadatas)
            return
        # Chroma returns the stored chunks in its own order, not the order asked for.
        old_metadata = dict(zip(old_ids, old.get("metadatas") or [None] * len(old_ids)))
        new_metadata = dict(zip(ids, metadatas))
        try:
            collection.upsert(  # type: ignore[union-attr]
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=[
                    _replacing(metadata, old_metadata.get(chunk_id))
                    for chunk_id, metadata in zip(ids, metadatas)
                ],
            )
        except Exception:
            # Chroma checks a call before it writes, so this seldom has anything
            # to undo; a write that failed partway is undone here.
            new_ids = [chunk_id for chunk_id in ids if chunk_id not in old_metadata]
            if new_ids:
                collection.delete(ids=new_ids)  # type: ignore[union-attr]
            if old_ids:
                collection.upsert(  # type: ignore[union-attr]
                    ids=old_ids,
                    embeddings=old["embeddings"],
                    documents=old["documents"],
                    metadatas=[
                        _replacing(old_metadata[chunk_id], new_metadata.get(chunk_id))
                        for chunk_id in old_ids
                    ],
                )
            raise

    def _delete_then_add(self, old, ids, embeddings, texts, metadatas) -> None:
        """:meth:`_replace_slice` for a Chroma that cannot remove a metadata key."""
        collection = self._collection
        old_ids = list(old.get("ids") or [])
        if old_ids:
            collection.delete(ids=old_ids)  # type: ignore[union-attr]
        try:
            collection.add(  # type: ignore[union-attr]
                ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
            )
        except Exception:
            if old_ids:
                collection.add(  # type: ignore[union-attr]
                    ids=old_ids,
                    embeddings=old["embeddings"],
                    documents=old["documents"],
                    metadatas=old["metadatas"],
                )
            raise

    def delete_document(self, document_id: str | int, *, owner: str | None = None) -> int:
        """Delete every chunk of one document and one owner.

        ``add()`` records each chunk's document under ``gaik_document_key``
        (the chunk's own ``document_id``, else its ``source``, else its
        ``document_name``, as a string). Chunks stored by a gaik release before
        that have none and are never deleted here, even when their metadata
        names a ``document_id``: index them again into a new collection.

        Args:
            document_id: The document, compared exactly. A string, or an int
                compared as its string; other types raise ``ValueError``.
            owner: Delete only the chunks recorded for this owner (metadata
                ``gaik_owner``). Without it, only chunks that name no owner are
                deleted, so a call without an owner never removes an owner's
                chunks. A store with its own ``owner`` uses that one.

        Returns:
            The number of chunks deleted.
        """
        doc_id, owner = delete_scope(self, document_id, owner)
        with self._writing([(doc_id, owner)]):
            ids = self._ids_in_scope(doc_id, owner)
            self._delete_ids(ids)
        return len(ids)

    def _ids_in_scope(self, document_id: str, owner: str | None) -> list[str]:
        """The ids of the stored chunks of ``document_id`` and exactly ``owner``."""
        if not self.persist:
            return [
                chunk_id
                for chunk_id, doc in zip(self._ids, self._documents)
                if in_scope(doc.metadata, document_id, owner)
            ]
        found = self._collection.get(  # type: ignore[union-attr]
            where={DOCUMENT_KEY: {"$eq": document_id}}, include=["metadatas"]
        )
        return [
            chunk_id
            for chunk_id, metadata in zip(found.get("ids") or [], found.get("metadatas") or [])
            if in_scope(metadata, document_id, owner)
        ]

    def _delete_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        if not self.persist:
            gone = set(ids)
            keep = [index for index, chunk_id in enumerate(self._ids) if chunk_id not in gone]
            self._documents = [self._documents[i] for i in keep]
            self._embeddings = [self._embeddings[i] for i in keep]
            self._ids = [self._ids[i] for i in keep]
            return
        batch = _max_batch_size(self._client) or len(ids)
        for start in range(0, len(ids), batch):
            self._collection.delete(ids=ids[start : start + batch])  # type: ignore[union-attr]

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
            with self._lock:
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
            # A copy of the lists as one write left them; a write may rebuild them.
            with self._lock:
                snapshot = list(zip(self._documents, self._embeddings))
            scored = []
            for doc, embedding in snapshot:
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


def _replacing(metadata: dict | None, stored: dict | None) -> dict | None:
    """``metadata`` for an upsert over a chunk stored with ``stored``.

    An upsert keeps a stored key the new metadata lacks, so each such key is sent
    as ``None``, which Chroma 1.x removes.
    """
    new = metadata or {}
    removed = {key: None for key in (stored or {}) if key not in new}
    return {**removed, **new} or None


_removes_none: bool | None = None  # the probe's answer, once it has one
_probe_runs_left = 3  # probes that could not run are tried again this many times


def _chroma_removes_none_values() -> bool:
    """Whether this chromadb removes a metadata key that an upsert sends as ``None``.

    Chroma 1.x does; 0.5 and 0.6 refuse the value. A client that accepts ``None``
    does not show what the store then does with it, so this is a real upsert into
    a throwaway in-memory collection. Once it gives an answer, the answer is kept
    for the process. A probe that could not run (no in-memory client) answers
    ``False``, the delete-then-add path, and is tried again on a later write; after
    three such runs ``False`` is kept.
    """
    global _removes_none, _probe_runs_left
    if _removes_none is None:
        found = _probe_none_removal()
        if found is None:
            _probe_runs_left -= 1
            if _probe_runs_left > 0:
                return False
            found = False
        _removes_none = found
    return _removes_none


def _probe_none_removal() -> bool | None:
    """``True`` or ``False`` as the probe write shows, ``None`` if it could not run."""
    try:
        import chromadb

        client = chromadb.EphemeralClient()
        name = f"gaik-probe-{uuid.uuid4().hex}"
        collection = client.create_collection(name)
    except Exception:  # noqa: BLE001 - no in-memory client now: ask again later
        return None
    try:
        collection.add(ids=["probe"], embeddings=[[1.0, 0.0]], metadatas=[{"kept": 1, "gone": 1}])
    except Exception:  # noqa: BLE001 - the probe could not write at all
        _drop_quietly(client, name)
        return None
    try:
        try:
            collection.upsert(
                ids=["probe"], embeddings=[[1.0, 0.0]], metadatas=[{"kept": 1, "gone": None}]
            )
        except Exception:  # noqa: BLE001 - it took a write but not this one: it refuses
            return False  # 0.5 and 0.6: "Expected metadata value to be a str, ..."
        [metadata] = collection.get(ids=["probe"], include=["metadatas"])["metadatas"]
        return metadata == {"kept": 1}
    except Exception:  # noqa: BLE001 - the read back failed: ask again later
        return None
    finally:
        _drop_quietly(client, name)


def _drop_quietly(client, name: str) -> None:
    try:
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - an in-memory collection goes with the process
        pass


def _folder_key(path: str) -> str:
    """One spelling of a folder: absolute, links resolved, and case folded on Windows
    and macOS, whose file systems ignore case by default."""
    key = os.path.normcase(os.path.realpath(path))
    return key.casefold() if sys.platform == "darwin" else key


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
