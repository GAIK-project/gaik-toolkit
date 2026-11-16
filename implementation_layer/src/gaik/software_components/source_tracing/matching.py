"""Plain-code matching: finds a quote in a source and compares a value with its quote.

No model is involved. Words are compared with case, punctuation and spacing ignored, and
numbers and dates are compared as numbers and dates, so ``3.000 kg`` matches ``3000`` and
``11.04.2025`` matches ``2025-04-11``.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any

from .models import TracePolicy, ValueStatus, Verdict

# Underscores split words too, so a code such as approved_with_remarks reads as words.
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
# A schema code such as ok or not_applicable: the model maps a ticked box or a label to
# it, so it is not printed in the document and cannot be compared with the quote.
_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_NUMBER = re.compile(r"\d(?:[\d\s.,'’]*\d)?")
# Digits grouped in threes by one kind of separator, as thousands are written:
# 3.000 or 1,234,567.
_THOUSANDS = re.compile(r"[1-9]\d{0,2}(?:(?:\.\d{3})+|(?:,\d{3})+)")
_DATE_PARTS = re.compile(r"\d+")
# English month names by their first three letters, for dates such as "October 12, 2025".
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}
_DEFAULT_POLICY = TracePolicy()


def tokens(text: str) -> list[str]:
    """Lowercased words with punctuation and spacing removed.

    The text is put in Unicode NFC form first, so a decomposed ``a`` plus a combining
    diaeresis reads as the same word as a precomposed ``ä``.
    """
    text = unicodedata.normalize("NFC", text)
    return [token for token in _NON_WORD.sub(" ", text).lower().split() if token]


def find_run(haystack: list[str], needle: list[str]) -> int | None:
    """Index where ``needle`` starts as a contiguous run in ``haystack``."""
    if not needle:
        return None
    first, size = needle[0], len(needle)
    for start in range(len(haystack) - size + 1):
        if haystack[start] == first and haystack[start : start + size] == needle:
            return start
    return None


def _numbers_in(text: str) -> list[float]:
    """Every number in the text, read both the European and the American way."""
    readings: list[float] = []
    for match in _NUMBER.finditer(text):
        # A space may group thousands (1 234) or only separate two numbers (010 6061).
        pieces = match.group().split()
        for piece in [match.group(), *pieces] if len(pieces) > 1 else [match.group()]:
            readings += _readings_of(piece)
    return readings


def _signed_numbers_in(text: str) -> list[float]:
    """Like :func:`_numbers_in`, with a minus sign written right before a number kept.

    A dash between two numbers or after a word (10-20, PO-2025) is not a sign.
    """
    readings: list[float] = []
    for match in _NUMBER.finditer(text):
        start = match.start()
        negative = (
            start > 0 and text[start - 1] in "-−–" and (start == 1 or not text[start - 2].isalnum())
        )
        for reading in _numbers_in(match.group()):
            readings.append(-reading if negative else reading)
    return readings


def _readings_of(number: str) -> list[float]:
    raw = re.sub(r"[\s'’]", "", number)
    candidates: set[str] = set()
    separators = {char for char in raw if char in ",."}
    if not separators:
        candidates.add(raw)
    elif len(separators) == 1 and (
        _THOUSANDS.fullmatch(raw) or raw.count(next(iter(separators))) > 1
    ):
        # Separators that group digits can be left out: groups of three (3.000),
        # or one separator used more than once (1,00,000). A single separator
        # before any other number of digits is a decimal point, and leaving it
        # out would read 12.5 as 125.
        candidates.add(raw.replace(",", "").replace(".", ""))
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        group = "." if decimal == "," else ","
        candidates.add(raw.replace(group, "").replace(decimal, "."))
    else:
        for sep in (",", "."):
            if raw.count(sep) == 1:
                candidates.add(raw.replace(sep, "."))
    readings: list[float] = []
    for candidate in candidates:
        try:
            readings.append(float(candidate))
        except ValueError:
            pass
    return readings


def as_number(value: Any) -> float | None:
    """The value as a number when it is one (or a string of digits), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()):
        return float(value)
    return None


