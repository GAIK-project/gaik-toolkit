"""Inputs and results of the operations, JSON-ready with ``model_dump(mode="json")``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

FieldType = Literal["str", "int", "float", "bool", "date", "decimal", "list[str]"]
Verdict = Literal["verified", "check", "reworded", "unchecked"]


def readable_name(name: str) -> str:
    """A field name as a label: ``work_done`` -> ``Work done``."""
    words = " ".join(name.replace("_", " ").split())
    return words[:1].upper() + words[1:]


class FieldDefinition(BaseModel):
    """One field to fill from a text."""

    model_config = ConfigDict(extra="forbid")

    name: str
    """Any text, unique in a list. Letters outside ASCII are fine."""
    type: FieldType = "str"
    description: str = ""
    label: str | None = None
    """Display label. None: derived from the name."""
    required: bool = False
    options: list[str] | None = None
    """Allowed values. Only with type ``str``."""
    format: str | None = None
    """Date output format (strftime). Only with type ``date``."""

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("a field needs a name")
        return value

    @field_validator("options")
    @classmethod
    def _options_not_empty(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value or any(not option.strip() for option in value):
            raise ValueError("options must hold at least one value and no blank ones")
        return value

    @model_validator(mode="after")
    def _options_and_format_fit_the_type(self) -> FieldDefinition:
        if self.options is not None and self.type != "str":
            raise ValueError("options are only for a field of type str")
        if self.format is not None and self.type != "date":
            raise ValueError("format is only for a field of type date")
        return self

    @property
    def display_label(self) -> str:
        """``label``, or the name made readable."""
        label = (self.label or "").strip()
        return label or readable_name(self.name)


class ParsedDocument(BaseModel):
    """The text of a file."""

    text: str
    """The non-empty pages joined with a blank line."""
    pages: list[str]
    """One entry per PDF page. A DOCX or a text file is one page."""
    kind: Literal["pdf", "docx", "text"]


class Transcript(BaseModel):
    """The text of a recording."""

    text: str
    duration_s: float | None = None
    """Length of the audio in seconds."""
    language: str | None = None
    """What the caller asked for."""
    model: str = ""
    failed_segments: int = 0
    """Parts of a long recording that failed."""


class ExtractedField(BaseModel):
    """The value of one field, with the quote it rests on."""

    name: str
    """``FieldDefinition.name``, unchanged."""
    label: str
    value: str | int | float | bool | list[str] | None = None
    evidence: str | None = None
    """The quote exactly as it stands in the text. None when it is not there."""
    verdict: Verdict | None = None
    """``check`` means look at the value: its quote is not in the text, or it is there but
    does not support the value (another number or date). ``evidence`` can be filled."""


class Classification(BaseModel):
    """The label chosen for a text."""

    label: str
    confidence: float
    """Not the same figure on both backends, so one threshold does not fit both.

    ``llm``: the probability of the chosen label, equal to ``probabilities[label]``.
    ``jev``: Jev's own confidence, which is high when nearly all probability landed on one
    label and is not that label's probability. The probability of the chosen label is
    ``probabilities[label]`` on either backend.
    """
    probabilities: dict[str, float]
    """One per label. ``llm``: the model's own estimates. ``jev``: calibrated."""
    model: str
    backend: Literal["llm", "jev"]
