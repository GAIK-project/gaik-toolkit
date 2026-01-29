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
store.add(documents: list[Document], embeddings: list[list[float]]) -> None

results = store.search(
    query_embedding: list[float],
    top_k: int = 5,
    filters: dict | None = None
)  # -> list[tuple[Document, float]]
```

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
