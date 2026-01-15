---
name: gaik-toolkit
version: "1.0.0"
description: |
  GAIK (Generative AI Knowledge Management Toolkit) development guidance.
  Use when working with: structured data extraction from documents/PDFs/audio,
  schema generation, document parsing (VisionParser, PyMuPDFParser, DoclingParser),
  audio transcription with Whisper, document classification, or end-to-end pipelines
  (AudioToStructuredData, DocumentsToStructuredData).
---

# GAIK Toolkit

Python toolkit for knowledge extraction, capture, and generation. Use when working with:
- Structured data extraction from documents, PDFs, images, or audio
- Schema generation from natural language requirements
- Document parsing (PDF, DOCX, images)
- Audio/video transcription with Whisper + GPT enhancement
- Document classification
- End-to-end pipelines: AudioToStructuredData, DocumentsToStructuredData

## Quick Links

- **Documentation**: https://gaik-project.github.io/gaik-toolkit/
- **GitHub**: https://github.com/GAIK-project/gaik-toolkit
- **Source Code**: https://github.com/GAIK-project/gaik-toolkit/tree/main/src/gaik
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
| **Service** | Logical capability | `speech_to_text`, `document_parsing`, `information_extraction` |
| **Building block** | Atomic toolkit class/function | `Transcriber`, `SchemaGenerator`, `DataExtractor`, `VisionParser` |
| **Software component** | Composed, workflow-ready unit | `AudioToStructuredData`, `DocumentsToStructuredData` |

## Maintenance Notes

This skill is designed for gaik-toolkit v0.2.x. Update when:
- New building blocks or software components are added
- Import paths change in `src/gaik/`
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