def _plausible_date(parts: list[int]) -> bool:
    """Whether three numbers can be a year, a month and a day, in any order."""
    for year in range(3):
        month, day = (parts[i] for i in range(3) if i != year)
        if not (1000 <= parts[year] <= 2999 or parts[year] < 100):
            continue
        # Day and month may come in either order: both fit in 1-31 and one is a month.
        if 1 <= month <= 31 and 1 <= day <= 31 and min(month, day) <= 12:
            return True
    return False


def date_parts(value: str) -> list[int] | None:
    """Year, month and day of a date-like value such as 2025-04-11 or 04/11/2025.

    Three groups of digits with separators are not always a date: a purchase order number
    formatted as 7200-4453-21 is not, and is compared as text instead.
    """
    parts = _DATE_PARTS.findall(value)
    if len(parts) != 3 or not re.fullmatch(r"[\d\s./-]+", value.strip()):
        return None
    numbers = [int(part) for part in parts]
    return numbers if _plausible_date(numbers) else None


_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,4})([./-]|\s)\s*(\d{1,2})\2\s*(\d{1,4})(?!\d)")
_DAY_MONTH_YEAR = re.compile(r"(?<!\d)(\d{1,2})\.?\s+([A-Za-z]{3,})\.?,?\s+(\d{4})(?!\d)")
_MONTH_DAY_YEAR = re.compile(r"\b([A-Za-z]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)")


def _valid(year: int, month: int, day: int) -> tuple[int, int, int] | None:
    if year < 100:
        year += 2000
    if 1000 <= year <= 2999 and 1 <= month <= 12 and 1 <= day <= 31:
        return year, month, day
    return None


def _orders(first: str, second: str, third: str, separator: str) -> set[tuple[int, int, int]]:
    """The (year, month, day) readings of three groups of digits written with ``separator``.

    A four-digit first group is a year (2025-04-11). Otherwise the year comes last, and
    dots mean day first (11.04.2025); a slash, a dash or a space may also mean month
    first (04/11/2025). Only the year may be written with two digits.
    """
    a, b, c = int(first), int(second), int(third)
    if len(first) == 4:
        candidates = [(a, b, c)] if len(third) <= 2 else []
    elif len(third) in (2, 4) and len(second) <= 2:
        candidates = [(c, b, a)] if separator == "." else [(c, b, a), (c, a, b)]
    else:
        candidates = []
    return {date for date in (_valid(*cand) for cand in candidates) if date}


def _date_readings(value: str) -> set[tuple[int, int, int]]:
    """The (year, month, day) readings of a date value such as 2025-04-11 or 04/11/2025."""
    groups = _DATE_PARTS.findall(value)
    if len(groups) != 3:
        return set()
    separator = next((char for char in value.strip() if not char.isdigit()), "-")
    return _orders(*groups, separator)


def _named_month(name: str) -> int | None:
    return _MONTHS.get(name[:3].lower())


def _dates_in(quote: str) -> set[tuple[int, int, int]]:
    """Every (year, month, day) a quote can be read as holding, in the order it is written."""
    dates: set[tuple[int, int, int]] = set()
    for first, separator, second, third in _NUMERIC_DATE.findall(quote):
        dates |= _orders(first, second, third, separator)
    named = [(day, month, year) for day, month, year in _DAY_MONTH_YEAR.findall(quote)]
    named += [(day, month, year) for month, day, year in _MONTH_DAY_YEAR.findall(quote)]
    for day, month, year in named:
        number = _named_month(month)
        date = _valid(int(year), number, int(day)) if number else None
        if date:
            dates.add(date)
    return dates


