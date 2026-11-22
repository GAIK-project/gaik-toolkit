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
        # The model's own wording with the same numbers, or numbers the quote spells out.
        ("2 weeks", "Toimitusaika 2 viikkoa", "reworded"),
        ("12.5 kg", "Paino 12,50 kg", "reworded"),
        ("2 weeks", "Toimitusaika kaksi viikkoa", "reworded"),
        ("Room 12B, floor 3", "Huone 12B, kerros kolme", "reworded"),
        ("Delivered 11.4.2025", "Toimitettu 2025-04-11", "reworded"),
        ("Delivered 2025-04-11", "Toimitettu 11.4.2025", "reworded"),
        ("Minor bruise", "lievä ruhje", "reworded"),
    ],
)
def test_a_text_value_with_another_number_needs_a_person(value, quote, verdict) -> None:
    assert _check(value, quote) == verdict


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


def test_a_decomposed_value_matches_a_composed_quote() -> None:
    assert value_status(_nfd("Tapaturma Ä"), "tapaturma ä sattui") == "match"
