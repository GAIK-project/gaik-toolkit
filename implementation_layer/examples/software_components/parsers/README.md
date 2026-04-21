# Document Parser Examples

This folder demonstrates how to use different document parsing strategies to convert PDFs and Word documents into clean, structured markdown.

## Files

- `demo_pymupdf.py` - Local parsing example using PyMuPDF for fast, cost-efficient document processing
- `demo_docling.py` - Advanced parsing example using Docling with OCR/table extraction support
- `demo_visionPlus.py` - VisionPlus parsing example (Docling + Vision, returns markdown + metadata, no chunking)
- `demo_docling_api_client.py` - Remote parsing example using Haaga-Helia Docling API client parser
- `demo_vision_simple.py` - Vision-based parsing example using GPT for complex layouts and tables
- `demo_multimodal_parser.py` - Multi-provider (OpenAI / Claude / Gemini) PDF parser with token usage + USD cost printed per call
- `sample_report.pdf` - Sample PDF document for testing local/remote parsing
- `WEF-page-10.pdf` - Sample PDF with complex layout for testing vision-based parsing

## What These Examples Show

- How to use local parsing (PyMuPDF) for straightforward documents
- How to use Docling parsing for OCR/table-aware extraction
- How to use VisionPlus parsing without chunking (markdown + metadata only)
- How to use remote parsing through the Haaga-Helia Docling service client
- How to use vision-based parsing for complex layouts, tables, and multi-column documents
- How to choose the right parsing strategy based on document complexity
- How to preserve document structure (headings, tables, formatting) in markdown output

## Usage

```bash
# Local parsing example
python demo_pymupdf.py

# Docling parsing example
python demo_docling.py

# VisionPlus parsing example
python demo_visionPlus.py

# Remote Docling API client example
python demo_docling_api_client.py

# Vision-based parsing example
python demo_vision_simple.py

# Multi-provider vision parsing with per-call cost reporting
python demo_multimodal_parser.py
```

## Related Documentation

- [Document Parser Component](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/parsers)
- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components#document-parser)
