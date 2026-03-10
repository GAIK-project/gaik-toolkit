---
name: gaik-toolkit
description: GAIK (Generative AI Knowledge Management Toolkit) development guidance. Use when working with structured data extraction from documents/PDFs/audio, schema generation, document parsing (VisionParser, PyMuPDFParser, DoclingParser), audio transcription with Whisper, parallel transcription (ParallelTranscriber), SRT/VTT subtitle generation (srt_utils), document classification, RAG pipelines (Embedder, VectorStore, PgVectorStore, Retriever, AnswerGenerator), semantic video search (video_search_helpers), or end-to-end pipelines (AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow).
---

# GAIK Toolkit

Python toolkit for knowledge extraction, capture, and generation. Use when working with:
- Structured data extraction from documents, PDFs, images, or audio
- Schema generation from natural language requirements
- Document parsing (PDF, DOCX, images)
- Audio/video transcription with Whisper + GPT enhancement
- **Parallel transcription** with FFmpeg chunking (ParallelTranscriber)
- Document classification
- **RAG pipelines**: embedder, vector store (Chroma / PostgreSQL), retriever, answer generator
- End-to-end pipelines: AudioToStructuredData, DocumentsToStructuredData, **RAGWorkflow**

## Quick Links

- **Documentation**: https://gaik-project.github.io/gaik-toolkit/
- **Live Demo**: https://gaik-demo.2.rahtiapp.fi/ (registration required)
- **GitHub**: https://github.com/GAIK-project/gaik-toolkit
- **Source Code**: `implementation_layer/src/gaik/`
- **PyPI**: https://pypi.org/project/gaik/
- **PyPI JSON API**: https://pypi.org/pypi/gaik/json

## Repository Structure

The toolkit is organized in a layer-based architecture:

| Path | Description |
|------|-------------|
| `implementation_layer/src/gaik/` | Python package source (building blocks + software modules) |
| `implementation_layer/toolkit_demo_app/` | Next.js + FastAPI interactive demo app (bun + uv) |
| `guidance_layer/website/` | Documentation website (Fumadocs/Next.js, deployed to GitHub Pages) |
| `guidance_layer/website/content/docs/` | Documentation source (`.mdx` files) |
| `guidance_layer/website/content/docs/use-cases/` | Use-case documentation |
| `guidance_layer/website/content/docs/toolkit/evals/` | Evaluation methods (extraction, RAG, transcription, translation) |
| `implementation_layer/no-code-assets/` | Prompt templates and agent skills for no-code usage |
| `strategy_layer/` | Value evaluation framework, AI maturity assessment |
| `business_layer/` | GenAI product canvas templates |

## Toolkit Demo App

Interactive web application at `implementation_layer/toolkit_demo_app/`. Provides UI for all toolkit components.

- **Tech stack**: Next.js 16 + FastAPI, bun + uv, Tailwind v4, shadcn/ui
- **Live**: https://gaik-demo.2.rahtiapp.fi/
- **See**: `implementation_layer/toolkit_demo_app/CLAUDE.md` for dev conventions

**Demo features:**
- Extractor (schema-free structured extraction)
- Document Parser (multi-backend PDF/DOCX parsing)
- Document Classifier (zero-shot classification)
- Transcriber (Whisper + GPT enhancement)
- RAG Builder (document upload, indexing, Q&A with citations)
- Incident Reporting demo (voice -> structured report)
- Construction Diary demo (voice notes -> diary entries)
- Dental Transcription & Captioning (local Whisper -> SRT/VTT subtitles)
- Semantic Dental Video Search (pgvector hybrid search over pre-seeded videos)

## Documentation Website

Source at `guidance_layer/website/`, built with Fumadocs (Next.js). Content in `.mdx` files under `guidance_layer/website/content/docs/`.

**Key doc pages:**
- `index.mdx` - Toolkit overview, knowledge processes, layer architecture
- `demo.mdx` - Demo app feature descriptions
- `toolkit/software-components.mdx` - Building blocks documentation
- `toolkit/software-modules.mdx` - Software modules documentation
- `toolkit/evals/` - Evaluation methods (extraction, RAG, transcription, translation, report writing)
- `toolkit/no-code-assets.mdx` - Prompt templates and agent skills
- `use-cases/*.mdx` - Use case documentation

## Installation

Choose based on your needs:

