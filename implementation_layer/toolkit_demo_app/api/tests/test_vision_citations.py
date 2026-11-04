"""Tests for the Vision Extractor demo's source citations."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from api.utils import citations
from api.utils.citations import UploadedDocument, check_sources, value_status
from pydantic import BaseModel

EXAMPLES = Path(__file__).parent.parent.parent / "public" / "vision-extractor-example"


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (3000, "Quantity: 3.000 kg", "match"),
        (3000, "Quantity: 3,000 kg", "match"),
        (3.0, "Quantity: 3,000 kg", "match"),
        (27578.55, "TOTAL: $27,578.55", "match"),
        (1234.5, "Total: 1.234,50 EUR", "match"),
        (2000, "Quantity: 200 pcs", "mismatch"),
        (1234, "Total: 1 234 EUR", "match"),
        ("010", "010 6061-T6 Aluminium Alloy Round Bar", "match"),
        (6061, "010 6061-T6 Aluminium Alloy Round Bar", "match"),
        ("7200-4453-21", "PURCHASE NO: 7200445321", "match"),
        ("7200-4453-22", "PURCHASE NO: 7200445321", "mismatch"),
        ("2025-10-12", "PO Date: October 12, 2025", "match"),
        ("2025-04-11", "11.04.2025", "match"),
        ("2025-04-12", "11.04.2025", "mismatch"),
        ("PO-2025-15903", "PO Number: PO-2025-15903", "match"),
        ("Acme Ltd", "Supplier Name: Precision Steel", "mismatch"),
        (True, "[x] Eligible", "unchecked"),
        ("approved_with_remarks", "[X] Approved with remarks", "match"),
        ("not_ok", "Waste sorted and removed [ ] [X] [ ]", "unchecked"),
        (None, "anything", "unchecked"),
    ],
)
def test_value_status_tolerates_formats_but_not_other_values(value, quote, expected) -> None:
    assert value_status(value, quote) == expected


def test_with_sources_adds_the_citation_list_and_keeps_the_name() -> None:
    class Invoice(BaseModel):
        total: float | None = None

    model = citations.with_sources(Invoice)

    assert model.__name__ == "Invoice"
    assert set(model.model_fields) == {"total", citations.SOURCES_FIELD}
    assert model.model_validate({"total": 1}).field_sources == []


def test_value_at_follows_list_paths() -> None:
    data = {"items": [{"qty": 1}, {"qty": 2}], "total": 3}

    assert citations.value_at(data, "items[1].qty") == 2
    assert citations.value_at(data, "total") == 3
    assert citations.value_at(data, "items[5].qty") is None


def test_check_sources_verifies_corrects_and_flags(tmp_path: Path) -> None:
    pdf = tmp_path / "po.pdf"
    shutil.copy(EXAMPLES / "PO.pdf", pdf)
    image = tmp_path / "receipt.jpg"
    shutil.copy(EXAMPLES / "receipt.jpg", image)
    documents = [UploadedDocument("PO.pdf", pdf), UploadedDocument("receipt.jpg", image)]
    data = {
        "po_number": "PO-2025-15903",
        "total": 27578.55,
        "items": [{"quantity": 2000}],
        "store": "K-Market",
    }
    raw = [
        {"field": "po_number", "document": 1, "page": 1, "quote": "PO Number: PO-2025-15903"},
        {"field": "total", "document": 1, "page": 2, "quote": "TOTAL: $27,578.55"},
        {"field": "items[0].quantity", "document": 1, "page": 1, "quote": "200 pcs"},
        {"field": "po_number", "document": 1, "page": 1, "quote": "PO Number: PO-1999-00000"},
        {"field": "store", "document": 2, "page": 1, "quote": "K-Market"},
    ]

    result = check_sources(raw, data, documents)
    found, moved, wrong_value, invented, image_source = result["sources"]

    assert found["status"] == "found" and found["value_status"] == "match"
    assert found["rects"] and found["value_rects"]
    assert all(0 <= r["x"] <= 1 and 0 <= r["y"] <= 1 for r in found["rects"])
    # The PO has one page: the quote is there, so the page is corrected.
    assert moved["status"] == "moved" and moved["page"] == 1
    assert wrong_value["status"] == "found" and wrong_value["value_status"] == "mismatch"
    assert invented["status"] == "not_found" and invented["rects"] == []
    assert image_source["status"] == "no_text_layer"
    # The image is shown too, scaled down, for a person to compare.
    assert set(result["pages"]) == {"1:1", "2:1"}
    assert result["pages"]["1:1"]["image"].startswith("data:image/jpeg;base64,")
    assert result["pages"]["2:1"]["image"].startswith("data:image/jpeg;base64,")
    assert max(result["pages"]["2:1"]["width"], result["pages"]["2:1"]["height"]) <= 1400


@pytest.mark.asyncio
async def test_extract_with_sources_asks_for_them_and_returns_them_checked(monkeypatch) -> None:
    import io
    from types import SimpleNamespace

    import gaik.software_components.vision_extractor as component
    from api.routers import vision_extractor as route
    from fastapi import UploadFile

    captured: dict = {}

    class FakeVisionExtractor:
        def __init__(self, **kwargs):
            captured["constructor"] = kwargs

        def extract(self, **kwargs):
            captured["extract"] = kwargs
            return SimpleNamespace(
                data={
                    "po_number": "PO-2025-15903",
                    "field_sources": [
                        {
                            "field": "po_number",
                            "document": 1,
                            "page": 1,
                            "quote": "PO Number: PO-2025-15903",
                        }
                    ],
                },
                verification=None,
                model="m",
                documents_processed=1,
                duration_s=0.1,
                usage=None,
            )

    monkeypatch.setattr(component, "VisionExtractor", FakeVisionExtractor)
    task, schema, _ = route._load_example_schema()
    upload = UploadFile(filename="PO.pdf", file=io.BytesIO((EXAMPLES / "PO.pdf").read_bytes()))

    response = await route.extract_vision(
        files=[upload],
        user_requirements=task,
        schema_id=route.EXAMPLE_SCHEMA_ID,
        model_provider="openai",
        model=route._server_model(),
        reasoning_effort="low",
        merge_table=False,
        additional_instructions=None,
        include_verification=False,
        include_sources=True,
    )

    assert citations.SOURCES_FIELD in captured["extract"]["extraction_model"].model_fields
    assert "SOURCE CITATIONS" in captured["constructor"]["additional_instructions"]
    assert response.data == {"po_number": "PO-2025-15903"}
    assert response.sources["sources"][0]["status"] == "found"
    assert response.sources["sources"][0]["value_status"] == "match"


def test_check_text_sources_finds_quotes_in_pasted_text() -> None:
    text = "Invoice no. 100234\nTotal: 1.234,50 EUR"
    raw = {
        "items": [
            {"field": "total", "document": 1, "page": 1, "quote": "Total: 1.234,50 EUR"},
            {"field": "number", "document": 1, "page": 1, "quote": "Invoice no. 999"},
        ]
    }

    result = citations.check_text_sources(raw, {"total": 1234.5, "number": "999"}, text)
    total, number = result["sources"]

    assert total["status"] == "found" and total["value_status"] == "match"
    assert number["status"] == "not_found"
    assert result["pages"] == {}


@pytest.mark.asyncio
async def test_text_extraction_with_sources_asks_for_them_and_checks_the_text() -> None:
    from api.routers import extractor as route

    captured: dict = {}

    class FakeExtractor:
        def extract(self, **kwargs):
            captured.update(kwargs)
            return [
                {
                    "total": 1234.5,
                    citations.SOURCES_FIELD: {
                        "items": [
                            {"field": "total", "document": 1, "page": 1, "quote": "Total: 1.234,50"}
                        ]
                    },
                }
            ]

    class Plain(BaseModel):
        total: float | None = None

    response = await route._run_extraction(
        FakeExtractor(), Plain, None, "Extract the total", ["Total: 1.234,50 EUR"], True
    )

    assert citations.SOURCES_FIELD in captured["extraction_model"].model_fields
    assert "SOURCE CITATIONS" in captured["user_requirements"]
    assert response.results == [{"total": 1234.5}]
    assert response.sources["sources"][0]["status"] == "found"
    assert response.raw_sources[0]["items"][0]["quote"] == "Total: 1.234,50"


def test_a_formatted_identifier_matches_the_document_s_own_spelling() -> None:
    # The task asked for 7200-4453-21; the document, and so the quote, has 7200445321.
    assert citations.value_status("7200-4453-21", "PURCHASE NO: 7200445321") == "match"
    assert citations.value_status("7200-4453-21", "PURCHASE NO: 7200445322") == "mismatch"
    # A prefix or a piece of the identifier is another value, not a formatting of it.
    assert citations.value_status("7200-4453", "PURCHASE NO: 7200445321") == "mismatch"
    assert citations.value_status("4453-21", "PURCHASE NO: 7200445321") == "mismatch"
    # Several words of the quote can spell the value: 7200 4453 21 for 7200445321.
    assert citations.value_status("7200445321", "PO 7200 4453 21") == "match"
    # Three groups of digits are a date only when they can be a year, a month and a day.
    assert citations.value_status("2025-04-11", "Date 11.04.2025") == "match"
    assert citations.value_status("2025-04-11", "Date 12.04.2025") == "mismatch"


def test_a_value_longer_than_its_quote_is_checked_against_the_page_text() -> None:
    page = "010 6061-T6 Aluminium Alloy Round Bar O 12.700 (+/- 0.038) x 3658 mm Mill Length"
    data = {"description": "6061-T6 Aluminium Alloy Round Bar; O 12.700 (+/- 0.038) x 3658 mm"}
    raw = {
        "items": [
            {
                "field": "description",
                "document": 1,
                "page": 1,
                "quote": "6061-T6 Aluminium Alloy Round Bar",
            }
        ]
    }
    result = citations.check_text_sources(raw, data, page)
    assert result["sources"][0]["value_status"] == "match"

    wrong = {"description": "6061-T6 Aluminium Alloy Round Bar; O 99.000 mm"}
    result = citations.check_text_sources(raw, wrong, page)
    assert result["sources"][0]["value_status"] == "mismatch"

    # The value's words elsewhere on the page are not evidence for it: it must run through
    # the quote.
    elsewhere = page + " Note Special Handling Required"
    other = {"description": "Special Handling Required"}
    result = citations.check_text_sources(raw, other, elsewhere)
    assert result["sources"][0]["value_status"] == "mismatch"


def test_a_value_longer_than_its_quote_is_located_in_the_pdf(tmp_path) -> None:
    import fitz

    pdf = fitz.open()
    sheet = pdf.new_page()
    sheet.insert_text((72, 72), "6061-T6 Aluminium Alloy Round Bar")
    sheet.insert_text((72, 90), "O 12.700 mm Mill Length")
    path = tmp_path / "po.pdf"
    pdf.save(path)
    raw = {
        "items": [
            {
                "field": "description",
                "document": 1,
                "page": 1,
                "quote": "6061-T6 Aluminium Alloy Round Bar",
            }
        ]
    }
    data = {"description": "6061-T6 Aluminium Alloy Round Bar; O 12.700 mm"}

    result = citations.check_sources(
        raw, data, [citations.UploadedDocument("po.pdf", path)], cited_pages=False
    )
    source = result["sources"][0]
    assert source["status"] == "found" and source["value_status"] == "match"
    assert len(source["value_rects"]) >= 2

    sheet.insert_text((72, 140), "Note Special Handling Required")
    pdf.save(path)
    result = citations.check_sources(
        raw,
        {"description": "Special Handling Required"},
        [citations.UploadedDocument("po.pdf", path)],
        cited_pages=False,
    )
    assert result["sources"][0]["value_status"] == "mismatch"


@pytest.mark.asyncio
async def test_several_documents_each_get_their_own_checked_sources() -> None:
    from api.routers import extractor as route

    def record(total: float, quote: str) -> dict:
        return {
            "total": total,
            citations.SOURCES_FIELD: {
                "items": [{"field": "total", "document": 1, "page": 1, "quote": quote}]
            },
        }

    class FakeExtractor:
        def extract(self, **kwargs):
            return [record(10.0, "Total: 10,00"), record(20.0, "Total: 99,00")]

    class Plain(BaseModel):
        total: float | None = None

    response = await route._run_extraction(
        FakeExtractor(),
        Plain,
        None,
        "Extract the total",
        ["Total: 10,00 EUR", "Total: 20,00 EUR"],
        True,
    )

    assert response.document_count == 2
    assert [r["total"] for r in response.results] == [10.0, 20.0]
    assert len(response.raw_sources) == 2
    first, second = response.document_sources
    assert first["sources"][0]["status"] == "found"
    # The second quote is checked against the second document, not the first.
    assert second["sources"][0]["status"] == "not_found"
    assert response.sources == first


@pytest.mark.asyncio
async def test_trace_locates_text_quotes_in_the_pdf_without_trusting_the_page() -> None:
    import io
    import json

    from api.routers import extractor as route
    from fastapi import UploadFile

    upload = UploadFile(filename="PO.pdf", file=io.BytesIO((EXAMPLES / "PO.pdf").read_bytes()))
    raw = {
        "items": [{"field": "po", "document": 1, "page": 3, "quote": "PO Number: PO-2025-15903"}]
    }

    result = await route.trace_sources(
        file=[upload], sources=json.dumps(raw), data=json.dumps({"po": "PO-2025-15903"})
    )
    source = result["sources"][0]

    assert source["status"] == "found" and source["page"] == 1
    assert source["rects"] and "1:1" in result["pages"]


@pytest.mark.asyncio
async def test_trace_finds_a_quote_in_whichever_of_several_pdfs_holds_it() -> None:
    import io
    import json

    import fitz
    from api.routers import extractor as route
    from fastapi import UploadFile

    def pdf(text: str) -> bytes:
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), text)
        return doc.tobytes()

    uploads = [
        UploadFile(filename="PO.pdf", file=io.BytesIO(pdf("Order number 100"))),
        UploadFile(filename="BOM.pdf", file=io.BytesIO(pdf("Sawing length = 1153,00 mm"))),
    ]
    # Read together as one text, the model names document 1 for every quote.
    raw = {
        "items": [
            {"field": "length", "document": 1, "page": 1, "quote": "Sawing length = 1153,00 mm"}
        ]
    }

    result = await route.trace_sources(
        file=uploads, sources=json.dumps(raw), data=json.dumps({"length": "1153mm"})
    )
    source = result["sources"][0]

    assert source["document"] == 2 and source["page"] == 1
    assert source["rects"] and "2:1" in result["pages"]
    assert result["documents"] == ["PO.pdf", "BOM.pdf"]
