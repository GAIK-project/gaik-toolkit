---
name: gaik-toolkit
version: "1.1.0"
description: |
  GAIK (Generative AI Knowledge Management Toolkit) development guidance.
  Use when working with: structured data extraction from documents/PDFs/audio,
  schema generation, document parsing (VisionParser, PyMuPDFParser, DoclingParser),
  audio transcription with Whisper, document classification, or end-to-end pipelines
  (AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow).
---

# GAIK Toolkit

Python toolkit for knowledge extraction, capture, and generation. Use when working with:
- Structured data extraction from documents, PDFs, images, or audio
- Schema generation from natural language requirements
- Document parsing (PDF, DOCX, images)
- Audio/video transcription with Whisper + GPT enhancement
- Document classification
- **RAG pipelines**: embedder, vector store, retriever, answer generator
- End-to-end pipelines: AudioToStructuredData, DocumentsToStructuredData, **RAGWorkflow**

## Quick Links

- **Documentation**: https://gaik-project.github.io/gaik-toolkit/
- **GitHub**: https://github.com/GAIK-project/gaik-toolkit
- **Source Code**: https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik
- **Docs Source**: https://github.com/GAIK-project/gaik-toolkit/tree/main/website/content/docs
- **PyPI**: https://pypi.org/project/gaik/
- **PyPI JSON API**: https://pypi.org/pypi/gaik/json

## Installation

Choose based on your needs:

```bash
# Structured extraction (schema generation + extraction)
pip install "gaik[extract]"

# Document parsing (includes docling with GPU support)
pip install "gaik[parser]"

# Document parsing (CPU-only, no docling/torch)
pip install "gaik[parser-cpu]"

# Audio/video transcription
pip install "gaik[transcriber]"

# Document classification
pip install "gaik[classifier]"

# Software components (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"

# RAG building blocks
pip install "gaik[embedder]"
pip install "gaik[vector-store]"
pip install "gaik[retriever]"
pip install "gaik[answer-generator]"
pip install "gaik[rag-parser-docling]"
pip install "gaik[rag-parser-vision]"

# RAG workflow (full RAG pipeline)
pip install "gaik[rag-workflow]"

# Everything with GPU support
pip install "gaik[all]"

# Everything CPU-only (recommended for cloud deployments like CSC Rahti)
pip install "gaik[all-cpu]"
```

**Note:** For video processing and audio compression, install `ffmpeg` on your system.

## Environment Variables

**Azure OpenAI (recommended):**
```bash
AZURE_API_KEY=your-key
AZURE_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_DEPLOYMENT=gpt-4o
AZURE_API_VERSION=2025-03-01-preview
```

**OpenAI:**
```bash
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o
```

## Configuration Pattern

All components use `get_openai_config()`:

```python
from gaik.building_blocks.extractor import get_openai_config

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
```

## Building Blocks

### SchemaGenerator + DataExtractor

Generate Pydantic schema from natural language, then extract structured data:

```python
from gaik.building_blocks.extractor import (
    SchemaGenerator, DataExtractor, get_openai_config
)

config = get_openai_config(use_azure=True)

# Generate schema from natural language
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(
    user_requirements="Extract invoice number, total amount, and vendor name."
)

# Extract structured data
extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements="Extract invoice data",
    documents=["Invoice #12345 from Acme Corp, Total: $1,500"],
    save_json=True,
    json_path="results.json",
)
```

### VisionParser (PDF to Markdown via LLM)

```python
from gaik.building_blocks.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)
parser = VisionParser(openai_config=config, use_context=True)

pages = parser.convert_pdf("document.pdf", dpi=150, clean_output=True)
parser.save_markdown(pages, "output.md")
```

### PyMuPDFParser (Fast Local PDF)

```python
from gaik.building_blocks.parsers import PyMuPDFParser, parse_pdf

parser = PyMuPDFParser()
result = parser.parse_document("document.pdf")
text = result["text_content"]

# Or convenience function:
text = parse_pdf("document.pdf")
```

### DocxParser (Word Documents)

```python
from gaik.building_blocks.parsers import DocxParser, parse_docx

parser = DocxParser()
result = parser.parse_document("document.docx")
text = result["text_content"]

# Or convenience function:
text = parse_docx("document.docx")
```

### DoclingParser (Advanced OCR + Multi-format)

```python
from gaik.building_blocks.parsers import DoclingParser, parse_document

parser = DoclingParser()
result = parser.parse_document("complex_document.pdf")
text = result["text_content"]

# Or convenience function:
text = parse_document("complex_document.pdf")
```

### Transcriber (Audio/Video)

```python
from gaik.building_blocks.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)
transcriber = Transcriber(
    api_config=config,
    output_dir="transcripts/",
    enhanced_transcript=True,  # GPT enhancement
)

result = transcriber.transcribe("meeting.mp3")
print(result.enhanced_transcript or result.raw_transcript)
result.save("output/")
```

### DocumentClassifier

```python
from gaik.building_blocks.doc_classifier import DocumentClassifier, get_openai_config

config = get_openai_config(use_azure=True)
classifier = DocumentClassifier(config=config)

result = classifier.classify(
    file_or_dir="documents/",
    classes=["invoice", "receipt", "contract", "report"]
)
# Returns: {"filename.pdf": {"class": "invoice", "confidence": 0.95, "reasoning": "..."}}
```

### RAG Building Blocks

#### Embedder (Text Embeddings)

```python
from gaik.building_blocks.RAG.embedder import Embedder
from gaik.building_blocks.config import get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config, model="text-embedding-3-large")

# Embed documents
embeddings, docs = embedder.embed(["Document text 1", "Document text 2"])

# Embed a single query for search
query_embedding = embedder.embed_query("What is the main topic?")
```

