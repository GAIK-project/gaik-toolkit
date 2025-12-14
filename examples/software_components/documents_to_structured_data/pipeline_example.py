"""
Example: parse documents (PDF/images/DOCX) and extract structured fields by dynamically building extraction models from user requiements
Workflow: input documents->parse documents (vision_parser, docling, pymupdf, docx)-> parse user requirement and build schema->extract key data
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData  # noqa: E402


USER_REQUIREMENTS = """
Extract invoice number, sender name, receiver name, purchase order number, date of invoice, subtotal, discount, tax, and grand total from the invoice.
"""


def main() -> None:
    schema_dir = Path(__file__).parent / "schema"
    extract_options = {
        "save_json": True,
        "json_path": "extraction_results.json",
        "generate_schema": True,  # Set False to reuse an existing saved schema
        "schema_name": "schema",  # Without .py; defaults to 'schema'
    }

    generate_schema = extract_options.pop("generate_schema", True)
    schema_name = extract_options.pop("schema_name", "schema")

    pipeline = DocumentsToStructuredData(use_azure=True)

    existing = None if generate_schema else pipeline.load_schema(schema_dir, schema_name)
    schema = requirements = None
    if existing:
        schema, requirements = existing

    result = pipeline.run(
        file_path=Path(r"input/scanned_invoice.jpeg"),
        user_requirements=USER_REQUIREMENTS,
        parser_choice="vision_parser",  # vision_parser | docling | pymupdf | docx
        parser_ctor={
            # Example: {"clean_output": True} for VisionParser
        },
        parse_options={},
        extractor_ctor={
            # Optional: override model; applies to schema generation and extraction.
            # "model": "gpt-5.2"
        },
        extract_options=extract_options,
        schema=schema,
        requirements=requirements,
    )

    if result.schema and result.requirements and generate_schema:
        pipeline.save_schema(result.schema, result.requirements, schema_dir, schema_name)

    print("Parsed documents:", len(result.parsed_documents))
    print("\nExtracted fields:\n")
    print(json.dumps(result.extracted_fields, indent=2, default=str))


if __name__ == "__main__":
    main()
