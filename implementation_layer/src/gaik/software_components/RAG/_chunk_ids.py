"""Chunk ids derived from the document a chunk belongs to, its owner and its text.

The vector stores give a chunk the same id each time the same document is indexed,
so indexing it again updates its chunks instead of storing a second copy, and the
chunks of one document can be found and deleted by its ``document_id``.

A chunk can also name an owner (metadata ``gaik_owner``, a user or session id). The
owner is part of the chunk id, and replacing or deleting a document touches only the
chunks of one owner, so two owners who index a document under the same id in one
store keep separate chunks.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, NamedTuple

#: Metadata keys that name the document a chunk comes from, in order of preference.
#: The RAG parsers set ``source`` (the file path) and ``document_name``.
DOCUMENT_ID_KEYS = ("document_id", "source", "document_name")

#: Metadata key that names the owner (a user or session id) of a chunk.
CHUNK_OWNER_KEY = "gaik_owner"

#: Metadata key under which the stores record a chunk's document id as a string.
#: Only stores that derive chunk ids write it, so replacing or deleting a document
#: never touches a chunk stored by an earlier gaik release, even one whose caller
#: metadata already named a ``document_id``. The caller's ``document_id`` is kept
#: as given, so a filter on it matches as before.
DOCUMENT_KEY = "gaik_document_key"


class ChunkKey(NamedTuple):
    """A chunk's document, its owner and its id; all ``None`` for no document."""

    document_id: str | None
    owner: str | None
    chunk_id: str | None


def check_document_id(value: Any) -> str:
    """``value`` as a document id: a non-empty string, or an int as its string.

    Raises:
        ValueError: For any other type, or an empty string. Document ids are
            compared exactly, so a value that is not plain text is refused.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"document_id must be a string, not {type(value).__name__}")
    text = str(value)
    if not text:
        raise ValueError("document_id must not be empty")
    return text


def owner_value(value: Any) -> str | None:
    """``value`` as an owner: ``None``, or a non-blank string."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{CHUNK_OWNER_KEY} must be a non-blank string, such as a user or session id"
        )
    return value


def owner_of(metadata: dict[str, Any] | None) -> str | None:
    """The owner a chunk's metadata names, or ``None``."""
    return owner_value((metadata or {}).get(CHUNK_OWNER_KEY))


def document_id_of(metadata: dict[str, Any] | None) -> str | None:
    """The document a chunk belongs to: the first of ``DOCUMENT_ID_KEYS`` set."""
    for key in DOCUMENT_ID_KEYS:
        value = (metadata or {}).get(key)
        if value is not None and value != "":
            return check_document_id(value) if key == "document_id" else str(value)
    return None


def chunk_ids(documents: list[Any]) -> list[ChunkKey]:
    """A :class:`ChunkKey` for each chunk, in order.

    The chunk id is a SHA-256 of the document id, the chunk text, how many
    chunks before it in the same call have the same document, owner and text,
    and the owner when there is one. A text repeated inside one document (a
    running header) keeps one chunk per occurrence, and indexing the same
    document again gives the same ids. The occurrence is counted within one
    call only: pass all of a document's chunks in one call, because a text
    repeated across two calls gets the same id and is stored once.

    A chunk whose metadata names no document gets ``ChunkKey(None, None, None)``:
    the same text can belong to different documents, so such a chunk is stored
    as a new one each time, as before.
    """
    seen: Counter[tuple[str, str | None, str]] = Counter()
    result: list[ChunkKey] = []
    for doc in documents:
        doc_id = document_id_of(doc.metadata)
        if doc_id is None:
            result.append(ChunkKey(None, None, None))
            continue
        owner = owner_of(doc.metadata)
        text = doc.page_content
        key = (doc_id, owner, text)
        occurrence = seen[key]
        seen[key] += 1
        parts: list[Any] = [doc_id, text, occurrence]
        if owner is not None:
            parts.append(owner)
        payload = json.dumps(parts, ensure_ascii=False)
        result.append(ChunkKey(doc_id, owner, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
    return result


def document_scopes(keys: list[ChunkKey]) -> list[tuple[str, str | None]]:
    """The distinct ``(document_id, owner)`` pairs in ``keys``, in order."""
    return list(dict.fromkeys((k.document_id, k.owner) for k in keys if k.document_id is not None))


def delete_scope(store: Any, document_id: Any, owner: Any) -> tuple[str, str | None]:
    """The document and owner a store's ``delete_document`` acts on.

    ``owner`` defaults to the store's own ``owner`` attribute when it has one; an
    owner other than the store's is refused.
    """
    doc_id = check_document_id(document_id)
    owner = owner_value(owner)
    own = getattr(store, "owner", None)
    if own is not None:
        if owner is not None and owner != own:
            raise ValueError("owner differs from this store's owner")
        owner = own
    return doc_id, owner


def in_scope(metadata: dict[str, Any] | None, document_id: str, owner: str | None) -> bool:
    """Whether a stored chunk belongs to ``document_id`` and exactly ``owner``.

    Only chunks that carry :data:`DOCUMENT_KEY` match. With ``owner=None`` only
    chunks that name no owner match.
    """
    metadata = metadata or {}
    return metadata.get(DOCUMENT_KEY) == document_id and metadata.get(CHUNK_OWNER_KEY) == owner


def with_document_id(metadata: dict[str, Any] | None, doc_id: str | None) -> dict[str, Any]:
    """A copy of ``metadata`` as a store keeps it for a chunk of ``doc_id``.

    A ``document_id`` the caller set is kept as given (an int stays an int);
    without one it is set to ``doc_id``. :data:`DOCUMENT_KEY` is set to ``doc_id``,
    and removed for a chunk that names no document.
    """
    copied = dict(metadata or {})
    copied.pop(DOCUMENT_KEY, None)
    if doc_id is not None:
        if copied.get("document_id") is None or copied.get("document_id") == "":
            copied["document_id"] = doc_id
        copied[DOCUMENT_KEY] = doc_id
    return copied
