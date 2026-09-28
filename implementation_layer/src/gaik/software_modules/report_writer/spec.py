"""The report spec: one JSON file that defines a report and its sources.

A spec holds model names only, never credentials; ``extra="forbid"`` rejects any
unknown key, including an ``api_key``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gaik.software_components.knowledge_curator.models import SectionSpec, check_sections


class ModelSettings(BaseModel):
    """Model or deployment name per step; ``None`` uses the model in the config."""

    model_config = ConfigDict(extra="forbid")

    vision: str | None = None
    transcription: str | None = None
    curator: str | None = None
    writer: str | None = None
    reviewer: str | None = None


class StepOptions(BaseModel):
    """Chat options for every call of one step; ``None`` leaves the option unset."""

    model_config = ConfigDict(extra="forbid")

    reasoning_effort: str | None = None
    temperature: float | None = None

    def chat_kwargs(self) -> dict:
        return self.model_dump(exclude_none=True)


class RunSettings(BaseModel):
    """How the stages run: transcription, parallelism, review and output."""

    model_config = ConfigDict(extra="forbid")

    transcription_language: str = "auto"
    """Language of the recordings, e.g. ``en`` or ``fi``, or ``auto``."""
    curator_workers: int = Field(4, ge=1)
    """Sections curated in parallel."""
    review_attempts: int = Field(5, ge=1)
    """Most reviewer requests per section, the first one included."""
    strict_review: bool = False
    """Fail the synthesize stage when a reviewer edit cannot be applied, instead of
    logging it in the review log."""
    docx: bool = True
    """Also write ``report.docx``; needs ``pypandoc`` and the Pandoc binary."""
    curator: StepOptions = StepOptions()
    writer: StepOptions = StepOptions()
    reviewer: StepOptions = StepOptions()


class ReportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    """What the report is for. For people and the demo; not sent to the model."""
    language: str = "English"
    sections: list[SectionSpec]
    instructions: str = ""
    """Rules for every section, such as the source hierarchy and style."""
    sources: dict[Literal["primary", "secondary"], list[Path]]
    sample_report: Path | None = None
    """A report whose structure and style the new report follows."""
    models: ModelSettings = ModelSettings()
    settings: RunSettings = RunSettings()

    @model_validator(mode="after")
    def _check(self) -> ReportSpec:
        check_sections(self.sections)
        if not any(self.sources.values()):
            raise ValueError("The spec lists no sources")
        return self

    @classmethod
    def load(cls, path: str | Path) -> ReportSpec:
        """Read a spec; relative paths are resolved against the spec file's folder."""
        path = Path(path)
        spec = cls.model_validate_json(path.read_text(encoding="utf-8"))
        root = path.resolve().parent
        spec.sources = {k: [root / p for p in v] for k, v in spec.sources.items()}
        if spec.sample_report is not None:
            spec.sample_report = root / spec.sample_report
        return spec

    def save(self, path: str | Path) -> Path:
        """Write the spec with paths relative to the spec file's folder, in POSIX form."""
        path = Path(path)
        root = path.resolve().parent

        def rel(p: Path) -> str:
            return Path(os.path.relpath(Path(p).resolve(), root)).as_posix()

        data = self.model_dump(mode="json")
        data["sources"] = {k: [rel(p) for p in v] for k, v in self.sources.items()}
        data["sample_report"] = rel(self.sample_report) if self.sample_report else None
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
