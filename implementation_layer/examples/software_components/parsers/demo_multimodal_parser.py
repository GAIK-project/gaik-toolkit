"""Multimodal Parser Example

Demonstrates how to parse PDFs using the multimodal_parser component
with different model providers and how to read the per-call token
usage + USD cost from ``result.usage``.
"""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers.multimodal_parser import MultimodalParser
from gaik.software_components.parsers.multimodal_parser.usage import UsageRecord

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


def print_usage(result, label: str) -> None:
    """Pretty-print the UsageRecord attached to a ParseResult."""
    usage: UsageRecord | None = result.usage
    if usage is None:
        print(f"Usage ({label}): not available")
        return

    cost_str = (
        f"${usage.cost_usd:.4f}"
        if usage.cost_usd > 0
        else f"pricing unknown for {usage.model}"
    )
    thinking = f"  (thinking: {usage.thinking_tokens:,})" if usage.thinking_tokens else ""

    print(f"\nUsage ({label}):")
    print(f"  provider        : {usage.provider}")
    print(f"  model           : {usage.model}")
    print(f"  input tokens    : {usage.input_tokens:,}")
    print(f"  output tokens   : {usage.output_tokens:,}{thinking}")
    print(f"  total tokens    : {usage.total_tokens:,}")
    print(f"  llm duration    : {usage.duration_s}s")
    print(f"  cost            : {cost_str}")


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
    print(f"Parsing time: {time.time() - start:.1f}s")
    save_result(result, "output_openai")
    print_usage(result, "openai")
    return result


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
    print(f"Parsing time: {time.time() - start:.1f}s")
    save_result(result, "output_claude")
    print_usage(result, "claude")
    return result


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
    print(f"Parsing time: {time.time() - start:.1f}s")
    save_result(result, "output_google")
    print_usage(result, "google")
    return result


def print_total(results: list) -> None:
    """Sum cost + tokens across multiple ParseResults and print a TOTAL row."""
    usages = [r.usage for r in results if r is not None and r.usage is not None]
    if len(usages) < 2:
        return
    total_in = sum(u.input_tokens for u in usages)
    total_out = sum(u.output_tokens for u in usages)
    total_cost = sum(u.cost_usd for u in usages)
    print("\n" + "=" * 60)
    print("TOTAL across providers")
    print("=" * 60)
    print(f"  calls           : {len(usages)}")
    print(f"  input tokens    : {total_in:,}")
    print(f"  output tokens   : {total_out:,}")
    print(f"  cost            : ${total_cost:.4f}")


if __name__ == "__main__":
    # Put a PDF in the same directory or provide a path
    sample_pdf = str(Path(__file__).parent / "sample.pdf")

    # Run one provider at a time (comment out the others)
    results = [
        openai_example(sample_pdf),
        # claude_example(sample_pdf),
        # google_example(sample_pdf),
    ]

    print_total(results)
