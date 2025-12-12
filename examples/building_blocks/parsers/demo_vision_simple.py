"""Simple demonstration of VisionParser for PDF to Markdown conversion.

This example shows how to use the vision parser with minimal setup.
Requires: pip install gaik[parser]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.parsers import VisionParser, get_openai_config


def main() -> None:
    """Convert a sample PDF to Markdown using VisionParser."""

    # Check if test PDF exists
    pdf_path = Path(__file__).parent / "WEF-page-10.pdf"

    if not pdf_path.exists():
        print("[WARNING] No sample PDF found.")
        print(f"   Expected: {pdf_path}")
        print("\n[TIP] To test VisionParser:")
        print("   1. Place a PDF file in the examples/ directory")
        print("   2. Update pdf_path variable above")
        print("   3. Set your OpenAI API key:")
        print("      export OPENAI_API_KEY='sk-...'")
        print("   4. Or use Azure OpenAI:")
        print("      export AZURE_API_KEY='...'")
        print("      export AZURE_ENDPOINT='https://...'")
        print("      export AZURE_DEPLOYMENT='gpt-4o'")
        print("\n[INFO] For CLI usage, see: demo_vision_parser.py")
        return

    # Initialize parser (defaults to Azure OpenAI, or set use_azure=False for OpenAI)
    print("[SETUP] Initializing VisionParser...")
    config = get_openai_config(use_azure=True)  # or use_azure=False for OpenAI
    parser = VisionParser(openai_config=config)

    # Convert PDF to Markdown
    print(f"[DOC] Converting PDF: {pdf_path.name}")
    markdown_pages = parser.convert_pdf(
        str(pdf_path),
        dpi=200,  # Image quality for PDF rendering
        clean_output=True,  # Merge and clean multi-page output
    )

    # Display result
    print("\n" + "=" * 60)
    print("MARKDOWN OUTPUT")
    print("=" * 60)
    for i, page in enumerate(markdown_pages, 1):
        print(f"\n--- Page {i} ---")
        print(page)

    # Save to file
    output_path = pdf_path.with_suffix(".md")
    parser.save_markdown(markdown_pages, str(output_path))
    print(f"\n[OK] Markdown saved to: {output_path}")


if __name__ == "__main__":
    main()


