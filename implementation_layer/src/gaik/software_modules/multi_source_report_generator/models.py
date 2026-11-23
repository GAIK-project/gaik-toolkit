"""Public data models for the multi-source report generator.

These dataclasses live in their own module so both the single-call path
(``pipeline.py``) and the agentic path (``agentic/``) can import them without
``agentic`` having to import ``pipeline`` internals. ``__init__.py`` re-exports
them, so the public import surface is unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _slug(text: str, *, max_len: int = 40) -> str:
    """A section title as a lowercase file-name stem, shared by both paths."""
    keep = [c.lower() if c.isalnum() else "_" for c in text.strip()]
    s = "".join(keep)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:max_len] or "section"


def _normalize_heading(text: str) -> str:
    """Normalize a heading for tolerant matching.

    Lowercase; strip leading markdown markers and section numbering; drop
    punctuation; collapse whitespace.
    """
    t = text.strip()
    t = re.sub(r"^#+\s*", "", t)  # markdown heading markers
    t = re.sub(r"^\d+([.)]\d*)*[.)]?\s+", "", t)  # leading numbering e.g. "1." / "1.2)"
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)  # punctuation -> space
    t = re.sub(r"\s+", " ", t).strip()
    return t


_HEADING_LINE = re.compile(r"#{1,6}[ \t]+(.*?)[ \t#]*$")


def _strip_title_heading(text: str, title: str) -> str:
    """``text`` without a first line that is a heading repeating the section's ``title``.

    A writer told to leave the heading out sometimes echoes it (``## Findings``, also
    numbered or as ``SECTION: Findings``). Any other first heading, such as the
    ``### Roof`` of a section with subsections, is the section's own content and stays.
    """
    stripped = text.lstrip()
    first, _, rest = stripped.partition("\n")
    match = _HEADING_LINE.fullmatch(first.strip())
    if match is None:
        return text
    heading = re.sub(r"^section\s*:\s*", "", match.group(1).strip(), flags=re.IGNORECASE)
    if _normalize_heading(heading) != _normalize_heading(title):
        return text
    return rest.lstrip()


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
