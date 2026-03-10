"""Example for DoclingApiClientParser (remote parsing service).

This example returns parsed markdown and metadata without saving output files.
To use this service, request API_BASE and PASSWORD from Haaga-Helia.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

# ------------------------------------------------------------------
# Configure these values before running
# ------------------------------------------------------------------
DOCUMENT_PATH = Path(__file__).parent / "sample_report.pdf"
API_BASE = os.getenv("API_BASE", "http://myedge-unique-label.swedencentral.cloudapp.azure.com:8080")
PASSWORD = os.getenv("PASSWORD", "4FGR26D5G1CGE")


def main() -> None:
    if not DOCUMENT_PATH.exists():
        print(f"Document not found: {DOCUMENT_PATH}")
        return

    if not API_BASE or not PASSWORD:
        print("Missing API_BASE or PASSWORD.")
        print("Set both values as environment variables before running this example.")
        return

    parser = DoclingApiClientParser(
        api_base=API_BASE,
        password=PASSWORD,
    )

    result = parser.parse_document(DOCUMENT_PATH)

    print("\n" + "=" * 60)
    print("PARSE RESULT")
    print("=" * 60)
    print(f"Source file: {result['source_file']}")
    print(f"Elapsed: {result['elapsed_seconds']}s")
    print(f"Metadata: {result['metadata']}")

    markdown = result["parsed_markdown"]
    preview = markdown[:2000]
    if preview:
        print("\n--- PARSED MARKDOWN PREVIEW ---\n")
        print(preview)
        if len(markdown) > len(preview):
            print("\n... (truncated preview)")
    else:
        print("\nNo parsed markdown returned.")


    print(f"\nTime taken: {result['elapsed_seconds']}s")

if __name__ == "__main__":
    main()

