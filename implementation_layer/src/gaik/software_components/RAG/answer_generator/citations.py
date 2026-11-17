"""Citations built from the retrieved chunks, not from the model's text.

Each retrieved chunk gets a reference number, ``[1]`` for the first chunk, ``[2]`` for
the second, and so on. The model cites by those numbers. A ``CitationResolver`` reads
the answer, turns each reference into ``[document_name, page X]`` from that chunk's
metadata, and collects the chunks it cited. A reference that is not one of the
retrieved chunks, and a ``[name, page X]`` written by the model that matches no
retrieved chunk, is removed from the answer and listed in ``dropped``.

Only two bracket forms are read as citations: a list of numbers (``[1]``,
``[1, 3]``, ``[2; 4]``) and a document with a page (``[report.pdf, page 3]``,
``[Document: report.pdf, Page: 3]``). Any other bracketed text is left as it is.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

# A bracket that is still open after this many characters is ordinary text.
_MAX_CITATION_LENGTH = 300

_NUMBERS = re.compile(r"\d+(?:\s*[,;]\s*\d+)*")
_NAME_AND_PAGE = re.compile(
    r"(?:document\s*:\s*)?(?P<name>.+?)\s*,\s*(?:pages?|p\.)\s*:?\s*(?P<page>[^\s,;]+(?:\s*[-\u2013]\s*[^\s,;]+)?)",
    re.IGNORECASE,
)
_PAGE_RANGE = re.compile(r"(\d+)\s*[-\u2013]\s*(\d+)")
# Optional horizontal space before a bracket, so a removed citation takes its space along.
_BRACKET = re.compile(r"[ \t]*\[(?P<inner>[^\[\]\n]{1," + str(_MAX_CITATION_LENGTH) + r"})\]")


@dataclass(frozen=True)
class Citation:
    """One retrieved chunk the answer cites.

    ``reference`` is the number the chunk had in the prompt; ``document_name`` and
    ``page_number`` come from the chunk's metadata (``None`` when it has none), and
    ``document`` is the retrieved chunk itself.
    """

    reference: int
    document_name: str | None
    page_number: Any
    document: Any = field(default=None, compare=False, repr=False)

    @property
    def label(self) -> str:
        """The text the answer shows for this citation."""
        if not self.document_name:
            return f"[{self.reference}]"
        if self.page_number is None:
            return f"[{self.document_name}]"
        return f"[{self.document_name}, page {self.page_number}]"


def citation_for(reference: int, document: Any) -> Citation:
    """The citation of the retrieved chunk that had ``reference`` in the prompt."""
    meta = getattr(document, "metadata", None) or {}
    name = meta.get("document_name")
    page = meta.get("page_number")
    return Citation(
        reference=reference,
        document_name=str(name) if name else None,
        page_number=page,
        document=document,
    )


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _name_keys(value: str) -> set[str]:
    """A document name with and without its file extension."""
    name = _normalize_name(value)
    keys = {name}
    stem, dot, extension = name.rpartition(".")
    if dot and stem and extension.isalnum() and len(extension) <= 5:
        keys.add(stem)
    return keys


def _pages(spec: str) -> list[str]:
    """The pages a page spec names: ``3`` or the range ``5-7``."""
    spec = spec.strip()
    found = _PAGE_RANGE.fullmatch(spec)
    if found:
        start, end = int(found.group(1)), int(found.group(2))
        if 0 <= end - start <= 50:
            return [str(page) for page in range(start, end + 1)]
    return [spec]


class CitationResolver:
    """Turns the model's references into citations of the retrieved chunks.

    Feed it the answer (whole, or delta by delta while it streams), then call
    ``finish``. ``citations`` lists the cited chunks in the order the answer first
    cites them; ``dropped`` lists the citations the answer wrote that are not one of
    the retrieved chunks, as written.
    """

    def __init__(self, documents: Sequence[Any] | None) -> None:
        self._citations = [
            citation_for(number, document) for number, document in enumerate(documents or [], 1)
        ]
        self._by_name_and_page: dict[tuple[str, str], Citation] = {}
        for citation in self._citations:
            if not citation.document_name or citation.page_number is None:
                continue
            for key in _name_keys(citation.document_name):
                self._by_name_and_page.setdefault((key, str(citation.page_number)), citation)
        self.citations: list[Citation] = []
        self.dropped: list[str] = []
        self._buffer = ""

    def resolve(self, answer: str) -> str:
        """The whole answer with its citations resolved."""
        return self.feed(answer) + self.finish()

    def feed(self, delta: str) -> str:
        """The part of the answer so far that can be shown; the rest waits for more."""
        self._buffer += delta
        hold = self._hold_from(self._buffer)
        ready, self._buffer = self._buffer[:hold], self._buffer[hold:]
        return self._replace(ready)

    def finish(self) -> str:
        """The rest of the answer, at its end."""
        rest, self._buffer = self._buffer, ""
        return self._replace(rest)

    def stream(self, deltas: Iterable[str]) -> Iterator[str]:
        """The deltas with their citations resolved; ``citations`` is complete at the end."""
        for delta in deltas:
            text = self.feed(delta)
            if text:
                yield text
        text = self.finish()
        if text:
            yield text

    @staticmethod
    def _hold_from(text: str) -> int:
        """Where the text that may still become a citation starts.

        An open bracket with no closing one yet waits, with the space before it;
        so does trailing space, in case a citation that is removed follows it.
        """
        open_at = text.rfind("[")
        if open_at != -1 and "]" not in text[open_at:]:
            tail = text[open_at:]
            if "\n" not in tail and len(tail) <= _MAX_CITATION_LENGTH:
                return len(text[:open_at].rstrip(" \t"))
        return len(text.rstrip(" \t"))

    def _replace(self, text: str) -> str:
        return _BRACKET.sub(self._replace_bracket, text)

    def _replace_bracket(self, match: re.Match[str]) -> str:
        read = self._read(match.group("inner").strip())
        if read is None:
            return match.group(0)
        found, dropped = read
        self.dropped.extend(dropped)
        if not found:
            return ""
        space = match.group(0)[: match.start("inner") - match.start() - 1]
        labels: list[str] = []
        for citation in found:
            if citation not in self.citations:
                self.citations.append(citation)
            if citation.label not in labels:
                labels.append(citation.label)
        return space + " ".join(labels)

    def _read(self, inner: str) -> tuple[list[Citation], list[str]] | None:
        """The retrieved chunks a bracket cites and the parts that cite none.

        ``None`` when the bracket is not a citation at all.
        """
        cited: list[Citation] = []
        dropped: list[str] = []
        if _NUMBERS.fullmatch(inner):
            for number in (int(text) for text in re.findall(r"\d+", inner)):
                if 1 <= number <= len(self._citations):
                    cited.append(self._citations[number - 1])
                else:
                    dropped.append(f"[{number}]")
            return cited, dropped
        parts = [part.strip() for part in inner.split(";")]
        matches = [_NAME_AND_PAGE.fullmatch(part) for part in parts]
        if not all(matches):
            return None
        for part, found in zip(parts, matches, strict=True):
            keys = _name_keys(found.group("name"))
            hits = []
            for page in _pages(found.group("page")):
                hit = next(
                    (
                        self._by_name_and_page[(key, page)]
                        for key in keys
                        if (key, page) in self._by_name_and_page
                    ),
                    None,
                )
                if hit is not None:
                    hits.append(hit)
            if hits:
                cited.extend(hits)
            else:
                dropped.append(f"[{part}]")
        return cited, dropped


@dataclass
class CitedAnswer:
    """An answer with the retrieved chunks it cites.

    With ``stream=True``, ``answer`` is an iterator and ``citations`` and
    ``dropped_citations`` are filled in when it has been read to the end.
    """

    answer: str | Iterable[str]
    citations: list[Citation] = field(default_factory=list)
    dropped_citations: list[str] = field(default_factory=list)
