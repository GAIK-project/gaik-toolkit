---
name: gaik-toolkit
description: >-
  GAIK toolkit overview and reference. Use when needing context on GAIK
  components (extractors, parsers, transcribers, RAG, TTS, classifiers,
  pipelines), the repository structure, configuration pattern, environment
  variables, building-block API tables, the documentation update map, or the
  demo app and docs website setup. For CREATING a new component package use
  build-software-component; for ADDING EXAMPLES and running the canonical
  publish flow (docs → demo app → PyPI tag) use gaik-add-examples. Covers:
  structured data extraction, document parsing, audio transcription
  (Whisper/local), transcript enhancement, text-to-speech, RAG pipelines
  (pgvector/Chroma), document classification, text-to-SQL agents (PostgreSQL,
  CSV/Excel via DuckDB), end-to-end pipelines.
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
- Text-to-SQL: natural-language querying of PostgreSQL databases and CSV/Excel/Parquet files (DuckDB)
- RAG pipelines: embedder, vector store (Chroma / PostgreSQL), retriever, answer generator
- End-to-end pipelines: AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow

## Related Skills

This skill is the **overview / reference**. Two sibling skills handle workflows:

| Task | Skill |
|------|-------|
| Create a new installable component package (source + `pyproject.toml` + extras) | **`build-software-component`** |
| Add an example, then optionally publish (docs → demo app → PyPI tag) | **`gaik-add-examples`** |
| Understand the toolkit: components, config, repo layout, docs update map | **this skill** |

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
AZURE_DEPLOYMENT=gpt-5.4
AZURE_API_VERSION=2025-03-01-preview
```

**OpenAI:**

```bash
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-5.4
```

## Configuration Pattern

Two parallel surfaces ship since `gaik>=0.3.21`. Pick the simpler one for OpenAI/Azure-only use cases; pick the multi-provider one when the same code needs to switch between OpenAI, Azure, Anthropic, or Google.

**Legacy surface (OpenAI/Azure only — bit-for-bit unchanged):**

```python
from gaik.software_components.config import get_openai_config, create_openai_client

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
client = create_openai_client(config)        # OpenAI/AzureOpenAI client
```

**Multi-provider surface (Anthropic, Google, OpenAI, Azure):**

```python
from gaik.software_components.llm import get_llm_config, create_llm_client

