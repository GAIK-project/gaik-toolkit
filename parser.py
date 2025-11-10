"""CLI helper for the vision parser demo."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

from gaik.parsers import VisionParser, get_openai_config

DEFAULT_PROMPT = (
    "Convert this document page to accurate markdown format. Follow these rules STRICTLY:\n\n"
    "**CRITICAL RULES:**\n"
    "1. **NO HALLUCINATION**: Only output content that is actually visible on the page\n"
    "2. **NO EMPTY ROWS**: Do NOT create empty table rows. If you see a table, only include rows with "
    "actual data\n"
    "3. **STOP when content ends**: When you reach the end of visible content, STOP. Do not continue "
    "with empty rows\n\n"
    "**Formatting Requirements:**\n"
    "- Tables: Use markdown table syntax with | separators\n"
    "- Multi-row cells: Keep item descriptions/notes in the same row as the item data\n"
    "- Table continuations: If a table continues from a previous page, continue it without repeating "
    "headers\n"
    "- Preserve ALL visible text: headers, data, footers, page numbers, everything\n"
    "- Keep numbers, dates, and text exactly as shown\n"
    "- Maintain document structure and layout\n\n"
    "**What to include:**\n"
    "- All table data\n"
    "- All text paragraphs\n"
    "- Company information, addresses\n"
    "- Terms and conditions\n"
    "- Page numbers, dates\n"
    "- Total amounts and summaries\n\n"
    "Return ONLY the markdown content, no explanations."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert PDFs to markdown using OpenAI vision models.",
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the PDF file to convert.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to save the markdown output. Defaults to <pdf_name>.md next to the PDF.",
    )
    parser.add_argument(
        "--poppler-path",
        type=Path,
        help="Optional path to the Poppler bin directory (required on Windows).",
    )
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Use the standard OpenAI API instead of Azure OpenAI.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip LLM cleanup for multi-page documents (returns per-page markdown).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        help="Optional path to a text file containing a custom prompt override.",
    )
    return parser


def read_prompt(prompt_path: Path | None) -> str:
    if prompt_path is None:
        return DEFAULT_PROMPT
    return prompt_path.read_text(encoding="utf-8")


def save_markdown(markdown_pages: Iterable[str], output_path: Path) -> None:
    payload = "\n\n---\n\n".join(markdown_pages)
    output_path.write_text(payload, encoding="utf-8")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    if not args.pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {args.pdf_path}")

    config = get_openai_config(use_azure=not args.openai)
    custom_prompt = read_prompt(args.prompt)

    vision_parser = VisionParser(
        config,
        custom_prompt=custom_prompt,
        poppler_path=str(args.poppler_path) if args.poppler_path else None,
    )

    markdown_pages = vision_parser.convert_pdf(
        str(args.pdf_path),
        clean_output=not args.no_clean,
    )

    save_path = args.output if args.output else args.pdf_path.with_suffix(".md")
    save_markdown(markdown_pages, save_path)
    logging.info("Markdown saved to %s", save_path)


if __name__ == "__main__":
    main()