#### VectorStore (Embeddings Storage)

```python
from gaik.building_blocks.RAG.vector_store import VectorStore

# In-memory storage
store = VectorStore(persist=False)

# Persistent Chroma storage
store = VectorStore(
    persist=True,
    persist_path="chroma_store",
    collection_name="my_collection"
)

# Add documents and embeddings
store.add(documents, embeddings)

# Search by query embedding
results = store.search(query_embedding, top_k=5)
# Returns: [(Document, score), ...]
```

#### Retriever (Semantic + Hybrid Search)

```python
from gaik.building_blocks.RAG.retriever import Retriever

retriever = Retriever(
    embedder=embedder,
    vector_store=store,
    hybrid_search=True,  # Combine vector + BM25
    re_rank=True,        # Cross-encoder reranking
    top_k=5,
)

documents = retriever.search(
    "What are the key findings?",
    include_scores=True
)
```

#### AnswerGenerator (RAG Response)

```python
from gaik.building_blocks.RAG.answer_generator import AnswerGenerator

generator = AnswerGenerator(
    config=config,
    citations=True,   # Include [document, page] citations
    stream=True,      # Stream response tokens
)

answer = generator.generate("What is the summary?", documents, stream=False)
# Or stream:
for chunk in generator.generate("What is the summary?", documents, stream=True):
    print(chunk, end="")
```

#### VisionRagParser (PDF to RAG Chunks)

```python
from gaik.building_blocks.RAG.rag_parser_vision import VisionRagParser

parser = VisionRagParser(vision_config=config)

# Get LangChain Document chunks with vision-enhanced image descriptions
chunks = parser.convert_pdf_to_chunks_with_vision("document.pdf")
# Each chunk has: page_content, metadata (source, document_name, page_number, heading)
```

## Software Components (End-to-End Pipelines)

### AudioToStructuredData

Audio -> Transcript -> Schema -> Structured JSON:

```python
from gaik.software_components.audio_to_structured_data import AudioToStructuredData

pipeline = AudioToStructuredData(use_azure=True)

result = pipeline.run(
    file_path="recording.mp3",
    user_requirements="Extract patient name, symptoms, diagnosis, and treatment.",
    transcriber_ctor={"enhanced_transcript": True},
    extract_options={"save_json": True, "json_path": "output.json"},
)

print(result.extracted_fields)
print(result.transcription.enhanced_transcript)
```

### DocumentsToStructuredData

PDF/Image/DOCX -> Parsed Text -> Schema -> Structured JSON:

```python
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(use_azure=True)

result = pipeline.run(
    file_path="invoice.pdf",
    user_requirements="Extract invoice number, date, total, and line items.",
    parser_choice="vision_parser",  # vision_parser | docling | pymupdf | docx
    extract_options={"save_json": True},
)

print(result.extracted_fields)
```

**Parser choices:**
- `vision_parser` - LLM-based, best for complex layouts
- `docling` - Advanced OCR, requires GPU
- `pymupdf` - Fast local extraction
- `docx` - Word documents

### RAGWorkflow

End-to-end RAG: PDF -> Parse -> Embed -> Store -> Retrieve -> Answer:

```python
from gaik.software_components.RAG_workflow import RAGWorkflow

# Initialize workflow
workflow = RAGWorkflow(
    use_azure=True,
    persist=True,                 # Use Chroma for persistence
    persist_path="chroma_store",
    retriever_top_k=5,
    retriever_hybrid=False,       # Enable hybrid search
    retriever_rerank=False,       # Enable cross-encoder reranking
    citations=True,               # Include citations in answers
    stream=True,                  # Stream responses
)

# Index documents (parses PDF, creates embeddings, stores in vector DB)
index_result = workflow.index_documents(["doc1.pdf", "doc2.pdf"])
print(f"Indexed {index_result.num_documents} docs, {index_result.num_chunks} chunks")

# Ask questions with RAG
result = workflow.ask("What are the key findings?", stream=False)
print(result.answer)

# Access retrieved source documents
for doc in result.documents:
    print(f"Source: {doc.metadata['document_name']}, Page: {doc.metadata['page_number']}")

# Stream the answer
for chunk in workflow.ask("Summarize the main points", stream=True).answer:
    print(chunk, end="")
```

### Schema Persistence

Save and reuse schemas across runs:

```python
from pathlib import Path

# Save schema after first run
if result.schema and result.requirements:
    pipeline.save_schema(result.schema, result.requirements, Path("schema/"), "invoice")

# Load existing schema for subsequent runs
existing = pipeline.load_schema(Path("schema/"), "invoice")
if existing:
    schema, requirements = existing
    result = pipeline.run(
        file_path="another_invoice.pdf",
        user_requirements="",  # Not needed when schema provided
        schema=schema,
        requirements=requirements,
    )
```

## Architecture Overview

| Level | Concept | Examples |
|-------|---------|----------|
| **Service** | Logical capability | `speech_to_text`, `document_parsing`, `information_extraction`, `rag` |
| **Building block** | Atomic toolkit class/function | `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `Embedder`, `VectorStore`, `Retriever`, `AnswerGenerator` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow` |

## Maintenance Notes

This skill is designed for gaik-toolkit v0.3.x. Update when:
- New building blocks or software components are added
- Import paths change in `implementation_layer/src/gaik/`
- Major API changes occur

The PyPI fetch script always retrieves the latest version info.

## Fetch Latest PyPI Info

Use the included script to fetch the latest package info:

```bash
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py --version  # Version only
```

## Detailed References

- [Building Blocks API](references/building-blocks.md) - Detailed API for all building blocks
- [Software Components](references/software-components.md) - Pipeline patterns and options
- [Examples](references/examples.md) - Complete working examples