```bash
# Structured extraction (schema generation + extraction)
pip install "gaik[extract]"

# Document parsing (includes docling with GPU support)
pip install "gaik[parser]"

# Document parsing (CPU-only, no docling/torch)
pip install "gaik[parser-cpu]"

# Audio/video transcription (sequential)
pip install "gaik[transcriber]"

# Parallel transcription (FFmpeg-based, requires ffmpeg on $PATH)
pip install "gaik[parallel-transcriber]"

# Document classification
pip install "gaik[classifier]"

# Software components (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"

# RAG building blocks
pip install "gaik[embedder]"
pip install "gaik[vector-store]"
pip install "gaik[pg-vector-store]"
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
AZURE_DEPLOYMENT=gpt-5.1
AZURE_API_VERSION=2025-03-01-preview
```

**OpenAI:**
```bash
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-5.1
```

## Configuration Pattern

All components use `get_openai_config()`:

```python
from gaik.software_components.config import get_openai_config, create_openai_client

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
client = create_openai_client(config)        # OpenAI/AzureOpenAI client
```

## Building Blocks

### SchemaGenerator + DataExtractor

Generate Pydantic schema from natural language, then extract structured data:

```python
from gaik.software_components.extractor import (
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
from gaik.software_components.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)
parser = VisionParser(openai_config=config, clean_output=True)

pages = parser.convert_pdf("document.pdf")
# pages is a list of markdown strings, one per page
```

### PyMuPDFParser (Fast Local PDF)

```python
from gaik.software_components.parsers import PyMuPDFParser, parse_pdf

parser = PyMuPDFParser()
text = parser.parse_pdf("document.pdf")

# Or convenience function:
text = parse_pdf("document.pdf")
```

### DocxParser (Word Documents)

```python
from gaik.software_components.parsers import DocxParser, parse_docx

parser = DocxParser()
text = parser.parse_docx("document.docx")

# Or convenience function:
text = parse_docx("document.docx")
```

### DoclingParser (Advanced OCR + Multi-format)

```python
from gaik.software_components.parsers import DoclingParser, parse_document

parser = DoclingParser()
text = parse_document("complex_document.pdf")
```

### Transcriber (Audio/Video)

```python
from gaik.software_components.transcriber import Transcriber, get_openai_config

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

### SRT/VTT Subtitle Utilities

Generate, parse, and chunk subtitle files from Whisper transcription segments:

```python
from gaik.software_components.transcriber import (
    segments_to_srt, segments_to_vtt, parse_srt, chunk_segments,
)

# Generate subtitles from Whisper segments [{start, end, text}, ...]
srt_content = segments_to_srt(segments)
vtt_content = segments_to_vtt(segments)

# Parse SRT back to structured segments
parsed = parse_srt(srt_content)

# Group short cues into 30-60s chunks for semantic search embedding
chunks = chunk_segments(parsed, target_seconds=45)
```

### Video Search Helpers (PgVectorStore)

Thin helper layer for video search on top of PgVectorStore:

```python
from gaik.software_components.RAG.pg_vector_store import (
    PgVectorStore, ingest_video_segments, format_search_results,
)

store = PgVectorStore(db_url, table_name="video_segments", embedding_dim=1536)
store.setup()

# Ingest chunked segments with video metadata
ids = ingest_video_segments(store, embedder, video_title="Lecture 1", video_id="abc123", segments=chunks)

# Format search results with timestamps
results = store.search_hybrid(query_vec, query_text, top_k=10)
formatted = format_search_results(results)
# Returns: [{text, video_title, video_id, start_seconds, end_seconds, timestamp, score}, ...]
```

### ParallelTranscriber (Production-grade Parallel Transcription)

Production parallel transcription using FFmpeg chunking. Requires `ffmpeg` + `ffprobe` on `$PATH`.

```python
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber, TranscriptionConfig, TranscriptionModel,
)
from gaik.software_components.config import get_openai_config

api_config = get_openai_config(use_azure=True)
tc = TranscriptionConfig(chunk_duration_minutes=15, model=TranscriptionModel.WHISPER)
transcriber = ParallelTranscriber(api_config, tc)

result = transcriber.transcribe("long_interview.mp4")
print(result.plain_text)
result.save("output/")
```

Models: `TranscriptionModel.WHISPER`, `TranscriptionModel.GPT4O_DIARIZE` (with speaker diarization).
Supports thread-safe cancellation via `SimpleCancellation` and progress callbacks.

### DocumentClassifier

```python
from gaik.software_components.doc_classifier import DocumentClassifier, get_openai_config

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
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.config import get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config, model="text-embedding-3-large")

