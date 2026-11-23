"""The date matcher of source tracing, case by case.

A date value matches its quote when the quote writes that year, month and day in an order
a date is written in, each part from its own number. ``VERIFIED_ON_MAIN`` lists spellings
the earlier any-order rule verified correctly; they must stay verified. ``WRONG_DATES``
lists wrong dates that rule verified because it compared the parts as a set and read every
number below 100 as a year.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from gaik.software_components.source_tracing import SOURCES_FIELD, SourceTracing
from gaik.software_components.source_tracing.matching import date_run, tokens, value_status

DATE = "2025-04-11"

VERIFIED_ON_MAIN = [
    # Numbers only.
    (DATE, "11.04.2025"),
    (DATE, "11.4.2025"),
    (DATE, "11. 4. 2025"),
    (DATE, "Pvm:11.04.2025"),
    (DATE, "(11.04.2025)"),
    (DATE, "11/04/2025"),
    (DATE, "04/11/2025"),  # a slash may put the month first
    (DATE, "2025-04-11"),
    (DATE, "2025-04-11T10:00:00"),
    (DATE, "2025-04-11 10:00"),
    (DATE, "2025/04/11"),
    (DATE, "2025.04.11."),
    (DATE, "11-04-2025"),
    (DATE, "11 04 2025"),
    (DATE, "11.04.25"),
    (DATE, "11/4/25"),
    (DATE, "11.4 2025"),
    (DATE, "11/4 2025"),
    (DATE, "11 . 04 . 2025"),
    (DATE, "11 / 04 / 2025"),
    (DATE, "11.04/2025"),
    (DATE, "2025年4月11日"),
    # Month names.
    (DATE, "11 April 2025"),
    (DATE, "11. April 2025"),
    (DATE, "11th April 2025"),
    (DATE, "11th of April 2025"),
    (DATE, "this 11th day of April, 2025"),
    (DATE, "April 11, 2025"),
    (DATE, "April 11th, 2025"),
    (DATE, "Apr. 11, 2025"),
    (DATE, "11 APR 2025"),
    (DATE, "Friday, 11 April 2025"),
    (DATE, "Fri, Apr 11, 2025"),
    (DATE, "Apr 11 '25"),
    (DATE, "11th April '25"),
    (DATE, "April, 11 2025"),
    (DATE, "April 2025, 11th"),
    (DATE, "11-Apr-2025"),
    (DATE, "11/Apr/2025"),
    (DATE, "Apr-11-2025"),
    (DATE, "2025-Apr-11"),
    (DATE, "11 Apr 25"),
    # Ranges and lists: the first date, the last date and one in between.
    (DATE, "Lomalla 11.–15.4.2025"),
    (DATE, "Lomalla 11.-15.4.2025"),
    (DATE, "Lomalla 11-15.4.2025"),
    (DATE, "Jakso 11.4.–15.4.2025"),
    (DATE, "11.4.-15.4.2025"),
    (DATE, "11–15 April 2025"),
    (DATE, "11-15 Apr 2025"),
    (DATE, "11 to 15 April 2025"),
    (DATE, "April 11–15, 2025"),
    (DATE, "April 11-15, 2025"),
    (DATE, "April 11 – May 2, 2025"),
    (DATE, "11/04/2025 – 15/04/2025"),
    (DATE, "1.-11.4.2025"),
    (DATE, "2025-04-01–11"),
    (DATE, "Työpäivät 9., 11. ja 15.4.2025"),
    (DATE, "11.4. ja 15.4.2025"),
    ("2025-03-01", "Laskutuskausi 1.–31.3.2025"),
    ("2025-03-31", "Laskutuskausi 1.–31.3.2025"),
    ("2025-04-15", "Lomalla 11.–15.4.2025"),
    ("2025-04-15", "Jakso 11.4.–15.4.2025"),
    ("2025-05-02", "April 11 – May 2, 2025"),
    ("2025-04-09", "Työpäivät 9., 11. ja 15.4.2025"),
    ("2025-04-09", "9, 11 and 15 April 2025"),
    ("2025-04-09", "April 9, 11 and 15, 2025"),
    (DATE, "11th–15th April 2025"),
    (DATE, "April 11th–15th, 2025"),
    ("2025-04-09", "9th, 11th and 15th April 2025"),
    (DATE, "11 ja 15.4.2025"),
    (DATE, "11/12 April 2025"),
    (DATE, "11 April – 2 May 2025"),
    ("2025-05-02", "11 April – 2 May 2025"),
    (DATE, "11 and 15/4/2025"),
    (DATE, "11.4./12.4.2025"),
    (DATE, "11, 12 and 15.4.2025"),
    (DATE, "11 Apr – 15.4.2025"),
    (DATE, "11.04. – 15 April 2025"),
    (DATE, "11.–15.–17.4.2025"),
    (DATE, "11-15-17.4.2025"),
    ("2025-04-15", "2025-04-11 and 15"),
    # A number just before a range of days is not one end of the range.
    ("2025-04-14", "Vk 16 14.–18.4.2025 koulutus"),
    (DATE, "1. 11.–15.4.2025"),
    (DATE, "Q2 11.–15.4.2025"),
    (DATE, "Week 15 11–15 April 2025"),
    ("2023-10-03", "Rev 2 3–4 October 2023"),
    ("2025-07-10", "1. 10–30 July 2025 vk 16"),
    ("2025-04-10", "Klo 9.30 10.–24.4.2025 (3 kpl)"),
    ("2021-10-08", "1. 8.–10.10.2021 – 30 pv"),
    ("2020-03-02", "Sivu 2/5 2–11 March 2020"),
    ("2024-07-06", "Vk 16 6–26 July 2024 klo 10.00"),
    (DATE, "10.–11.4.–15.4.2025"),
    (DATE, "10.4. ja April 11–15, 2025"),
    (DATE, "10.4. ja Apr 11 – 15, 2025"),
    (DATE, "3.2. 11–15 April 2025"),
    (DATE, "31.3. 11–15 April 2025"),
    # Separators the first rule read past: an apostrophe, a comma before the year,
    # brackets, Korean.
    (DATE, "11/04/'25"),
    (DATE, "11.04.’25"),
    (DATE, "11 04, 2025"),
    (DATE, "11/04, 2025"),
    (DATE, "11 April (2025)"),
    (DATE, "April 11 [2025]"),
    (DATE, "2025년 4월 11일"),
    # Other numbers before the date: a list marker, a count, an amount, an id.
    ("2025-03-12", "Invoice 4 dated 12 March 2025"),
    ("2025-03-12", "Rev 2 issued 12 March 2025"),
    ("2025-03-15", "Bolt M8 10 pcs 15 Mar 2025"),
    ("2025-03-15", "Net 30 days, 15 March 2025"),
    ("2025-06-14", "Delivered 5 pcs 14 June 2025"),
    ("2025-11-28", "Summa 1 234,50 EUR 28 November 2025"),
    ("2025-11-28", "Lasku 2025-0042 28 11 2025"),
    (DATE, "1. 11.04.2025"),
    (DATE, "3) 11.04.2025"),
    (DATE, "2. 11 April 2025"),
    ("2025-03-15", "Tapaturma 15.3.2025 klo 14.30"),
    ("2025-10-12", "PO Date: October 12, 2025"),
    ("2026-02-15", "DATE: 02/15/2026"),
    # Two-digit and zero-padded years.
    ("2005-04-11", "11.04.05"),
    ("2005-04-11", "11.4.2005"),
    # The value written in another format.
    ("11.04.2025", "11.04.2025"),
    ("11.04.2025", "2025-04-11"),
    ("11.04.2025", "April 11, 2025"),
    ("04/11/2025", "04/11/2025"),
    ("04/11/2025", "April 11, 2025"),
    ("11 . 04 . 2025", "11 . 04 . 2025"),
    ("11.04/2025", "11.04/2025"),
    ("2025 04 11", "2025 04 11"),
    ("11.4.25", "11.4.25"),
    ("2025-11-04", "04.11.2025"),  # dots put the day first: 4 November
    ("12-2025-03", "12-2025-03"),  # no date order reads it, but the quote is the same
    ("25-04-11", "25-04-11"),
]

NOW_VERIFIED = [
    # Finnish month names, in their case forms.
    ("2026-03-14", "14. maaliskuuta 2026"),
    ("2025-11-14", "Toimitus 14. marraskuuta 2025"),
    ("2025-06-01", "kesäkuun 1. päivänä 2025"),
    ("2025-06-01", "1. päivänä kesäkuuta 2025"),
    ("2025-12-24", "Jouluaatto 24. joulukuuta 2025"),
    ("2025-01-31", "31. tammikuuta 2025"),
    (DATE, "11.–15. huhtikuuta 2025"),
    (DATE, "11Apr2025"),
    ("1998-12-31", "31.12.98"),
    ("11.4.25", "11.4.2025"),
]

WRONG_DATES = [
    (DATE, "04.11.2025"),  # day and month swapped: dots put the day first
    ("2025-11-04", "11.04.2025"),
    ("2025-04-04", "04.11.2025"),  # one quote number used twice
    ("2025-11-11", "04.11.2025"),
    ("2025-11-04", "2025-04-11"),  # year first is year, month, day
    ("2004-03-12", "12.3. klo 4"),  # a number written with one digit is no year
    (DATE, "Item 25: 11 pcs, 4 boxes"),  # numbers that are not written as a date
    (DATE, "4 pcs, 11 boxes, order 2025"),
    ("2025-04-12", "11.04.2025"),
    ("2026-04-11", "11.04.2025"),
    (DATE, "11.04.2026"),
    ("2042-04-11", "Lasku 2025-0042 11.4."),  # a zero-padded group is no two-digit year
    (DATE, "April 2025"),
    ("2012-03-04", "Invoice 4 dated 12 March 2025"),
    ("2025-11-10", "2025-04-11 10.00"),
    # A list marker or a count is not the day of a date written after it.
    ("1998-01-01", "1. 09-01-98"),
    ("2025-01-01", "Qty 1, 09.01.25"),
    ("2025-04-01", "1. 11.04.2025"),
    (DATE, "qty 2025, section 04, item 11"),
    ("2025-11-15", "11.–15.–17.4.2025"),  # a range of days is not a day and a month
    ("2025-11-04", "2025年4月11日"),
    ("2025-04-15", "11.4.25–15.5.25"),
    ("2025-03-14", "14. marraskuuta 2025"),  # marraskuu is November, not March
    # With a month name, a number after the year is no day, and a month name after both
    # numbers makes no date.
    ("2025-04-15", "Maksettu 11. huhtikuuta 2025 15 €"),
    ("2025-03-02", "Toimitettu 1. maaliskuuta 2025 2 kpl"),
    ("2016-09-16", "Vk 16 17. elokuuta – 16. syyskuuta 2022"),
    ("2019-09-14", "1. 12.–15. syyskuuta 2019 14"),
    ("2024-06-16", "Vk 16 6–26 July 2024"),
    ("11.04.25", "Toimitettu 25.4.2011"),  # dots read year first only with four digits
    # A batch number and a comma do not start a list of days.
    ("2025-07-03", "Erä 3, 2.–15. heinäkuuta 2025 sivu 3"),
    ("2021-08-03", "Erä 3, 1. elokuuta 2021 klo 10.00"),
    # A number after the year and a comma is a day only with its suffix (April 2025, 11th).
    ("2019-04-12", "Week 15 11. huhtikuuta 2019, 12 kpl"),
    # Across a spaced en dash, the next day of a range is no two-digit year.
    ("2025-03-25", "10-12 25. maaliskuuta – 25. huhtikuuta 2026 vk 16"),
    ("2015-04-11", "April 11–15, 2025"),
]


@pytest.mark.parametrize(("value", "quote"), VERIFIED_ON_MAIN + NOW_VERIFIED)
def test_a_correct_date_is_matched(value, quote) -> None:
    assert value_status(value, quote) == "match"


@pytest.mark.parametrize(("value", "quote"), WRONG_DATES)
def test_a_wrong_date_is_not_matched(value, quote) -> None:
    assert value_status(value, quote) == "mismatch"


def test_a_swapped_date_needs_a_person() -> None:
    text = "Toimituspäivä 04.11.2025. Tilaus 11.04.2025."
    results = {
        "delivered": "2025-04-11",
        "ordered": "2025-04-11",
        SOURCES_FIELD: [
            {"field": "delivered", "quote": "Toimituspäivä 04.11.2025"},
            {"field": "ordered", "quote": "Tilaus 11.04.2025"},
        ],
    }

    _, report = SourceTracing().check_text(results, text)

    assert [item.verdict for item in report.items] == ["check", "verified"]


@pytest.mark.parametrize(
    ("value", "quote", "boxed"),
    [
        (DATE, "Päivä 11.04.2025 klo 10", "11 04 2025"),
        ("2005-04-11", "Päivä 11.04.05 klo 10", "11 04 05"),  # a zero-padded year
        (DATE, "Lomalla 11.–15.4.2025 koko viikon", "11 15 4 2025"),
        (DATE, "Delivered 12th April 2025 and 11th April 2025", "11th april 2025"),
        ("2025-04-04", "Delivered 04.11.2025, signed 4.4.2025", "4 4 2025"),
        # A list of days whose dots are gone: each day takes the month and year after it.
        ("2025-04-09", "Työpäivät 9., 11. ja 15.4.2025", "9 11 ja 15 4 2025"),
        (DATE, "Työpäivät 9., 11. ja 15.4.2025", "11 ja 15 4 2025"),
    ],
)
def test_the_date_is_located_in_the_words_of_its_quote(value, quote, boxed) -> None:
    words = tokens(quote)

    start, length = date_run(words, value)

    assert " ".join(words[start : start + length]) == boxed


def test_a_number_used_twice_is_not_located_as_a_date() -> None:
    assert date_run(tokens("04 11 2025"), "2025-04-04") is None


def test_a_long_run_of_digits_does_not_stop_the_check() -> None:
    quote = "Viite " + "9" * 5000 + " päivätty 11.04.2025"

    assert value_status(DATE, quote) == "match"
    assert value_status("2025-04-12", quote) == "mismatch"


def test_a_quote_with_many_numbers_is_checked_quickly() -> None:
    quote = ", ".join(str(n % 28 + 1) for n in range(3000)) + " ja 11.4.2025"

    started = time.perf_counter()
    assert value_status(DATE, quote) == "match"
    # Linear in the quote: about 0.05 s here. A quadratic reading of the list takes minutes.
    assert time.perf_counter() - started < 5


def test_a_zero_padded_year_is_boxed_in_a_pdf(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Toimitettu 11.04.05 varastoon")
    path = tmp_path / "date.pdf"
    doc.save(path)
    results = {
        "delivered": "2005-04-11",
        SOURCES_FIELD: [{"field": "delivered", "quote": "Toimitettu 11.04.05 varastoon"}],
    }

    _, report = SourceTracing().check_pdf(results, [path])
    [item] = report.items

    assert item.verdict == "verified"
    assert len(item.value_rects) == 1 and item.value_rects[0] in item.rects
