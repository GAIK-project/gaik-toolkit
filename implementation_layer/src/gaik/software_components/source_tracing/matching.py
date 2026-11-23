"""Plain-code matching: finds a quote in a source and compares a value with its quote.

No model is involved. Words are compared with case, punctuation and spacing ignored, and
numbers and dates are compared as numbers and dates, so ``3.000 kg`` matches ``3000`` and
``11.04.2025`` matches ``2025-04-11``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from .._ligatures import expand_ligatures
from ..source_material import _unescape_closing_tags
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
# Finnish month names by their stem and "kuu", in any case form: maaliskuu, maaliskuuta,
# marraskuun, kesäkuussa. Read before the English prefixes, which take marraskuu for March.
_FINNISH_MONTHS = {
    stem: number
    for number, stem in enumerate(
        (
            "tammi", "helmi", "maalis", "huhti", "touko", "kesä",
            "heinä", "elo", "syys", "loka", "marras", "joulu",
        ),
        start=1,
    )
}  # fmt: skip
_FINNISH_MONTH = re.compile(rf"({'|'.join(_FINNISH_MONTHS)})kuu", re.IGNORECASE)
_MINUS = "-\u2212\u2013"  # hyphen-minus, minus sign, en dash
_LIGATURE = re.compile("[\ufb00-\ufb06]")  # the ones _ligatures expands
# A minus set apart from the number after it, with a currency between them or not.
_MINUS_APART = re.compile(rf"([{_MINUS}])\s*(?:[A-Za-z]{{3}}\s*|[\u20ac$\u00a3]\s*)?$")
# A minus written against the digits, or against a currency written against them.
_MINUS_AGAINST = re.compile(rf"([{_MINUS}])(?:[\u20ac$\u00a3]\s*|[A-Z]{{3}}\s+)?$")
# A minus right after a number (250,00-), not one that joins it to another (10-20), or CR.
_TRAILING_MINUS = re.compile(rf"(?:[{_MINUS}](?![\d\w])|\s*CR\b)")
# A clock time after "klo" or "kello": 10.00, 9:30.
_CLOCK = re.compile(
    r"\b(?:klo|kello|kl)\.?\s*(\d{1,2})[.:](\d{2})\b", re.IGNORECASE
)  # The parts of a date in a text: runs of digits, and words, of which month names count.
_DATE_ITEM = re.compile(r"\d+|[^\W\d_]+")
_DASHES = "\\-\u2010\u2011\u2012\u2013\u2014"
# What stands between the numbers of a date written in numbers: 11.04.2025, 11/4 2025,
# 2025-04-11, 11/04/'25, 2025年4月11日, 2025년 4월 11일.
_NUMERIC_GAP = re.compile(rf"[\s./'’{_DASHES}年月년월]*")
_DAY_MONTH_GAP = re.compile(r"[\s./]*")
# A comma may also stand before a four-digit year at the end (11/04, 2025) or after one at
# the start (2025, 04 11).
_YEAR_GAP = re.compile(rf"[\s.,/'’{_DASHES}]*")
# What stands between the parts of a date with a month name: 11th of April, April 11, 2025,
# 11-Apr-2025, the 11th day of April, 11 April (2025).
# Only a hyphen joins its parts (11-Apr-2025): an en dash joins a range, so in
# "25. maaliskuuta – 25. huhtikuuta" the second 25 is no year.
_NAMED_GAP = re.compile(
    r"(?:st|nd|rd|th)?(?:[\s.,/'’()\[\]\-‐‑]|of|the|day|päivänä)*", re.IGNORECASE
)
# An ordinal suffix right after a day's digits: 11th, 2nd.
_ORDINAL = re.compile(r"(?:st|nd|rd|th)(?![^\W\d_])", re.IGNORECASE)
# What joins the days of a range or a list: 11.–15.4.2025, 9., 11. ja 15.4.2025, 11 to 15
# April, 11th–15th April, 11/12 April. A day's ordinal suffix may come first.
_LINK = re.compile(
    rf"(?:st|nd|rd|th)?(?:[\s.,&/{_DASHES}]|and|ja|och|und|et|to|until|till|through|bis)+",
    re.IGNORECASE,
)
_LINK_MARK = re.compile(rf"[,&/{_DASHES}]|[^\W\d_]")
# A dash or a word joins two days wherever it stands; a comma, "&" or "/" only lists days
# next to a month name, or after a day written with a dot.
_RANGE_MARK = re.compile(rf"[{_DASHES}]|to|until|till|through|bis|and|ja|och|und|et", re.IGNORECASE)
_DASH_ONLY = re.compile(rf"[\s.]*[{_DASHES}][\s.]*")
_HYPHEN_ONLY = re.compile(r"\s*[-‐‑]\s*")
_LINK_WORD = re.compile(r"[^\W\d_]")
_ORDINAL_START = re.compile(r"^(?:st|nd|rd|th)", re.IGNORECASE)
_DEFAULT_POLICY = TracePolicy()


def _nfc(text: str) -> str:
    """``text`` in NFC form: a letter with its accent as one character, as most text has it."""
    return text if unicodedata.is_normalized("NFC", text) else unicodedata.normalize("NFC", text)


def tokens(text: str) -> list[str]:
    """Lowercased words with punctuation and spacing removed.

    The text is put in NFC form first, so ``ä`` written as ``a`` and a combining mark (as
    some PDFs and macOS file systems store it) is the same word as ``ä`` written as one
    character.
    """
    text = expand_ligatures(_nfc(text))
    return [token for token in _NON_WORD.sub(" ", text).lower().split() if token]


def quote_needles(quote: str) -> list[list[str]]:
    """The words to look for in the source for a quote, most literal first.

    A closing ``source_material`` tag written in the source reaches the extractor's model
    with its bracket escaped (``&lt;/source_material``). A quote of that passage holds the
    escape, which the source does not: the second reading has the escape put back. Only an
    escape in front of that closing tag is put back, so any other ``&lt;`` stays a word.
    """
    needles = [tokens(quote)]
    unescaped = _unescape_closing_tags(quote)
    if unescaped != quote:
        needles.append(tokens(unescaped))
    return needles


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
    return [reading for group in _number_groups(text) for reading in group]


def _number_groups(text: str) -> list[list[float]]:
    """The readings of each number in the text, one list per number as written.

    A minus sign written against the digits (``-250,00``, ``(−5)``) makes the number
    negative. A dash after a letter or a digit joins two words or numbers instead
    (``PO-2025``, ``10-20``), and one set apart by a space (``- EUR 250``) is left to the
    caller.
    """
    groups: list[list[float]] = []
    for match in _NUMBER.finditer(text):
        sign = -1.0 if _signed(text, match.start()) else 1.0
        # A space may group thousands (1 234) or only separate two numbers (010 6061).
        pieces = match.group().split()
        readings = [sign * reading for reading in _readings_of(match.group())]
        if len(pieces) > 1:
            readings += [sign * reading for reading in _readings_of(pieces[0])]
            if sign > 0:
                # -1 250,00 is one negative number: its last group is not a 250 of its own.
                for piece in pieces[1:]:
                    readings += _readings_of(piece)
        groups.append(readings)
    return groups


def _negatives_in(text: str) -> list[float]:
    """The readings (without their sign) of the numbers written negative in another way than
    a minus against the digits: a minus set apart before it, perhaps with a currency
    (``- EUR 250``, ``– 250``), brackets around it (``(250.00)``), a minus right after it
    (``250,00-``) or ``CR`` after it."""
    readings: list[float] = []
    for match in _NUMBER.finditer(text):
        before, after = text[: match.start()], text[match.end() :]
        apart = _MINUS_APART.search(before)
        if (
            (apart and _minus_stands_alone(before[: apart.start(1)]))
            or (before.endswith("(") and after.startswith(")"))
            or _TRAILING_MINUS.match(after)
        ):
            readings += [abs(reading) for reading in _readings_of(match.group())]
    return readings


def _signed(text: str, start: int) -> bool:
    """Whether the number starting at ``start`` has a minus sign written against it, or
    against its currency (-250, (−5), -€250.00, -EUR 250)."""
    sign = _MINUS_AGAINST.search(text[:start])
    if not sign:
        return False
    before = text[: sign.start(1)]
    return _minus_stands_alone(before) and (before[-1:] in "([{:=;" or not before[-1:].strip())


def _minus_stands_alone(before: str) -> bool:
    """Whether a minus after ``before`` is a sign, not a dash joining two words or numbers:
    not written against a letter or a digit (PO-2025, 10-20), and not after a number and a
    space (Sivut 10 - 250, Ikä 10 -20 v)."""
    return not before[-1:].isalnum() and not before.rstrip()[-1:].isdigit()


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


# A date read from a text: year, the number of digits the year was written with, month, day.
_Date = tuple[int, int, int, int]
# A part of a date in a text: the digits as written (a number) or the month (a month name).
_Item = tuple[str | None, int | None]


def _date_items(text: str) -> tuple[list[_Item], list[str], list[bool]]:
    """The numbers and month names of ``text`` in order, the text between each two, and for
    each part whether it is a number with an ordinal suffix (11th)."""
    items: list[_Item] = []
    gaps: list[str] = []
    ordinals: list[bool] = []
    end: int | None = None
    for match in _DATE_ITEM.finditer(_nfc(text)):
        word = match.group()
        finnish = _FINNISH_MONTH.match(word)
        if word[0].isdigit():
            item: _Item = (word, None)
        elif finnish:
            item = (None, _FINNISH_MONTHS[finnish.group(1).lower()])
        elif len(word) >= 3 and word[:3].lower() in _MONTHS:
            item = (None, _MONTHS[word[:3].lower()])
        else:
            continue  # another word is part of the text between two parts
        if end is not None:
            gaps.append(match.string[end : match.start()])
        items.append(item)
        ordinals.append(item[0] is not None and bool(_ORDINAL.match(match.string, match.end())))
        end = match.end()
    return items, gaps, ordinals


def _year(digits: str) -> tuple[int, int] | None:
    """A year and the number of digits it was written with: four, or two (``'25``, ``05``)."""
    if len(digits) == 4 and 1000 <= int(digits) <= 2999:
        return int(digits), 4
    return (int(digits), 2) if len(digits) == 2 else None


def _small(digits: str, highest: int) -> int | None:
    """A day (``highest`` 31) or a month (12) written with one or two digits."""
    if 1 <= len(digits) <= 2 and 1 <= int(digits) <= highest:
        return int(digits)
    return None


def _dates_of_three(
    items: list[_Item], gaps: list[str], ordinals: Sequence[bool] = (False, False, False)
) -> set[_Date]:
    """The dates that three parts, in the order written, can be.

    Numbers alone are read year-month-day, day-month-year or month-day-year. Dates joined
    by dots are read day first (11.04.2025 is 11 April), or year first when the year has
    four digits (2025.04.11); 11.04.25 is not 2011-04-25. With a month name between the
    numbers, they are the day and the year in either order (11 April 2025, 2025 April 11);
    with the name first, the day comes next (April 11, 2025) or after the year and a comma
    (April 2025, 11th). A name after both numbers is no date: in "1. maaliskuuta 2025 2
    kpl" the count is no day.
    """
    named = [index for index, (_, month) in enumerate(items) if month is not None]
    dates: set[_Date] = set()
    if not named:
        first, second, third = (digits or "" for digits, _ in items)
        if not (
            (_NUMERIC_GAP.fullmatch(gaps[0]) or (len(first) == 4 and _YEAR_GAP.fullmatch(gaps[0])))
            and (
                _NUMERIC_GAP.fullmatch(gaps[1])
                or (len(third) == 4 and _YEAR_GAP.fullmatch(gaps[1]))
            )
        ):
            return dates
        dots = all(re.sub(r"[\s'’]", "", gap) == "." for gap in gaps)
        orders = [(third, second, first)]
        if not dots or len(first) == 4:
            orders.append((first, second, third))
        if not dots:
            orders.append((third, first, second))
        for year_digits, month_digits, day_digits in orders:
            year = _year(year_digits)
            month = _small(month_digits, 12)
            day = _small(day_digits, 31)
            if year and month and day:
                dates.add((*year, month, day))
        return dates
    if len(named) != 1 or not all(_NAMED_GAP.fullmatch(gap) for gap in gaps):
        return dates
    month = items[named[0]][1] or 0
    first, second = (items[index][0] or "" for index in range(3) if index != named[0])
    if named[0] == 1:
        pairs = [(first, second), (second, first)]
    elif named[0] == 0:
        # April 2025, 11th: the day after the year only with a comma and its suffix, not
        # the count in "huhtikuuta 2019, 12 kpl".
        late_day = "," in gaps[1] and ordinals[2]
        pairs = [(first, second), *([(second, first)] if late_day else [])]
    else:
        pairs = []
    for day_digits, year_digits in pairs:
        year = _year(year_digits)
        day = _small(day_digits, 31)
        if year and day:
            dates.add((*year, month, day))
    return dates


def _same_date(a: _Date, b: _Date) -> bool:
    """Whether two dates are one: a year written with two digits is that year's last two."""
    if a[2:] != b[2:]:
        return False
    (year_a, digits_a), (year_b, digits_b) = a[:2], b[:2]
    if digits_a == digits_b:
        return year_a == year_b
    full, short = (year_a, year_b) if digits_a == 4 else (year_b, year_a)
    return 1900 <= full <= 2099 and full % 100 == short


def _range_part(items: list[_Item], gaps: list[str], start: int, size: int) -> bool:
    """Whether ``size`` parts from ``start`` can be one end of a range: a day (11.), or a
    day and a month (11.4., 11 April, April 11)."""
    part = items[start : start + size]
    if any(digits is not None and _small(digits, 31) is None for digits, _ in part):
        return False
    if size == 1:
        return part[0][0] is not None
    (_, first_month), (_, second_month) = part
    if first_month is not None and second_month is not None:
        return False
    gap = gaps[start]
    if first_month is None and second_month is None:
        # 11.4. or 11/4: a day and a month written with a dot or a slash. Not 11.–15. (a
        # range of days), and not the number before a date (Vk 16 14.–18.4., Q2 11.–15.4.),
        # which a space parts from it or whose next number is no month (Klo 9.30 10.–24.4.).
        return (
            bool(_DAY_MONTH_GAP.fullmatch(gap))
            and ("." in gap or "/" in gap)
            and _small(part[1][0] or "", 12) is not None
        )
    return bool(_NAMED_GAP.fullmatch(gap))


def _mirrors(a: _Item, b: _Item) -> bool:
    """Whether two parts play the same role at the two ends of a range: both numbers, both
    month names, or a month name and a month in numbers (11 Apr – 15.4.2025)."""
    if (a[1] is None) == (b[1] is None):
        return True
    digits = a[0] if b[1] is not None else b[0]
    return _small(digits or "", 12) is not None


def _mixed_ends(items: list[_Item], start: int, after: int, link: str) -> bool:
    """Whether two ends of two parts, one with a month name and one in numbers only, can be
    one range: the name stands where the other end has its month (11 Apr – 15.4.2025, not
    10.4. ja April 11), and an end in numbers before the name is closed by its dot
    (11.04. – 15 April, not 1. 10–30 July)."""
    first, second = items[start : start + 2], items[after : after + 2]
    first_numbers = all(month is None for _, month in first)
    named = second if first_numbers else first
    if named[0][1] is not None or named[1][1] is None:
        return False
    return not first_numbers or link.lstrip().startswith(".")


def _link_kind(gap: str, loose: bool) -> str | None:
    """How ``gap`` joins two ends of a range or a list: ``dash``, ``word``, ``range``,
    ``slash``, ``list`` or None.

    ``loose`` reads words whose punctuation is gone (a PDF's), where any space can have
    been a dash.
    """
    if not _LINK.fullmatch(gap):
        return None
    if loose:
        return "range"
    gap = _ORDINAL_START.sub("", gap)  # 11th–15th: the suffix belongs to the day
    if _DASH_ONLY.fullmatch(gap):
        return "dash"
    if _LINK_WORD.search(gap):
        return "word"
    if _RANGE_MARK.search(gap):
        return "range"
    if not _LINK_MARK.search(gap):
        return None  # spacing and dots only
    if gap.lstrip().startswith("."):
        return "range"  # after a day written with a dot: 9., 11., 15.4.2025; 11.4./12.4.
    return "slash" if "/" in gap else "list"


def _chains(items: list[_Item], gaps: list[str], loose: bool) -> list[tuple[int, list[int]]]:
    """Ranges and lists of days or of dates that share the rest of a date.

    ``11.–15.4.2025`` is two days, ``11.4.–15.4.2025`` two days with their months, and
    ``9., 11. ja 15.4.2025`` three days; each shares the year (and the month) written after
    the last one. Each chain is the number of parts per end and the index of each end.
    """
    chains: list[tuple[int, list[int]]] = []
    covered: set[int] = set()
    count = len(items)
    for size in (2, 1):

        def kind_after(start: int, size: int = size) -> str | None:
            """How the end at ``start`` is joined to the next one, if it is."""
            after = start + size
            if after + size > count or covered.intersection(range(start, after + size)):
                return None
            if not (
                _range_part(items, gaps, start, size) and _range_part(items, gaps, after, size)
            ):
                return None
            if not all(
                _mirrors(a, b) for a, b in zip(items[start:after], items[after : after + size])
            ):
                return None
            if size == 2:
                first = [month is None for _, month in items[start:after]]
                second = [month is None for _, month in items[after : after + size]]
                if all(first) and all(second) and gaps[start] != gaps[after]:
                    return None  # 11.4.–15.4. is written alike at both ends; 1. 8.–10.10. not
                if all(first) != all(second) and not _mixed_ends(
                    items, start, after, gaps[after - 1]
                ):
                    return None
            return _link_kind(gaps[after - 1], loose)

        index = 0
        while index < count:
            kind = kind_after(index)
            if kind is None:
                index += 1
                continue
            ends, kinds = [index], []
            while kind is not None:
                kinds.append(kind)
                ends.append(ends[-1] + size)
                kind = kind_after(ends[-1])
            index = ends[-1] + size
            for part in _chain_parts(items, gaps, size, ends, kinds):
                chains.append((size, part))
                if size == 2 and not loose:
                    # Read loosely (no punctuation), 9 11 15 4 may be days or days and months.
                    covered.update(range(part[0], part[-1] + size))
    return chains


def _chain_parts(
    items: list[_Item], gaps: list[str], size: int, ends: list[int], kinds: list[str]
) -> list[list[int]]:
    """The ranges and lists in a run of joined ends.

    A bare comma or ``&`` lists days only in a list that also has a word (11, 12 and
    15.4.2025; 9, 11 and 15 April), or between dates that have a month name (11 April, 15 May
    2025): elsewhere it parts the run (``Qty 1, 09.01.98`` and ``Erä 3, 1. elokuuta`` list
    nothing). A ``/`` lists days next to a month name (11/12 April). A dash joins days
    (11-15.4.2025, 11.–15.4.2025) unless the same hyphen also stands just before or just
    after the run: in 2025-04-11 and 09-01-98 the hyphens part a date.
    """
    count = len(items)
    if size == 1:
        named = (ends[0] > 0 and items[ends[0] - 1][1] is not None) or (
            ends[-1] + size < count and items[ends[-1] + size][1] is not None
        )
    else:
        named = any(month is not None for _, month in items[ends[0] : ends[0] + size])
    listed = "word" in kinds or (size == 2 and named)
    after = ends[-1] + size
    # Only a hyphen parts a date (2025-04-11, 09-01-98); an en dash joins a range.
    edges = {
        gap
        for gap in (
            gaps[ends[0] - 1] if ends[0] > 0 else "",
            gaps[after - 1] if after < count else "",
        )
        if gap and _HYPHEN_ONLY.fullmatch(gap)
    }
    parts: list[list[int]] = [[ends[0]]]
    for right, kind in zip(ends[1:], kinds):
        if (
            (kind == "list" and not listed)
            or (kind == "slash" and not named)
            or (kind == "dash" and gaps[right - 1] in edges)
        ):
            parts.append([right])
            continue
        parts[-1].append(right)
    return [part for part in parts if len(part) > 1]


def _dates_with_places(
    items: list[_Item],
    gaps: list[str],
    loose: bool = False,
    ordinals: Sequence[bool] | None = None,
) -> list[tuple[_Date, int, int]]:
    """Every date the parts can be read as, with the index of its first and last part.

    Three parts in a row are a date. In a range or a list, each end also takes the parts
    written after the last end (and before the first), so ``11.–15.4.2025`` holds the 11th
    as well as the 15th.
    """
    found: list[tuple[_Date, int, int]] = []
    flags = list(ordinals) if ordinals is not None else [False] * len(items)
    for index in range(len(items) - 2):
        for date in _dates_of_three(
            items[index : index + 3], gaps[index : index + 2], flags[index : index + 3]
        ):
            found.append((date, index, index + 2))
    for size, ends in _chains(items, gaps, loose):
        first = ends[0]
        # Without punctuation any space may join two ends, so a chain read from a PDF's
        # words can run on into the month (11 15 4 2025): the chain ending one or two
        # ends earlier is tried too.
        lasts = range(max(1, len(ends) - 3), len(ends)) if loose else [len(ends) - 1]
        for last in lasts:
            after = ends[last] + size
            for end in ends[: last + 1]:
                # The end kept, with up to two parts on each side of the whole chain.
                places = [
                    *range(max(0, first - 2), first),
                    *range(end, end + size),
                    *range(after, min(len(items), after + 2)),
                ]
                texts = [
                    gaps[later - 1] if later == after else gaps[earlier]
                    for earlier, later in zip(places, places[1:])
                ]
                for offset in range(len(places) - 2):
                    three = places[offset : offset + 3]
                    for date in _dates_of_three(
                        [items[place] for place in three],
                        texts[offset : offset + 2],
                        [flags[place] for place in three],
                    ):
                        found.append((date, three[0], three[-1]))
    return found


def _value_dates(value: str) -> set[_Date]:
    """The dates a date value such as 2025-04-11, 11.04.2025 or 04/11/2025 can be."""
    items, gaps, ordinals = _date_items(value)
    return _dates_of_three(items, gaps, ordinals) if len(items) == 3 else set()


def _date_in(value: str, quote: str) -> bool:
    """Whether the quote writes the date of ``value``, each part from its own number."""
    if find_run(tokens(quote), tokens(value)) is not None:
        return True  # the same numbers in the same order, however they are separated
    wanted = _value_dates(value)
    if not wanted:
        return False
    items, gaps, ordinals = _date_items(quote)
    return any(
        _same_date(date, other)
        for date, _, _ in _dates_with_places(items, gaps, ordinals=ordinals)
        for other in wanted
    )


def value_status(value: Any, quote: str, policy: TracePolicy = _DEFAULT_POLICY) -> ValueStatus:
    """Whether the extracted value is in the quote, tolerant of number and date formats."""
    if value is None or isinstance(value, bool | dict | list):
        return "unchecked"
    quote = _unescape_closing_tags(quote)  # the source's own text, as quote_needles reads it
    number = as_number(value)
    if number is not None:
        tolerance = policy.number_tolerance
        readings = _numbers_in(quote)
        found = any(abs(reading - number) < tolerance for reading in readings)
        if not found and number < 0:
            # A negative written another way: a sign set apart (Discount - EUR 1,014.50),
            # brackets (250.00), a sign after it (250,00-) or CR. A dash elsewhere in the
            # quote (Lasku 2026-0042) says nothing about the number.
            found = any(abs(reading + number) < tolerance for reading in _negatives_in(quote))
        return "match" if found else "mismatch"
    text = str(value)
    if date_parts(text) is not None:
        if _date_in(text, quote):
            return "match"
        if _value_dates(text):
            return "mismatch"
        # No date reads it (1.2.3, 12-2025-03): a version or an identifier, as written in
        # the quote (v1.2.3), but not as part of a longer one (1.2.3.4, 11.2.3).
        if re.search(rf"(?<!\d)(?<!\d[.,]){re.escape(text.strip())}(?![.,]?\d)", _nfc(quote)):
            return "match"
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


def date_run(words: list[str], value: str | list[int]) -> tuple[int, int] | None:
    """The shortest run of words that writes the date ``value``, as start and length.

    ``words`` are :func:`tokens` (a page's words, without their punctuation). The run must
    hold the year, the month and the day in an order a date is written in, each from its
    own word, so ``04 11 2025`` is not found for ``2025-04-04``. ``value`` is the date as
    the model wrote it; a list of its numbers (from :func:`date_parts`) is also accepted.
    """
    text = value if isinstance(value, str) else "-".join(str(part) for part in value)
    wanted = _value_dates(text)
    if not wanted:
        return None
    items: list[_Item] = []
    gaps: list[str] = []
    ordinals: list[bool] = []
    places: list[int] = []
    between: list[str] = []
    for index, word in enumerate(words):
        inner, inner_gaps, inner_ordinals = _date_items(word)
        if not inner:
            between.append(word)  # a word such as "of" between two parts
            continue
        if items:
            gaps.append(" " + " ".join(between) + " " if between else " ")
        between = []
        items += inner
        gaps += inner_gaps
        ordinals += inner_ordinals
        places += [index] * len(inner)
    best: tuple[int, int] | None = None
    for date, first, last in _dates_with_places(items, gaps, loose=True, ordinals=ordinals):
        if any(_same_date(date, other) for other in wanted):
            run = (places[first], places[last] - places[first] + 1)
            if best is None or run[1] < best[1]:
                best = run
    return best


def locate_in_text(text: str, quote: str) -> tuple[int, int] | None:
    """Where in ``text`` a quote sits, as character offsets, however it is spaced or punctuated.

    Words are compared as in :func:`tokens`, so a quote that the model copied with other
    line breaks, spacing or punctuation is still found.
    """
    spans = _word_spans(text)
    words = [word for word, _, _ in spans]
    for needle in quote_needles(quote):
        found = _locate_in_words(spans, words, needle)
        if found is not None:
            return found
    return None


def _word_spans(text: str) -> list[tuple[str, int, int]]:
    """Lowercased words of ``text`` in NFC form and with ligatures written as their letters
    (as :func:`tokens` reads them), with their offsets in ``text`` as given."""
    if unicodedata.is_normalized("NFC", text) and not _LIGATURE.search(text):
        return [
            (match.group().lower(), match.start(), match.end()) for match in _WORD.finditer(text)
        ]
    composed, origin = _composed(text)
    return [
        (match.group().lower(), origin[match.start()][0], origin[match.end() - 1][1])
        for match in _WORD.finditer(composed)
    ]


def _composed(text: str) -> tuple[str, list[tuple[int, int]]]:
    """``text`` in NFC form with ligatures expanded, and for each of its characters the span
    of ``text`` it came from.

    The text is composed one cluster at a time: a character with the marks and the
    conjoining letters (Hangul jamo) that compose with it.
    """
    pieces: list[str] = []
    origin: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text) and _composes_with(text, start, end):
            end += 1
        piece = expand_ligatures(unicodedata.normalize("NFC", text[start:end]))
        pieces.append(piece)
        origin += [(start, end)] * len(piece)
        start = end
    return "".join(pieces), origin


