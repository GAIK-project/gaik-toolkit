---
name: gaik-toolkit
description: GAIK (Generative AI Knowledge Management Toolkit) development guidance. Use when working with structured data extraction from documents/PDFs/audio, schema generation, document parsing (VisionParser, PyMuPDFParser, DoclingParser), audio transcription with Whisper (Transcriber, ParallelTranscriber), local Whisper backends (whisper_local with Finnish fine-tuned model), transcript enhancement/error correction (TranscriptEnhancer, enhance_transcript), text-to-speech (TextToSpeech), SRT/VTT subtitle generation (srt_utils), document classification, RAG pipelines (Embedder, VectorStore, PgVectorStore, Retriever, AnswerGenerator), semantic video search (video_search_helpers), end-to-end pipelines (AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow), the GAIK demo app (Next.js + FastAPI), or the GAIK documentation website (Fumadocs).
---

# GAIK Toolkit

Python toolkit for knowledge extraction, capture, and generation. Use when working with:

- Structured data extraction from documents, PDFs, images, or audio
- Schema generation from natural language requirements
- Document parsing (PDF, DOCX, images)
- Audio/video transcription with Whisper + local Whisper backends (Finnish fine-tuned model)
- **Transcript enhancement** — two-pass LLM error correction (TranscriptEnhancer, enhance_transcript)
- **Parallel transcription** with FFmpeg chunking (ParallelTranscriber)
- **Text-to-speech** generation (TextToSpeech)
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

All components use `get_openai_config()`:

```python
from gaik.software_components.config import get_openai_config, create_openai_client

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
client = create_openai_client(config)        # OpenAI/AzureOpenAI client
```

## Building Blocks

For detailed API docs, see [Building Blocks Reference](references/building-blocks.md) and [RAG Reference](references/rag.md).

### SchemaGenerator + DataExtractor

Generate Pydantic schema from natural language, then extract structured data:

```python
from gaik.software_components.extractor import SchemaGenerator, DataExtractor, get_openai_config

config = get_openai_config(use_azure=True)
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(user_requirements="Extract invoice number, total, vendor name.")

extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema, requirements=generator.item_requirements,
    user_requirements="Extract invoice data",
    documents=["Invoice #12345 from Acme Corp, Total: $1,500"],
    save_json=True, json_path="results.json",
)
```

### Parsers

```python
from gaik.software_components.parsers import VisionParser, PyMuPDFParser, DocxParser, get_openai_config

# VisionParser - LLM-based PDF to markdown (best for complex layouts)
config = get_openai_config(use_azure=True)
parser = VisionParser(openai_config=config, clean_output=True)
pages = parser.convert_pdf("document.pdf")  # list of markdown strings per page

# PyMuPDFParser - fast local PDF extraction
text = PyMuPDFParser().parse_pdf("document.pdf")

# DocxParser - Word documents
text = DocxParser().parse_docx("document.docx")

# DoclingParser - advanced OCR + multi-format (requires GPU)
from gaik.software_components.parsers import DoclingParser
text = DoclingParser().parse("complex_document.pdf")
```

### Transcriber

```python
from gaik.software_components.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)

# Basic usage with transcript error correction
transcriber = Transcriber(api_config=config, enhanced_transcript=True)
result = transcriber.transcribe("meeting.mp3")
print(result.enhanced_transcript or result.raw_transcript)

# Local Whisper backend (e.g. Finnish fine-tuned model on AI Hub)
transcriber = Transcriber(
    api_config=config,
    enhanced_transcript=True,
    enhanced_transcript_instructions="",  # Optional domain-specific instructions
    transcription_model="whisper_local",  # Force local transcription backend
    local_api_base="http://your-server:8080",
    local_api_key="your-api-key",
    language="fi",  # "fi" = Finnish fine-tuned model, "auto" or "en" = whisper-large-v3
)
result = transcriber.transcribe("meeting.mp3")
print(result.srt_content)  # SRT subtitles (whisper_local only)
```

Transcription models: `"whisper"`, `"gpt-4o-transcribe"`, `"whisper_local"`.
When `enhanced_transcript=True`, the Transcriber runs the raw transcript through the standalone `TranscriptEnhancer` component.

### TranscriptEnhancer (enhance_transcript)

Standalone two-pass LLM transcript error correction, currently tuned for Finnish.

```python
from gaik.software_components.enhance_transcript import TranscriptEnhancer, get_openai_config

config = get_openai_config(use_azure=True)
enhancer = TranscriptEnhancer(api_config=config)
result = enhancer.enhance_text(
    "tama on suomenkielinen litterointi jossa on virheita",
    generate_summary=True,
    diff_chunks=True,
    additional_instructions="Keep company names exactly as written.",
)
print(result.enhanced_text)
```

### TextToSpeech

```python
from gaik.software_components.text_to_speech import TextToSpeech, get_openai_config

config = get_openai_config(use_azure=True)
tts = TextToSpeech(api_config=config, language="fi", voice="alloy")
result = tts.synthesize("Tama on tekstista puheeksi.")
result.save("tts_outputs")
```

### ParallelTranscriber

Production parallel transcription using FFmpeg chunking. Requires `ffmpeg` + `ffprobe` on `$PATH`.

```python
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber, TranscriptionConfig, TranscriptionModel,
)
from gaik.software_components.config import get_openai_config

config = get_openai_config(use_azure=True)
tc = TranscriptionConfig(chunk_duration_minutes=15, model=TranscriptionModel.WHISPER)
transcriber = ParallelTranscriber(config, tc)
result = transcriber.transcribe("long_interview.mp4")
print(result.plain_text)
result.save("output/")
```

