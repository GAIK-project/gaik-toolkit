"""Source tracing: ask an extractor for evidence, then check each value against its source.

The class works around an extractor you call yourself and changes none of them:

1. :meth:`SourceTracing.augment` returns the extraction model and the task text with the
   request for one verbatim quote per value added.
2. You call the extractor with them.
3. :meth:`SourceTracing.check_text` or :meth:`SourceTracing.check_pdf` removes the quotes
   from the results, finds each in the source, compares the value with it, and reports.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from .augment import SOURCES_FIELD, Augmented, augment_task
from .matching import (
    find_all,
    locate_in_text,
    tokens,
    value_around_quote,
    value_at,
    value_status,
    verdict_of,
)
from .models import QuoteStatus, TracedValue, TracePolicy, TraceReport, ValueStatus
from .pdf import PageWords, read_pages, rects, value_span

# What a checker returns for one citation: where the quote was, how the value compares.
_Found = tuple[QuoteStatus, int, int, ValueStatus, dict]
_Checker = Callable[[int, bool, str, int, int, Any], _Found]


class SourceTracing:
    """Evidence for extracted values: ask for a quote per value, then check it.

    Args:
        policy: The judgment calls of the check (see :class:`TracePolicy`). The defaults
            suit most documents.

    Example:
        >>> st = SourceTracing()
        >>> task = st.augment(Invoice, "Extract the invoice", source="text")
        >>> results = DataExtractor(config=config).extract(
        ...     extraction_model=task.model,
        ...     requirements=requirements,
        ...     user_requirements=task.prompt,
        ...     documents=[text],
        ... )
        >>> clean, report = st.check_text(results, [text])
        >>> report.summary()
    """

    def __init__(self, policy: TracePolicy | None = None):
        self.policy = policy or TracePolicy()

    def augment(
        self,
        schema: type[BaseModel],
        user_requirements: str,
        source: Literal["text", "files"] = "text",
    ) -> Augmented:
        """The extraction model and task text to pass to the extractor.

        Args:
            schema: The extraction model you would pass to the extractor.
            user_requirements: The task text.
            source: ``"text"`` for an extractor that reads text, ``"files"`` for one that
                reads the files themselves (``VisionExtractor``).

        Returns:
            The model with a ``field_sources`` field added (a copy; ``schema`` is not
            changed) and the task text with the evidence instruction appended.
        """
        return augment_task(schema, user_requirements, source)

    def check_text(self, results: Any, texts: str | list[str]) -> tuple[Any, TraceReport]:
        """Check the quotes against the text the extractor read.

        Args:
            results: What the extractor returned: a result dict or a list of them.
            texts: The text(s) the extractor read. When there is one result per text, each
                result is checked against its own text first; otherwise against the text
                the model named. A quote found in another text is reported as ``moved``.

        Returns:
            ``(clean, report)``: the results with ``field_sources`` removed (same shape,
            the input is not modified) and the :class:`TraceReport`.
        """
        documents = [texts] if isinstance(texts, str) else list(texts)
        token_lists = [tokens(text) for text in documents]

        def check(
            index: int, paired: bool, field: str, quote: str, document: int, page: int, value: Any
        ) -> _Found:
            needle = tokens(quote)
            preferred = (
                index if paired else (document - 1 if 1 <= document <= len(documents) else 0)
            )
            order = [preferred, *(i for i in range(len(documents)) if i != preferred)]
            found_in = None
            span = None
            for number in order:
                span = locate_in_text(documents[number], quote)
                if span is not None:
                    found_in = number
                    break
            state = value_status(value, quote, self.policy)
            if (
                state == "mismatch"
                and found_in is not None
                and value_around_quote(token_lists[found_in], value, needle) is not None
            ):
                state = "match"
            if found_in is None:
                status: QuoteStatus = "not_found"
                where = preferred
            else:
                status = "found" if found_in == preferred else "moved"
                where = found_in
            occurrences = (
                len(find_all(token_lists[found_in], needle)) if found_in is not None else 0
            )
            return status, where + 1, 1, state, {"span": span, "occurrences": occurrences}

        return self._trace(results, len(documents), [], check)

    def check_pdf(
        self,
        results: Any,
        pdf_paths: list[str | Path],
        *,
        cited_pages: bool = True,
    ) -> tuple[Any, TraceReport]:
        """Check the quotes against the PDF files the extractor read, and box the words.

        Needs PyMuPDF (``pip install gaik[source-tracing]``). A quote is looked for on
        the page the model named, then on the other pages of that file, then in the other
        files, so a wrong page or file number does not make a correct quote "not found".
        Word boxes come from the PDF's own text layer, never from the model. A file that is
        not a PDF, or a PDF without a text layer, is reported as ``no_text_layer``.

        Args:
            results: What the extractor returned: a result dict or a list of them.
            pdf_paths: The files, in the order the extractor was given them (the model counts
                them from 1).
            cited_pages: Set False when the model read text without page marks: its page is
                then a guess, and a quote found on another page is not a wrong page.

        Returns:
            ``(clean, report)`` as in :meth:`check_text`. The report's items carry
            ``rects`` and ``value_rects``, as fractions of the page.
        """
        paths = [Path(path) for path in pdf_paths]
        pages: dict[int, list[list[PageWords]]] = {}
        for number, path in enumerate(paths, start=1):
            if path.suffix.lower() == ".pdf":
                try:
                    pages[number] = read_pages(path)
                except ImportError:
                    raise
                except Exception:
                    pages[number] = []

        def check(
            index: int, paired: bool, field: str, quote: str, document: int, page: int, value: Any
        ) -> _Found:
            state = value_status(value, quote, self.policy)
            extra: dict = {"rects": [], "value_rects": []}
            if paired:
                document = index + 1
            if document not in pages:
                if 1 <= document <= len(paths) or not pages:
                    # A file that is not a PDF (an image), or no PDF at all.
                    return "no_text_layer", document, page, state, extra
                # A document number beyond the files: some models count pages, or invent a
                # number. The quote is looked for in the PDFs, starting with the first.
                document = min(pages)
            needle = tokens(quote)
            # The named page first, then the rest of that file, then the other files.
            order = [(document, page)]
            order += [(document, p) for p in range(1, len(pages[document]) + 1) if p != page]
            order += [
                (d, p) for d, pdf in pages.items() if d != document for p in range(1, len(pdf) + 1)
            ]
            status: QuoteStatus = "not_found"
            at_document, at_page = document, page
            for doc_number, page_number in order:
                readings = pages.get(doc_number, [])
                if not 1 <= page_number <= len(readings):
                    continue
                for reading in readings[page_number - 1]:
                    starts = find_all(reading.tokens, needle)
                    if not starts:
                        continue
                    # The same words may occur several times; the first is boxed and
                    # ``occurrences`` tells the reviewer how many there are.
                    start = starts[0]
                    extra["occurrences"] = len(starts)
                    at_document, at_page = doc_number, page_number
                    status = (
                        "found"
                        if (doc_number, page_number) == (document, page) or not cited_pages
                        else "moved"
                    )
                    extra["rects"] = rects(reading, start, len(needle))
                    span = value_span(reading, start, len(needle), value)
                    if span is not None:
                        extra["value_rects"] = rects(reading, *span)
                    elif state == "mismatch":
                        # A value longer than its quote: it must run through the quote.
                        for other in readings[page_number - 1]:
                            wide = value_around_quote(other.tokens, value, needle)
                            if wide is not None:
                                state = "match"
                                extra["value_rects"] = rects(other, *wide)
                                break
                    break
                if status != "not_found":
                    break
            # A scanned PDF: pages but no words on any of them.
            if (
                status == "not_found"
                and pages[document]
                and not any(r.tokens for readings in pages[document] for r in readings)
            ):
                status = "no_text_layer"
            return status, at_document, at_page, state, extra

        return self._trace(results, len(paths), [path.name for path in paths], check)

    def _trace(
        self, results: Any, document_count: int, names: list[str], check: _Checker
    ) -> tuple[Any, TraceReport]:
        """Take the citations out of the results and check each with ``check``."""
        single = isinstance(results, dict)
        given = [results] if single else list(results)
        # One result per document: each result is about its own document.
        paired = len(given) == document_count > 1
        report = TraceReport(documents=names)
        clean: list[Any] = []
        offset = 0
        for index, result in enumerate(given):
            if not isinstance(result, dict):
                clean.append(result)
                offset += 1
                continue
            data = {key: value for key, value in result.items() if key != SOURCES_FIELD}
            clean.append(data)
            lists = _record_lists(data)
            key = lists[0] if len(lists) == 1 else None
            cited: set[str] = set()
            for entry in _entries(result.get(SOURCES_FIELD)):
                parsed = _parse(entry)
                if parsed is None:
                    continue
                field, quote, document, page = parsed
                value = _bare(value_at(data, field))
                status, at_document, at_page, state, extra = check(
                    index, paired, field, quote, document, page, value
                )
                item = TracedValue(
                    field=field,
                    value=value,
                    quote=quote,
                    document=at_document,
                    page=at_page,
                    cited_page=page,
                    status=status,
                    value_status=state,
                    rects=extra.get("rects", []),
                    value_rects=extra.get("value_rects", []),
                    span=extra.get("span"),
                    occurrences=extra.get("occurrences", 0),
                )
                item.verdict = verdict_of(
                    status, state, value, quote, self.policy, item.occurrences
                )
                if key is None:
                    item.record = offset
                else:
                    inside = re.match(rf"{re.escape(key)}\[(\d+)\]", field)
                    item.record = offset + int(inside.group(1)) if inside else None
                report.items.append(item)
                if value is not None:
                    cited.add(field)
            leaves = set(_leaf_paths(data))
            report.values += len(leaves)
            report.cited += len(leaves & cited)
            offset += len(data[key]) if key else 1
        return (clean[0] if single else clean), report


def transcript_used(result: Any) -> str:
    """The transcript an ``AudioToStructuredData`` result was extracted from.

    The pipeline extracts from the enhanced transcript when there is one, otherwise from the
    raw one, so quotes must be checked against exactly that text.
    """
    transcription = result.transcription
    return getattr(transcription, "enhanced_transcript", None) or transcription.raw_transcript


def _plain(value: Any) -> Any:
    """A citation field as a value, also when verification wrapped it in an envelope."""
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _is_envelope(value: Any) -> bool:
    """A value that ``VisionExtractor(include_verification=True)`` wrapped with its confidence."""
    return isinstance(value, dict) and "value" in value and "confidence_score" in value


def _bare(value: Any) -> Any:
    """The value itself, whether or not verification wrapped it in a confidence envelope."""
    return value["value"] if _is_envelope(value) else value


def _entries(raw: Any) -> list:
    """The citation entries, whether they came as a list or wrapped in an object."""
    if isinstance(raw, dict):
        raw = _plain(raw.get("items"))
    return raw if isinstance(raw, list) else []


def _parse(entry: Any) -> tuple[str, str, int, int] | None:
    """Field, quote, document and page of a citation; None when it is unusable."""
    if not isinstance(entry, dict):
        return None
    field = str(_plain(entry.get("field")) or "").strip()
    quote = str(_plain(entry.get("quote")) or "").strip()
    if not field or not quote:
        return None
    try:
        document = int(_plain(entry.get("document")) or 1)
        page = int(_plain(entry.get("page")) or 1)
    except (TypeError, ValueError):
        document, page = 1, 1
    return field, quote, document, page


def _record_lists(result: dict) -> list[str]:
    """The fields of a result that hold a list of records (as the demos unwrap them)."""
    return [
        key
        for key, value in result.items()
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value)
    ]


def _leaf_paths(value: Any, prefix: str = "") -> Iterator[str]:
    """Paths of the values that could carry a citation: every non-empty scalar or list."""
    if _is_envelope(value):
        value = value["value"]
    if isinstance(value, dict):
        for name, inner in value.items():
            yield from _leaf_paths(inner, f"{prefix}.{name}" if prefix else name)
    elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        for index, item in enumerate(value):
            yield from _leaf_paths(item, f"{prefix}[{index}]")
    elif value not in (None, [], ""):
        yield prefix