def _composes_with(text: str, start: int, end: int) -> bool:
    """Whether ``text[end]`` belongs to the cluster ``text[start:end]`` when composed."""
    char = text[end]
    if ord(char) < 0x300:  # no character below the combining marks composes with one before
        return False
    if unicodedata.combining(char):
        return True
    cluster = text[start:end]
    return unicodedata.normalize("NFC", cluster + char) != unicodedata.normalize(
        "NFC", cluster
    ) + unicodedata.normalize("NFC", char)


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
    or a summary), so it is only noted, unless the policy asks for verbatim values. A text
    value whose numbers the quote does not hold (``PO-2025-15903`` for ``PO-2025-15908``,
    ``04/2026`` for ``03/2026``) is a problem too, when the quote has as many numbers: with
    fewer, the model may have written a number the quote spells in words.
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
            if policy.reworded_is_problem or (
                isinstance(value, str) and _other_numbers(value, quote, policy.number_tolerance)
            ):
                return "check"
            return "reworded"
        # A number spelled out in words ("kaksi päivää") cannot be compared with a digit.
        return "check" if re.search(r"\d", quote) else "unchecked"
    return "unchecked"


def _other_numbers(value: str, quote: str, tolerance: float) -> bool:
    """Whether a text value holds a number its quote does not, the quote having as many.

    Numbers are compared as numbers, sign included (``12.5 kg`` is in ``12,50 kg``, ``250``
    is not in ``-250``), and a date as a date (``11.4.2025`` is in ``2025-04-11``, not in
    ``04.11.2025``), so only a different number counts: an identifier with another digit,
    another month or year, another count. With fewer runs of digits in the quote than in
    the value, the quote may spell a number in words, and nothing is said.
    """
    wanted = list(_NUMBER.finditer(value))
    if not wanted or len(_DATE_PARTS.findall(quote)) < len(_DATE_PARTS.findall(value)):
        return False
    readings = [reading for group in _number_groups(quote) for reading in group]
    # A clock time with a dot (klo 10.00) is hours and minutes, not 10.0.
    readings += [float(part) for clock in _CLOCK.finditer(quote) for part in clock.groups()]
    in_shared_date = _shared_date_parts(value, quote)
    for match, group in zip(wanted, _number_groups(value)):
        if any(abs(mine - theirs) < tolerance for mine in group for theirs in readings):
            continue
        written = match.group()
        if date_parts(written) is not None and _date_in(written, quote):
            continue  # 11.4.2025 in the value, 2025-04-11 in the quote
        if all(_digits(run) in in_shared_date for run in _DATE_PARTS.findall(written)):
            continue  # a part of a date both write (the 2025 of 2025-04-11 and 11.4.2025)
        if _short_form_of(written, quote, value[: match.start()].endswith("+")):
            continue
        return True
    return False


