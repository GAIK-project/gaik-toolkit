"""Minimal example for running the VisionRagParser on a PDF."""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
from gaik.software_components.config import get_openai_config


def main() -> None:
    print("VISION ENHANCED RAG PARSER:\n")
    sample_pdf = Path(__file__).parent.parent / "parsers" / "sample_report.pdf"

    if not sample_pdf.exists():
        print("No sample PDF found.")
        print(f"Expected: {sample_pdf}")
        print("\nTo test the vision parser:")
        print("  1. Place a PDF file in implementation_layer/implementation_layer/examples/software_modules/parsers/")
        print("  2. Update sample_pdf in this script")
        return

    vision_config = get_openai_config(use_azure=True)
    parser = VisionRagParser(
        vision_config=vision_config,
        verbose=True,
        save_markdown=True,  
        enable_ocr=False,
        enable_table_structure=True,
        enable_formula_enrichment=False
    )

    print("\nConverting to markdown and chunks...")
    markdown_output = sample_pdf.with_name(f"{sample_pdf.stem}_vision.md")
    _markdown, chunks = parser.convert_doc_to_chunks_with_vision(
        str(sample_pdf), output_path=str(markdown_output), return_markdown=True
    )
    print(f"Total chunks: {len(chunks)}")

    for idx, chunk in enumerate(chunks[:2], start=1):
        print("\n" + "-" * 60)
        print(f"Chunk {idx} metadata:")
        print(chunk.metadata)


if __name__ == "__main__":
    main()