# Embed documents
embeddings, docs = embedder.embed(["Document text 1", "Document text 2"])

# Embed a single query for search
query_embedding = embedder.embed_query("What is the main topic?")
```

#### VectorStore (In-Memory + Chroma)

```python
from gaik.software_components.RAG.vector_store import VectorStore

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

#### PgVectorStore (PostgreSQL + pgvector)

Production PostgreSQL vector store with semantic, keyword, and hybrid search.

```python
from gaik.software_components.RAG.pg_vector_store import PgVectorStore

with PgVectorStore("postgresql://user:pass@host:5432/db", embedding_dim=3072) as store:
    store.setup()  # Create extensions, table, indexes (idempotent)
    ids = store.add(documents, embeddings)

    # 4 search methods
    results = store.search_semantic(query_vec, top_k=5, threshold=0.7)
    results = store.search_keyword("search terms", top_k=5)
    results = store.search_hybrid(query_vec, "search terms", top_k=5)
    results = store.search_hybrid_weighted(query_vec, "terms", semantic_weight=0.7)
```

Requires: PostgreSQL with `pgvector`, `pg_trgm`, `unaccent` extensions.
Drop-in compatible with `Retriever` (same `search()` interface as `VectorStore`).

#### Retriever (Semantic + Hybrid Search)

```python
from gaik.software_components.RAG.retriever import Retriever

retriever = Retriever(
    embedder=embedder,
    vector_store=store,       # VectorStore or PgVectorStore
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
from gaik.software_components.RAG.answer_generator import AnswerGenerator

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
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

parser = VisionRagParser(vision_config=config)

# Get LangChain Document chunks with vision-enhanced image descriptions
chunks = parser.convert_doc_to_chunks_with_vision("document.pdf")
# Each chunk has: page_content, metadata (source, document_name, page_number, heading)
```

#### DoclingRagParser (Structure-aware RAG Chunks)

```python
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

parser = DoclingRagParser(enable_ocr=True, ocr_engine="tesseract_cli")

# Convert PDF to markdown
markdown = parser.convert_pdf_to_markdown("document.pdf")

# Convert PDF to LangChain Document chunks (HierarchicalChunker)
chunks = parser.convert_pdf_to_chunks_with_metadata("document.pdf")
```

## Software Components (End-to-End Pipelines)

### AudioToStructuredData

Audio -> Transcript -> Schema -> Structured JSON:

```python
from gaik.software_modules.audio_to_structured_data import AudioToStructuredData

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
from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

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
from gaik.software_modules.RAG_workflow import RAGWorkflow

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
| **Building block** | Atomic toolkit class/function | `Transcriber`, `ParallelTranscriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `Embedder`, `VectorStore`, `PgVectorStore`, `Retriever`, `AnswerGenerator`, `VisionRagParser`, `DoclingRagParser`, `srt_utils`, `video_search_helpers` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow` |

## Use Cases

The toolkit has documented use cases in `guidance_layer/website/content/docs/use-cases/`. These demonstrate real-world applications across industries:

| Use Case | Status | Components Used |
|----------|--------|-----------------|
| **Dental Transcription & Close Captioning** | Documented | ParallelTranscriber, TranscriptionConfig |
| **Semantic Dental Video Search** | Documented | Embedder, PgVectorStore, Retriever (hybrid search) |
| **Incident Reporting** | Documented | AudioToStructuredData (voice -> structured report) |
| **Dental Learning Assistant** | Coming soon | RAGWorkflow (Q&A over course content) |
| **Purchase Order Processing** | Coming soon | DocumentsToStructuredData |
| **Construction Site Diary Creation** | Coming soon | AudioToStructuredData (voice notes -> diary) |
| **Report Writing** | Coming soon | AnswerGenerator, RAGWorkflow |
| **Sales Proposal Generation** | Coming soon | DocumentsToStructuredData, RAGWorkflow |
| **Customer Onboarding & Sales Assistant** | Coming soon | RAGWorkflow |

**Use-case docs source:** `guidance_layer/website/content/docs/use-cases/`
**Published docs:** https://gaik-project.github.io/gaik-toolkit/

## Maintenance Notes

This skill documents gaik-toolkit. Update when:
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
- [RAG Building Blocks](references/rag.md) - RAG components API reference
- [Software Components](references/software-components.md) - Pipeline patterns and options
- [Examples](references/examples.md) - Complete working examples (invoice extraction, medical transcription, meeting notes, batch processing, RAG with PostgreSQL, parallel transcription, FastAPI integration)
