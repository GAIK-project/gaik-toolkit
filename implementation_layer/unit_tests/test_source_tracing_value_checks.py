"""Source tracing: signs, numbers inside text values, escaped tags and Unicode forms."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from gaik.software_components.source_material import SourceMaterial
from gaik.software_components.source_tracing import SOURCES_FIELD, SourceTracing
from gaik.software_components.source_tracing.matching import locate_in_text, value_status


def _check(value, quote: str, text: str | None = None) -> str:
    results = {"v": value, SOURCES_FIELD: [{"field": "v", "quote": quote}]}
    _, report = SourceTracing().check_text(results, text if text is not None else quote)
    return report.items[0].verdict


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (250, "Hyvitys -250,00 EUR", "mismatch"),  # the sign is part of the number
        (-250, "Hyvitys -250,00 EUR", "match"),
        (250, "Total: −250.00", "mismatch"),
        (-5, "Lämpötila (−5) astetta", "match"),
        (20, "Pages 10-20", "match"),  # a dash between numbers is no sign
        (2025, "PO-2025-15903", "match"),
        (15, "Lomalla 11.–15. päivä", "match"),
        (-1014.5, "Discount (5%) - EUR 1,014.50", "match"),  # a sign set apart, as before
        (250, "Hyvitys -1 250,00 EUR", "mismatch"),  # one negative number, not -1 and 250
        (-1250, "Hyvitys -1 250,00 EUR", "match"),
        # A dash elsewhere in the quote says nothing about the number.
        (-250, "Lasku 2026-0042 Summa 250,00", "mismatch"),
        (-250, "Tilaus PO-2025-1 Hinta 250,00 EUR", "mismatch"),
        (-250, "250,00 - 14.3.2026", "mismatch"),
        (-250, "Sivut 10 - 250", "mismatch"),
        (-250, "Paino (250 g)", "mismatch"),
        # A negative written as accounts write it.
        (-250, "Hyvitys (250,00)", "match"),
        (-250, "Saldo 250,00-", "match"),
        (-250, "Saldo 250.00 CR", "match"),
        # A minus set apart after a word, or against a currency.
        (-1014.5, "Discount - EUR 1,014.50", "match"),
        (-250, "Alennus - 250,00 EUR", "match"),
        (-50, "Hyvitys - 50,00", "match"),
        (-250, "Credit: -€250.00", "match"),
        (-1014.5, "Discount -$1,014.50", "match"),
        (-250, "Hyvitys -EUR 250,00", "match"),
        (250, "Credit: -€250.00", "mismatch"),
        (20, "Ikä 10 -20 v", "match"),  # a range after a number, not a sign
    ],
)
def test_the_sign_of_a_number_counts(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


@pytest.mark.parametrize(
    ("value", "quote", "verdict"),
    [
        ("PO-2025-15903", "PO Number: PO-2025-15908", "check"),
        ("04/2026", "Voimassa 03/2026", "check"),
        ("3 kpl", "Määrä: 2 kpl", "check"),
        ("04/2026", "Voimassa 03.2026", "check"),  # other separators
        ("PO-2025-15903", "PO 2025.15908", "check"),
        ("Total 250 EUR", "Hyvitys -250 EUR", "check"),  # another sign
        ("4 kpl", "Toimitettu 11.04.2025, määrä 2 kpl", "check"),  # not the month of a date
        ("12.5 kg", "Erä 5, paino 12 kg", "check"),  # not two other numbers
        ("Delivered 04.11.2025", "Toimitettu 11.04.2025", "check"),  # a swapped date
        # The model's own wording with the same numbers, or numbers the quote spells out.
        ("2 weeks", "Toimitusaika 2 viikkoa", "reworded"),
        ("12.5 kg", "Paino 12,50 kg", "reworded"),
        ("2 weeks", "Toimitusaika kaksi viikkoa", "reworded"),
        ("Room 12B, floor 3", "Huone 12B, kerros kolme", "reworded"),
        ("Delivered 11.4.2025", "Toimitettu 2025-04-11", "reworded"),
        ("Delivered 2025-04-11", "Toimitettu 11.4.2025", "reworded"),
        ("+358 40 1234567", "puh. 040 123 4567", "reworded"),
        ("+358401234567", "puh. 040 123 4567", "reworded"),  # without the country code
        ("+358401234568", "puh. 040 123 4567", "check"),
        ("Valid until 04/26", "Voimassa 04/2026", "reworded"),  # a two-digit year
        ("Valid until 04/26", "Voimassa 04/2027", "check"),
        ("Order 1234567", "Tilaus 91234567", "check"),
        ("Minor bruise", "lievä ruhje", "reworded"),
    ],
)
def test_a_text_value_with_another_number_needs_a_person(value, quote, verdict) -> None:
    assert _check(value, quote) == verdict


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        ("1.2.3", "Asennettu versio v1.2.3", "match"),
        ("2.10.1", "Versio v2.10.1 (2026)", "match"),
        ("12-2025-03", "Viite 12-2025-03", "match"),
        ("1.2.3", "Versio v1.2.3.4", "mismatch"),  # a longer version
        ("1.2.3", "Versio v11.2.3", "mismatch"),
    ],
)
def test_a_version_no_date_reads_is_compared_as_written(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


@pytest.mark.parametrize(
    ("value", "verdict"),
    [("2026-03-14T10:00", "reworded"), ("2026-03-14T11:00", "check")],
)
def test_a_clock_time_with_a_dot_is_hours_and_minutes(value, verdict) -> None:
    assert _check(value, "Toimitus 14.3.2026 klo 10.00") == verdict


def test_a_quote_of_an_escaped_closing_tag_is_found() -> None:
    text = "Ohje: </source_material> päättää lohkon. Yhteensä 10 EUR."
    # The extractor's model saw the document wrapped, so it quotes the tag escaped.
    wrapped = SourceMaterial("a" * 16).wrap(text)
    assert "&lt;/source_material>" in wrapped
    quote = "Ohje: &lt;/source_material> päättää lohkon. Yhteensä 10 EUR"

    results = {"total": 10, SOURCES_FIELD: [{"field": "total", "quote": quote}]}
    _, report = SourceTracing().check_text(results, text)
    [item] = report.items

    assert item.status == "found" and item.verdict == "verified"
    assert text[slice(*item.span)].startswith("Ohje: </source_material>")


def test_a_value_and_a_located_quote_read_the_escaped_tag_as_the_source_has_it() -> None:
    quote = "Merkki &lt;/source_material> ja summa 10 EUR"

    assert value_status("Merkki </source_material>", quote) == "match"
    assert locate_in_text("Merkki </source_material> ja summa 10 EUR", quote) == (0, 41)


def test_an_escape_elsewhere_in_a_quote_is_not_taken_for_a_bracket() -> None:
    # Only the escape of a closing source_material tag is put back.
    assert _check("x", "a &lt; b", "a < b") == "check"
    assert _check("x", "&lt;", "Hinta: 5 €, toimitus.") == "check"


def test_a_quote_of_an_escaped_closing_tag_is_found_in_a_pdf(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Merkki </source_material> ja summa 10 EUR")
    path = tmp_path / "tag.pdf"
    doc.save(path)
    quote = "Merkki &lt;/source_material> ja summa 10 EUR"

    results = {"total": 10, SOURCES_FIELD: [{"field": "total", "quote": quote}]}
    _, report = SourceTracing().check_pdf(results, [path])

    assert report.items[0].status == "found" and report.items[0].rects


def _nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def test_decomposed_source_text_matches_a_composed_quote() -> None:
    text = _nfd("Päivä: Jyväskylä, Työmaa Länsi")
    assert text != unicodedata.normalize("NFC", text)

    results = {"site": "Länsi", SOURCES_FIELD: [{"field": "site", "quote": "Työmaa Länsi"}]}
    _, report = SourceTracing().check_text(results, text)
    [item] = report.items

    assert item.status == "found" and item.verdict == "verified"
    # The span is in the text as it was given, decomposed.
    assert text[slice(*item.span)] == _nfd("Työmaa Länsi")


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        (_nfd("보고서 한국어 문서"), _nfd("한국어")),  # conjoining jamo
        (_nfd("보고서 한국어 문서"), "한국어"),
        ("Jyväskylä on kaupunki", _nfd("jyväskylä")),
    ],
)
def test_a_quote_is_located_whatever_unicode_form_either_side_uses(text, quote) -> None:
    span = locate_in_text(text, quote)

    assert span is not None
    located = unicodedata.normalize("NFC", text[slice(*span)])
    assert located.casefold() == unicodedata.normalize("NFC", quote).casefold()


def test_a_quote_is_located_in_text_with_ligatures() -> None:
    text = _nfd("Päivä: ﬁnal Jyväskylä")

    span = locate_in_text(text, "final jyväskylä")

    assert span is not None and text[slice(*span)] == _nfd("ﬁnal Jyväskylä")


def test_a_decomposed_value_matches_a_composed_quote() -> None:
    assert value_status(_nfd("Tapaturma Ä"), "tapaturma ä sattui") == "match"