config = get_llm_config("google")            # or "anthropic", "openai", "azure"
client = create_llm_client(config)           # ProviderClient with chat/chat_parsed/chat_stream/embed
```

`gaik[llm-anthropic]` and `gaik[llm-google]` extras pull in the provider SDKs on demand. Audio components (transcriber, TTS) and vision parsing only support OpenAI/Azure — they raise `NotImplementedError` for native Anthropic/Google. For multi-provider vision, use `MultimodalParser`. For Gemini-via-OpenAI-compat-endpoint, set `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/` on a standard OpenAI config — every component then routes through the legacy path.

## Building Blocks

Core classes in `gaik.software_components.*`. For detailed API and constructor parameters, see [Building Blocks Reference](references/building-blocks.md).

| Component | Import | Key Method |
|-----------|--------|------------|
| SchemaGenerator | `from gaik.software_components.extractor import SchemaGenerator` | `generate_schema(user_requirements)` |
| DataExtractor | `from gaik.software_components.extractor import DataExtractor` | `extract(extraction_model, requirements, ...)` |
| VisionExtractor | `from gaik.software_components.vision_extractor import VisionExtractor` | `extract(file_paths, user_requirements, extraction_model=None, requirements=None, schema_dir=None)` → VisionExtractionResult (single-pass PDF/image → structured data; OpenAI / Claude / Google) |
| VisionParser | `from gaik.software_components.parsers import VisionParser` | `convert_pdf(path)` → list[str] per page |
| PyMuPDFParser | `from gaik.software_components.parsers import PyMuPDFParser` | `parse_pdf(path)` → str |
| DocxParser | `from gaik.software_components.parsers import DocxParser` | `parse_docx(path)` → str |
| DoclingParser | `from gaik.software_components.parsers import DoclingParser` | `parse(path)` → str |
| VisionPlusParser | `from gaik.software_components.parsers import VisionPlusParser` | `parse_document_with_vision_plus(path)` → markdown + metadata |
| DoclingApiClientParser | `from gaik.software_components.parsers import DoclingApiClientParser` | `parse_document_via_api(path)` → remote Docling result |
| MultimodalParser | `from gaik.software_components.parsers import MultimodalParser` | `parse(pdf_path)` → `ParseResult` (OpenAI / Claude / Gemini) |
| Transcriber | `from gaik.software_components.transcriber import Transcriber` | `transcribe(path)` → TranscriptionResult |
| TranscriptEnhancer | `from gaik.software_components.enhance_transcript import TranscriptEnhancer` | `enhance_text(text)` / `enhance_file(path)` |
| ParallelTranscriber | `from gaik.software_components.parallel_transcriber import ParallelTranscriber` | `transcribe(path)` → TranscriptionResult |
| TextToSpeech | `from gaik.software_components.text_to_speech import TextToSpeech` | `synthesize(text)` → SpeechSynthesisResult |
| DocumentClassifier | `from gaik.software_components.doc_classifier import DocumentClassifier` | `classify(file_or_dir, classes)` |
| FormUnderstander | `from gaik.software_components.form_understander import FormUnderstander` | `clean_labels(fields, language_hint="fi")` → `dict[str, str]` (cryptic ASP.NET / generated form ids → readable labels) |
| PostgresAgent | `from gaik.software_components.postgres_agent import PostgresAgent` | `ask(question)` → AnswerResult (text-to-SQL agent: introspects schema, generates validated read-only SQL, runs it, answers; also `get_schema()` / `generate_sql()` / `query()` / `run_sql()`; install `gaik[postgres-agent]`) |
| TabularAgent | `from gaik.software_components.tabular_agent import TabularAgent` | `ask(question)` → AnswerResult (text-to-SQL agent for files: loads CSV/Excel/Parquet/JSON into DuckDB, profiles columns, generates validated read-only SQL, answers; cleans up messy report sheets — title rows, subtotals, Nordic comma-decimals; one table per Excel sheet so cross-sheet joins work; same `get_schema()` / `run_sql()` tool surface as PostgresAgent; install `gaik[tabular-agent]`) |
| LLMJudge | `from gaik.software_components.validators import LLMJudge` | `validate(source_pages, extracted, rubric)` → ValidationResult (rubric scoring; Likert 1-5 via `rubric.scoring_mode="likert_1_5"`) / `detect_hallucinations(source, extracted)` → schema-agnostic post-validator / `judge_text_pair(a, b)` → text-vs-text equivalence (multi-provider) |
| LLMJudgePanel | `from gaik.software_components.validators import LLMJudgePanel` | `validate(source_pages, extracted, rubric)` → JudgePanelResult (3+ judges, majority vote, agreement metric) |
| compare_pairwise | `from gaik.software_components.validators import compare_pairwise` | `compare_pairwise(judge, pages, a, b, swap_and_average=True)` → PairwiseResult (A/B with position-bias mitigation) |
| calibrate_against_human_labels | `from gaik.software_components.validators import calibrate_against_human_labels` | `calibrate_against_human_labels(judge, dataset)` → CalibrationReport (Pearson r vs. human raters) |
| FinnishTextProcessor | `from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor` | `lemmatize(text)` / `to_tsvector_text(text)` / `expand_query(text)` (Finnish lemmatization + compound splitting; backends: voikko / spacy / uralic / simple) |
| ExtractionEvaluator | `from gaik.software_components.evaluators import ExtractionEvaluator` | `evaluate_dataset(dataset, extracted_outputs)` → ExtractionEvaluationResult (field-level P/R/F1 + hallucination rate; optional semantic mode via LLMJudge) |
| RAGEvaluator | `from gaik.software_components.evaluators import RAGEvaluator` | `evaluate_dataset(items)` → RAGEvaluationResult (RAGAS-style faithfulness / answer_relevance / context_precision / context_recall via LLMJudge) |
| BatchEvaluationRunner | `from gaik.software_components.evaluators import BatchEvaluationRunner` | `run(dataset)` → RunnerResult (applies a pipeline callable over a dataset; on_error="skip" tolerates failures) |

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
| MultiSourceReportGenerator | Mixed files (PDF/DOCX/Excel/audio/images) → Normalize → Sectioned Markdown report | `from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator` |

The first three pipelines follow: `pipeline = Pipeline(use_azure=True)` → `result = pipeline.run(file_path, user_requirements, ...)`. `MultiSourceReportGenerator` instead takes a set of source files plus a report structure (section titles + per-section instructions) and returns the assembled Markdown report with a per-section breakdown.

## Architecture Overview

| Level | Concept | Examples |
|-------|---------|----------|
| **Service** | Logical capability | `speech_to_text`, `document_parsing`, `information_extraction`, `rag` |
| **Building block** | Atomic toolkit class/function | `Transcriber`, `ParallelTranscriber`, `TranscriptEnhancer`, `TextToSpeech`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `Embedder`, `VectorStore`, `PgVectorStore`, `Retriever`, `AnswerGenerator` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow`, `MultiSourceReportGenerator` |

