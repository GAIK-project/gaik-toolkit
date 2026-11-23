"""VisionExtractor checks extracted values against the PDF text layer (issue #56).

``confidence_score`` is the model's own rating, so a misread value can still come
back as 1.0. ``found_in_text`` and ``page`` are an independent check. Offline: the
model call is replaced by a canned answer.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

fitz = pytest.importorskip("fitz")

from gaik.software_components.extractor.schema import (  # noqa: E402
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.vision_extractor import VisionExtractor  # noqa: E402
from gaik.software_components.vision_extractor import text_layer  # noqa: E402


def _pdf(path: Path, pages: list[str]) -> Path:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    document.save(path)
    document.close()
    return path


@pytest.fixture
def invoice(tmp_path):
    return _pdf(
        tmp_path / "invoice.pdf",
        [
            "Invoice INV-2026-0042\nVendor no: V-518834\nDate: 12.1.2026",
            "Total due: 1 234,50 EUR\nPaid: no",
        ],
    )


def test_locate_tolerates_formatting_but_not_a_misread(invoice):
    pages = text_layer.read_pdf_pages([invoice])
    assert text_layer.locate("V-518834", pages) == (True, 1)
    assert text_layer.locate("v 518834", pages) == (True, 1)
    # The issue's case: one digit dropped by the model.
    assert text_layer.locate("V-51834", pages) == (False, None)
    assert text_layer.locate(Decimal("1234.50"), pages) == (True, 2)
    assert text_layer.locate(1234.5, pages) == (True, 2)
    assert text_layer.locate("2026-01-12", pages) == (True, 1)
    assert text_layer.locate("5", pages) == (False, None)  # whole tokens only
    assert text_layer.locate(True, pages) == (None, None)
    assert text_layer.locate(None, pages) == (None, None)


def test_no_text_layer_means_unchecked(tmp_path):
    image_only = tmp_path / "scan.png"
    image_only.write_bytes(b"not read")
    assert text_layer.read_pdf_pages([image_only]) == []
    assert text_layer.locate("V-518834", []) == (None, None)


def test_list_rows_are_annotated(invoice):
    pages = text_layer.read_pdf_pages([invoice])
    data = {"vendor": "V-518834", "lines": [{"code": "INV-2026-0042"}, {"code": "X-1"}]}
    verification = {
        "vendor": {"confidence_score": 1.0, "confidence_reason": "explicit"},
        "lines": [
            {"code": {"confidence_score": 1.0, "confidence_reason": "explicit"}},
            {"code": {"confidence_score": 0.9, "confidence_reason": "explicit"}},
        ],
    }
    result = text_layer.annotate(data, verification, pages)
    assert result["vendor"]["found_in_text"] is True
    assert result["lines"][0]["code"] == {
        "confidence_score": 1.0,
        "confidence_reason": "explicit",
        "found_in_text": True,
        # Plain page texts do not say which file they come from.
        "file": None,
        "page": 1,
    }
    assert result["lines"][1]["code"]["found_in_text"] is False


class Invoice(BaseModel):
    vendor_number: str
    total: float


def test_extract_flags_a_confident_misread(invoice, monkeypatch):
    extractor = VisionExtractor(
        api_config={"api_key": "unused", "model": "test-model"},
        include_verification=True,
    )
    requirements = ExtractionRequirements(
        use_case_name="Invoice",
        fields=[
            FieldSpec(field_name="vendor_number", field_type="str", description="Vendor"),
            FieldSpec(field_name="total", field_type="float", description="Total"),
        ],
    )
    canned = {
        "vendor_number": {
            "value": "V-51834",
            "confidence_score": 1.0,
            "confidence_reason": "Stated explicitly.",
        },
        "total": {"value": 1234.5, "confidence_score": 1.0, "confidence_reason": "Stated."},
    }
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (canned, None))

    result = extractor.extract(
        file_paths=[invoice],
        user_requirements="vendor number and total",
        extraction_model=Invoice,
        requirements=requirements,
    )

    vendor = result.data["vendor_number"]
    assert vendor["value"] == "V-51834"
    assert vendor["confidence_score"] == 1.0
    assert vendor["found_in_text"] is False and vendor["page"] is None
    assert vendor["file"] is None
    assert result.data["total"]["found_in_text"] is True
    assert result.data["total"]["file"] == "invoice.pdf"
    assert result.data["total"]["page"] == 2
    assert result.verification["vendor_number"]["found_in_text"] is False


@pytest.fixture
def order_files(tmp_path):
    """The issue's case (#141 item 7): a two-page PO, then a BOM."""
    po = _pdf(tmp_path / "PO.pdf", ["Purchase order PO-77", "Delivery terms FCA"])
    bom = _pdf(tmp_path / "BOM1.pdf", ["Part number BX-4410\nQty 12"])
    return po, bom


def test_each_file_is_numbered_from_its_own_first_page(order_files):
    po, bom = order_files
    pages = text_layer.read_pdf_page_texts([po, bom])

    assert [(page.file, page.page) for page in pages] == [
        ("PO.pdf", 1),
        ("PO.pdf", 2),
        ("BOM1.pdf", 1),
    ]
    assert text_layer.locate("BX-4410", pages) == (True, 1)
    entry = {"confidence_score": 1.0, "confidence_reason": "Stated."}
    result = text_layer.annotate(
        {"part": "BX-4410", "terms": "FCA"}, {"part": entry, "terms": entry}, pages
    )
    assert result["part"] == {**entry, "found_in_text": True, "file": "BOM1.pdf", "page": 1}
    assert result["terms"] == {**entry, "found_in_text": True, "file": "PO.pdf", "page": 2}


def test_an_unreadable_pdf_does_not_shift_the_pages_of_the_next(order_files, tmp_path):
    po, bom = order_files
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7 not really")

    pages = text_layer.read_pdf_page_texts([broken, bom, po])

    assert [(page.file, page.page) for page in pages] == [
        ("BOM1.pdf", 1),
        ("PO.pdf", 1),
        ("PO.pdf", 2),
    ]
    assert text_layer.read_pdf_pages([broken, bom]) == [pages[0].text]


def test_extract_names_the_file_and_its_own_page(order_files, monkeypatch):
    po, bom = order_files
    extractor = VisionExtractor(
        api_config={"api_key": "unused", "model": "test-model"},
        include_verification=True,
    )
    requirements = ExtractionRequirements(
        use_case_name="Order",
        fields=[FieldSpec(field_name="part_number", field_type="str", description="Part")],
    )

    class Order(BaseModel):
        part_number: str

    canned = {
        "part_number": {"value": "BX-4410", "confidence_score": 0.9, "confidence_reason": "BOM."}
    }
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (canned, None))

    result = extractor.extract(
        file_paths=[po, bom],
        user_requirements="part number",
        extraction_model=Order,
        requirements=requirements,
    )

    assert result.data["part_number"]["file"] == "BOM1.pdf"
    assert result.data["part_number"]["page"] == 1
