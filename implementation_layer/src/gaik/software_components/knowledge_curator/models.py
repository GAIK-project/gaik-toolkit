"""Data models for report sections and curated knowledge.

Pydantic only. ``SectionSpec`` is shared by KnowledgeCurator, ReportSynthesizer and
the ReportWriter module; the knowledge models are the persisted Stage 2 output.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gaik.software_components.source_normalizer.models import NormalizedSources


class SectionSpec(BaseModel):
    """One report section: what it covers and which sections it is written from."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    title: str
    instructions: str = ""
    required_items: list[str] = []
    """Items the section must cover; each one no source covers is recorded as missing."""
    depends_on: list[str] = []
    """Ids of the sections whose drafts this section is written from."""

    @property
    def derived(self) -> bool:
        """True for a section written from other drafts, not curated from sources."""
        return bool(self.depends_on)


def check_sections(sections: Sequence[SectionSpec]) -> None:
    """Raise ``ValueError`` on duplicate ids or a dependency on an unknown section."""
    ids = [s.id for s in sections]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"Duplicate section ids: {duplicates}")
    for section in sections:
        unknown = [d for d in section.depends_on if d not in ids]
        if unknown:
            raise ValueError(f"Section {section.id!r} depends on unknown sections: {unknown}")


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    """Original file name of the cited source."""
    locator: str | None
    """Place in the source, e.g. ``page 3`` or ``sheet Log, row 7``; null if none."""


class FactUnit(BaseModel):
    """One fact: a short summary paired with the exact words of its source."""

    model_config = ConfigDict(extra="forbid")

    id: str
    topic: str
    time_qualifier: str | None
    summary: str
    quote: str
    source: SourceRef
    source_class: str | None
    confidence: Literal["high", "medium", "low"]


class Conflict(BaseModel):
    """A disagreement between sources on one topic."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    description: str
    status: Literal["resolved", "unresolved"]
    unit_ids: list[str]


class SectionKnowledge(BaseModel):
    """The curated knowledge of one section."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    units: list[FactUnit]
    missing: list[str]
    """Required items that no source covers."""
    conflicts: list[Conflict]


def quote_in_text(quote: str, text: str) -> bool:
    """True if ``quote`` occurs in ``text`` verbatim, ignoring differences in whitespace."""
    squashed = " ".join(quote.split())
    return bool(squashed) and squashed in " ".join(text.split())


class KnowledgeBase(BaseModel):
    """The curated knowledge of every non-derived section."""

    model_config = ConfigDict(extra="forbid")

    sections: list[SectionKnowledge]
    usage: dict[str, int] = {}
    """Token usage of the curator calls. Not saved, so empty after :meth:`load`."""

    def get(self, section_id: str) -> SectionKnowledge:
        for section in self.sections:
            if section.section_id == section_id:
                return section
        raise KeyError(f"No knowledge for section {section_id!r}")

    def verify_quotes(self, sources: NormalizedSources) -> list[FactUnit]:
        """Return the units whose quote is not found in the source they cite.

        An empty list means every quote was found verbatim.
        """
        texts = {s.file: s.text for s in sources.sources}
        return [
            unit
            for section in self.sections
            for unit in section.units
            if not quote_in_text(unit.quote, texts.get(unit.source.file, ""))
        ]

    def save(self, directory: str | Path) -> dict[str, Path]:
        """Write one ``<section_id>.json`` per section."""
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        for section in self.sections:
            paths[section.section_id] = out / f"{section.section_id}.json"
            paths[section.section_id].write_text(
                section.model_dump_json(indent=2), encoding="utf-8"
            )
        return paths

    @classmethod
    def load(cls, directory: str | Path) -> KnowledgeBase:
        """Read every ``*.json`` file of a folder written by :meth:`save`."""
        files = sorted(Path(directory).glob("*.json"))
        if not files:
            raise FileNotFoundError(f"No knowledge files in {directory}")
        return cls(
            sections=[
                SectionKnowledge.model_validate_json(f.read_text(encoding="utf-8")) for f in files
            ]
        )
