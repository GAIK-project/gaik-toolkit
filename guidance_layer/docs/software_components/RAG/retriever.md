# Retriever

Semantic and hybrid retriever for RAG workflows.

## Installation

```bash
pip install gaik[retriever]
```

**Note:** Requires embedder + vector store software components.

---

## Quick Start

```python
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.vector_store import VectorStore
from gaik.software_components.RAG.retriever import Retriever
from gaik.software_components.config import get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config)
store = VectorStore(persist=False)
retriever = Retriever(embedder=embedder, vector_store=store)

docs = retriever.search("What is the total?", top_k=3, include_scores=True)
```

---

## Features

- **Semantic Search** - Vector similarity search
- **Hybrid Search** - Optional BM25 keyword weighting
- **Re-ranking** - Optional score-based rerank
- **Top-k + Threshold** - Optional score threshold filtering

---

## Basic API

### Retriever

```python
retriever = Retriever(
    embedder: Embedder,
    vector_store: VectorStore,
    hybrid_search: bool = False,
    re_rank: bool = False,
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
    top_k: int = 5,
    score_threshold: float | None = None
)
```

### Methods

```python
docs = retriever.search(
    query: str,
    top_k: int | None = None,
    score_threshold: float | None = None,
    filters: dict | None = None,
    include_scores: bool = False,
    hybrid_search: bool | None = None,
    re_rank: bool | None = None,
)  # -> list[Document]
```

---

## Configuration

This software component uses the shared embedder configuration from `gaik.software_components.config`.

---

## Environment Variables

Same as embedder/OpenAI config. See `gaik.software_components.config`.

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `retriever_example.py` - Basic and hybrid search

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues]

## License

MIT - see [LICENSE](../../../../LICENSE)
