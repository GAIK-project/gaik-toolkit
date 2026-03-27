---
name: gaik-toolkit
description: >-
  GAIK toolkit development: structured data extraction, document parsing,
  audio transcription (Whisper/local), transcript enhancement, text-to-speech,
  RAG pipelines (pgvector/Chroma), document classification, end-to-end pipelines,
  demo app (Next.js + FastAPI), and docs website (Fumadocs).
argument-hint: "[component-name]"
---

# GAIK Toolkit

Current PyPI version: !`python ${CLAUDE_SKILL_DIR}/scripts/fetch_pypi_readme.py --version`

Python toolkit for knowledge extraction, capture, and generation. Use when working with:

- Structured data extraction from documents, PDFs, images, or audio
- Schema generation from natural language requirements
- Document parsing (PDF, DOCX, images)
- Audio/video transcription with Whisper + local Whisper backends (Finnish fine-tuned model)
- Transcript enhancement — two-pass LLM error correction
- Parallel transcription with FFmpeg chunking
- Text-to-speech generation
- Document classification
- RAG pipelines: embedder, vector store (Chroma / PostgreSQL), retriever, answer generator
- End-to-end pipelines: AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow

## Quick Links

- **Documentation**: https://gaik-project.github.io/gaik-toolkit/
- **Live Demo**: https://gaik-demo.2.rahtiapp.fi/ (registration required)
- **GitHub**: https://github.com/GAIK-project/gaik-toolkit
- **Source Code**: `implementation_layer/src/gaik/`
- **PyPI**: https://pypi.org/project/gaik/

## Repository Structure

| Path | Description |
|------|-------------|
| `implementation_layer/src/gaik/` | Python package source (building blocks + software modules) |
| `implementation_layer/toolkit_demo_app/` | Next.js + FastAPI interactive demo app (bun + uv) |
| `guidance_layer/website/` | Documentation website (Fumadocs/Next.js, deployed to GitHub Pages) |
| `guidance_layer/website/content/docs/` | Documentation source (`.mdx` files) |
| `implementation_layer/no-code-assets/` | Prompt templates and agent skills for no-code usage |
| `strategy_layer/` | Value evaluation framework, AI maturity assessment |
| `business_layer/` | GenAI product canvas templates |

## Toolkit Demo App

Interactive web app at `implementation_layer/toolkit_demo_app/`. Next.js 16 + FastAPI (bun + uv).

- **Live**: https://gaik-demo.2.rahtiapp.fi/ (registration required)
- **Dev**: `bun run dev:all` (runs both frontend and API)
- **See**: [Demo App Reference](references/demo-app.md) for full architecture, routes, and conventions

## Documentation Website

Fumadocs/Next.js site at `guidance_layer/website/`. Content in `.mdx` files under `content/docs/`.

- **Live**: https://gaik-project.github.io/gaik-toolkit/
- **Dev**: `pnpm dev` (from `guidance_layer/website/` -- uses pnpm, not bun)
- **See**: [Docs Website Reference](references/docs-website.md) for content structure and editing guide

## Installation

Install via pip with optional extras: `pip install "gaik[extract]"`, `pip install "gaik[all-cpu]"`, etc.
See [Installation Reference](references/installation.md) for all available extras and setup.

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

Core classes in `gaik.software_components.*`. For detailed API and constructor parameters, see [Building Blocks Reference](references/building-blocks.md).

| Component | Import | Key Method |
|-----------|--------|------------|
| SchemaGenerator | `from gaik.software_components.extractor import SchemaGenerator` | `generate_schema(user_requirements)` |
| DataExtractor | `from gaik.software_components.extractor import DataExtractor` | `extract(extraction_model, requirements, ...)` |
| VisionParser | `from gaik.software_components.parsers import VisionParser` | `convert_pdf(path)` → list[str] per page |
| PyMuPDFParser | `from gaik.software_components.parsers import PyMuPDFParser` | `parse_pdf(path)` → str |
| DocxParser | `from gaik.software_components.parsers import DocxParser` | `parse_docx(path)` → str |
| DoclingParser | `from gaik.software_components.parsers import DoclingParser` | `parse(path)` → str |
| Transcriber | `from gaik.software_components.transcriber import Transcriber` | `transcribe(path)` → TranscriptionResult |
| TranscriptEnhancer | `from gaik.software_components.enhance_transcript import TranscriptEnhancer` | `enhance_text(text)` / `enhance_file(path)` |
| ParallelTranscriber | `from gaik.software_components.parallel_transcriber import ParallelTranscriber` | `transcribe(path)` → TranscriptionResult |
| TextToSpeech | `from gaik.software_components.text_to_speech import TextToSpeech` | `synthesize(text)` → SpeechSynthesisResult |
| DocumentClassifier | `from gaik.software_components.doc_classifier import DocumentClassifier` | `classify(file_or_dir, classes)` |

