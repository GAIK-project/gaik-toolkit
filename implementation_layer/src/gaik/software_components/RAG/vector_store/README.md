# Vector Store

Store embeddings with metadata and perform similarity search for RAG workflows.

## Installation

```bash
pip install gaik[vector-store]
```

**Note:** Uses in-memory storage by default. Set `persist=True` to use Chroma.

---

## Quick Start

```python
from langchain_core.documents import Document
from gaik.software_components.RAG.vector_store import VectorStore

docs = [Document(page_content="hello", metadata={"page_number": 1})]
embeddings = [[0.1, 0.2, 0.3]]

store = VectorStore(persist=False)
store.add(docs, embeddings)

results = store.search([0.1, 0.2, 0.3], top_k=1)
print(results[0][0].metadata, results[0][1])
```

---

## Features

- **In-Memory Store** - Fast, lightweight default
- **Chroma Persistence** - Optional on-disk store (`persist=True`)
- **Metadata Preservation** - Stores full metadata dict
- **Filtering** - Basic metadata filters for search

---

## Basic API

### VectorStore

```python
from gaik.software_components.RAG.vector_store import VectorStore

store = VectorStore(
    persist: bool = False,
    persist_path: str = "chroma_store",
    collection_name: str = "gaik_rag",
    owner: str | None = None,  # a user or session id: see below
)
```

### Several users on one store

Pass `owner` (a user or session id) and the store records it on every chunk it adds,
under the metadata key `gaik_owner`, and its searches and counts see only that owner's
chunks. A caller's filter is added to the owner condition; it cannot replace it. Without
`owner`, everyone using the same collection reads every chunk in it, and `add()` refuses
metadata that already names an owner.

This is a filter in gaik, not access control. Every process that can open the folder (a
store without an owner, an older gaik, chromadb itself) reads and writes every owner's
chunks, including chunks that name an owner. Treat all of them as trusted, or give users
who must not reach each other's data separate collections or folders.

### Methods

```python
store.add(documents: list[Document], embeddings: list[list[float]], *, replace: bool = False) -> None
store.delete_document(document_id: str | int, *, owner: str | None = None) -> int  # chunks deleted

results = store.search(
    query_embedding: list[float],
    top_k: int = 5,
    filters: dict | None = None
)  # -> list[tuple[Document, float]]
```

#### Chunk ids and re-indexing

A chunk's id comes from its document, its owner and its text. The document is
`metadata["document_id"]`, else `source`, else `document_name` (the RAG parsers set
the last two). A `document_id` you set is stored as given, so a filter such as
`filters={"document_id": 7}` matches it; without one, `add()` sets `document_id` to
the document. `add()` also records the document as a string under
`metadata["gaik_document_key"]`, and `replace=True` and `delete_document` match on that
key only. A `document_id` must be a string or an int; other types raise `ValueError`,
and document ids are compared exactly (an int as its string). The owner is the store's
`owner` (recorded as `metadata["gaik_owner"]`).

- Adding a document's chunks again replaces them, metadata included, instead of
  storing a second copy.
  A text repeated inside one document keeps one chunk per occurrence, counted within
  one call: pass all of a document's chunks in one call.
- `add(..., replace=True)` stores the chunks, then deletes the other stored chunks of
  each document in the call, so the chunks a changed document no longer has do not
  stay behind. If storing fails, no stored chunk is lost: the stale chunks are deleted
  only after every chunk is stored, and in Chroma a slice whose write fails (an
  embedding of another dimension, say) has its earlier versions put back as they were.
  Chroma takes the chunks in slices of at most its maximum batch size; slices stored
  before a failure keep their new version. Chroma 1.x updates a stored chunk in place,
  so a process that stops partway leaves each chunk old or new; before 1.0 a chunk
  is deleted and added again, and one can be lost if the process stops in between.
- Threads can share a store. Writes of one document and owner wait for each other,
  so two overlapping replacements leave one version: in memory every call waits,
  and in Chroma the writes of every store in the process on the same folder and
  collection. Other processes writing to the same Chroma folder are not covered.
- `delete_document(document_id, owner=...)` deletes one document's chunks and returns
  how many.
- Two owners who index a document under the same id keep separate chunks.
  `replace=True` deletes only chunks of the owner of the chunks added, and
  `delete_document` only those of the `owner` given; without an owner, both touch
  only chunks that name no owner.
- A chunk whose metadata names no document is stored as a new one each time.

A Chroma collection built by an earlier gaik release still loads and searches, but
its chunks have random ids and no `gaik_document_key`: `delete_document` and
`replace=True` never delete them, even when their metadata names a `document_id`, and
adding a document again stores it next to its old copy. Index
the documents again into a new `collection_name` (or a new `persist_path`).

---

## Configuration

No OpenAI/Azure configuration required.

---

## Environment Variables

No required environment variables.

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `vector_store_example.py` - In-memory and persistent search

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