Models: `TranscriptionModel.WHISPER`, `TranscriptionModel.GPT4O_DIARIZE` (with speaker diarization).
Supports thread-safe cancellation via `SimpleCancellation` and progress callbacks.

### SRT/VTT Subtitle Utilities

```python
from gaik.software_components.transcriber import segments_to_srt, segments_to_vtt, parse_srt, chunk_segments

srt_content = segments_to_srt(segments)  # Whisper segments [{start, end, text}, ...]
vtt_content = segments_to_vtt(segments)
parsed = parse_srt(srt_content)          # Parse SRT back to segments
chunks = chunk_segments(parsed, target_seconds=45)  # Group for embedding
```

### Video Search Helpers

```python
from gaik.software_components.RAG.pg_vector_store import PgVectorStore, ingest_video_segments, format_search_results

store = PgVectorStore(db_url, table_name="video_segments", embedding_dim=1536)
store.setup()
ids = ingest_video_segments(store, embedder, video_title="Lecture 1", video_id="abc", segments=chunks)
results = store.search_hybrid(query_vec, query_text, top_k=10)
formatted = format_search_results(results)
# Returns: [{text, video_title, video_id, start_seconds, end_seconds, timestamp, score}, ...]
```

### DocumentClassifier

```python
from gaik.software_components.doc_classifier import DocumentClassifier, get_openai_config

config = get_openai_config(use_azure=True)
classifier = DocumentClassifier(config=config)
result = classifier.classify(file_or_dir="documents/", classes=["invoice", "receipt", "contract"])
# Returns: {"filename.pdf": {"class": "invoice", "confidence": 0.95, "reasoning": "..."}}
```

### RAG Building Blocks

For full API, see [RAG Reference](references/rag.md).

```python
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.vector_store import VectorStore
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from gaik.software_components.RAG.retriever import Retriever
from gaik.software_components.RAG.answer_generator import AnswerGenerator
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

# Embedder
embedder = Embedder(config=config, model="text-embedding-3-large")
embeddings, docs = embedder.embed(["Document text 1", "Document text 2"])
query_vec = embedder.embed_query("What is the main topic?")

# VectorStore (in-memory or Chroma)
store = VectorStore(persist=True, persist_path="chroma_store")
store.add(docs, embeddings)
results = store.search(query_vec, top_k=5)  # [(Document, score), ...]

# PgVectorStore (PostgreSQL + pgvector) - production
with PgVectorStore("postgresql://user:pass@host:5432/db", embedding_dim=3072) as store:
    store.setup()
    store.add(docs, embeddings)
    results = store.search_hybrid(query_vec, "search terms", top_k=5)

# Retriever (wraps any vector store)
retriever = Retriever(embedder=embedder, vector_store=store, hybrid_search=True, re_rank=True, top_k=5)
documents = retriever.search("What are the key findings?", include_scores=True)

# AnswerGenerator
generator = AnswerGenerator(config=config, citations=True)
answer = generator.generate("What is the summary?", documents, stream=False)

# RAG Parsers
chunks = VisionRagParser(vision_config=config).convert_doc_to_chunks_with_vision("doc.pdf")
chunks = DoclingRagParser(enable_ocr=True).convert_pdf_to_chunks_with_metadata("doc.pdf")
```

## Software Components (End-to-End Pipelines)

For full API, see [Software Components Reference](references/software-components.md).

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
)
print(result.extracted_fields)
```

### RAGWorkflow

End-to-end RAG: PDF -> Parse -> Embed -> Store -> Retrieve -> Answer:

```python
from gaik.software_modules.RAG_workflow import RAGWorkflow

workflow = RAGWorkflow(
    use_azure=True, persist=True, persist_path="chroma_store",
    retriever_top_k=5, citations=True, stream=True,
)
index_result = workflow.index_documents(["doc1.pdf", "doc2.pdf"])
result = workflow.ask("What are the key findings?", stream=False)
print(result.answer)
```

## Architecture Overview

| Level | Concept | Examples |
|-------|---------|----------|
| **Service** | Logical capability | `speech_to_text`, `document_parsing`, `information_extraction`, `rag` |
| **Building block** | Atomic toolkit class/function | `Transcriber`, `ParallelTranscriber`, `TranscriptEnhancer`, `TextToSpeech`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `Embedder`, `VectorStore`, `PgVectorStore`, `Retriever`, `AnswerGenerator`, `VisionRagParser`, `DoclingRagParser`, `srt_utils`, `video_search_helpers` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData`, `RAGWorkflow` |

## Use Cases

Documented use cases in `guidance_layer/website/content/docs/use-cases/`: incident reporting, dental transcription & captioning, semantic dental video search, construction diary, dental learning assistant, purchase order processing, report writing, sales proposal generation, customer onboarding.

## Detailed References

- [Building Blocks API](references/building-blocks.md) - Detailed API for all building blocks
- [RAG Building Blocks](references/rag.md) - RAG components API reference
- [Software Components](references/software-components.md) - Pipeline patterns and options
- [Examples](references/examples.md) - Complete working examples
- [Demo App](references/demo-app.md) - Demo app architecture, routes, and dev conventions
- [Docs Website](references/docs-website.md) - Documentation site structure and editing guide
- [Installation](references/installation.md) - All pip install extras and environment setup
- [Maintenance](references/maintenance.md) - Skill maintenance and PyPI fetch script
