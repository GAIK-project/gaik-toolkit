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
- **Software modules** – end‑to‑end pipelines combining the software components such as "audio → structured data", "documents → structured data", "RAG workflow", "multi‑source report generation" and "CURACT report writing"

## Architecture overview

GAIK distinguishes three levels:

| Level                  | Concept in GAIK                         | Examples                                                      |
|------------------------|-----------------------------------------|---------------------------------------------------------------|
| **Knowledge Service**            | Logical capability                      | `speech_to_text`, `document_parsing`, `information_extraction` |
| **Software component** | Atomic toolkit class / function         | `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `PyMuPDFParser`, `DoclingParser`, `VisionExtractor`, `DocumentClassifier`, `LLMJudge`, `TextToSpeech`, `KnowledgeCurator`, `DraftReviewer` |
| **Software module**    | Composed, workflow‑ready unit           | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow`, `MultiSourceReportGenerator`, `ReportWriter` |

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

# Report writing stages (each one also installs on its own)
pip install "gaik[source-normalizer]"
pip install "gaik[knowledge-curator]"
pip install "gaik[draft-reviewer]"
pip install "gaik[report-synthesizer]"

# Software modules (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"
pip install "gaik[rag-workflow]"
pip install "gaik[multi-source-report-generator]"
pip install "gaik[report-writer]"

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
- Shared helpers: `get_llm_config`, `create_llm_client` for provider-aware configuration; `get_openai_config`, `create_openai_client` remain available for legacy OpenAI/Azure code

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
- `VisionRagParser` – combines Docling with vision models for RAG‑optimized parsing (chunked outputs with image descriptions)
- `SpreadsheetParser` – Excel and CSV files → Markdown tables with sheet names and row numbers

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
- `embedder` – generates vector embeddings with OpenAI/Azure, Google, or a configured embedding model on Aitta / another OpenAI-compatible server
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

### 9. Report Writing – sources → curated knowledge → reviewed report

**Goal:** write governed, source-grounded reports in stages whose results are plain files that a person can inspect and edit. Each component also works on its own.

Software components:

- `SourceNormalizer` – converts mixed files (PDF, DOCX, spreadsheets, text, recordings, images) into Markdown texts with their provenance and source class
- `KnowledgeCurator` – extracts section-bound fact units with verified verbatim quotes, and lists missing items and conflicts between sources
- `DraftReviewer` – fact-checks a generated text against reference material with exact search-and-replace edits and an edit log
- `ReportSynthesizer` – writes and reviews a report section by section from curated knowledge, and saves it as Markdown and DOCX

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

### Report Writer (CURACT)

`ReportWriter` writes a templated, source-grounded report from one report spec (`report_spec.json`) in three stages:

1. `SourceNormalizer` converts the primary and secondary sources to Markdown in `normalized/`
2. `KnowledgeCurator` curates fact units with verbatim quotes, one `knowledge/<section>.json` per section
3. `ReportSynthesizer` writes each section from its knowledge only, has `DraftReviewer` check it, and saves `report/`

Each stage reads the files of the stage before it, so knowledge files and section drafts can be edited and only the later stages rerun. `run(..., mode="single_call")` writes the report in one call as a baseline.

```python
from gaik.software_modules.report_writer import ReportSpec, ReportWriter
```

### Multi‑Source Report Generator (legacy)

`MultiSourceReportGenerator` turns a set of mixed source files into one user‑defined, long‑form Markdown report:

1. Normalises every file (PDF, DOCX, Excel/CSV, text, Markdown, audio/video, images) into Markdown evidence using the appropriate GAIK parser, transcriber, or extractor
2. Writes each section with an LLM from your section titles + per‑section instructions (optionally matching a sample report's format)
3. Returns the assembled Markdown plus a per‑section breakdown of the evidence used

```python
from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator
```

---

## Configuration & environment variables

Text components use `get_llm_config` and the shared `ProviderClient` interface. Supported
providers and their environment variables are:

| Provider | Required env vars | Model selection |
|----------|-------------------|-----------------|
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` |
| `azure` | `AZURE_API_KEY`, `AZURE_ENDPOINT` | `AZURE_DEPLOYMENT` names your deployed model |
| `google` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | `GOOGLE_MODEL`; install `gaik[llm-google]` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL`; install `gaik[llm-anthropic]` |
| `anthropic_foundry` | `ANTHROPIC_FOUNDRY_API_KEY` (fallback `AZURE_API_KEY`), `ANTHROPIC_FOUNDRY_RESOURCE` | `ANTHROPIC_MODEL`; install `gaik[llm-anthropic]` |
| `vertex` | `GOOGLE_PROJECT_ID` and Google application-default or service-account credentials | `GOOGLE_MODEL`, `GOOGLE_CLOUD_LOCATION`; install `gaik[llm-google]` |
| `litellm` | Provider credentials or `LITELLM_API_KEY` | Required provider-prefixed `LITELLM_MODEL`; install `gaik[llm-litellm]` |
| `aitta` | `AITTA_API_KEY` (also accepts `AITTA_API_TOKEN` or `AITTA_TOKEN`) | `AITTA_MODEL`, default `google/gemma-4-31b-it` |
| `openai_compatible` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Explicit model required |

```python
from gaik.software_components.llm import create_llm_client, get_llm_config

config = get_llm_config("aitta")  # or "azure", "google", "openai", "anthropic"
client = create_llm_client(config)
response = client.chat([{"role": "user", "content": "Explain knowledge management briefly."}])
print(response.text)
```

Pass the same config to `DataExtractor`, `DocumentClassifier`, `TranscriptEnhancer`,
`AnswerGenerator`, or `Embedder`. Choose a model that supports the component's operation:
extraction/classification need structured output, and embeddings need a separate embedding
model (`AITTA_EMBEDDING_MODEL` for Aitta). Aitta uses
`https://aitta-api.csc.fi/openai/v1` with a 600-second default timeout for cold starts.
`timeout` and `max_retries` can be overridden in `get_llm_config` for OpenAI SDK clients.
See the [official Aitta guide](https://docs.lumi-supercomputer.eu/laif/inference/aitta/) for
project tokens, available models, and capacity limits, and run
[`example_aitta_smoke.py`](examples/software_components/llm/example_aitta_smoke.py) to check
connectivity with your configured token.

OpenAI-compatible providers reuse the OpenAI SDK. Google/Vertex and Anthropic use native
SDKs; LiteLLM is an optional backend for other integrations. `VisionParser`,
`MultimodalParser(api_config=config)`, `VisionExtractor(api_config=config)`,
`FormUnderstander(config=config)`, and `LLMJudge(config=config)` accept shared provider
configs. Image inputs require a vision-capable model. Audio components require
OpenAI/Azure audio configs; choose separate transcription and extraction configs in
`AudioToStructuredData` when using a different provider for text extraction.

The September 2026 Aitta checks passed chat, structured extraction and vision with
`google/gemma-4-31b-it`. Embedding service availability was not confirmed; configure an
explicit supported embedding model or use a separate embedding provider in `RAGWorkflow`.

Legacy `get_openai_config(use_azure=True)` and `create_openai_client` remain supported.
Provider resolution prioritizes an explicit provider, then `config["provider"]`, then
legacy `config["use_azure"]`, then `LLM_PROVIDER`, then Azure. See the
[multi-provider guide](../guidance_layer/website/content/docs/toolkit/multi-provider-llm.mdx)
for the capability matrix and component examples.

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
 `Transcriber` + `DocumentClassifier` + `VisionRagParser` + `ReportWriter` 

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
