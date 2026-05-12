"""
Single-pass vision extraction: PDF/image → structured data in one LLM call.

Combines the document analysis quality of MultimodalParser with the structured
output of DataExtractor — no intermediate markdown step.

Main class:
    VisionExtractor: Extract structured data from PDFs/images via vision LLM.

Result type:
    VisionExtractionResult: data dict + optional verification metadata + usage stats.

Verification:
    VerifiableField: Per-field wrapper with confidence_score and reasoning (opt-in).
"""

from .vision_extractor import (
    VerifiableField,
    VisionExtractionResult,
    VisionExtractor,
)

__all__ = [
    "VisionExtractor",
    "VisionExtractionResult",
    "VerifiableField",
]

__version__ = "0.1.0"
