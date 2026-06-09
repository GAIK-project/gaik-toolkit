"""
Multi-source report generator: turn mixed source files (PDF, Word, Excel/CSV,
text, Markdown, audio/video, images) into a user-defined Markdown report.
"""

from .pipeline import (
    EvidenceItem,
    GeneratedSection,
    MultiSourceReportGenerator,
    ReportGenerationResult,
    ReportSectionSpec,
)

__all__ = [
    "MultiSourceReportGenerator",
    "ReportGenerationResult",
    "ReportSectionSpec",
    "EvidenceItem",
    "GeneratedSection",
]
