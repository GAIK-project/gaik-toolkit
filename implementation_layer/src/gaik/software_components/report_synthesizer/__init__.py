"""Report Synthesizer

Stage 3 of CURACT report writing: writes a report section by section from curated
knowledge. Technical sections are written in parallel, each from its own knowledge only;
derived sections such as recommendations and a summary are written after their
prerequisites, from the reviewed texts of those sections only. A DraftReviewer checks
every draft against the same material and the review log records its edits.

Main Classes:
    - ReportSynthesizer: write a Report from a KnowledgeBase and the section specs
    - Report: the written sections and the review log, with save/load and DOCX export
    - ReportSection: one written section
    - ReviewEntry: the applied and unresolved reviewer edits of one section

Configuration:
    - get_llm_config: Get the LLM provider configuration

Example:
    >>> from gaik.software_components.report_synthesizer import (
    ...     ReportSynthesizer, get_llm_config,
    ... )
    >>> synthesizer = ReportSynthesizer(get_llm_config())
    >>> report = synthesizer.synthesize(knowledge, sections, title="Condition assessment")
    >>> report.save("workspace/report")
"""

from gaik.software_components.llm import get_llm_config

from .models import Report, ReportSection, ReviewEntry
from .report_synthesizer import ReportSynthesizer

__all__ = [
    "ReportSynthesizer",
    "Report",
    "ReportSection",
    "ReviewEntry",
    "get_llm_config",
]

__version__ = "0.1.0"
