"""Chunk ids derived from the document a chunk belongs to and its text.

The vector stores give a chunk the same id each time the same document is indexed,
so indexing it again updates its chunks instead of storing a second copy, and the
chunks of one document can be found and deleted by its ``document_id``.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

#: Metadata keys that name the document a chunk comes from, in order of preference.
#: The RAG parsers set ``source`` (the file path) and ``document_name``.
DOCUMENT_ID_KEYS = ("document_id", "source", "document_name")


def document_id_of(metadata: dict[str, Any] | None) -> Any | None:
    """The document a chunk belongs to: the first of ``DOCUMENT_ID_KEYS`` set."""
    for key in DOCUMENT_ID_KEYS:
        value = (metadata or {}).get(key)
        if value is not None and value != "":
            return value if key == "document_id" else str(value)
    return None


def chunk_ids(documents: list[Any]) -> list[tuple[Any | None, str | None]]:
    """``(document_id, chunk_id)`` for each chunk, in order.

    The chunk id is a SHA-256 of the document id, the chunk text and how many
    chunks before it in the same call have the same document id and text. A text
    repeated inside one document (a running header) keeps one chunk per
    occurrence, and indexing the same document again gives the same ids.

    A chunk whose metadata names no document gets ``(None, None)``: the same
    text can belong to different documents, so such a chunk is stored as a new
    one each time, as before.
    """
    seen: Counter[tuple[str, str]] = Counter()
    result: list[tuple[Any | None, str | None]] = []
    for doc in documents:
        doc_id = document_id_of(doc.metadata)
        if doc_id is None:
            result.append((None, None))
            continue
        text = doc.page_content
        key = (json.dumps(doc_id, default=str), text)
        occurrence = seen[key]
        seen[key] += 1
        payload = json.dumps([doc_id, text, occurrence], ensure_ascii=False, default=str)
        result.append((doc_id, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
    return result


def with_document_id(metadata: dict[str, Any] | None, doc_id: Any | None) -> dict[str, Any]:
    """A copy of ``metadata`` with ``document_id`` set when it was absent."""
    copied = dict(metadata or {})
    if doc_id is not None and copied.get("document_id") in (None, ""):
        copied["document_id"] = doc_id
    return copied
