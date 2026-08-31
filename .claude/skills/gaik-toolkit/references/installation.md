# Installation Reference

Install via pip with optional extras based on your needs.

## Available Extras

```bash
# Structured extraction (schema generation + extraction)
pip install "gaik[extract]"

# Single-pass vision extraction (PDF/image → structured data)
# Pulls anthropic + google-auth + requests for multi-provider (OpenAI/Claude/Google).
pip install "gaik[vision-extract]"

# Document parsing (includes docling with GPU support)
pip install "gaik[parser]"

# Document parsing (CPU-only, no docling/torch)
pip install "gaik[parser-cpu]"

# Audio/video transcription (sequential)
pip install "gaik[transcriber]"

# Parallel transcription (FFmpeg-based, requires ffmpeg on $PATH)
pip install "gaik[parallel-transcriber]"

# Transcript enhancement (two-pass LLM error correction)
pip install "gaik[enhance-transcript]"

# Text-to-speech
pip install "gaik[text-to-speech]"

# Document classification
pip install "gaik[classifier]"

# Multi-provider PDF-to-markdown parsing (OpenAI / Claude / Gemini)
pip install "gaik[multimodal-parser]"

# Text-to-SQL agents
pip install "gaik[postgres-agent]"   # PostgreSQL: NL question -> validated read-only SQL
pip install "gaik[tabular-agent]"    # CSV/Excel/Parquet files via DuckDB (same pattern)

# LLM-as-judge validation and dataset evaluators
pip install "gaik[llm-judge]"
pip install "gaik[evaluators]"

# Multi-provider LLM client adapters (opt-in per provider)
pip install "gaik[llm-anthropic]"
pip install "gaik[llm-google]"

# Finnish RAG text processing (lemmatization + compound splitting)
pip install "gaik[finnish-rag]"

# Software components (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"
pip install "gaik[multi-source-report-generator]"   # + -agentic / -docx variants

# RAG building blocks
pip install "gaik[embedder]"
pip install "gaik[vector-store]"
pip install "gaik[pg-vector-store]"
pip install "gaik[retriever]"
pip install "gaik[ranker]"                # fusion/reordering; pure Python
pip install "gaik[ranker-rerank]"         # + cross-encoder reranking (torch)
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

## System Dependencies

- **ffmpeg + ffprobe:** Required for `parallel-transcriber` and video processing. Must be on `$PATH`.
- **PostgreSQL with pgvector:** Required for `pg-vector-store`. Needs `pgvector`, `pg_trgm`, `unaccent` extensions.
- **GPU/CUDA:** Optional. `parser` and `rag-parser-docling` include docling with torch GPU support. Use `parser-cpu` / `all-cpu` for CPU-only.

## Quick Guide: Which Extra to Use

| Task | Extra |
|------|-------|
| Extract structured data from text | `extract` |
| Extract structured data from PDFs/images (single-pass, vision) | `vision-extract` |
| Parse PDFs (fast, local) | `parser-cpu` |
| Parse PDFs (with OCR/GPU) | `parser` |
| Transcribe audio/video | `transcriber` or `parallel-transcriber` |
| Fix transcript errors (LLM) | `enhance-transcript` |
| Text-to-speech | `text-to-speech` |
| Classify documents | `classifier` |
| Ask a PostgreSQL database questions in plain language | `postgres-agent` |
| Ask CSV/Excel/Parquet files questions in plain language | `tabular-agent` |
| Score/validate LLM outputs (judge, panel, hallucination check) | `llm-judge` |
| Generate reports from mixed source files | `multi-source-report-generator` |
| Build RAG pipeline | `rag-workflow` |
| Just embeddings | `embedder` |
| PostgreSQL vector store | `pg-vector-store` |
| Fuse or reorder search results (RRF, asc/desc) | `ranker` |
| Full toolkit (cloud/CPU) | `all-cpu` |
| Full toolkit (GPU) | `all` |
