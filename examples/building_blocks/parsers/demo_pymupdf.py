"""Simple demonstration of PyMuPDF parser for fast local PDF text extraction.

This example shows how to use PyMuPDF for PDF parsing without external APIs.
Requires: pip install gaik[parser]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.parsers.pymypdf import PyMuPDFParser


def main() -> None:
    """Extract text from a sample PDF using PyMuPDF."""

    # Check if test PDF exists
    pdf_path = Path(__file__).parent / "WEF-page-10.pdf"

    if not pdf_path.exists():
        print("No sample PDF found.")
        print(f"Expected: {pdf_path}")
        print("\nTo test PyMuPDF parser:")
        print("  1. Place a PDF file in the examples/parsers/ directory")
        print("  2. Update pdf_path variable above")
        return

    # Initialize parser (no API keys needed - runs locally)
    print("Initializing PyMuPDF parser...")
    parser = PyMuPDFParser()

    # Parse PDF
    print(f"Parsing PDF: {pdf_path.name}")
    result = parser.parse_document(str(pdf_path), use_markdown=True)

    # Display result
    print("\n" + "=" * 60)
    print("EXTRACTED TEXT")
    print("=" * 60)
    # Handle Unicode characters that may not be supported by Windows terminal
    try:
        print(result["text_content"])
    except UnicodeEncodeError:
        # Fall back to ASCII with replacement for unsupported characters
        print(result["text_content"].encode("ascii", errors="replace").decode("ascii"))

    # Show metadata
    print("\n" + "=" * 60)
    print("METADATA")
    print("=" * 60)
    print(f"File: {result['file_name']}")
    print(f"Content length: {result['content_length']} chars")
    print(f"Word count: {result['word_count']}")
    print(f"Parsing method: {result['parsing_method']}")

    # Save to file
    output_path = pdf_path.with_suffix(".txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result["text_content"])
    print(f"\nText saved to: {output_path}")


if __name__ == "__main__":
    main()


