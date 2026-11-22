"""Citations built from the retrieved chunks, not from the model's text.

Each retrieved chunk gets a reference number, ``[1]`` for the first chunk, ``[2]`` for
the second, and so on. The model cites by those numbers. A ``CitationResolver`` reads
the answer, turns each reference into ``[document_name, page X]`` from that chunk's
metadata, and collects the chunks it cited. A ``[name, page X]`` written by the model
that matches no retrieved chunk is removed from the answer and listed in ``dropped``.

Only two bracket forms are read as citations:

- a list of numbers (``[1]``, ``[1, 3]``, ``[2; 4]``) whose numbers are all between 1
  and the number of retrieved chunks. A list with any other number (``[0]``,
  ``[2019]``, or ``[7]`` with four chunks) is left as written and is not a citation,
  so a number the model invents stays in the text but never in ``citations``;
- a document with a page (``[report.pdf, page 3]``, ``[Document: report.pdf, Page: 3]``).
  A chunk without a page is ``page unknown``, in any case, as the context names it.

A bracket is not read at all when it is code or looks like an index: inside a fenced
code block, inside an inline code span on one line, directly after a letter, digit,
``_``, ``)`` or a bracket that is not a citation (``arr[0]``, ``matrix[1][2]``), or
after ``=`` (``nums = [1, 2]``). Any other text, including a source the model writes in
another form such as ``(report.pdf, page 3)``, is left as written.
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
_BRACKET = re.compile(r"\[(?P<inner>[^\[\]\n]{1," + str(_MAX_CITATION_LENGTH) + r"})\]")
# A fence line opens or closes a fenced code block; a line start that may still
# become one waits for more text.
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_MAYBE_FENCE = re.compile(r" {0,3}(`*|~*)")
_PLAIN = re.compile(r"[^`\[ \t]+")


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
        if self.page_number is None or not str(self.page_number).strip():
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


# The page of a chunk without one: the context names it "Page: unknown", and
# TextRagParser writes "Unknown" for a file that has no pages.
_NO_PAGE = "unknown"


def _page_key(page: Any) -> str:
    """A page as a citation is matched by it; any spelling of ``unknown`` is no page."""
    text = "" if page is None else str(page).strip()
    return _NO_PAGE if not text or text.lower() == _NO_PAGE else text


def _pages(spec: str) -> list[str]:
    """The pages a page spec names: ``3`` or the range ``5-7``."""
    spec = spec.strip()
    found = _PAGE_RANGE.fullmatch(spec)
    if found:
        start, end = int(found.group(1)), int(found.group(2))
        if 0 <= end - start <= 50:
            return [str(page) for page in range(start, end + 1)]
    return [_page_key(spec)]


class CitationResolver:
    """Turns the model's references into citations of the retrieved chunks.

    Feed it the answer (whole, or delta by delta while it streams), then call
    ``finish``. ``citations`` lists the cited chunks in the order the answer first
    cites them; ``dropped`` lists the ``[name, page X]`` citations the answer wrote
    that match no retrieved chunk, as written. A citation that repeats the label just
    before it (``[1][2]`` of one page) is shown once.
    """

    def __init__(self, documents: Sequence[Any] | None) -> None:
        self._citations = [
            citation_for(number, document) for number, document in enumerate(documents or [], 1)
        ]
        self._by_name_and_page: dict[tuple[str, str], Citation] = {}
        for citation in self._citations:
            if not citation.document_name:
                continue
            # A chunk without a page is cited as the context shows it, "page unknown".
            page = _page_key(citation.page_number)
            for key in _name_keys(citation.document_name):
                self._by_name_and_page.setdefault((key, page), citation)
        self.citations: list[Citation] = []
        self.dropped: list[str] = []
        self._buffer = ""
        # Where the answer is: the kind of the current line (None at a line start,
        # "text", "code" or "fence"), the marker of an open fenced block, the last
        # character shown, the label of a citation shown right before it, whether
        # space after a citation removed at a line start is dropped, and the space
        # before a citation removed right before, which a bracket next to it takes.
        self._line: str | None = None
        self._fence: str | None = None
        self._last = "\n"
        self._last_label: str | None = None
        self._skip_space = False
        self._held_space = ""

    def resolve(self, answer: str) -> str:
        """The whole answer with its citations resolved."""
        return self.feed(answer) + self.finish()

    def feed(self, delta: str) -> str:
        """The part of the answer so far that can be shown; the rest waits for more."""
        self._buffer += delta
        return self._process(final=False)

    def finish(self) -> str:
        """The rest of the answer, at its end."""
        return self._process(final=True)

    def stream(self, deltas: Iterable[str]) -> Iterator[str]:
        """The deltas with their citations resolved; ``citations`` is complete at the end."""
        for delta in deltas:
            text = self.feed(delta)
            if text:
                yield text
        text = self.finish()
        if text:
            yield text

    # The answer is read line by line, and a line that is not complete yet only as
    # far as the rest of it cannot change how it is read, so a streamed answer
    # shows the same text as the whole answer.

    def _process(self, *, final: bool) -> str:
        out: list[str] = []
        while self._buffer:
            newline = self._buffer.find("\n")
            line = self._buffer if newline == -1 else self._buffer[: newline + 1]
            complete = newline != -1 or final
            if self._line is None:
                if _FENCE.match(line):
                    self._line = "fence"
                elif not complete and _MAYBE_FENCE.fullmatch(line):
                    break
                else:
                    self._line = "code" if self._fence else "text"
            if self._line == "fence":
                if not complete:
                    break
                self._fence_line(line)
                consumed = len(line)
                out.append(self._show_code(line))
            elif self._line == "code":
                consumed = len(line)
                out.append(self._show_code(line))
            else:
                text, consumed = self._text(line, complete)
                out.append(text)
            self._buffer = self._buffer[consumed:]
            if consumed < len(line):
                break
            if line.endswith("\n"):
                self._line = None
        return "".join(out)

    def _fence_line(self, line: str) -> None:
        marker = _FENCE.match(line).group(1)
        if self._fence is None:
            self._fence = marker
        elif (
            marker[0] == self._fence[0]
            and len(marker) >= len(self._fence)
            and not line.strip(" \t\r\n").strip(marker[0])
        ):
            self._fence = None

    def _show_code(self, text: str) -> str:
        if text:
            self._last, self._last_label, self._skip_space = text[-1], None, False
            self._held_space = ""
        return text

    def _show_text(self, text: str) -> str:
        if self._skip_space:
            text = text.lstrip(" \t")
        return self._show_code(text)

    def _text(self, line: str, complete: bool) -> tuple[str, int]:
        """A line outside fenced code with its citations resolved, and how much of
        it was read; an incomplete line is read only as far as it is settled."""
        out: list[str] = []
        at = 0
        while at < len(line):
            char = line[at]
            if char == "`":
                end = self._code_span_end(line, at, complete)
                if end is None:
                    break
                out.append(self._show_text(line[at:end]))
                at = end
            elif char in " \t" or char == "[":
                space_end = at
                while space_end < len(line) and line[space_end] in " \t":
                    space_end += 1
                if space_end == len(line) and not complete:
                    break
                if space_end == len(line) or line[space_end] != "[":
                    out.append(self._show_text(line[at:space_end]))
                    at = space_end
                    continue
                bracket = _BRACKET.match(line, space_end)
                if bracket is None:
                    rest = line[space_end + 1 :]
                    if not complete and not re.search(r"[\[\]\n]", rest):
                        if len(rest) <= _MAX_CITATION_LENGTH:
                            break
                    out.append(self._show_text(line[at : space_end + 1]))
                    at = space_end + 1
                    continue
                if "`" in bracket.group("inner"):
                    out.append(self._show_text(line[at : space_end + 1]))
                    at = space_end + 1
                    continue
                out.append(self._bracket(line[at:space_end], bracket))
                at = bracket.end()
            else:
                plain = _PLAIN.match(line, at)
                out.append(self._show_text(plain.group(0)))
                at = plain.end()
        return "".join(out), at

    @staticmethod
    def _code_span_end(line: str, at: int, complete: bool) -> int | None:
        """The end of the code span or backtick run at ``at``; ``None`` to wait."""
        run = len(line[at:]) - len(line[at:].lstrip("`"))
        if at + run == len(line) and not complete:
            return None
        closing = re.compile(r"(?<!`)" + "`" * run + r"(?!`)")
        for found in closing.finditer(line, at + run):
            if found.end() == len(line) and not complete:
                return None
            return found.end()
        if not complete:
            return None
        return at + run

    def _may_cite(self, space: str) -> bool:
        """Whether a bracket after ``space`` can be a citation, not an index."""
        last = self._last
        if not space and (
            last.isalnum() or last in "_)" or (last == "]" and self._last_label is None)
        ):
            return False
        return last != "="

    def _bracket(self, space: str, match: re.Match[str]) -> str:
        # A bracket right after a removed citation stands where that one stood: in
        # "report [fake.pdf, page 9][1]" the [1] follows a space, not the "t".
        held, self._held_space = self._held_space, ""
        if self._skip_space:
            space = ""
        elif not space:
            space = held
        read = self._read(match.group("inner").strip()) if self._may_cite(space) else None
        if read is None:
            return self._show_text(space + match.group(0))
        found, dropped = read
        self.dropped.extend(dropped)
        if not found:
            if not space and self._last == "\n":
                self._skip_space = True
            self._held_space = space
            return ""
        labels: list[str] = []
        for citation in found:
            if citation not in self.citations:
                self.citations.append(citation)
            if citation.label not in labels and citation.label != self._last_label:
                labels.append(citation.label)
        if not labels:
            self._held_space = space
            return ""
        self._last, self._last_label, self._skip_space = "]", labels[-1], False
        return space + " ".join(labels)

    def _read(self, inner: str) -> tuple[list[Citation], list[str]] | None:
        """The retrieved chunks a bracket cites and the parts that cite none.

        ``None`` when the bracket is not a citation at all, which is also the case
        for a list of numbers with a number that is not a retrieved chunk's.
        """
        cited: list[Citation] = []
        dropped: list[str] = []
        if _NUMBERS.fullmatch(inner):
            numbers = [int(text) for text in re.findall(r"\d+", inner)]
            if not all(1 <= number <= len(self._citations) for number in numbers):
                return None
            return [self._citations[number - 1] for number in numbers], dropped
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
