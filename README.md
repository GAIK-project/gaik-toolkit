# GAIK – Generative AI Knowledge Management Toolkit

[![PyPI version](https://img.shields.io/pypi/v/gaik.svg)](https://pypi.org/project/gaik/)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tests](https://github.com/GAIK-project/gaik-toolkit/actions/workflows/tests.yml/badge.svg)

This is a generative AI toolkit of the GAIK project ([gaik.ai](https://gaik.ai)). It provides reusable building blocks and composable software components for knowledge-centric GenAI solutions.

The toolkit focuses on three core knowledge processes in organizational workflows:

- **Knowledge extraction** – extracting structured information from unstructured content (documents, PDFs, web pages, audio transcripts).
- **Knowledge capture** – precise and accurate access of information from variety of data sources (internal documents, ERPs, Drives, etc.).
- **Knowledge generation** – using the structured representations (and underlying models) to produce summaries, reports, insights, and other human-readable outputs tailored to specific tasks.

Internally, these capabilities are exposed as:

- **Building blocks** – atomic utilities such as `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `PyMuPDFParser`, `DoclingParser`
- **Software components** – opinionated end‑to‑end pipelines such as “audio → structured data” and “documents → structured data”

This repository is the **implementation layer** that the broader GAIK vision builds on. Solution templates, wizards and organization‑specific workflows can all be composed from these blocks.

> If the **Solution Wizard** decides *what* workflow you need, this toolkit is *how* that workflow gets implemented in Python.

---

## How this toolkit fits into the GAIK vision

At project level, GAIK aims to support **knowledge processes** in organizations – especially SMEs – by providing:

- **Building blocks** for *capture, access, and generation*  
  (e.g. transcribing calls, parsing documents, extracting structured records)
- **Software components** that combine those blocks into end‑to‑end pipelines  
  (e.g. “incident audio → structured incident JSON”, “invoice PDF → structured invoice”)
- A higher‑level **Solution Wizard** (under development) that:
  - selects a **template** for a use case (generic pattern)
  - maps business‑level requirements to **services**, **components**, and **connectors**
  - exports **deployable workflows** that call these toolkit components

This repository covers the **toolkit layer**:

- It gives you **well‑tested primitives** (`SchemaGenerator`, `DataExtractor`, `VisionParser`, `Transcriber`, …).
- It includes **composed pipelines** in `gaik.software_components` for common patterns:
  - Audio → structured data
  - Documents → structured data
- It is structured so higher‑level orchestration (templates / SolutionWizardSpec) can treat these as **standardized components**.

---

## Architecture overview

GAIK distinguishes three levels:

| Level                  | Concept in GAIK                         | Examples                                                      |
|------------------------|-----------------------------------------|---------------------------------------------------------------|
| **Service**            | Logical capability                      | `speech_to_text`, `document_parsing`, `information_extraction` |
| **Building block**     | Atomic toolkit class / function         | `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser`, `PyMuPDFParser`, `DoclingParser` |
| **Software component** | Composed, workflow‑ready unit           | `AudioToStructuredData`, `DocumentsToStructuredData`, future domain‑specific services |

In code, that maps to:

- `gaik.building_blocks.*` – low‑level, reusable primitives  
- `gaik.software_components.*` – opinionated end‑to‑end pipelines that orchestrate multiple building blocks

The higher‑level GAIK Solution Wizard (not part of this repo) will:

1. Select a template (generic pattern) for a use case
2. Choose required services
3. Map them to building blocks / software components from this toolkit
4. Generate an executable workflow and deployment configuration

---

## Installation

Install only what you need, or the full toolkit:

```bash
# Structured extraction (schema generation + extraction)
pip install "gaik[extractor]"

# Document parsing (vision-based + local parsers)
pip install "gaik[parser]"

# Audio/video transcription (Whisper + GPT enhancement)
pip install "gaik[transcriber]"

# Software components (pipelines)
pip install "gaik[audio-to-structured-data]"
pip install "gaik[documents-to-structured-data]"

# Everything
pip install "gaik[all]"
```

> For video processing and audio compression you’ll need `ffmpeg` installed on your system (optional but recommended).

---

## Core modules

### 1. Extractor – schema‑based structured data

**Goal:** turn natural‑language requirements into a schema, then use that schema to extract **type‑safe structured data** from text.

Key building blocks:

- `SchemaGenerator` – infers a Pydantic model from a requirements prompt (field names, types, nested structures)
- `DataExtractor` – uses that model to extract structured records from one or more documents
- Shared helpers: `get_openai_config`, `create_openai_client` for OpenAI/Azure configuration

Typical pattern:

```python
from gaik.building_blocks.extractor import SchemaGenerator, DataExtractor, get_openai_config

config = get_openai_config(use_azure=True)

generator = SchemaGenerator(config=config)
schema = generator.generate_schema(
    user_requirements="Extract invoice number, total amount in USD, and vendor name."
)

extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=generator.item_requirements.use_case_name,
    documents=["Invoice #12345 from Acme Corp, Total: $1,500"],
    save_json=True,
    json_path="results.json",
)
print(results)
```

### 2. Parsers – documents → text / markdown

**Goal:** convert PDFs and other documents into clean text or markdown, ready for extraction or retrieval.

Building blocks:

- `VisionParser` – LLM/vision‑based PDF → markdown (multi‑page context, table handling, custom prompts)
- `PyMuPDFParser` – fast, local PDF text extraction (no external binaries)
- `DoclingParser` – OCR and multi‑format parsing (for more complex documents)

Example (vision‑based PDF → markdown):

```python
from gaik.building_blocks.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)

parser = VisionParser(
    openai_config=config,
    use_context=True,
)

pages = parser.convert_pdf("invoice.pdf", dpi=150, clean_output=True)
markdown = "

".join(pages)
parser.save_markdown(pages, "invoice.md")
```

### 3. Transcriber – audio / video → transcripts

**Goal:** transcribe audio or video into raw and optionally GPT‑enhanced transcripts, with chunking and compression handled for you.

Building blocks:

- `Transcriber` – wraps Whisper + optional GPT enhancement, including:
  - chunking for long audio
  - optional audio compression (via ffmpeg)
  - context‑aware multi‑chunk transcription
- `TranscriptionResult` – container with save/export helpers

Example:

```python
from gaik.building_blocks.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)
transcriber = Transcriber(
    api_config=config,
    output_dir="transcriber_workspace",
)

result = transcriber.transcribe("meeting_recording.mp3")
print(result.enhanced_transcript or result.raw_transcript)
result.save("output/transcripts/")
```

---

## Software components (end‑to‑end pipelines)

To align with GAIK’s **template / Solution Wizard** vision, the toolkit also supports **reusable software components** built from the building blocks. These represent common generic patterns.

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

- **Incident reporting (voice → structured incident report)**  
  `Transcriber` + `SchemaGenerator` + `DataExtractor`
- **Invoice / PO processing (PDF → structured records)**  
  `VisionParser` / `PyMuPDFParser` + `SchemaGenerator` + `DataExtractor`
- **Contract review (documents → clause database)**  
  Any parser + extractor with nested schemas
- **Customer meetings (call / meeting → CRM fields + summary)**  
  `Transcriber` + extractor, optionally combined with your own task‑specific code or agents

At solution level, a template or SolutionWizardSpec can express these as **services** implemented by GAIK building blocks and software components.

---

## Examples & documentation

Explore the examples included in the repository:

- Building‑block level examples: `examples/building_blocks/`
- Software component examples: `examples/software_components/`
- Demos and experiments: `demo/`

Project documentation (work in progress) is available at:

- https://gaik-docs.2.rahtiapp.fi/

---

## Roadmap (GAIK project context)

Planned / evolving directions:

- Additional **building blocks**:
  - document classifiers
  - domain‑specific extractors
  - additional parsing / enrichment utilities
- More **software components** for common enterprise patterns:
  - incident reporting
  - meeting summarization
  - HR / recruitment workflows
- Tighter integration with **template catalogues** and a **Solution Wizard** that:
  - maps business requirements → templates
  - selects services & components
  - emits deployable workflows using GAIK toolkit components

---

## Contributing

Contributions are welcome — from bug reports and documentation improvements to new building blocks and software components that fit the GAIK architecture.

Please see `CONTRIBUTING.md` for contribution guidelines.

---

## License

This project is licensed under the MIT License – see `LICENSE` for details.
