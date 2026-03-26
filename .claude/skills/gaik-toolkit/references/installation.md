# Installation Reference

Install via pip with optional extras based on your needs.

## Available Extras

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

# Transcript enhancement (two-pass LLM error correction)
pip install "gaik[enhance-transcript]"

# Text-to-speech
pip install "gaik[text-to-speech]"

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

## System Dependencies

- **ffmpeg + ffprobe:** Required for `parallel-transcriber` and video processing. Must be on `$PATH`.
- **PostgreSQL with pgvector:** Required for `pg-vector-store`. Needs `pgvector`, `pg_trgm`, `unaccent` extensions.
- **GPU/CUDA:** Optional. `parser` and `rag-parser-docling` include docling with torch GPU support. Use `parser-cpu` / `all-cpu` for CPU-only.

## Quick Guide: Which Extra to Use

| Task | Extra |
|------|-------|
| Extract structured data from text | `extract` |
| Parse PDFs (fast, local) | `parser-cpu` |
| Parse PDFs (with OCR/GPU) | `parser` |
| Transcribe audio/video | `transcriber` or `parallel-transcriber` |
| Fix transcript errors (LLM) | `enhance-transcript` |
| Text-to-speech | `text-to-speech` |
| Classify documents | `classifier` |
| Build RAG pipeline | `rag-workflow` |
| Just embeddings | `embedder` |
| PostgreSQL vector store | `pg-vector-store` |
| Full toolkit (cloud/CPU) | `all-cpu` |
| Full toolkit (GPU) | `all` |
