"""Simple demonstration of VisionPlusParser (Docling + Vision, no chunking)."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers import VisionPlusParser, get_openai_config


def main() -> None:
    pdf_path = Path(__file__).parent / "WEF-page-10.pdf"

    if not pdf_path.exists():
        print("No sample PDF found.")
        print(f"Expected: {pdf_path}")
        print("Place a PDF file in examples/software_components/parsers and retry.")
        return

    config = get_openai_config(use_azure=False)
    parser = VisionPlusParser(
        vision_config=config,
        enable_ocr=False,
        enable_table_structure=True,
        enable_formula_enrichment=False,
        ocr_engine="rapidocr",
        verbose=True,
    )

    result = parser.parse_document(str(pdf_path))

    print("\n" + "=" * 60)
    print("METADATA")
    print("=" * 60)
    print(result["metadata"])

    markdown = result["parsed_markdown"]
    preview = markdown[:2000]
    print("\n" + "=" * 60)
    print("MARKDOWN PREVIEW")
    print("=" * 60)
    if preview:
        print(preview)
        if len(markdown) > len(preview):
            print("\n... (truncated preview)")
    else:
        print("No markdown returned.")


if __name__ == "__main__":
    main()
