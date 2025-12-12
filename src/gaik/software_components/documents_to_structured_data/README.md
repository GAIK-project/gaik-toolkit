# Documents to Structured Data (Software Component)

Parse documents (PDF/images/DOCX) with a selectable parser, then extract structured data.

- Import: `from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData`
- Example: `examples/software_components/documents_to_structured_data/pipeline_example.py`
- Outputs: parsed text, extracted fields, and the generated schema + requirements.
- Schema reuse: see `generate_schema` / `schema_name` flags in the example; schemas are persisted under `schema/`.

## Basic Usage

```python
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(use_azure=True)
result = pipeline.run(
    file_path="sample.pdf",
    user_requirements="""
    Extract invoice number, sender, receiver, PO number, date, subtotal, discount, tax
    """,
    parser_choice="vision_parser",   # vision_parser | docling | pymupdf | docx
    parser_ctor={},
    parse_options={},
    extractor_ctor={},               # e.g., {"model": "gpt-4.1"}
    extract_options={"save_json": False},
)

print(result.parsed_documents[0])
print(result.extracted_fields)
```

## Parameters

### Constructor
- `api_config`: Optional OpenAI/Azure config dict. If omitted, `get_openai_config(use_azure)` is used.
- `use_azure`: Boolean, passed to `get_openai_config` when `api_config` is not supplied.

### `run(...)`
- `file_path`: Path to the document to parse (PDF/image/DOCX).
- `user_requirements`: Natural-language description of fields to extract.
- `parser_choice`: `vision_parser`, `docling`, `pymupdf`, or `docx`.
- `parser_ctor`: Dict passed to the chosen parser constructor (e.g., `clean_output` for VisionParser).
- `parse_options`: Dict passed to the parser call (if applicable).
- `extractor_ctor`: Dict passed to `DataExtractor(...)` (e.g., `model` override, applied to schema gen and extraction).
- `extract_options`: Dict passed to `DataExtractor.extract(...)` (e.g., `save_json`, `json_path`). The example also uses:
  - `generate_schema` (bool): If `True`, generate a new schema; if `False`, try to load from disk via `load_schema`.
  - `schema_name` (str): Base filename (no `.py`) for saving/loading schema; defaults to `schema`.
- `schema`: Optional pre-generated schema model to reuse.
- `requirements`: Optional `ExtractionRequirements` matching the schema.

### Returns (`PipelineResult`)
- `parsed_documents`: List of parsed text strings.
- `extracted_fields`: List of dicts returned by the extractor.
- `schema`: Generated or provided schema model.
- `requirements`: Corresponding `ExtractionRequirements`.

## Schema Persistence (example pattern)
- To reuse a schema, set `generate_schema=False` and `schema_name` to the desired base name; ensure the schema and `<name>_requirements.json` exist under `schema/`.
- To generate and save a schema, set `generate_schema=True`; the example uses `pipeline.save_schema(...)` to write both artifacts to `schema/`.
