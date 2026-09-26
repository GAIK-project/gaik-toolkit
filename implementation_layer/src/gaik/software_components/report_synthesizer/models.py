"""Data models for ReportSynthesizer results. Pydantic only, except DOCX export."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gaik.software_components.draft_reviewer.models import Edit


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    title: str
    text: str
    """Section body in Markdown, without the heading."""


class ReviewEntry(BaseModel):
    """What the reviewer changed in one section, and what it could not apply."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    applied: list[Edit]
    unresolved: list[Edit]


class Report(BaseModel):
    """A written report: its sections in report order and the review log."""

    model_config = ConfigDict(extra="forbid")

    title: str
    sections: list[ReportSection]
    review_log: list[ReviewEntry]
    usage: dict[str, int] = {}
    """Token usage of the writer and reviewer calls. Not saved, so empty after :meth:`load`."""

    @property
    def markdown(self) -> str:
        parts = [f"# {self.title}"] + [f"## {s.title}\n\n{s.text.strip()}" for s in self.sections]
        return "\n\n".join(parts) + "\n"

    def save(self, directory: str | Path, *, docx: bool = True) -> dict[str, Path]:
        """Write ``sections/NN_<id>.md``, ``review_log.json``, ``report.md`` and ``report.docx``.

        Section files from an earlier save are replaced. ``docx`` needs ``pypandoc``
        and the Pandoc binary; without it, a ``report.docx`` of an earlier save is
        deleted, so it cannot pass for the current report.
        """
        out = Path(directory)
        section_dir = out / "sections"
        section_dir.mkdir(parents=True, exist_ok=True)
        for old in section_dir.glob("*.md"):
            old.unlink()
        paths: dict[str, Path] = {}
        for i, section in enumerate(self.sections, start=1):
            path = section_dir / f"{i:02d}_{section.id}.md"
            path.write_text(f"## {section.title}\n\n{section.text.strip()}\n", encoding="utf-8")
            paths[f"section:{section.id}"] = path
        paths["review_log"] = out / "review_log.json"
        paths["review_log"].write_text(
            json.dumps([e.model_dump() for e in self.review_log], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths["markdown"] = out / "report.md"
        paths["markdown"].write_text(self.markdown, encoding="utf-8")
        if docx:
            import pypandoc

            paths["docx"] = out / "report.docx"
            pypandoc.convert_file(str(paths["markdown"]), "docx", outputfile=str(paths["docx"]))
        else:
            (out / "report.docx").unlink(missing_ok=True)
        return paths

    @classmethod
    def load(cls, directory: str | Path) -> Report:
        """Read a folder written by :meth:`save`, including any edits to the section files.

        ``load(d).save(d)`` rebuilds ``report.md`` and ``report.docx`` from edited sections.
        """
        root = Path(directory)
        first_line = (root / "report.md").read_text(encoding="utf-8").split("\n", 1)[0]
        if not first_line.startswith("# "):
            raise ValueError(f"{root / 'report.md'} must start with '# <report title>'")
        sections = []
        for path in sorted((root / "sections").glob("*.md")):
            heading, _, body = path.read_text(encoding="utf-8").partition("\n")
            if not heading.startswith("## "):
                raise ValueError(f"{path} must start with '## <section title>'")
            sections.append(
                ReportSection(
                    id=path.stem.split("_", 1)[1], title=heading[3:].strip(), text=body.strip()
                )
            )
        if not sections:
            raise FileNotFoundError(f"No section files in {root / 'sections'}")
        review_log = json.loads((root / "review_log.json").read_text(encoding="utf-8"))
        return cls(
            title=first_line[2:].strip(),
            sections=sections,
            review_log=[ReviewEntry.model_validate(e) for e in review_log],
        )
