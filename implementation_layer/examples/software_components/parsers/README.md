# Document Parser Examples

This folder demonstrates how to use different document parsing strategies to convert PDFs and Word documents into clean, structured markdown.

## Files

- `demo_pymupdf.py` - Local parsing example using PyMuPDF for fast, cost-efficient document processing
- `demo_vision_simple.py` - Vision-based parsing example using GPT for complex layouts and tables
- `sample_report.pdf` - Sample PDF document for testing local parsing
- `WEF-page-10.pdf` - Sample PDF with complex layout for testing vision-based parsing

## What These Examples Show

- How to use local parsing (PyMuPDF) for straightforward documents
- How to use vision-based parsing for complex layouts, tables, and multi-column documents
- How to choose the right parsing strategy based on document complexity
- How to preserve document structure (headings, tables, formatting) in markdown output

## Usage

```bash
# Local parsing example
python demo_pymupdf.py

# Vision-based parsing example
python demo_vision_simple.py
```

## Related Documentation

- [Document Parser Component](../../../src/gaik/software_components/parsers)
- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components#document-parser)
