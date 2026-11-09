"""Tests for the source tracing component: matching, text and PDF checks, the report."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from gaik.software_components.source_tracing import (
    SOURCES_FIELD,
    SourceTracing,
    TracePolicy,
    with_sources,
)
from gaik.software_components.source_tracing.matching import (
    locate_in_text,
    value_at,
    value_status,
)
from pydantic import BaseModel

EXAMPLES = Path(__file__).parent.parent / "examples" / "software_components" / "source_tracing"


def _cite(field: str, quote: str, document: int = 1, page: int = 1) -> dict:
    return {"field": field, "document": document, "page": page, "quote": quote}


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (3000, "Quantity: 3.000 kg", "match"),
        (3000, "Quantity: 3,000 kg", "match"),
        (3.0, "Quantity: 3,000 kg", "match"),
        (27578.55, "TOTAL: $27,578.55", "match"),
        (1234.5, "Total: 1.234,50 EUR", "match"),
        (2000, "Quantity: 200 pcs", "mismatch"),
        # A decimal separator is not dropped: 12.5 is not 125.
        (125, "Rate: 12.5 %", "mismatch"),
        (12.5, "Rate: 12.5 %", "match"),
        (15, "Weight 1,5 kg", "mismatch"),
        (10, "Price 0.10", "mismatch"),
        (125, "Share 0.125", "mismatch"),
        (2757855, "TOTAL: $27,578.55", "mismatch"),
        (1234567, "Population: 1.234.567", "match"),
        (1234567, "Population: 1,234,567", "match"),
        (1234567.5, "Total: 1,234,567.50", "match"),
        (1234, "Total: 1 234 EUR", "match"),
        (-1014.5, "Discount (5%) - EUR 1,014.50", "match"),
        (-1014.5, "Discount (5%) EUR 1,014.50", "mismatch"),
        (-1014.5, "Discount (5%) - EUR 1,015.50", "mismatch"),
        ("010", "010 6061-T6 Aluminium Alloy Round Bar", "match"),
        (6061, "010 6061-T6 Aluminium Alloy Round Bar", "match"),
        ("7200-4453-21", "PURCHASE NO: 7200445321", "match"),
        ("7200-4453-22", "PURCHASE NO: 7200445321", "mismatch"),
        ("7200-4453", "PURCHASE NO: 7200445321", "mismatch"),
        ("4453-21", "PURCHASE NO: 7200445321", "mismatch"),
        ("7200445321", "PO 7200 4453 21", "match"),
        ("2025-10-12", "PO Date: October 12, 2025", "match"),
        ("2025-04-11", "11.04.2025", "match"),
        ("2025-04-12", "11.04.2025", "mismatch"),
        ("PO-2025-15903", "PO Number: PO-2025-15903", "match"),
        ("Acme Ltd", "Supplier Name: Precision Steel", "mismatch"),
        (True, "[x] Eligible", "unchecked"),
        ("approved_with_remarks", "[X] Approved with remarks", "match"),
        ("not_ok", "Waste sorted and removed [ ] [X] [ ]", "unchecked"),
        (None, "anything", "unchecked"),
        (Decimal("426.7"), "maksoi 340 euroa", "mismatch"),
        (Decimal("340"), "maksoi 340 euroa", "match"),
        ("Tapaturma Ä", "tapaturma ä sattui", "match"),
    ],
)
def test_value_status_tolerates_formats_but_not_other_values(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


def test_policy_can_turn_off_reformatted_identifiers() -> None:
    policy = TracePolicy(match_reformatted_identifiers=False)
    assert value_status("7200-4453-21", "PURCHASE NO: 7200445321", policy) == "mismatch"


def test_value_at_follows_list_paths() -> None:
    data = {"items": [{"qty": 1}, {"qty": 2}], "total": 3}

    assert value_at(data, "items[1].qty") == 2
    assert value_at(data, "total") == 3
    assert value_at(data, "items[5].qty") is None


def test_a_quote_is_located_in_the_text_whatever_its_spacing_and_punctuation() -> None:
    text = "Date: 15.03.2025.\nThe forklift hit a rack\nat the  north dock."
    span = locate_in_text(text, "The forklift hit a rack at the north dock")
    assert span is not None
    assert text[span[0] : span[1]] == "The forklift hit a rack\nat the  north dock"
    assert locate_in_text(text, "The truck hit a rack") is None


def test_with_sources_adds_the_citation_field_and_keeps_the_name() -> None:
    class Invoice(BaseModel):
        total: float | None = None

    plain = with_sources(Invoice)
    wrapped = with_sources(Invoice, wrapped=True)

    assert plain.__name__ == "Invoice"
    assert set(plain.model_fields) == {"total", SOURCES_FIELD}
    assert plain.model_validate({"total": 1}).field_sources == []
    assert wrapped.model_validate({"total": 1}).field_sources.items == []
    assert set(Invoice.model_fields) == {"total"}


def test_augment_adds_the_instruction_for_the_source_kind() -> None:
    class Invoice(BaseModel):
        total: float | None = None

    st = SourceTracing()
    text_task = st.augment(Invoice, "Extract the total", source="text")
    file_task = st.augment(Invoice, "Extract the total", source="files")

    assert text_task.prompt.startswith("Extract the total")
    assert "SOURCE CITATIONS" in text_task.prompt and "document: 1." in text_task.prompt
    assert "counting the attached files from 1" in file_task.prompt
    assert SOURCES_FIELD in text_task.model.model_fields
    with pytest.raises(ValueError):
        st.augment(Invoice, "x", source="audio")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        st.augment(text_task.model, "x")


def test_check_text_finds_quotes_and_removes_the_citations() -> None:
    text = "Invoice no. 100234\nTotal: 1.234,50 EUR"
    results = [
        {
            "total": 1234.5,
            "number": "999",
            SOURCES_FIELD: {
                "items": [
                    _cite("total", "Total: 1.234,50 EUR"),
                    _cite("number", "Invoice no. 999"),
                ]
            },
        }
    ]

    clean, report = SourceTracing().check_text(results, text)
    total, number = report.items

    assert clean == [{"total": 1234.5, "number": "999"}]
    assert SOURCES_FIELD in results[0]  # the input is not modified
    assert total.status == "found" and total.value_status == "match"
    assert total.verdict == "verified" and total.span is not None
    assert number.status == "not_found" and number.verdict == "check" and number.span is None
    assert report.summary() == {
        "verified": 1,
        "check": 1,
        "reworded": 0,
        "unchecked": 0,
        "total": 2,
        "coverage": 1.0,
    }


def test_check_text_accepts_a_single_result_dict_and_plain_list_citations() -> None:
    result = {"total": 10.0, SOURCES_FIELD: [_cite("total", "Total: 10,00")]}

    clean, report = SourceTracing().check_text(result, "Total: 10,00 EUR")

    assert clean == {"total": 10.0}
    assert report.items[0].verdict == "verified"


def test_results_without_citations_report_nothing_and_zero_coverage() -> None:
    clean, report = SourceTracing().check_text([{"place": "Depot"}], "text")

    assert clean == [{"place": "Depot"}]
    assert report.items == [] and report.coverage == 0.0
    assert report.summary()["total"] == 0


def test_coverage_counts_the_values_that_came_with_evidence() -> None:
    results = [
        {
            "a": "x",
            "b": 2,
            "c": None,
            "rows": [{"d": 1}, {"d": 2}],
            SOURCES_FIELD: {"items": [_cite("a", "x here"), _cite("rows[1].d", "d = 2")]},
        }
    ]

    _, report = SourceTracing().check_text(results, "x here d = 2")

    # a, b, rows[0].d and rows[1].d are values; c is empty. Two of four are cited.
    assert report.values == 4 and report.cited == 2 and report.coverage == 0.5


def test_a_value_longer_than_its_quote_is_checked_against_the_text() -> None:
    page = "010 6061-T6 Aluminium Alloy Round Bar O 12.700 (+/- 0.038) x 3658 mm Mill Length"
    citation = _cite("description", "6061-T6 Aluminium Alloy Round Bar")

    def verdict(value: str, text: str) -> str:
        results = [{"description": value, SOURCES_FIELD: [citation]}]
        return SourceTracing().check_text(results, text)[1].items[0].value_status

    assert verdict("6061-T6 Aluminium Alloy Round Bar; O 12.700 (+/- 0.038) x 3658 mm", page) == (
        "match"
    )
    assert verdict("6061-T6 Aluminium Alloy Round Bar; O 99.000 mm", page) == "mismatch"
    # The value's words elsewhere on the page are not evidence for it.
    elsewhere = page + " Note Special Handling Required"
    assert verdict("Special Handling Required", elsewhere) == "mismatch"


def test_traced_results_say_where_each_quote_is_and_which_record_it_is_for() -> None:
    text = "Report 1: slipped at the depot. Report 2: fell at the north dock."
    results = [
        {
            "incidents": [{"place": "Depot"}, {"place": "North dock"}],
            SOURCES_FIELD: {
                "items": [
                    _cite("incidents[1].place", "at the north dock"),
                    _cite("incidents[0].place", "was never written"),
                ]
            },
        }
    ]

    _, report = SourceTracing().check_text(results, text)
    second, first = report.items

    assert second.record == 1 and text[slice(*second.span)] == "at the north dock"
    # A quote that is not in the text is not located, and says so.
    assert first.record == 0 and first.span is None and first.status == "not_found"


def test_traced_values_are_flagged_only_when_there_is_something_to_check() -> None:
    text = (
        "Tapaturma 15.3.2025 klo 14.30. Virtanen sai lievän ruhjeen käteen. "
        "Sairauslomalla kaksi päivää."
    )
    entries = [
        ("date", "2025-03-15", "Tapaturma 15.3.2025"),  # another format: verified
        ("time", "15.30", "klo 14.30"),  # a different number: check
        ("injury", "Minor bruise", "lievän ruhjeen käteen"),  # own wording: reworded
        ("cause", "Slipped", "kaatui liukkaalla"),  # quote not in the text: check
        ("people", ["Virtanen"], "Virtanen"),  # list: unchecked
        ("days", 2, "sairauslomalla kaksi päivää"),  # a number in words: unchecked
        ("cost", Decimal("426.7"), "maksoi 340 euroa"),  # another number: check
    ]
    results = [
        {
            **{field: value for field, value, _ in entries},
            SOURCES_FIELD: {"items": [_cite(field, quote) for field, _, quote in entries]},
        }
    ]

    _, report = SourceTracing().check_text(results, text)

    assert {item.field: item.verdict for item in report.items} == {
        "date": "verified",
        "time": "check",
        "injury": "reworded",
        "cause": "check",
        "people": "unchecked",
        "days": "unchecked",
        "cost": "check",
    }


def test_the_policy_can_make_rewording_a_problem_and_short_quotes_not_evidence() -> None:
    text = "Virtanen sai lievän ruhjeen käteen."
    results = [
        {
            "injury": "Minor bruise",
            "who": "Virtanen",
            SOURCES_FIELD: [
                _cite("injury", "lievän ruhjeen käteen"),
                _cite("who", "Virtanen"),
            ],
        }
    ]

    _, strict = SourceTracing(TracePolicy(reworded_is_problem=True)).check_text(results, text)
    _, short = SourceTracing(TracePolicy(min_quote_words=2)).check_text(results, text)

    assert strict.items[0].verdict == "check"
    assert [item.verdict for item in short.items] == ["reworded", "check"]


def test_several_texts_are_checked_each_against_its_own_and_moved_quotes_are_reported() -> None:
    def record(total: float, quote: str) -> dict:
        return {"total": total, SOURCES_FIELD: {"items": [_cite("total", quote)]}}

    results = [record(10.0, "Total: 10,00"), record(20.0, "Total: 99,00")]
    texts = ["Total: 10,00 EUR", "Total: 20,00 EUR"]

    clean, report = SourceTracing().check_text(results, texts)
    first, second = report.items

    assert [r["total"] for r in clean] == [10.0, 20.0]
    assert first.status == "found" and first.document == 1 and first.record == 0
    # The second quote is not in the second text, nor in the first.
    assert second.status == "not_found" and second.document == 2 and second.record == 1

    # A quote the model attributed to the wrong text is still found, and says so.
    stray = [{"total": 10.0, SOURCES_FIELD: [_cite("total", "Total: 20,00", document=1)]}]
    _, report = SourceTracing().check_text(stray, texts)
    assert report.items[0].status == "moved" and report.items[0].document == 2


def test_citations_in_a_verification_envelope_are_read() -> None:
    wrapped = {
        "total": 1234.5,
        SOURCES_FIELD: {
            "items": [
                {
                    "field": {"value": "total"},
                    "document": {"value": 1},
                    "page": {"value": 1},
                    "quote": {"value": "Total: 1.234,50"},
                }
            ]
        },
    }

    _, report = SourceTracing().check_text(wrapped, "Total: 1.234,50 EUR")

    assert report.items[0].verdict == "verified"


def test_a_broken_citation_is_skipped() -> None:
    result = {"total": 1, SOURCES_FIELD: [{"field": "", "quote": "x"}, "text", _cite("total", "")]}

    _, report = SourceTracing().check_text(result, "text")

    assert report.items == []


def test_the_report_converts_to_plain_json() -> None:
    import json

    results = [{"total": 10.0, SOURCES_FIELD: [_cite("total", "Total: 10,00")]}]

    _, report = SourceTracing().check_text(results, "Total: 10,00 EUR")

    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["summary"]["verified"] == 1
    assert payload["sources"][0]["span"] == [0, 12]


# --- PDF -------------------------------------------------------------------------------


def _pdf(path: Path, *pages: str) -> Path:
    import pymupdf as fitz

    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 100), text)
    doc.save(path)
    return path


def test_check_pdf_gives_boxes_corrects_the_page_and_flags(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "po.pdf", "PO Number: PO-2025-15903", "TOTAL: $27,578.55")
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"not a pdf")
    data = {
        "po_number": "PO-2025-15903",
        "total": 27578.55,
        "items": [{"quantity": 2000}],
        "store": "K-Market",
    }
    results = {
        **data,
        SOURCES_FIELD: [
            _cite("po_number", "PO Number: PO-2025-15903"),
            _cite("total", "TOTAL: $27,578.55", page=1),
            _cite("items[0].quantity", "200 pcs"),
            _cite("po_number", "PO Number: PO-1999-00000"),
            _cite("store", "K-Market", document=2),
        ],
    }

    clean, report = SourceTracing().check_pdf(results, [pdf, image])
    found, moved, wrong_value, invented, image_source = report.items

    assert clean == data
    assert found.status == "found" and found.value_status == "match" and found.verdict == "verified"
    assert found.rects and found.value_rects
    assert all(0 <= r["x"] <= 1 and 0 <= r["y"] <= 1 for r in found.rects)
    # The model named page 1 for a quote that is on page 2: the page is corrected.
    assert moved.status == "moved" and moved.page == 2 and moved.cited_page == 1
    assert moved.verdict == "verified"
    assert wrong_value.status == "not_found" and wrong_value.verdict == "check"
    assert invented.status == "not_found" and invented.rects == []
    assert image_source.status == "no_text_layer" and image_source.verdict == "unchecked"
    assert report.documents == ["po.pdf", "receipt.jpg"]


def test_a_value_longer_than_its_quote_is_located_in_the_pdf(tmp_path: Path) -> None:
    import pymupdf as fitz

    doc = fitz.open()
    sheet = doc.new_page()
    sheet.insert_text((72, 72), "6061-T6 Aluminium Alloy Round Bar")
    sheet.insert_text((72, 90), "O 12.700 mm Mill Length")
    path = tmp_path / "po.pdf"
    doc.save(path)
    results = {
        "description": "6061-T6 Aluminium Alloy Round Bar; O 12.700 mm",
        SOURCES_FIELD: [_cite("description", "6061-T6 Aluminium Alloy Round Bar")],
    }

    _, report = SourceTracing().check_pdf(results, [path], cited_pages=False)
    item = report.items[0]
    assert item.status == "found" and item.value_status == "match"
    assert len(item.value_rects) >= 2

    sheet.insert_text((72, 140), "Note Special Handling Required")
    doc.save(path)
    results = {
        "description": "Special Handling Required",
        SOURCES_FIELD: [_cite("description", "6061-T6 Aluminium Alloy Round Bar")],
    }
    _, report = SourceTracing().check_pdf(results, [path], cited_pages=False)
    assert report.items[0].value_status == "mismatch"


def test_a_quote_is_found_in_whichever_of_several_pdfs_holds_it(tmp_path: Path) -> None:
    first = _pdf(tmp_path / "PO.pdf", "Order number 100")
    second = _pdf(tmp_path / "BOM.pdf", "Sawing length = 1153,00 mm")
    # Read together as one text, the model names document 1 for every quote.
    results = {
        "length": "1153mm",
        SOURCES_FIELD: [_cite("length", "Sawing length = 1153,00 mm")],
    }

    _, report = SourceTracing().check_pdf(results, [first, second])
    item = report.items[0]

    assert item.document == 2 and item.page == 1 and item.rects
    assert item.status == "moved" and report.documents == ["PO.pdf", "BOM.pdf"]


def test_a_pdf_without_text_is_reported_as_unchecked(tmp_path: Path) -> None:
    import pymupdf as fitz

    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "scan.pdf"
    doc.save(path)
    results = {"total": 1, SOURCES_FIELD: [_cite("total", "Total 1")]}

    _, report = SourceTracing().check_pdf(results, [path])

    assert report.items[0].status == "no_text_layer"
    assert report.items[0].verdict == "unchecked"


# --- the sample purchase orders (D8) -----------------------------------------------------


def test_the_sample_purchase_orders_are_checked_with_pages_and_boxes() -> None:
    po, po2 = EXAMPLES / "PO.pdf", EXAMPLES / "PO2.pdf"
    assert po.exists() and po2.exists()
    # The quotes are copied from the text of the PDFs; the model names document 1 and page 1
    # for all of them, which is wrong for the second file and for the page break.
    results = {
        "purchase_no": "7200-4453-21",
        "order_date": "2026-02-15",
        "items": [{"quantity": 6000}, {"quantity": 5000}],
        SOURCES_FIELD: [
            _cite("purchase_no", "PURCHASE NO: 7200445321"),
            _cite("order_date", "DATE: 02/15/2026"),
            _cite("items[0].quantity", "6,000 LB LB"),
            _cite("items[1].quantity", "5,000 LB LB"),
        ],
    }

    _, report = SourceTracing().check_pdf(results, [po2, po])
    by_field = {item.field: item for item in report.items}

    assert by_field["purchase_no"].verdict == "verified"
    assert by_field["order_date"].verdict == "verified"
    assert by_field["items[0].quantity"].page == 1 and by_field["items[0].quantity"].rects
    assert by_field["items[1].quantity"].page == 2
    assert by_field["items[1].quantity"].status == "moved"
    assert by_field["items[1].quantity"].cited_page == 1


# --- repeated quotes and value boxes ----------------------------------------------------------


def test_a_quote_that_occurs_twice_is_counted_and_can_be_made_a_check(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Quantity: 1 LB")
    page.insert_text((72, 300), "Quantity: 1 LB")
    path = tmp_path / "twice.pdf"
    doc.save(path)
    results = {"qty": 1, SOURCES_FIELD: [_cite("qty", "Quantity: 1 LB")]}

    _, report = SourceTracing().check_pdf(results, [path])
    _, strict = SourceTracing(TracePolicy(ambiguous_quote_is_check=True)).check_pdf(results, [path])
    item = report.items[0]

    assert item.occurrences == 2 and item.verdict == "verified"
    # The first occurrence is boxed: it is the upper one on the page.
    assert item.rects[0]["y"] < 0.2
    assert strict.items[0].verdict == "check"
    assert report.to_dict()["sources"][0]["occurrences"] == 2


def test_occurrences_are_counted_in_text_and_zero_when_not_found() -> None:
    text = "Total: 10,00 EUR\nTotal: 10,00 EUR\nVAT: 2,40 EUR"
    results = {
        "total": 10.0,
        "vat": 2.4,
        "other": "x",
        SOURCES_FIELD: [
            _cite("total", "Total: 10,00 EUR"),
            _cite("vat", "VAT: 2,40 EUR"),
            _cite("other", "was never written"),
        ],
    }

    _, report = SourceTracing().check_text(results, text)

    assert [item.occurrences for item in report.items] == [2, 1, 0]


@pytest.mark.parametrize(
    ("value", "quote", "words"),
    [
        ("7200-4453-21", "PURCHASE NO: 7200445321", 1),  # an identifier in another format
        ("2026-02-15", "DATE: 02/15/2026", 1),  # a date in another order
        (6000.0, "010 6061-T6 Aluminium Alloy Round Bar 6,000 LB LB", 1),  # a number as a float
    ],
)
def test_a_value_in_another_format_still_gets_its_own_box(value, quote, words) -> None:
    results = {"v": value, SOURCES_FIELD: [_cite("v", quote)]}

    _, report = SourceTracing().check_pdf(results, [EXAMPLES / "PO2.pdf"])
    item = report.items[0]

    assert item.verdict == "verified"
    assert len(item.value_rects) == words
    # The value box is one of the quote's boxes, not a box somewhere else.
    assert item.value_rects[0] in item.rects


def test_a_number_in_a_european_format_is_boxed_as_one_word(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Total: 1.234,50 EUR")
    path = tmp_path / "eur.pdf"
    doc.save(path)
    results = {"total": 1234.5, SOURCES_FIELD: [_cite("total", "Total: 1.234,50 EUR")]}

    _, report = SourceTracing().check_pdf(results, [path])
    item = report.items[0]

    assert item.verdict == "verified" and len(item.value_rects) == 1
    assert item.value_rects[0]["w"] < item.rects[0]["w"] * 3


def test_a_cited_document_number_beyond_the_files_is_searched_not_given_up_on() -> None:
    # Some models count pages as documents: page 2 of the only PDF is cited as document 2.
    results = {"q": "5,000 LB", SOURCES_FIELD: [_cite("q", "5,000 LB LB", document=2, page=2)]}

    _, report = SourceTracing().check_pdf(results, [EXAMPLES / "PO2.pdf"])
    item = report.items[0]

    # The page was right and there is one file, so it counts as found there.
    assert item.status == "found" and item.verdict == "verified"
    assert (item.document, item.page) == (1, 2) and item.rects


def test_a_cited_image_file_is_still_reported_as_having_no_text_layer(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"not a pdf")
    results = {"q": 1, SOURCES_FIELD: [_cite("q", "Total 1", document=1)]}

    _, report = SourceTracing().check_pdf(results, [image])

    assert report.items[0].status == "no_text_layer"
    assert report.items[0].verdict == "unchecked"


# --- the viewer example ------------------------------------------------------------------------


def test_the_viewer_example_writes_one_self_contained_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    import trace_viewer

    hostile = "</script><img src=x onerror=alert(1)>"
    results = {
        "purchase_no": "7200445321",
        "note": hostile,
        SOURCES_FIELD: [
            _cite("purchase_no", "PURCHASE NO: 7200445321"),
            _cite("note", hostile),
        ],
    }
    pdf = EXAMPLES / "PO2.pdf"
    clean, report = SourceTracing().check_pdf(results, [pdf])

    out = trace_viewer.write_trace_view(
        tmp_path / "view.html",
        pdf_paths=[pdf],
        report=report,
        clean_results=clean,
        task_prompt="Extract the number.\n\nEVIDENCE REQUEST",
        task_text="Extract the number.",
        notes=["a note"],
    )
    page = out.read_text(encoding="utf-8")

    assert "drawBoxes" in page and "PURCHASE NO: 7200445321" in page
    assert "data:image/jpeg;base64," in page and "EVIDENCE REQUEST" in page
    # The page needs nothing from outside, and a hostile quote can not break out of it.
    assert "http://" not in page and "https://" not in page
    assert hostile not in page


@pytest.mark.parametrize(
    ("verdict", "status", "value", "expected"),
    [
        ("verified", "found", "x", "agrees with the text"),
        ("check", "not_found", "x", "not found anywhere"),
        ("check", "found", 1.5, "different number or date"),
        ("reworded", "found", "x", "own words"),
        ("unchecked", "found", ["a"], "value is a list"),
        ("unchecked", "no_text_layer", "x", "no text layer"),
    ],
)
def test_the_viewer_explains_each_verdict(verdict, status, value, expected, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    import trace_viewer

    item = {"verdict": verdict, "status": status, "value": value, "page": 2}

    assert expected in trace_viewer.explain(item)
