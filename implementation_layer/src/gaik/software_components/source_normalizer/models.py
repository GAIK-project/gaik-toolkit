"""Data models for SourceNormalizer results.

Pydantic only, so consumers such as KnowledgeCurator can import them without the
parser and transcriber dependencies.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, model_validator


def source_id(index: int, name: str) -> str:
    """``01_floor_plan_1`` for ``floor_plan (1).png``: the order number and an ASCII slug of
    the stem, so any file name gives a portable name for the Markdown file."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", PurePosixPath(name).stem).strip("_.")
    return f"{index:02d}_{slug}" if slug else f"{index:02d}"


class NormalizedSource(BaseModel):
    """One input file converted to Markdown text, with its provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    """Order number and ASCII slug of the file stem, e.g. ``01_rec1_exterior_attic``; names
    the Markdown file."""
    file: str
    """Original file name. Fact units cite a source by this name."""
    source_class: str | None
    """Input group the file was given in, e.g. ``primary`` or ``secondary``."""
    source_type: str
    """``pdf``, ``docx``, ``spreadsheet``, ``text``, ``audio`` or ``image``."""
    tool: str
    """Component that produced the text, e.g. ``PyMuPDFParser`` or ``Transcriber``."""
    text: str


class NormalizedSources(BaseModel):
    """The normalized texts of a set of sources, in input order."""

    model_config = ConfigDict(extra="forbid")

    sources: list[NormalizedSource]
    usage: dict[str, int] = {}
    """Usage of the transcription and vision calls. Not saved, so empty after :meth:`load`."""

    @model_validator(mode="after")
    def _unique(self) -> NormalizedSources:
        for field in ("id", "file"):
            values = [getattr(s, field) for s in self.sources]
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(f"Duplicate source {field}s: {duplicates}")
        return self

    def get(self, file: str) -> NormalizedSource:
        """Return the source with the given original file name."""
        for source in self.sources:
            if source.file == file:
                return source
        raise KeyError(f"No normalized source for file {file!r}")

    @classmethod
    def from_texts(
        cls, texts: Mapping[str, str], source_class: str | None = None
    ) -> NormalizedSources:
        """Wrap texts that are already available, keyed by file name."""
        return cls(
            sources=[
                NormalizedSource(
                    id=source_id(i, name),
                    file=name,
                    source_class=source_class,
                    source_type="text",
                    tool="provided",
                    text=text,
                )
                for i, (name, text) in enumerate(texts.items(), start=1)
            ]
        )

    def save(self, directory: str | Path) -> dict[str, Path]:
        """Write one ``<id>.md`` per source and a ``sources.json`` manifest."""
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        for source in self.sources:
            paths[source.id] = out / f"{source.id}.md"
            paths[source.id].write_text(source.text, encoding="utf-8")
        manifest = [s.model_dump(exclude={"text"}) for s in self.sources]
        paths["sources"] = out / "sources.json"
        paths["sources"].write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return paths

    @classmethod
    def load(cls, directory: str | Path) -> NormalizedSources:
        """Read a folder written by :meth:`save`."""
        root = Path(directory)
        manifest = json.loads((root / "sources.json").read_text(encoding="utf-8"))
        return cls(
            sources=[
                NormalizedSource(
                    **entry, text=(root / f"{entry['id']}.md").read_text(encoding="utf-8")
                )
                for entry in manifest
            ]
        )
