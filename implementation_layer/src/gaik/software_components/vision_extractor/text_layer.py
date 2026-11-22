"""Check extracted values against a PDF's own text layer.

``confidence_score`` is the model rating its own answer in the same call that
produced it, so a misread value can still come back as 1.0. A value that is
written in the document should also be in the PDF's text layer: this module
looks it up there and reports ``found_in_text``, the ``file`` it is in and the
1-based ``page`` within that file. Each file's pages are numbered on their own,
so a value on the first page of the second PDF is ``page`` 1 of that file.

``found_in_text`` is

- ``True`` when the value is on a page, ignoring case, spacing, punctuation,
  thousands separators, the decimal separator and the order of an ISO date;
- ``False`` when there is a text layer and the value is not on any page. A value
  the model inferred or reworded (a category, a summary) is ``False`` as well:
  it means "not written verbatim", not "wrong";
- ``None`` when nothing could be checked: no PDF with a text layer, or a value
  that is not a string or a number (a boolean, an empty value).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def normalize(text: str) -> str:
    """Lowercased words separated by single spaces, punctuation removed."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(_NON_WORD.sub(" ", text).split())


@dataclass(frozen=True)
class PdfPage:
    """One page of a PDF's text layer."""

    file: str
    """The PDF's file name, without its folder."""
    page: int
    """The 1-based page number within that file."""
    text: str
    """The page's normalised text; ``""`` for a page without text."""


def read_pdf_page_texts(paths: list[Path]) -> list[PdfPage]:
    """Every page of every PDF in ``paths``, numbered within its own file.

    Files that are not PDFs are skipped, and so is a PDF that cannot be read,
    without shifting the page numbers of the others. Returns an empty list when
    no PDF has a text layer.
    """
    try:
        import fitz  # PyMuPDF, part of the vision-extract extra
    except ImportError:
        return []
    pages: list[PdfPage] = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() != ".pdf":
            continue
        try:
            with fitz.open(path) as document:
                texts = [normalize(page.get_text()) for page in document]
        except Exception:  # an unreadable PDF is simply not checked
            continue
        pages.extend(
            PdfPage(file=path.name, page=number, text=text)
            for number, text in enumerate(texts, start=1)
        )
    return pages if any(page.text for page in pages) else []


def read_pdf_pages(paths: list[Path]) -> list[str]:
    """Normalised text of every PDF page, in order; pages without text are ``""``.

    The pages of all files form one list, so a page's position in it is not its
    page number in its file once there is more than one PDF; use
    :func:`read_pdf_page_texts` for that. Returns an empty list when no PDF has a
    text layer.
    """
    return [page.text for page in read_pdf_page_texts(paths)]


def _grouped(digits: str) -> str:
    """1234567 -> 1 234 567 (separators are spaces once normalised)."""
    head = len(digits) % 3 or 3
    groups = [digits[:head]] + [digits[i : i + 3] for i in range(head, len(digits), 3)]
    return " ".join(groups)


def _number_forms(value: int | float | Decimal) -> set[str]:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return set()
    if not number.is_finite():
        return set()
    sign = "-" if number < 0 else ""
    number = abs(number)
    plain = format(number.normalize(), "f")
    candidates = {plain, f"{number:.2f}"}
    if number == number.to_integral_value():
        candidates.add(str(int(number)))
    forms: set[str] = set()
    for candidate in candidates:
        whole, _, fraction = candidate.partition(".")
        for whole_form in {whole, _grouped(whole)}:
            text = f"{whole_form} {fraction}" if fraction else whole_form
            forms.add(f"{sign}{text}".strip())
    return {normalize(form) for form in forms}


def _string_forms(value: str) -> set[str]:
    forms = {normalize(value)}
    if match := _ISO_DATE.match(value.strip()):
        year, month, day = match.groups()
        m, d = int(month), int(day)
        for form in (
            f"{d}.{m}.{year}",
            f"{day}.{month}.{year}",
            f"{m}/{d}/{year}",
            f"{month}/{day}/{year}",
        ):
            forms.add(normalize(form))
    return {form for form in forms if form}


Pages = list[PdfPage] | list[str]


def _find(value: object, pages: Pages) -> tuple[bool | None, PdfPage | None]:
    """``(found_in_text, the page it is on)`` for one extracted value.

    ``pages`` is :func:`read_pdf_page_texts` output, or plain page texts as
    :func:`read_pdf_pages` gives them, which are numbered by their position.
    """
    if not pages or value is None or isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float, Decimal)):
        forms = _number_forms(value)
    elif isinstance(value, str):
        forms = _string_forms(value)
    else:
        return None, None
    if not forms:
        return None, None
    for position, page in enumerate(pages, start=1):
        if not isinstance(page, PdfPage):
            page = PdfPage(file="", page=position, text=page)
        padded = f" {page.text} "
        if any(f" {form} " in padded for form in forms):
            return True, page
    return False, None


def locate(value: object, pages: Pages) -> tuple[bool | None, int | None]:
    """``(found_in_text, page)`` for one extracted value; ``page`` is within its file."""
    found, page = _find(value, pages)
    return found, page.page if page else None


def annotate(data: dict, verification: dict, pages: Pages) -> dict:
    """Add ``found_in_text``, ``file`` and ``page`` to each field's verification entry.

    ``data`` holds the plain extracted values and ``verification`` the matching
    ``{confidence_score, confidence_reason}`` entries, rows of a list field as
    lists. ``file`` and ``page`` name the PDF the value was found in and the
    1-based page within it; both are ``None`` when it was not found, and ``file``
    is ``None`` too when ``pages`` are plain texts without their file. Returns
    ``verification`` with the three keys added.
    """
    result: dict = {}
    for field, entry in verification.items():
        value = data.get(field)
        if isinstance(entry, list):
            rows = value if isinstance(value, list) else []
            result[field] = [
                annotate(rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}, row, pages)
                if isinstance(row, dict)
                else row
                for i, row in enumerate(entry)
            ]
        elif isinstance(entry, dict):
            found, page = _find(value, pages)
            result[field] = {
                **entry,
                "found_in_text": found,
                "file": (page.file or None) if page else None,
                "page": page.page if page else None,
            }
        else:
            result[field] = entry
    return result
