"""Simple demonstration of DoclingParser for advanced PDF parsing.

This example shows how to use DoclingParser for OCR-aware parsing,
table extraction, and markdown output.
Requires: pip install gaik[parser]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers import DoclingParser


def main() -> None:
    """Parse a sample PDF using DoclingParser."""

    pdf_path = Path(__file__).parent / "receipt.pdf"

    if not pdf_path.exists():
        print("No sample PDF found.")
        print(f"Expected: {pdf_path}")
        print("\nTo test Docling parser:")
        print("  1. Place a PDF file in the examples/parsers/ directory")
        print("  2. Update pdf_path variable above")
        return

    print("Initializing Docling parser...")
    parser = DoclingParser(
        enable_ocr=False,
        enable_table_structure=True,
        enable_formula_enrichment=False,
        ocr_engine="rapidocr",
    )

    print(f"Parsing document: {pdf_path.name}")
    result = parser.parse_document(str(pdf_path), use_markdown=True)

    print("\n" + "=" * 60)
    print("MARKDOWN OUTPUT")
    print("=" * 60)
    print(result["text_content"])

    print("\n" + "=" * 60)
    print("METADATA")
    print("=" * 60)
    print(f"File: {result['file_name']}")
    print(f"Extension: {result['file_extension']}")
    print(f"Content length: {result['content_length']} chars")
    print(f"Word count: {result['word_count']}")
    print(f"Parsing method: {result['parsing_method']}")
    print(f"Format used: {result['format_used']}")

    # output_path = pdf_path.with_suffix(".docling.md")
    # output_path.write_text(result["text_content"], encoding="utf-8")
    # print(f"\nMarkdown saved to: {output_path}")


if __name__ == "__main__":
    main()
