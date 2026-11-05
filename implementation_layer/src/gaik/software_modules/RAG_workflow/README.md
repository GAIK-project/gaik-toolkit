# RAG Workflow

End-to-end RAG workflow:
parser -> embedder -> vector store -> retriever -> answer generator.

## Installation

```bash
pip install gaik[rag-workflow]        # parser="vision" (default): Docling + a vision model
pip install gaik[rag-workflow-text]   # parser="text": the text layer only, no Docling or torch
```

**Note:** Requires an embedding provider, a chat model, and Chroma for persistence, plus a vision model with the default parser. These stages can use different providers.

## Choosing the parser

| `parser` | Reads | Needs | Use when |
|---|---|---|---|
| `"vision"` (default) | PDFs, with Docling layout and a vision model describing images and figures | `gaik[rag-workflow]` (Docling, torch) and a vision-capable model | Scans, figures, diagrams or charts must be understood |
| `"text"` | The text layer of PDFs, and Word (.docx), text and Markdown files | `gaik[rag-workflow-text]` | Text-based documents; faster, cheaper and no model call while indexing |

`parser="text"` keeps the page number of each PDF chunk for citations and raises a
`ValueError` for a PDF without a text layer (a scan): use `parser="vision"` there.

---

## Quick Start

```python
from gaik.software_modules.RAG_workflow import RAGWorkflow

workflow = RAGWorkflow()                 # or RAGWorkflow(parser="text")
workflow.index_documents(["document.pdf"])

result = workflow.ask("What is the total amount?", stream=False)
print(result.answer)
```

---

## Features

- **Vision Parsing** - Extracts text and image descriptions (default)
- **Text Parsing** - `parser="text"` reads the text layer without Docling or a vision model
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
    parser: Literal["vision", "text"] = "vision",
    parser_config: dict | None = None,
    embedding_config: dict | None = None,
    answer_config: dict | None = None,
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

Use `get_llm_config` to select separate providers for each stage. Omitted stage configs use the shared `api_config`; the legacy `use_azure` default still works. When all three stage configs are explicit, no default Azure/OpenAI credentials are loaded.

```python
from gaik.software_components.llm import get_llm_config

workflow = RAGWorkflow(
    parser_config=get_llm_config("openai", model="gpt-6-luna"),
    embedding_config=get_llm_config("google", embedding_model="gemini-embedding-001"),
    answer_config=get_llm_config("aitta"),
)
```

Choose a vision-capable model for parsing and a service-supported embedding model. Anthropic has no native embedding API; Aitta and custom compatible servers require an explicit embedding model from their catalog.

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
