"""Source citations for the Vision Extractor demo: where each value was read.

The model is asked for one citation per value: the document, the page and a short
verbatim quote. It is never asked for coordinates, because a vision model cannot give
reliable ones. Everything after that is plain code against the PDF's own text layer:

1. The quote is looked for on the page the model named, then on the other pages.
   Case, spacing and punctuation are ignored; otherwise the words must appear in order.
2. The words that matched give the box, from the positions the PDF stores for them.
3. The extracted value is looked for inside the quote, with numbers and dates compared
   as numbers and dates, so ``3.000 kg`` matches ``3000`` and ``11.04.2025`` matches
   ``2025-04-11``. A quote that is found but does not hold the value is flagged too.

An image has no text layer, so its citations cannot be checked and are shown as such.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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

# Pages rendered for the viewer: enough for any demo document, small enough to send.
MAX_RENDERED_PAGES = 12
RENDER_DPI = 110

# Underscores split words too, so a code such as approved_with_remarks reads as words.
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
# A schema code such as ok or not_applicable: the model maps a ticked box or a label to
# it, so it is not printed in the document and cannot be compared with the quote.
_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_NUMBER = re.compile(r"\d(?:[\d\s.,'’]*\d)?")
_DATE_PARTS = re.compile(r"\d+")
# English month names by their first three letters, for dates such as "October 12, 2025".
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}


class Source(BaseModel):
    """One citation, as the model returns it."""

    field: str = Field(description="Path of the value, e.g. total or items[0].quantity")
    document: int = Field(description="1-based number of the attached file")
    page: int = Field(description="1-based page in that file")
    quote: str = Field(description="Short verbatim snippet of the document holding the value")


def with_sources(model: type[BaseModel]) -> type[BaseModel]:
    """The extraction model with a list of citations next to its own fields."""
    return create_model(
        model.__name__,
        __base__=model,
        **{
            SOURCES_FIELD: (
                list[Source],
                Field(
                    default_factory=list,
                    description="Where each extracted value was read: one entry per value.",
                ),
            )
        },
    )


def tokens(text: str) -> list[str]:
    """Lowercased words with punctuation and spacing removed."""
    return [token for token in _NON_WORD.sub(" ", text).lower().split() if token]


def _numbers_in(text: str) -> list[float]:
    """Every number in the text, read both the European and the American way."""
    readings: list[float] = []
    for match in _NUMBER.finditer(text):
        raw = re.sub(r"[\s'’]", "", match.group())
        candidates = {raw.replace(",", "").replace(".", "")}
        if "," in raw and "." in raw:
            decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
            group = "." if decimal == "," else ","
            candidates.add(raw.replace(group, "").replace(decimal, "."))
        else:
            for sep in (",", "."):
                if raw.count(sep) == 1:
                    candidates.add(raw.replace(sep, "."))
        for candidate in candidates:
            try:
                readings.append(float(candidate))
            except ValueError:
                pass
    return readings


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()):
        return float(value)
    return None


def _date_parts(value: str) -> list[int] | None:
    """Year, month and day of a date-like value such as 2025-04-11 or 04/11/2025."""
    parts = _DATE_PARTS.findall(value)
    if len(parts) != 3 or not re.fullmatch(r"[\d\s./-]+", value.strip()):
        return None
    return [int(part) for part in parts]


ValueStatus = Literal["match", "mismatch", "unchecked"]


def value_status(value: Any, quote: str) -> ValueStatus:
    """Whether the extracted value is in the quote, tolerant of number and date formats."""
    if value is None or isinstance(value, bool | dict | list):
        return "unchecked"
    number = _as_number(value)
    if number is not None:
        found = any(abs(reading - number) < 1e-6 for reading in _numbers_in(quote))
        return "match" if found else "mismatch"
    text = str(value)
    parts = _date_parts(text)
    if parts is not None:
        quote_parts = [int(p) for p in _DATE_PARTS.findall(quote)]
        quote_parts += [_MONTHS[t[:3]] for t in tokens(quote) if t[:3] in _MONTHS and t.isalpha()]
        expanded = quote_parts + [2000 + p for p in quote_parts if p < 100]
        return "match" if all(part in expanded for part in parts) else "mismatch"
    wanted = tokens(text)
    if not wanted:
        return "unchecked"
    if _find(tokens(quote), wanted) is not None:
        return "match"
    return "unchecked" if _CODE.fullmatch(text) else "mismatch"


def _find(haystack: list[str], needle: list[str]) -> int | None:
    """Index where ``needle`` starts as a contiguous run in ``haystack``."""
    if not needle:
        return None
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start : start + len(needle)] == needle:
            return start
    return None


@dataclass
class _Page:
    width: float
    height: float
    # One entry per token: the box of the word it came from.
    tokens: list[str]
    boxes: list[tuple[float, float, float, float]]


def _read_pages(pdf_bytes: bytes) -> list[list[_Page]]:
    """Each page's words, in two reading orders.

    The order the PDF stores its text and the order on the page (top to bottom, left
    to right) disagree in tables whose cells wrap: one of them reads a row as a row.
    A quote only has to be found in one.
    """
    import fitz  # PyMuPDF

    pages: list[list[_Page]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            readings: list[_Page] = []
            for sort in (False, True):
                words: list[str] = []
                boxes: list[tuple[float, float, float, float]] = []
                for x0, y0, x1, y1, word, *_ in page.get_text("words", sort=sort):
                    for token in tokens(word):
                        words.append(token)
                        boxes.append((x0, y0, x1, y1))
                readings.append(_Page(page.rect.width, page.rect.height, words, boxes))
            pages.append(readings)
    return pages


def _rects(page: _Page, start: int, length: int) -> list[dict]:
    """Boxes of the matched words, as fractions of the page, one per word."""
    seen: list[tuple[float, float, float, float]] = []
    for box in page.boxes[start : start + length]:
        if box not in seen:
            seen.append(box)
    return [
        {
            "x": x0 / page.width,
            "y": y0 / page.height,
            "w": (x1 - x0) / page.width,
            "h": (y1 - y0) / page.height,
        }
        for x0, y0, x1, y1 in seen
    ]


def _value_span(page: _Page, start: int, length: int, value: Any) -> tuple[int, int] | None:
    """Where the value sits inside the matched quote, in page tokens."""
    window = page.tokens[start : start + length]
    if _as_number(value) is not None:
        for index, token in enumerate(window):
            if value_status(value, token) == "match":
                return start + index, 1
        return None
    wanted = tokens(str(value))
    offset = _find(window, wanted)
    if offset is None or len(wanted) >= length:
        return None
    return start + offset, len(wanted)


def value_at(data: dict, path: str) -> Any:
    """The value at a path such as ``items[2].quantity``; None when there is none."""
    current: Any = data
    for name, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
        if name:
            current = current.get(name) if isinstance(current, dict) else None
        else:
            position = int(index)
            current = (
                current[position] if isinstance(current, list) and position < len(current) else None
            )
        if current is None:
            return None
    return current


def _plain(value: Any) -> Any:
    """A citation field as a value, also when verification wrapped it in an envelope."""
    return value.get("value") if isinstance(value, dict) and "value" in value else value


@dataclass
class UploadedDocument:
    name: str
    path: Path


def check_sources(raw: Any, data: dict, documents: list[UploadedDocument]) -> dict:
    """Verify the model's citations and lay out what the viewer needs to show them."""
    pdf_pages: dict[int, list[list[_Page]]] = {}
    for number, document in enumerate(documents, start=1):
        if document.path.suffix.lower() == ".pdf":
            try:
                pdf_pages[number] = _read_pages(document.path.read_bytes())
            except Exception:
                pdf_pages[number] = []

    checked: list[dict] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        field = str(_plain(entry.get("field")) or "").strip()
        quote = str(_plain(entry.get("quote")) or "").strip()
        if not field or not quote:
            continue
        try:
            document = int(_plain(entry.get("document")) or 1)
            page = int(_plain(entry.get("page")) or 1)
        except (TypeError, ValueError):
            document, page = 1, 1
        value = value_at(data, field)
        result = {
            "field": field,
            "document": document,
            "page": page,
            "cited_page": page,
            "quote": quote,
            "value": value,
            "status": "not_found",
            "value_status": value_status(value, quote),
            "rects": [],
            "value_rects": [],
        }
        if document not in pdf_pages:
            result["status"] = "no_text_layer"
            checked.append(result)
            continue

        needle = tokens(quote)
        # The named page first, then the rest of that file, then the other files.
        order = [(document, page)]
        order += [(document, p) for p in range(1, len(pdf_pages[document]) + 1) if p != page]
        order += [
            (d, p)
            for d, pages in pdf_pages.items()
            if d != document
            for p in range(1, len(pages) + 1)
        ]
        for doc_number, page_number in order:
            pages = pdf_pages.get(doc_number, [])
            if not 1 <= page_number <= len(pages):
                continue
            for target in pages[page_number - 1]:
                start = _find(target.tokens, needle)
                if start is None:
                    continue
                result.update(
                    document=doc_number,
                    page=page_number,
                    status="found" if (doc_number, page_number) == (document, page) else "moved",
                    rects=_rects(target, start, len(needle)),
                )
                span = _value_span(target, start, len(needle), value)
                if span is not None:
                    result["value_rects"] = _rects(target, *span)
                break
            if result["status"] != "not_found":
                break
        # A scanned PDF: pages but no words on any of them.
        if (
            result["status"] == "not_found"
            and pdf_pages[document]
            and not any(r.tokens for readings in pdf_pages[document] for r in readings)
        ):
            result["status"] = "no_text_layer"
        checked.append(result)

    return {
        "sources": checked,
        "pages": _render_pages(documents, checked),
        "documents": [document.name for document in documents],
    }


def _render_pages(documents: list[UploadedDocument], sources: list[dict]) -> dict[str, dict]:
    """The cited PDF pages as images, keyed ``"<document>:<page>"``."""
    import fitz  # PyMuPDF

    wanted: list[tuple[int, int]] = []
    for source in sources:
        key = (source["document"], source["page"])
        if key not in wanted:
            wanted.append(key)
    rendered: dict[str, dict] = {}
    for document, page in wanted[:MAX_RENDERED_PAGES]:
        if not 1 <= document <= len(documents):
            continue
        path = documents[document - 1].path
        if path.suffix.lower() != ".pdf":
            continue
        try:
            with fitz.open(path) as doc:
                if not 1 <= page <= len(doc):
                    continue
                pixmap = doc[page - 1].get_pixmap(dpi=RENDER_DPI)
                image = base64.b64encode(pixmap.tobytes("jpeg", jpg_quality=80)).decode()
                rendered[f"{document}:{page}"] = {
                    "image": f"data:image/jpeg;base64,{image}",
                    "width": pixmap.width,
                    "height": pixmap.height,
                }
        except Exception:
            continue
    return rendered
