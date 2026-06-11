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
    """A user-defined report section.

    ``id`` is a stable identifier used to reference the section in ``depends_on``
    (and for output filenames). When omitted it is derived from ``title``.
    ``depends_on`` lists the ids of sections that must be written *before* this
    one; in the agentic workflow their finalized content is passed in as context.
    """

    title: str
    instructions: str
    required: bool = True
    id: str | None = None
    depends_on: list[str] = field(default_factory=list)


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
    docx_path: Path | None = None
