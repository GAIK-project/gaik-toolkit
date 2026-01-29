"""Docling-based RAG parser."""

from .parser import (
    DoclingRagParser,
    parse_pdf_to_chunks_with_metadata,
    parse_pdf_to_markdown,
)

__all__ = [
    "DoclingRagParser",
    "parse_pdf_to_markdown",
    "parse_pdf_to_chunks_with_metadata",
]

__version__ = "0.2.0"
