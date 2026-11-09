"""Plain-code matching: finds a quote in a source and compares a value with its quote.

No model is involved. Words are compared with case, punctuation and spacing ignored, and
numbers and dates are compared as numbers and dates, so ``3.000 kg`` matches ``3000`` and
``11.04.2025`` matches ``2025-04-11``.
"""

from __future__ import annotations

import re
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
    """Lowercased words with punctuation and spacing removed."""
    return [token for token in _NON_WORD.sub(" ", text).lower().split() if token]


def find_run(haystack: list[str], needle: list[str]) -> int | None:
    """Index where ``needle`` starts as a contiguous run in ``haystack``."""
    if not needle:
        return None
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start : start + len(needle)] == needle:
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


def _readings_of(number: str) -> list[float]:
    raw = re.sub(r"[\s'’]", "", number)
    candidates: set[str] = set()
    if "," not in raw and "." not in raw:
        candidates.add(raw)
    elif _THOUSANDS.fullmatch(raw):
        # Separators that group thousands can be left out. Any other separator is
        # a decimal point: leaving it out would read 12.5 as 125.
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


def value_status(value: Any, quote: str, policy: TracePolicy = _DEFAULT_POLICY) -> ValueStatus:
    """Whether the extracted value is in the quote, tolerant of number and date formats."""
    if value is None or isinstance(value, bool | dict | list):
        return "unchecked"
    number = as_number(value)
    if number is not None:
        tolerance = policy.number_tolerance
        readings = _numbers_in(quote)
        found = any(abs(reading - number) < tolerance for reading in readings)
        # A sign set apart from its number ("Discount - EUR 1,014.50") reads as positive.
        if not found and number < 0 and re.search(r"[-−–]", quote):
            found = any(abs(reading + number) < tolerance for reading in readings)
        return "match" if found else "mismatch"
    text = str(value)
    parts = date_parts(text)
    if parts is not None:
        quote_parts = [int(p) for p in _DATE_PARTS.findall(quote)]
        quote_parts += [_MONTHS[t[:3]] for t in tokens(quote) if t[:3] in _MONTHS and t.isalpha()]
        expanded = quote_parts + [2000 + p for p in quote_parts if p < 100]
        return "match" if all(part in expanded for part in parts) else "mismatch"
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
    index = 0
    while index <= len(haystack) - len(needle):
        if haystack[index : index + len(needle)] == needle:
            starts.append(index)
            index += len(needle)
        else:
            index += 1
    return starts


def date_run(words: list[str], parts: list[int]) -> tuple[int, int] | None:
    """The shortest run of words that holds every part (year, month, day) of a date."""
    values: list[set[int]] = []
    for word in words:
        if word.isdigit():
            number = int(word)
            values.append({number, number + 2000} if number < 100 else {number})
        elif word.isalpha() and word[:3] in _MONTHS:
            values.append({_MONTHS[word[:3]]})
        else:
            values.append(set())
    for length in range(1, len(words) + 1):
        for start in range(len(words) - length + 1):
            held = set().union(*values[start : start + length])
            if all(part in held for part in parts):
                return start, length
    return None


def locate_in_text(text: str, quote: str) -> tuple[int, int] | None:
    """Where in ``text`` a quote sits, as character offsets, however it is spaced or punctuated.

    Words are compared as in :func:`tokens`, so a quote that the model copied with other
    line breaks, spacing or punctuation is still found.
    """
    words = [(match.group().lower(), match.start(), match.end()) for match in _WORD.finditer(text)]
    needle = tokens(quote)
    at = find_run([word for word, _, _ in words], needle)
    if at is None:
        return None
    return words[at][1], words[at + len(needle) - 1][2]


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
        exact = as_number(value) is not None or (
            isinstance(value, str) and date_parts(value) is not None
        )
        if not exact:
            return "check" if policy.reworded_is_problem else "reworded"
        # A number spelled out in words ("kaksi päivää") cannot be compared with a digit.
        return "check" if re.search(r"\d", quote) else "unchecked"
    return "unchecked"
