# Documents-to-Structured-Data Module Examples

This folder demonstrates how to use the Documents-to-Structured-Data module, which combines the Document Parser and Extractor components into a single end-to-end pipeline.

## Files

- `pipeline_example.py` - Complete example showing the full document-to-structured-data workflow
- `input/` - Sample PDF and Word documents for testing the pipeline

## What These Examples Show

- How to process PDF and Word documents and extract structured data in one pipeline
- How to choose between vision-based and local parsing strategies
- How to define extraction fields in plain language
- How to get both parsed markdown and structured output from a single function call
- How to use schema reuse for efficient batch document processing

## Usage

```bash
python pipeline_example.py
```

## Module Outputs

The pipeline returns:
- **Parsed Markdown** - Document content converted to clean, structured markdown
- **Structured Fields** - All defined fields extracted and validated
- **Reusable Schema** - Pydantic schema saved for future runs

## Parsing Strategies

- **Vision-based** - Use for complex layouts, multi-column documents, and documents with tables
- **Local (PyMuPDF/Docling)** - Use for simpler documents where speed and cost-efficiency are priorities

## Related Documentation

- [Documents-to-Structured-Data Module](../../../src/gaik/software_modules/documents_to_structured_data)
- [Software Modules Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-modules#document-to-structured-data)
- [Document Parser Component](../../../src/gaik/software_components/parsers)
- [Extractor Component](../../../src/gaik/software_components/extractor)
