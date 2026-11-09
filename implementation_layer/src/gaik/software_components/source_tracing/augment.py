"""Asking the model for evidence: the schema field and the instruction that go with a task.

The model is asked for one citation per value: the document, the page and a short verbatim
quote. It is never asked for coordinates, because a model cannot give reliable ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, create_model

SOURCES_FIELD = "field_sources"

SOURCE_INSTRUCTION = f"""
SOURCE CITATIONS (REQUIRED):
Fill `{SOURCES_FIELD}` with one entry for every value you extracted (skip null values).
- field: the path of the value, e.g. "invoice_number", or "items[0].quantity" for the
  first row of the list "items" (rows count from 0).
- document: the number of the file the value is in, counting the attached files from 1.
- page: the 1-based page of that file.
- quote: a SHORT snippet (max ~80 characters) copied EXACTLY from the document, with the
  value in it. Do not paraphrase, translate or reformat it: keep the original casing,
  punctuation, digit grouping and date format. Include the label when it is next to the
  value, e.g. "Total: 1.234,50 EUR" or "Invoice no. 100234".
""".strip()

# The same for text a parser or a transcriber produced: it may not mark its pages.
TEXT_SOURCE_INSTRUCTION = SOURCE_INSTRUCTION.replace(
    "- document: the number of the file the value is in, counting the attached files from 1.\n"
    "- page: the 1-based page of that file.\n",
    "- document: 1.\n- page: the 1-based page when the text marks its pages, otherwise 1.\n",
)


class Source(BaseModel):
    """One citation, as the model returns it."""

    field: str = Field(description="Path of the value, e.g. total or items[0].quantity")
    document: int = Field(description="1-based number of the attached file")
    page: int = Field(description="1-based page in that file")
    quote: str = Field(description="Short verbatim snippet of the document holding the value")


class SourceList(BaseModel):
    """The citations as one object, for extractors that read every list as table rows."""

    items: list[Source] = Field(default_factory=list)


@dataclass
class Augmented:
    """A task prepared to ask for evidence.

    Attributes:
        model: Copy of the extraction model with the citation field added; the original
            model is not changed.
        prompt: The task text with the evidence instruction appended.
    """

    model: type[BaseModel]
    prompt: str


def with_sources(model: type[BaseModel], *, wrapped: bool = False) -> type[BaseModel]:
    """The extraction model with the citations next to its own fields.

    ``wrapped`` puts them in an object: the text extractor post-processes every list of
    records as rows of the schema, which would rewrite the citations.
    """
    description = "Where each extracted value was read: one entry per value."
    field = (
        (SourceList, Field(default_factory=SourceList, description=description))
        if wrapped
        else (list[Source], Field(default_factory=list, description=description))
    )
    return create_model(model.__name__, __base__=model, **{SOURCES_FIELD: field})


def augment_task(
    model: type[BaseModel],
    user_requirements: str,
    source: Literal["text", "files"] = "text",
) -> Augmented:
    """The model and the task with the request for a quote per value added.

    Args:
        model: The extraction model the task would use.
        user_requirements: The task text.
        source: ``"text"`` when the extractor reads text (``DataExtractor`` and the two
            pipeline modules); ``"files"`` when it reads the files themselves
            (``VisionExtractor``), so the model can name the file and the page.
    """
    if source not in ("text", "files"):
        raise ValueError(f"source must be 'text' or 'files', not {source!r}")
    if SOURCES_FIELD in model.model_fields:
        raise ValueError(f"the model already has a {SOURCES_FIELD!r} field")
    if source == "files":
        return Augmented(with_sources(model), f"{user_requirements}\n\n{SOURCE_INSTRUCTION}")
    return Augmented(
        with_sources(model, wrapped=True), f"{user_requirements}\n\n{TEXT_SOURCE_INSTRUCTION}"
    )
