"""Minimal example for running the DoclingRagParser on a PDF."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser


def main() -> None:

    sample_pdf = Path(__file__).parent.parent / "parsers" / "WEF-page-10.pdf"

    if not sample_pdf.exists():
        print("No sample PDF found.")
        print(f"Expected: {sample_pdf}")
        print("\nTo test the parser:")
        print("  1. Place a PDF file in implementation_layer/implementation_layer/examples/software_modules/parsers/")
        print("  2. Update sample_pdf in this script")
        return

    parser = DoclingRagParser(
        verbose=True,
        enable_ocr=False,
        ocr_engine="tesseract_cli",
        enable_formula_enrichment=False,
    )

    print("\nConverting to markdown...")
    markdown_output = sample_pdf.with_suffix(".md")
    parser.convert_pdf_to_markdown(str(sample_pdf), output_path=str(markdown_output))
    print(f"Markdown saved to: {markdown_output}")

    print("\nCreating RAG chunks...")
    # Chunks by document structure (headings, sections) using HierarchicalChunker
    chunks = parser.convert_pdf_to_chunks_with_metadata(str(sample_pdf))
    print(f"Total chunks: {len(chunks)}")

    for idx, chunk in enumerate(chunks[:2], start=1):
        print("\n" + "-" * 60)
        print(f"Chunk {idx} metadata:")
        print(chunk.metadata)


if __name__ == "__main__":
    main()
