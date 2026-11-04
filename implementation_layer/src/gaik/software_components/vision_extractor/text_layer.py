"""Check extracted values against a PDF's own text layer.

``confidence_score`` is the model rating its own answer in the same call that
produced it, so a misread value can still come back as 1.0. A value that is
written in the document should also be in the PDF's text layer: this module
looks it up there and reports ``found_in_text`` and the 1-based ``page``.

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
from decimal import Decimal, InvalidOperation
from pathlib import Path

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def normalize(text: str) -> str:
    """Lowercased words separated by single spaces, punctuation removed."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(_NON_WORD.sub(" ", text).split())


def read_pdf_pages(paths: list[Path]) -> list[str]:
    """Normalised text of every PDF page, in order; pages without text are ``""``.

    Returns an empty list when no PDF has a text layer.
    """
    try:
        import fitz  # PyMuPDF, part of the vision-extract extra
    except ImportError:
        return []
    pages: list[str] = []
    for path in paths:
        if path.suffix.lower() != ".pdf":
            continue
        try:
            with fitz.open(path) as document:
                pages.extend(normalize(page.get_text()) for page in document)
        except Exception:  # an unreadable PDF is simply not checked
            continue
    return pages if any(pages) else []


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


def locate(value: object, pages: list[str]) -> tuple[bool | None, int | None]:
    """``(found_in_text, page)`` for one extracted value."""
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
    for number, page in enumerate(pages, start=1):
        padded = f" {page} "
        if any(f" {form} " in padded for form in forms):
            return True, number
    return False, None


def annotate(data: dict, verification: dict, pages: list[str]) -> dict:
    """Add ``found_in_text`` and ``page`` to each field's verification entry.

    ``data`` holds the plain extracted values and ``verification`` the matching
    ``{confidence_score, confidence_reason}`` entries, rows of a list field as
    lists. Returns ``verification`` with the two keys added.
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
            found, page = locate(value, pages)
            result[field] = {**entry, "found_in_text": found, "page": page}
        else:
            result[field] = entry
    return result
