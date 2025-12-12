# Documents → Structured Data (parser + extractor)

Parses documents (PDF/images/DOCX) with a selectable parser, then extracts structured data. Returns parsed text, extracted fields, and the generated schema + requirements. Supports schema reuse/persistence (see `generate_schema` / `schema_name` flags in the example).

- Import: `from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData`
- Example: `examples/software_components/documents_to_structured_data/pipeline_example.py`
- Parser choices: `vision_parser`, `docling`, `pymupdf`, `docx` (ensure corresponding optional deps are installed).

## Basic Usage

```python
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(use_azure=True)
result = pipeline.run(
    file_path="sample.pdf",
    user_requirements="Extract invoice number, sender, receiver, PO number, date, subtotal, discount, tax",
    parser_choice="vision_parser",   # or docling / pymupdf / docx
    parser_ctor={},
    parse_options={},
    extractor_ctor={},               # e.g., {"model": "gpt-4.1"}
    extract_options={"save_json": False},
)

print(result.parsed_documents[0])
print(result.extracted_fields)
```

## Parameters (run)
- `file_path`: Path to document (PDF/image/DOCX).
- `user_requirements`: Natural-language fields to extract.
- `parser_choice`: `vision_parser`, `docling`, `pymupdf`, or `docx`.
- `parser_ctor`: Args to the chosen parser constructor (e.g., `clean_output` for VisionParser).
- `parse_options`: Args passed to the parser call (if applicable).
- `extractor_ctor`: Args to `DataExtractor(...)` (e.g., `model` override, applied to schema generation and extraction).
- `extract_options`: Args to `DataExtractor.extract(...)` (e.g., `save_json`, `json_path`). Example adds `generate_schema` (bool) and `schema_name` (base filename) for schema reuse/persistence.
- `schema`, `requirements`: Optional pre-generated schema/requirements to reuse.

## Returns (`PipelineResult`)
- `parsed_documents`: List of parsed text strings.
- `extracted_fields`: List of dicts.
- `schema`: Generated or provided schema model.
- `requirements`: Matching `ExtractionRequirements`.