### Transcriber notes

- Models: `"whisper"`, `"whisper-1"`, `"gpt-4o-transcribe"`, `"whisper_local"`
- `enhanced_transcript=True` runs output through TranscriptEnhancer (two-pass LLM correction)
- `whisper_local` requires `local_api_base` + `local_api_key`; `language="fi"` selects Finnish fine-tuned model
- ParallelTranscriber uses FFmpeg chunking; requires `ffmpeg` + `ffprobe` on `$PATH`

### SRT/VTT Utilities

```python
from gaik.software_components.transcriber import segments_to_srt, segments_to_vtt, parse_srt, chunk_segments
```

### Video Search Helpers

```python
from gaik.software_components.RAG.pg_vector_store import PgVectorStore, ingest_video_segments, format_search_results
```

## RAG Building Blocks

Core RAG classes in `gaik.software_components.RAG.*`. For full API, see [RAG Reference](references/rag.md).

| Component | Import | Key Method |
|-----------|--------|------------|
| Embedder | `from gaik.software_components.RAG.embedder import Embedder` | `embed(docs)`, `embed_query(text)` |
| VectorStore | `from gaik.software_components.RAG.vector_store import VectorStore` | `add(docs, embeddings)`, `search(vec, top_k)` |
| PgVectorStore | `from gaik.software_components.RAG.pg_vector_store import PgVectorStore` | `search_hybrid(vec, text, top_k)` |
| Retriever | `from gaik.software_components.RAG.retriever import Retriever` | `search(query, top_k, hybrid_search, re_rank)` |
| AnswerGenerator | `from gaik.software_components.RAG.answer_generator import AnswerGenerator` | `generate(query, documents, stream)` |
| VisionRagParser | `from gaik.software_components.RAG.rag_parser_vision import VisionRagParser` | `convert_doc_to_chunks_with_vision(path)` |
| DoclingRagParser | `from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser` | `convert_pdf_to_chunks_with_metadata(path)` |

## End-to-End Pipelines

Composed pipelines in `gaik.software_modules.*`. For full API, see [Software Components Reference](references/software-components.md).

| Pipeline | Flow | Import |
|----------|------|--------|
| AudioToStructuredData | Audio → Transcript → Schema → JSON | `from gaik.software_modules.audio_to_structured_data import AudioToStructuredData` |
| DocumentsToStructuredData | PDF/DOCX → Parse → Schema → JSON | `from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData` |
| RAGWorkflow | PDF → Parse → Embed → Store → Retrieve → Answer | `from gaik.software_modules.RAG_workflow import RAGWorkflow` |

All pipelines follow: `pipeline = Pipeline(use_azure=True)` → `result = pipeline.run(file_path, user_requirements, ...)`.

## Architecture Overview

| Level | Concept | Examples |
|-------|---------|----------|
| **Service** | Logical capability | `speech_to_text`, `document_parsing`, `information_extraction`, `rag` |
| **Building block** | Atomic toolkit class/function | `Transcriber`, `ParallelTranscriber`, `TranscriptEnhancer`, `TextToSpeech`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `Embedder`, `VectorStore`, `PgVectorStore`, `Retriever`, `AnswerGenerator` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow` |

## Use Cases

Documented in `guidance_layer/website/content/docs/use-cases/`: incident reporting, dental transcription & captioning, semantic dental video search, construction diary, dental learning assistant, purchase order processing, report writing, sales proposal generation, customer onboarding.

## Detailed References

- [Building Blocks API](references/building-blocks.md) - Constructor params, return types, all options
- [RAG Building Blocks](references/rag.md) - RAG components: Embedder, stores, Retriever, AnswerGenerator
- [Software Components](references/software-components.md) - Pipeline patterns, schema persistence, batch processing
- [Examples](references/examples.md) - Complete working examples (invoice extraction, RAG, parallel transcription, etc.)
- [Demo App](references/demo-app.md) - Demo app architecture, routes, env vars, deployment
- [Docs Website](references/docs-website.md) - Documentation site structure and editing guide
- [Installation](references/installation.md) - All pip install extras and system dependencies
- [Maintenance](references/maintenance.md) - Skill maintenance and PyPI fetch script
