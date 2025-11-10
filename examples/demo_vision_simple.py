"""Simple demonstration of VisionParser for PDF to Markdown conversion.

This example shows how to use the vision parser with minimal setup.
Requires: pip install gaik[vision]
"""

from __future__ import annotations

from pathlib import Path

from gaik.parsers import VisionParser, get_openai_config


def main() -> None:
    """Convert a sample PDF to Markdown using VisionParser."""

    # Check if test PDF exists
    pdf_path = Path(__file__).parent / "sample_invoice.pdf"

    if not pdf_path.exists():
        print("⚠️  No sample PDF found.")
        print(f"   Expected: {pdf_path}")
        print("\n💡 To test VisionParser:")
        print("   1. Place a PDF file in the examples/ directory")
        print("   2. Update pdf_path variable above")
        print("   3. Set your OpenAI API key:")
        print("      export OPENAI_API_KEY='sk-...'")
        print("   4. Or use Azure OpenAI:")
        print("      export AZURE_API_KEY='...'")
        print("      export AZURE_ENDPOINT='https://...'")
        print("      export AZURE_DEPLOYMENT='gpt-4o'")
        print("\n📖 For CLI usage, see: demo_vision_parser.py")
        return

    # Initialize parser (defaults to Azure OpenAI, or set use_azure=False for OpenAI)
    print("🔧 Initializing VisionParser...")
    config = get_openai_config(use_azure=True)  # or use_azure=False for OpenAI
    parser = VisionParser(config)

    # Convert PDF to Markdown
    print(f"📄 Converting PDF: {pdf_path.name}")
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
    print(f"\n✅ Markdown saved to: {output_path}")


if __name__ == "__main__":
    main()