def _short_form_of(written: str, quote: str, international: bool) -> bool:
    """Whether a number of a text value is the quote's number written shorter or longer: a
    two-digit year (04/26 for 04/2026), or a phone number with or without its country code
    and leading zero (+358401234567 for 040 123 4567)."""
    runs = _DATE_PARTS.findall(quote)
    if len(written) == 2 and written.isdigit():
        return any(
            len(run) == 4 and run[:2] in ("19", "20") and run.endswith(written) for run in runs
        )
    mine = re.sub(r"\D", "", written)
    for match in _NUMBER.finditer(quote):
        theirs = re.sub(r"\D", "", match.group())
        plus = quote[: match.start()].endswith("+")
        # One side +358 40..., the other 040...: the same number without its country code.
        for long, short in ((mine, theirs), (theirs, mine)):
            if (
                (international if long == mine else plus)
                and short.startswith("0")
                and len(short) >= 7
                and long.endswith(short[1:])
            ):
                return True
    return False


def _shared_date_parts(value: str, quote: str) -> set[str]:
    """The year, month and day digits of each date that both texts write."""
    value_items, value_gaps, value_ordinals = _date_items(value)
    mine = {
        date for date, _, _ in _dates_with_places(value_items, value_gaps, ordinals=value_ordinals)
    }
    if not mine:
        return set()
    quote_items, quote_gaps, quote_ordinals = _date_items(quote)
    parts: set[str] = set()
    for date, _, _ in _dates_with_places(quote_items, quote_gaps, ordinals=quote_ordinals):
        for other in mine:
            if _same_date(date, other):
                for found in (date, other):
                    parts |= {str(found[0]), str(found[0] % 100), str(found[2]), str(found[3])}
    return parts


def _digits(run: str) -> str:
    """A run of digits without its leading zeros (``04`` and ``4`` are one number)."""
    return run.lstrip("0") or "0"
