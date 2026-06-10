"""
Multi-source report generator: turn mixed source files (PDF, Word, Excel/CSV,
text, Markdown, audio/video, images) into a user-defined Markdown report.
"""

from .models import (
    EvidenceItem,
    GeneratedSection,
    ReportGenerationResult,
    ReportSectionSpec,
)
from .pipeline import MultiSourceReportGenerator

__all__ = [
    "MultiSourceReportGenerator",
    "ReportGenerationResult",
    "ReportSectionSpec",
    "EvidenceItem",
    "GeneratedSection",
]
