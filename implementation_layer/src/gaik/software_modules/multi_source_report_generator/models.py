"""Public data models for the multi-source report generator.

These dataclasses live in their own module so both the single-call path
(``pipeline.py``) and the agentic path (``agentic/``) can import them without
``agentic`` having to import ``pipeline`` internals. ``__init__.py`` re-exports
them, so the public import surface is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReportSectionSpec:
    """A user-defined report section."""

    title: str
    instructions: str
    required: bool = True


@dataclass
class EvidenceItem:
    """One normalized source, ready to feed the report writer."""

    source_path: str
    source_type: str
    content_markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedSection:
    title: str
    content_markdown: str
    usage: dict[str, Any] | None = None
    # Non-fatal warnings raised while generating the section (e.g. reviewer
    # edits that could not be applied, or "no matching sample section").
    revision_warnings: list[str] = field(default_factory=list)


@dataclass
class ReportGenerationResult:
    title: str
    evidence_items: list[EvidenceItem]
    sections: list[GeneratedSection]
    markdown: str
    markdown_path: Path | None
    usage: dict[str, Any]
