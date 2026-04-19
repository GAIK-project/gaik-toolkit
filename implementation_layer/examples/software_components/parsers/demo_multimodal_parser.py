"""Multimodal Parser Example

Demonstrates how to parse PDFs using the multimodal_parser component
with different model providers.
"""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers.multimodal_parser import MultimodalParser  

OUTPUT_DIR = Path(__file__).parent / "output"


def save_result(result, prefix: str) -> None:
    """Save parse results to the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = OUTPUT_DIR / f"{prefix}_raw.md"
    raw_path.write_text(result.raw_markdown, encoding="utf-8")

    clean_path = OUTPUT_DIR / f"{prefix}_clean.md"
    clean_path.write_text(result.clean_markdown, encoding="utf-8")

    print(f"Saved: {raw_path}")
    print(f"Saved: {clean_path}")

    if result.html is not None:
        html_path = OUTPUT_DIR / f"{prefix}_clean.html"
        html_path.write_text(result.html, encoding="utf-8")
        print(f"Saved: {html_path}")


def openai_example(pdf_path: str):
    """Parse a PDF using OpenAI / Azure OpenAI."""
    print("=" * 60)
    print("OpenAI / Azure OpenAI Parser")
    print("=" * 60)

    parser = MultimodalParser(
        model_provider="openai",
        model="gpt-5.4",
        use_azure=True,
        reasoning_effort="low",
        merge_table=True,
        create_html=True,
    )

    print("parsing....\n")
    start = time.time()
    result = parser.parse(pdf_path)
    print(f"Parsing time: {time.time() - start:.1f}s\n")
    save_result(result, "output_openai")


def claude_example(pdf_path: str):
    """Parse a PDF using Claude via Anthropic Foundry."""
    print("\n" + "=" * 60)
    print("Claude / Anthropic Foundry Parser")
    print("=" * 60)

    parser = MultimodalParser(
        model_provider="claude",
        model="claude-sonnet-4-6",
        use_azure=True,
        reasoning_effort="medium",
        merge_table=True,
        create_html=True,
    )

    print("parsing....\n")
    start = time.time()
    result = parser.parse(pdf_path)
    print(f"Parsing time: {time.time() - start:.1f}s\n")
    save_result(result, "output_claude")


def google_example(pdf_path: str):
    """Parse a PDF using Google Gemini via Vertex AI."""
    print("\n" + "=" * 60)
    print("Google Gemini / Vertex AI Parser")
    print("=" * 60)

    parser = MultimodalParser(
        model_provider="google",
        model="gemini-3-flash-preview",
        vertex_ai=True,
        reasoning_effort="medium",
        merge_table=True,
        create_html=True,
    )

    print("parsing....\n")
    start = time.time()
    result = parser.parse(pdf_path)
    print(f"Parsing time: {time.time() - start:.1f}s\n")
    save_result(result, "output_google")


if __name__ == "__main__":
    # Put a PDF in the same directory or provide a path
    sample_pdf = str(Path(__file__).parent / "sample.pdf")

    # Run one provider at a time (comment out the others)
    openai_example(sample_pdf)
    # claude_example(sample_pdf)
    # google_example(sample_pdf)
