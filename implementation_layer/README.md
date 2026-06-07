# GAIK Toolkit Implementation layer description
[![PyPI version](https://img.shields.io/pypi/v/gaik.svg)](https://pypi.org/project/gaik/)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)

## Two approaches for Generative AI solution implementation

Two approaches for Generative AI solution implementation are supported by the toolkit:
1. Code-based
2. No-code

## Code-based implementation 

The key parts of the code-based implementation layer includes:

- **Software components** – reusable utilities for extraction, parsing, transcription, transcript enhancement, classification, RAG, validation/evaluation, LLM provider access, text-to-speech, PostgreSQL querying, and one-call vision extraction
- **Software modules** – end‑to‑end pipelines combining the software components such as "audio → structured data", "documents → structured data", and "RAG workflow"

## Architecture overview

GAIK distinguishes three levels:

| Level                  | Concept in GAIK                         | Examples                                                      |
|------------------------|-----------------------------------------|---------------------------------------------------------------|
| **Knowledge Service**            | Logical capability                      | `speech_to_text`, `document_parsing`, `information_extraction` |
| **Software component** | Atomic toolkit class / function         | `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `PyMuPDFParser`, `DoclingParser`, `VisionExtractor`, `DocumentClassifier`, `LLMJudge`, `TextToSpeech` |
| **Software module**    | Composed, workflow‑ready unit           | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow` |

In code, that maps to:

- `gaik.software_components.*` – low‑level, reusable primitives
- `gaik.software_modules.*` – opinionated end‑to‑end pipelines that orchestrate multiple software components

The higher‑level GAIK Solution Wizard (under development) will:

1. Select a template (generic pattern) for a use case
2. Choose required services
3. Map them to building blocks / software components from this toolkit
4. Generate an executable workflow and deployment configuration

---

## Installation

Install only what you need, or the full toolkit:

```bash
# Structured extraction (schema generation + extraction)
pip install "gaik[extract]"

# Document parsing (vision-based + local parsers)
pip install "gaik[parser]"

# RAG parsing (chunked outputs)
pip install "gaik[rag-parser-docling]"
pip install "gaik[rag-parser-vision]"
pip install "gaik[embedder]"
pip install "gaik[vector-store]"
pip install "gaik[pg-vector-store]"
pip install "gaik[retriever]"
pip install "gaik[answer-generator]"

# Audio/video transcription (Whisper + GPT enhancement)
pip install "gaik[transcriber]"
pip install "gaik[parallel-transcriber]"
pip install "gaik[enhance-transcript]"

# Document classification
pip install "gaik[classifier]"

# Single-call vision extraction (document/image -> structured data)
pip install "gaik[vision-extract]"

# Multi-provider multimodal parsing
pip install "gaik[multimodal-parser]"

# LLM adapters, validation, and evaluation
pip install "gaik[llm-anthropic]"
pip install "gaik[llm-google]"
pip install "gaik[llm-judge]"
pip install "gaik[evaluators]"
pip install "gaik[rag-response-evaluator]"

# Text-to-speech and database agent
pip install "gaik[text-to-speech]"
pip install "gaik[postgres-agent]"

# Software modules (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"
pip install "gaik[rag-workflow]"

# Everything
pip install "gaik[all]"

```

For video processing and audio compression you'll need `ffmpeg` installed on your system (optional but recommended).

---

## Core Software Components

### 1. Extractor – schema‑based structured data

**Goal:** turn natural‑language requirements into a schema, then use that schema to extract **type‑safe structured data** from text.

Key software components:

- `SchemaGenerator` – infers a Pydantic model from a requirements prompt (field names, types, nested structures)
- `DataExtractor` – uses that model to extract structured records from one or more documents
- Shared helpers: `get_openai_config`, `create_openai_client` for OpenAI/Azure configuration

### 2. Vision Extractor – document/image → structured data in one call

**Goal:** combine visual document understanding and structured extraction in a single LLM call for complex layouts where parse-then-extract workflows may lose important context.

Software components:

- `VisionExtractor` – sends PDFs/images directly to OpenAI, Claude, or Gemini models and returns schema-validated structured data
- Supports schema reuse, optional schema generation, provider-specific reasoning settings, verification metadata, usage, timing, and cost reporting

### 3. Parsers – documents → text / markdown

**Goal:** convert PDFs and other documents into clean text or markdown, ready for extraction or retrieval.

Software components:

- `VisionParser` / multimodal parser – LLM/vision‑based PDF → markdown (multi‑page context, table handling, custom prompts)
- `PyMuPDFParser` – fast, local PDF text extraction (no external binaries)
- `DoclingParser` – OCR and multi‑format parsing (for more complex documents)
- `VisionRAGParser` – combines Docling with vision models for RAG‑optimized parsing (chunked outputs with image descriptions)

### 4. Transcriber and Transcript Enhancement – audio / video → transcripts

**Goal:** transcribe audio or video into raw and optionally GPT‑enhanced transcripts, with chunking and compression handled for you.

Software components:

- `Transcriber` – wraps Whisper + optional GPT enhancement, including:
  - chunking for long audio
  - optional audio compression (via ffmpeg)
  - context‑aware multi‑chunk transcription
- `ParallelTranscriber` – FFmpeg-based parallel transcription for longer media and faster throughput
- `TranscriptEnhancer` – two-pass transcript correction/enhancement, especially useful for Finnish or domain-heavy audio
- `TranscriptionResult` – container with save/export helpers

### 5. Classification and Form Understanding

**Goal:** classify documents and understand form-like inputs before routing them into extraction, RAG, or downstream workflows.

Software components:

- `DocumentClassifier` – classifies PDF/DOCX/text inputs into user-defined categories
- `form_understander` – form-oriented understanding utilities for structured document inputs

### 6. RAG Components – retrieval‑augmented generation

**Goal:** build retrieval‑augmented generation pipelines that parse documents, store them as searchable vectors, retrieve relevant context, and generate accurate, cited answers.

Software components:

- `rag_parser_docling` – parses PDFs with Docling into chunked Documents with metadata
- `rag_parser_vision` – combines Docling with vision models to add image descriptions into chunks
- `embedder` – generates vector embeddings from text chunks using OpenAI/Azure models
- `vector_store` – stores embeddings and metadata (in‑memory or Chroma persistent storage)
- `pg_vector_store` – PostgreSQL/pgvector storage with hybrid vector and full-text retrieval support
- `retriever` – retrieves relevant chunks using semantic search (supports hybrid search + reranking)
- `answer_generator` – generates answers from retrieved context with optional citations and conversation history

### 7. LLM, Validation, and Evaluation Utilities

**Goal:** provide shared model-provider access and quality checks for extraction, RAG, and other GenAI workflows.

Software components:

- `llm` – provider adapters and shared LLM access patterns
- `validators` – LLM-as-judge style validation utilities
- `evaluators` – RAG and extraction evaluation helpers, including response evaluation and comparison workflows

### 8. Speech Output and Database Interaction

**Goal:** support additional workflow endpoints beyond extraction and retrieval.

Software components:

- `text_to_speech` – generates spoken audio from text
- `postgres_agent` – turns natural-language questions into controlled PostgreSQL queries with schema introspection and safety constraints

---

## Software modules (end‑to‑end pipelines)

To align with GAIK's **template / Solution Wizard** vision, the toolkit also supports **reusable software modules** built from the software components. These represent common generic patterns.

### Audio → Structured Data

A generic pattern that:

1. Transcribes audio/video into text  
2. Generates a schema from user requirements  
3. Extracts structured fields from the transcript(s)  
4. Optionally persists or reuses schemas across runs

Conceptually:

```text
Audio
  → Transcriber
    → Transcript
      → SchemaGenerator
        → Schema
          → DataExtractor
            → Structured JSON
```

### Documents → Structured Data

A generic pattern that:

1. Parses documents (PDFs, etc.) to text/markdown (VisionParser / Docling / PyMuPDF / DOCX parsing)
2. Generates a schema from user requirements
3. Extracts structured fields from the parsed text
4. Supports schema reuse/persistence similar to the audio pipeline

These pipelines are what higher‑level templates (e.g. “Incident Reporting (Voice → Structured Report)”, “Invoice PDF → Structured Invoice Record”) will bind to.

### RAG Workflow

A retrieval‑augmented pipeline that:

1. Parses documents into structured chunks (Docling + vision)
2. Generates embeddings and stores them in a vector database (Chroma)
3. Retrieves top‑k relevant chunks for a query
4. Produces a cited answer from retrieved context

---

## Configuration & environment variables

All modules share a consistent configuration pattern via `get_openai_config` and `create_openai_client`.

Supported providers & environment variables:

| Provider | Required env vars                                     |
|----------|--------------------------------------------------------|
| OpenAI   | `OPENAI_API_KEY`                                      |
| Azure    | `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_DEPLOYMENT` |

`get_openai_config(use_azure=True)` returns a config dict that can be passed to all building blocks.

---

## Typical GAIK workflows this toolkit enables

Although the full Solution Wizard and template catalogue live outside this repo, this toolkit is designed to support patterns such as:

- **Incident reporting (voice/recording + images → structured extraction → report generation)**
  `Transcriber` + `SchemaGenerator` + `DataExtractor` + `ReportWriter`
- **PO and BOM processing (PDF → structured extraction → price calculation →  sales order generation)**
  `VisionParser` / `PyMuPDFParser` + `SchemaGenerator` + `DataExtractor` + `ReportWriter`
- **Construction Diary Creation (voice/recording + images → structured extraction → report generation)**
`Transcriber` + `SchemaGenerator` + `DataExtractor` + `ReportWriter`
- **Transcription and Translation of domain-specific videos (Transcription + Translation)**
 `Transcriber` + `PostTranscriptEnhancer`
 - **Semantic Video Search (Semantic + keyword based search within videos)**
 `Embedder` + `vectorStore` + `HybridRetriever` + `ReRanker`
- **Construction Site Report Generation (Multiple documents + images + audios + notes + sample report → A structured report)**
 `Transcriber` + `DocumentClassifier` + `VisionRAGParser` + `ReportWriter` 

At solution level, a template or SolutionWizardSpec can express these as **services** implemented by GAIK software components and modules.

---

## Examples & documentation

Explore the examples included in the repository:

- Software component examples (including RAG components): `implementation_layer/examples/software_components/`
- Software module examples: `implementation_layer/examples/software_modules/`
- Demos and experiments: `implementation_layer/toolkit_demo_app/`

---
## Contributing

Contributions are welcome — from bug reports and documentation improvements to new software components and modules that fit the GAIK architecture.

Please see [`guidance_layer/CONTRIBUTING.md`](guidance_layer/CONTRIBUTING.md) for contribution guidelines.

---