## Observability

Token usage, execution time, and provider-specific pricing for all LLM calls. A shared `UsageRecord` type ensures all components report data in the same format regardless of provider (OpenAI / Azure / Anthropic / Google).

```python
from gaik.observability import (
    UsageRecord, build_usage_record,         # uniform usage shape
    compute_cost_usd, lookup_price,          # cost from prompt/completion tokens
    measure_duration,                        # context-manager timing helper
    openai_usage_to_dict,                    # OpenAI-shape → dict normalizer
    OPENAI_PRICING_PER_M, ANTHROPIC_PRICING_PER_M, GEMINI_PRICING_PER_M,
)
```

Use when building a dashboard, logging pipeline, or compliance reporter that needs a unified cost/duration report across providers.

## Use Cases

Documented in `guidance_layer/website/content/docs/use-cases/`: incident reporting, dental transcription & captioning, semantic dental video search, construction diary, dental learning assistant, purchase order processing, report writing, sales proposal generation, customer onboarding.

## When to Update Documentation

When adding or modifying a component, update **both** documentation locations:

| What changed | Update |
|---|---|
| New/modified building block or pipeline | `guidance_layer/docs/software_components/` or `guidance_layer/docs/software_modules/` |
| New/modified building block or pipeline | `guidance_layer/website/content/docs/toolkit/software-components.mdx` or `software-modules.mdx` |
| New use case or example | `guidance_layer/website/content/docs/use-cases/` (new `.mdx` file) |
| New examples added | `implementation_layer/examples/` + README updated |

- **`guidance_layer/docs/`**: Technical Markdown docs (API-level details, constructor params)
- **`guidance_layer/website/content/docs/`**: User-facing MDX for the Fumadocs website
- Run `pnpm dev` from `guidance_layer/website/` to preview website changes
- For the gated, step-by-step publish flow (docs → demo app → PyPI tag), use the **`gaik-add-examples`** skill Step 6 — the canonical follow-up workflow

## Gotchas

Non-obvious things that cause real mistakes in this repo. Check here before assuming.

- **Docs website uses `pnpm`, not `bun`.** Everything else in `toolkit_demo_app/` uses `bun`. Running `bun dev` inside `guidance_layer/website/` silently installs a second lockfile and breaks Fumadocs build.
- **Fumadocs needs `meta.json` updates.** When adding a new `.mdx` page under `content/docs/`, also add it to the parent directory's `meta.json`, or it will not appear in the navigation.
- **`ParallelTranscriber` requires `ffmpeg` + `ffprobe` on `$PATH`.** On Windows that means installing ffmpeg and adding its `bin/` to PATH — there is no Python wheel fallback.
- **`whisper_local` model needs `local_api_base` + `local_api_key`.** `language="fi"` switches to the Finnish fine-tuned model. Leaving `local_api_base` unset fails with an unhelpful OpenAI-style error.
- **Never edit `__version__` strings by hand.** The package version is derived from the git tag by `setuptools-scm`. Manual edits desync the wheel and break the PyPI publish workflow's version validation.
- **CORS_ORIGINS must be valid JSON, not `"*"`.** In the OpenShift API deployment, `CORS_ORIGINS='["*"]'` works; plain `*` crashloops (pydantic-settings parses the env var as a list[str]).
- **OpenAI structured outputs can't use `additionalProperties`.** Prefer an explicit list-of-entries model (see `FormUnderstander.LabelEntry`) over a free-form dict.

## Detailed References

- [Building Blocks API](references/building-blocks.md) - Constructor params, return types, all options
- [RAG Building Blocks](references/rag.md) - RAG components: Embedder, stores, Retriever, AnswerGenerator
- [Software Components](references/software-components.md) - Pipeline patterns, schema persistence, batch processing
- [Evaluators](references/evaluators.md) - ExtractionEvaluator, RAGEvaluator, BatchEvaluationRunner (LLMJudge v2 -based)
- [Examples](references/examples.md) - Complete working examples (invoice extraction, RAG, parallel transcription, etc.)
- [Demo App](references/demo-app.md) - Demo app architecture, routes, env vars, deployment
- [Docs Website](references/docs-website.md) - Documentation site structure and editing guide
- [Installation](references/installation.md) - All pip install extras and system dependencies
- [Maintenance](references/maintenance.md) - Skill maintenance and PyPI fetch script
