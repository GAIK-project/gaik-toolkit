# RAG Workflow

End-to-end RAG workflow:
vision parser -> embedder -> vector store -> retriever -> answer generator.

## Installation

```bash
pip install gaik[rag-workflow]
```

**Note:** Requires OpenAI/Azure OpenAI access and Chroma for persistence.

---

## Quick Start

```python
from gaik.software_modules.RAG_workflow import RAGWorkflow

workflow = RAGWorkflow()
workflow.index_documents(["document.pdf"])

result = workflow.ask("What is the total amount?", stream=False)
print(result.answer)
```

---

## Features

- **Vision Parsing** - Extracts text and image descriptions
- **Persistent Vector Store** - Chroma-backed storage
- **Re-ranked Retrieval** - Optional cross-encoder reranking
- **Citations** - Optional citation formatting
- **Conversation History** - Last-n Q/A memory

---

## Basic API

### RAGWorkflow

```python
workflow = RAGWorkflow(
    api_config: dict | None = None,
    use_azure: bool = True,
    persist: bool = True,
    persist_path: str = "chroma_store",
    collection_name: str = "gaik_rag",
    embedding_model: str | None = None,
    retriever_top_k: int = 5,
    retriever_threshold: float | None = None,
    retriever_hybrid: bool = False,
    retriever_rerank: bool = False,
    citations: bool = True,
    stream: bool = True,
    conversation_history: bool = True,
    last_n: int = 3,
)
```

### Methods

```python
index_result = workflow.index_documents(
    file_paths: list[str | Path]
)

result = workflow.ask(
    query: str,
    top_k: int | None = None,
    score_threshold: float | None = None,
    filters: dict | None = None,
    include_scores: bool = False,
    stream: bool | None = None,
)
```

---

## Configuration

This workflow uses `gaik.software_components.config` for OpenAI/Azure configuration.

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

See [examples/RAG/](../../../../examples/RAG/) for usage:
- `rag_workflow_chat.py` - Interactive conversation loop

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
