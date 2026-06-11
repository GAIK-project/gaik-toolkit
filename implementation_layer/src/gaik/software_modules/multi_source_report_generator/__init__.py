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
from .pipeline import MultiSourceReportGenerator, load_report_config, save_report_config

__all__ = [
    "MultiSourceReportGenerator",
    "ReportGenerationResult",
    "ReportSectionSpec",
    "EvidenceItem",
    "GeneratedSection",
    "save_report_config",
    "load_report_config",
]
