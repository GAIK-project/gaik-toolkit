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
    collection_name: str = "gaik_rag"
)
```

### Methods

```python
store.add(documents: list[Document], embeddings: list[list[float]], *, replace: bool = False) -> None
store.delete_document(document_id) -> int  # chunks deleted

results = store.search(
    query_embedding: list[float],
    top_k: int = 5,
    filters: dict | None = None
)  # -> list[tuple[Document, float]]
```

#### Chunk ids and re-indexing

A chunk's id comes from its document and its text. The document is
`metadata["document_id"]`, else `source`, else `document_name` (the RAG parsers set
the last two), and `add()` stores it with the chunk as `document_id`.

- Adding a document's chunks again updates them instead of storing a second copy.
  A text repeated inside one document keeps one chunk per occurrence.
- `add(..., replace=True)` first deletes every stored chunk of each document in the
  call, so the chunks a changed document no longer has do not stay behind. Pass all
  of a document's chunks in one call.
- `delete_document(document_id)` deletes one document's chunks and returns how many.
- A chunk whose metadata names no document is stored as a new one each time.

A Chroma collection built by an earlier gaik release still loads and searches, but
its chunks have random ids and no `document_id`: `delete_document` and `replace=True`
do not find them, and adding a document again stores it next to its old copy. Index
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