def value_status(value: Any, quote: str, policy: TracePolicy = _DEFAULT_POLICY) -> ValueStatus:
    """Whether the extracted value is in the quote, tolerant of number and date formats."""
    if value is None or isinstance(value, bool | dict | list):
        return "unchecked"
    number = as_number(value)
    if number is not None:
        tolerance = policy.number_tolerance
        readings = _signed_numbers_in(quote)
        found = any(abs(reading - number) < tolerance for reading in readings)
        # A sign set apart from its number ("Discount - EUR 1,014.50") reads as positive.
        if not found and number < 0 and re.search(r"[-−–]", quote):
            found = any(abs(reading + number) < tolerance for reading in readings)
        return "match" if found else "mismatch"
    text = str(value)
    parts = date_parts(text)
    if parts is not None:
        return "match" if _date_readings(text) & _dates_in(quote) else "mismatch"
    wanted = tokens(text)
    if not wanted:
        return "unchecked"
    if find_run(tokens(quote), wanted) is not None:
        return "match"
    # The same characters with other separators: an identifier the task asked to format
    # (7200-4453-21 for 7200445321). The quote holds the document's own spelling.
    # It must equal whole words of the quote: a prefix of an identifier is another value.
    if policy.match_reformatted_identifiers and _spells(tokens(quote), "".join(wanted)):
        return "match"
    return "unchecked" if _CODE.fullmatch(text) else "mismatch"


def spelling_run(words: list[str], squeezed: str) -> tuple[int, int] | None:
    """Start and length of a run of whole words that, joined without separators, is ``squeezed``."""
    if len(squeezed) < 4:
        return None
    for start in range(len(words)):
        joined = ""
        for length, word in enumerate(words[start:], start=1):
            joined += word
            if joined == squeezed:
                return start, length
            if not squeezed.startswith(joined):
                break
    return None


def _spells(words: list[str], squeezed: str) -> bool:
    """Whether a run of whole words, joined without separators, is exactly ``squeezed``."""
    return spelling_run(words, squeezed) is not None


def find_all(haystack: list[str], needle: list[str]) -> list[int]:
    """Indices where ``needle`` starts as a contiguous run in ``haystack``, without overlaps."""
    starts: list[int] = []
    if not needle:
        return starts
    first, size = needle[0], len(needle)
    index = 0
    while index <= len(haystack) - size:
        if haystack[index] == first and haystack[index : index + size] == needle:
            starts.append(index)
            index += size
        else:
            index += 1
    return starts


def date_run(words: list[str], parts: list[int]) -> tuple[int, int] | None:
    """The shortest run of words that holds a date's year, month and day, one per word.

    ``parts`` are the value's three numbers as :func:`date_parts` gives them. The words
    must hold them in an order a date is written in (year-month-day, day-month-year or
    month-day-year), each from its own word, so 04 11 2025 is not found for 2025-04-04.
    """
    if len(parts) != 3:
        return None
    first, second, third = (str(part) for part in parts)
    if parts[0] >= 1000:
        wanted = {_valid(*parts)} - {None}
    else:
        wanted = _orders(first, second, third, "/")
    items: list[tuple[int, int, bool]] = []  # (word index, number, is a month name)
    for index, word in enumerate(words):
        if word.isdigit():
            items.append((index, int(word), False))
        elif word.isalpha() and word[:3] in _MONTHS:
            items.append((index, _MONTHS[word[:3]], True))
    best: tuple[int, int] | None = None
    for i in range(len(items) - 2):
        (ia, a, ma), (_, b, mb), (ic, c, mc) = items[i : i + 3]
        readings: set[tuple[int, int, int] | None] = set()
        if mb and not ma and not mc:
            readings.add(_valid(c, b, a))  # 12 October 2025
        elif ma and not mb and not mc:
            readings.add(_valid(c, a, b))  # October 12, 2025
        elif not (ma or mb or mc):
            readings |= {_valid(a, b, c), _valid(c, b, a), _valid(c, a, b)}
        if readings & wanted and (best is None or ic - ia + 1 < best[1]):
            best = (ia, ic - ia + 1)
    return best


def locate_in_text(text: str, quote: str) -> tuple[int, int] | None:
    """Where in ``text`` a quote sits, as character offsets, however it is spaced or punctuated.

    Words are compared as in :func:`tokens`, so a quote that the model copied with other
    line breaks, spacing or punctuation is still found.
    """
    spans = _word_spans(text)
    return _locate_in_words(spans, [word for word, _, _ in spans], tokens(quote))


