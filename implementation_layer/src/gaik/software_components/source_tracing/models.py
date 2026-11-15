"""Result and policy types for source tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Where the quote was looked for: found on the cited page (or in the cited text), found
# somewhere else, not found at all, or the file has no text layer to look in.
QuoteStatus = Literal["found", "moved", "not_found", "no_text_layer"]
ValueStatus = Literal["match", "mismatch", "unchecked"]
Verdict = Literal["verified", "check", "reworded", "unchecked"]


@dataclass
class TracePolicy:
    """The judgment calls of the check, with the defaults the demo grew into.

    Attributes:
        number_tolerance: Largest difference at which two numbers count as equal.
        match_reformatted_identifiers: Count ``7200-4453-21`` as matching a quote that holds
            ``7200445321`` (the same characters with other separators).
        reworded_is_problem: A text value that is not in its quote is usually the model's own
            wording (a translation or a summary) and is reported as ``reworded``. Set this to
            have it reported as ``check`` instead, for tasks that must copy values verbatim.
        min_quote_words: A quote with fewer words is too short to be evidence and is reported
            as ``check`` even if it is found.
        ambiguous_quote_is_check: A quote that occurs more than once in the text or on the
            page can not say which occurrence the model read. Set this to report such a quote
            as ``check`` instead of ``verified``; off by default, because the same words often
            repeat (a unit, a header) and ``TracedValue.occurrences`` shows how many.
    """

    number_tolerance: float = 1e-6
    match_reformatted_identifiers: bool = True
    reworded_is_problem: bool = False
    min_quote_words: int = 1
    ambiguous_quote_is_check: bool = False


@dataclass
class TracedValue:
    """One extracted value with the evidence the model gave for it, after the check.

    Attributes:
        field: Path of the value, e.g. ``total`` or ``items[0].quantity``.
        value: The extracted value at that path (None when the path holds nothing).
        quote: The snippet the model gave as evidence.
        document: 1-based number of the document the quote was found in (the cited one when
            it was not found anywhere).
        page: 1-based page it was found on (the cited page when it was not found).
        cited_page: The page the model named.
        status: Whether the quote is in the source (see :data:`QuoteStatus`).
        value_status: Whether the value is in the quote (see :data:`ValueStatus`).
        verdict: ``verified``, ``check``, ``reworded`` or ``unchecked``.
        rects: Boxes of the quote's words on the page, as fractions of the page (PDF only).
        value_rects: Boxes of the value inside the quote (PDF only).
        span: Character offsets of the quote in the text (text only; None when not found).
        occurrences: How many times the quote occurs in the text, or on the page it was found
            on (PDF). Above 1, the boxes or offsets are those of the first
            occurrence; 0 when the quote was not found.
        record: Index of the record the value belongs to when the results are unwrapped into
            rows; None for a value every record shares.
    """

    field: str
    value: Any
    quote: str
    document: int
    page: int
    cited_page: int
    status: QuoteStatus
    value_status: ValueStatus
    verdict: Verdict = "unchecked"
    rects: list[dict] = field(default_factory=list)
    value_rects: list[dict] = field(default_factory=list)
    span: tuple[int, int] | None = None
    occurrences: int = 0
    record: int | None = None

    def to_dict(self) -> dict:
        """Plain JSON-ready form."""
        return {
            "field": self.field,
            "value": self.value,
            "quote": self.quote,
            "document": self.document,
            "page": self.page,
            "cited_page": self.cited_page,
            "status": self.status,
            "value_status": self.value_status,
            "verdict": self.verdict,
            "rects": self.rects,
            "value_rects": self.value_rects,
            "span": list(self.span) if self.span else None,
            "occurrences": self.occurrences,
            "record": self.record,
        }


@dataclass
class TraceReport:
    """What the check found, for all results of one run.

    Attributes:
        items: One entry per citation the model gave, in the order it gave them.
        documents: Names of the checked documents (file names for PDFs, empty for texts).
        values: Number of extracted values that could have had a citation.
        cited: How many of them have one.
    """

    items: list[TracedValue] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    values: int = 0
    cited: int = 0

    @property
    def coverage(self) -> float | None:
        """Share of the extracted values that came with evidence (None: nothing extracted)."""
        return self.cited / self.values if self.values else None

    def summary(self) -> dict:
        """Counts per verdict, the number of citations and the coverage."""
        counts = {"verified": 0, "check": 0, "reworded": 0, "unchecked": 0}
        for item in self.items:
            counts[item.verdict] += 1
        return {**counts, "total": len(self.items), "coverage": self.coverage}

    def to_dict(self) -> dict:
        """Plain JSON-ready form."""
        return {
            "summary": self.summary(),
            "documents": self.documents,
            "sources": [item.to_dict() for item in self.items],
        }
