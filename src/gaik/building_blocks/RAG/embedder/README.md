# Embedder

Generate vector embeddings from text using OpenAI or Azure OpenAI embedding models.

## Installation

```bash
pip install gaik[embedder]
```

**Note:** Requires OpenAI or Azure OpenAI API access.

---

## Quick Start

```python
from gaik.building_blocks.RAG.embedder import Embedder, get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config)

texts = ["First chunk", "Second chunk"]
embeddings, documents = embedder.embed(texts)

print(len(embeddings), len(documents))
```

---

## Features

- **OpenAI + Azure Support** - Works with both providers
- **Batch Processing** - Efficient embedding for large inputs
- **Metadata Preservation** - Uses LangChain `Document` for metadata
- **Retries** - Exponential backoff on rate limits/timeouts

---

## Basic API

### Embedder

```python
from gaik.building_blocks.RAG.embedder import Embedder

embedder = Embedder(
    config: dict,                 # From get_openai_config()
    model: str | None = None,     # Default: "text-embedding-3-large"
    batch_size: int = 100
)

embeddings, documents = embedder.embed(
    documents: list[Document] | list[str],
    batch_size: int | None = None
)  # -> (List[List[float]], List[Document])
```

### Convenience Function

```python
from gaik.building_blocks.RAG.embedder import embed_texts

embeddings, documents = embed_texts(
    texts=["chunk 1", "chunk 2"],
    use_azure=True,
    model="text-embedding-3-large",
    batch_size=100
)
```

---

## Configuration

This building block uses the shared `get_openai_config` from `gaik.building_blocks.config`.

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

See [examples/building_blocks/RAG/](../../../../examples/building_blocks/RAG/) for usage:
- `embedder_example.py` - Minimal embedding workflow

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [examples/building_blocks/](https://github.com/GAIK-project/gaik-toolkit/tree/main/examples/building_blocks)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
