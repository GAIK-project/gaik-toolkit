"""Value checks in source tracing: date order, signs, changed digits, NFD text (#144)."""

from __future__ import annotations

import unicodedata

import pytest
from gaik.software_components.source_tracing.matching import (
    date_parts,
    date_run,
    locate_in_text,
    tokens,
    value_status,
    verdict_of,
)


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        ("2025-11-04", "Päivämäärä 04.11.2025", "match"),  # day first with dots
        ("2025-04-11", "Päivämäärä 04.11.2025", "mismatch"),  # day and month swapped
        ("2025-04-04", "Päivämäärä 04.11.2025", "mismatch"),  # one number used twice
        ("2003-03-25", "Päivämäärä 25.03.2025", "mismatch"),  # month read as a year
        ("2025-03-15", "Tapaturma 15.3.2025", "match"),
        ("2025-03-15", "Tapaturma 15.3.25", "match"),  # two-digit year
        ("2026-02-15", "DATE: 02/15/2026", "match"),  # month first with slashes
        ("2025-10-12", "PO Date: October 12, 2025", "match"),
        ("2025-10-12", "Päivätty 12 October 2025", "match"),
        ("2025-10-13", "PO Date: October 12, 2025", "mismatch"),
        ("11.04.2025", "Date 2025-04-11", "match"),
    ],
)
def test_dates_are_compared_in_the_order_they_are_written(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        ("2025-10-12", "12th October 2025", "match"),  # ordinal day before the month
        ("2025-10-12", "12 Oct 25", "match"),  # two-digit year after a month name
        ("2025-10-12", "Oct 12, 25", "match"),
        ("2025-10-13", "12th October 2025", "mismatch"),
    ],
)
def test_a_named_month_date_may_have_an_ordinal_day_or_a_two_digit_year(
    value, quote, expected
) -> None:
    assert value_status(value, quote) == expected


@pytest.mark.parametrize(
    "value",
    ["12-2025-03", "2025-18-04", "03.25.2025"],
)
def test_digits_that_cannot_be_read_as_a_written_date_are_compared_as_text(value) -> None:
    # Three groups of digits that no date order reads (year in the middle, a month of 18,
    # month first with dots) are not a date: the same characters in the quote still match.
    assert date_parts(value) is None
    quote = f"Ref: {value}"
    assert value_status(value, quote) == "match"
    assert verdict_of("found", "match", value, quote) == "verified"
    changed = quote[:-1] + ("9" if quote[-1] != "9" else "8")
    state = value_status(value, changed)
    assert state == "mismatch"
    assert verdict_of("found", state, value, changed) == "check"


def test_date_run_takes_each_part_from_its_own_word_in_date_order() -> None:
    words = tokens("Päivämäärä 04.11.2025 klo 10")
    assert date_run(words, date_parts("2025-11-04")) == (1, 3)
    assert date_run(words, date_parts("2025-04-04")) is None


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (250, "Hyvitys -250,00 EUR", "mismatch"),
        (-250, "Hyvitys -250,00 EUR", "match"),
        (-1014.5, "Discount - EUR 1,014.50", "match"),  # a sign set apart still counts
        (20, "Range 10-20 kg", "match"),  # a dash between numbers is not a sign
        (2025, "PO-2025-15903", "match"),  # nor is one after a word
        (250, "Hinta 250,00 EUR", "match"),
        (20, "-10 20", "match"),  # the sign is the first number's, not the next one's
        (-10, "-10 20", "match"),
        (-1234, "Hyvitys -1 234 EUR", "match"),  # a space grouping thousands keeps the sign
    ],
)
def test_a_minus_sign_right_before_a_number_is_kept(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("PO-2025-15903", "PO Number: PO-2025-15908"),
        ("04/2026", "Voimassa 03/2026"),
    ],
)
def test_a_text_value_with_other_digits_than_its_quote_needs_a_check(value, quote) -> None:
    state = value_status(value, quote)
    assert state == "mismatch"
    assert verdict_of("found", state, value, quote) == "check"


def test_a_reworded_text_value_without_numbers_is_still_reworded() -> None:
    quote = "Trukki osui hyllyyn pohjoisella laiturilla"
    value = "A forklift hit a rack at the north dock"
    assert verdict_of("found", value_status(value, quote), value, quote) == "reworded"


def test_decomposed_text_matches_a_composed_value() -> None:
    nfd = unicodedata.normalize("NFD", "Nimi: Mäkinen, Jyväskylä")
    assert value_status("Mäkinen", nfd) == "match"
    assert value_status(unicodedata.normalize("NFD", "Mäkinen"), "Nimi: Mäkinen") == "match"


def test_a_composed_quote_is_located_in_decomposed_text_at_the_original_offsets() -> None:
    text = "Asiakas " + unicodedata.normalize("NFD", "Mäkinen Oy") + " maksoi."
    span = locate_in_text(text, "Mäkinen Oy")
    assert span is not None
    start, end = span
    assert unicodedata.normalize("NFC", text[start:end]) == "Mäkinen Oy"
