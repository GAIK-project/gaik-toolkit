"""
Single-pass vision extraction: PDF/image → structured data in one LLM call.

Combines the document analysis quality of MultimodalParser with the structured
output of DataExtractor — no intermediate markdown step.

Main class:
    VisionExtractor: Extract structured data from PDFs/images via vision LLM.

Result types:
    VisionExtractionResult: data dict + optional verification metadata + usage stats.
    RequirementsSuggestionResult: suggested extraction requirements + usage stats.

Verification:
    VerifiableField: Per-field wrapper with confidence_score and reasoning (opt-in).

Requirements suggestion:
    VisionExtractor.suggest_requirements: describe which fields to extract from a
    sample document (feeds SchemaGenerator / extract).
"""

from .vision_extractor import (
    RequirementsSuggestionResult,
    VerifiableField,
    VisionExtractionResult,
    VisionExtractor,
)

__all__ = [
    "VisionExtractor",
    "VisionExtractionResult",
    "RequirementsSuggestionResult",
    "VerifiableField",
]

__version__ = "0.1.0"
