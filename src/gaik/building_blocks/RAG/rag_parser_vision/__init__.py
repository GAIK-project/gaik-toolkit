"""Vision-enhanced RAG parser combining Docling structure analysis with AI vision models."""

from .parser import (
    VisionRagParser,
    parse_doc_to_chunks_with_vision,
)

__all__ = [
    "VisionRagParser",
    "parse_doc_to_chunks_with_vision",
]

__version__ = "0.1.0"
