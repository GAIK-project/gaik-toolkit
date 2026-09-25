# Embedder

Generate vector embeddings from text with OpenAI, Azure OpenAI, Google, or an embedding
model served by CSC Aitta or another OpenAI-compatible server.

## Installation

```bash
pip install gaik[embedder]
```

**Note:** Pass a `get_llm_config()` or `get_openai_config()` config. Anthropic has no
embedding API; Aitta and other compatible servers need an explicit `embedding_model`.
See the [multi-provider guide](https://gaik-project.github.io/gaik-toolkit/toolkit/multi-provider-llm/).

---

## Quick Start

```python
from gaik.software_components.RAG.embedder import Embedder, get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config)

texts = ["First chunk", "Second chunk"]
embeddings, documents = embedder.embed(texts)

print(len(embeddings), len(documents))
```

---

## Features

- **Multi-Provider** - OpenAI, Azure, Google, and compatible embedding endpoints
- **Batch Processing** - Efficient embedding for large inputs
- **Metadata Preservation** - Uses LangChain `Document` for metadata
- **Retries** - Exponential backoff on rate limits/timeouts

---

## Basic API

### Embedder

```python
from gaik.software_components.RAG.embedder import Embedder

embedder = Embedder(
    config: dict,                 # get_llm_config() or get_openai_config()
    model: str | None = None,     # Default: config["embedding_model"]
    batch_size: int = 100
)

embeddings, documents = embedder.embed(
    documents: list[Document] | list[str],
    batch_size: int | None = None
)  # -> (List[List[float]], List[Document])
```

### Convenience Function

```python
from gaik.software_components.RAG.embedder import embed_texts

embeddings, documents = embed_texts(
    texts=["chunk 1", "chunk 2"],
    use_azure=True,
    model="text-embedding-3-large",
    batch_size=100
)
```

---

## Configuration

`model` falls back to the config's `embedding_model`. `get_llm_config()` sets it from
`EMBEDDING_MODEL` (default `text-embedding-3-small` for OpenAI/Azure,
`gemini-embedding-001` for Google/Vertex). A legacy `get_openai_config()` config has
no `embedding_model` and keeps the `text-embedding-3-large` default. Index documents
and queries with the same model.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2025-03-01-preview) |

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `embedder_example.py` - Minimal embedding workflow

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