def _word_spans(text: str) -> list[tuple[str, int, int]]:
    """Lowercased words of ``text`` in NFC form, with their offsets in the original text."""
    if unicodedata.is_normalized("NFC", text):
        return [
            (match.group().lower(), match.start(), match.end()) for match in _WORD.finditer(text)
        ]
    # Compose each base character with its combining marks, remembering where it came from.
    pieces: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    index = 0
    while index < len(text):
        end = index + 1
        while end < len(text) and unicodedata.combining(text[end]):
            end += 1
        for char in unicodedata.normalize("NFC", text[index:end]):
            pieces.append(char)
            starts.append(index)
            ends.append(end)
        index = end
    normal = "".join(pieces)
    return [
        (match.group().lower(), starts[match.start()], ends[match.end() - 1])
        for match in _WORD.finditer(normal)
    ]


def _locate_in_words(
    spans: list[tuple[str, int, int]], words: list[str], needle: list[str]
) -> tuple[int, int] | None:
    """:func:`locate_in_text` on a text already split by :func:`_word_spans`.

    ``words`` is the word column of ``spans``; a caller that checks many quotes against
    one text splits it once and passes both.
    """
    at = find_run(words, needle)
    if at is None:
        return None
    return spans[at][1], spans[at + len(needle) - 1][2]


def value_around_quote(haystack: list[str], value: Any, quote: list[str]) -> tuple[int, int] | None:
    """Where a text value sits in the words of a page when it runs through its quote.

    The model is asked for a short quote, so a value that spans several lines (a complete
    description) is never inside it. It is still the document's own text when its words
    follow each other on the page and take in the quote: the quote is then the evidence
    for part of the value. The same words elsewhere on the page are not evidence for it.
    """
    if value is None or isinstance(value, bool | int | float | Decimal | dict | list):
        return None
    wanted = tokens(str(value))
    quoted = find_run(haystack, quote)
    if not wanted or quoted is None:
        return None
    for start in range(len(haystack) - len(wanted) + 1):
        if haystack[start : start + len(wanted)] != wanted:
            continue
        if start < quoted + len(quote) and quoted < start + len(wanted):
            return start, len(wanted)
    return None


def value_at(data: Any, path: str) -> Any:
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


def verdict_of(
    status: str,
    value_state: str,
    value: Any,
    quote: str,
    policy: TracePolicy = _DEFAULT_POLICY,
    occurrences: int = 1,
) -> Verdict:
    """How far a person can trust a value on its quote: verified, check, reworded or unchecked.

    A quote that is not in the source, or that holds another number or date, is a problem. A
    text value that is not in its quote is usually the model's own wording (a translation
    or a summary), so it is only noted, unless the policy asks for verbatim values.
    """
    if status == "no_text_layer":
        return "unchecked"
    if status not in ("found", "moved") or len(tokens(quote)) < policy.min_quote_words:
        return "check"
    if value_state == "match":
        return "check" if policy.ambiguous_quote_is_check and occurrences > 1 else "verified"
    if value_state == "mismatch":
        exact = (
            as_number(value) is not None
            or (isinstance(value, str) and date_parts(value) is not None)
            or _other_digits(value, quote)
        )
        if not exact:
            return "check" if policy.reworded_is_problem else "reworded"
        # A number spelled out in words ("kaksi päivää") cannot be compared with a digit.
        return "check" if re.search(r"\d", quote) else "unchecked"
    return "unchecked"


def _other_digits(value: Any, quote: str) -> bool:
    """Whether a text value holds a number that its quote, which has numbers, does not.

    An identifier or a month and year (PO-2025-15908, 03/2026) with one digit changed is
    another value, not the model's own wording.
    """
    if not isinstance(value, str):
        return False
    quoted = {int(group) for group in _DATE_PARTS.findall(quote)}
    wanted = {int(group) for group in _DATE_PARTS.findall(value)}
    return bool(quoted) and bool(wanted - quoted)
