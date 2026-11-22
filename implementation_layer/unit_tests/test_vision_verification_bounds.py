"""A verification value outside its bounds does not fail the extraction (#141 item 6).

Gemini's schema drops ``minimum``, ``maximum`` and ``maxLength``, and nothing
moved a provider's value inside them, so one score of 0.0 or one long reason made
``extract()`` raise. Offline: the model call is replaced by a canned answer.
"""

from __future__ import annotations

import pytest
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_components.vision_extractor import VerifiableField, VisionExtractor
from gaik.software_components.vision_extractor.vision_extractor import (
    _prepare_google_schema,
    _wrap_model_for_verification,
)
from pydantic import BaseModel, create_model


def _verifiable(value_type=str) -> type[BaseModel]:
    return create_model("Checked", __base__=VerifiableField, value=(value_type, ...))


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, 0.01),
        (-1, 0.01),
        (1.0, 1.0),
        # With a percent sign or above 10: a percentage; else moved into the
        # bounds (reviews of #317).
        (85, 0.85),
        ("85", 0.85),
        (100, 1.0),
        (150, 1.0),
        (1.2, 1.0),
        (4, 1.0),
        (10, 1.0),
        (10.5, 0.105),
        ("0.8", 0.8),
        ("0,9", 0.9),
        ("85%", 0.85),
        ("85,5 %", 0.855),
        ("4%", 0.04),
        ("0.5%", 0.01),
        ("high", 0.01),
        (None, 0.01),
        (float("nan"), 0.01),
        (float("inf"), 1.0),
        (True, 0.01),
        (0.5, 0.5),
    ],
)
def test_a_score_outside_the_bounds_is_moved_inside(score, expected):
    checked = _verifiable().model_validate(
        {"value": "x", "confidence_score": score, "confidence_reason": "r"}
    )

    assert checked.confidence_score == pytest.approx(expected)


def test_a_long_reason_is_cut_to_400_characters():
    model = _verifiable()

    long = model.model_validate(
        {"value": "x", "confidence_score": 0.5, "confidence_reason": "a" * 401}
    )
    missing = model.model_validate(
        {"value": "x", "confidence_score": 0.5, "confidence_reason": None}
    )
    exact = model.model_validate(
        {"value": "x", "confidence_score": 0.5, "confidence_reason": "b" * 400}
    )

    assert len(long.confidence_reason) == 400
    assert long.confidence_reason.endswith("…")
    assert missing.confidence_reason == ""
    assert exact.confidence_reason == "b" * 400


def test_the_schema_still_asks_for_the_bounds():
    properties = _verifiable().model_json_schema()["properties"]

    assert properties["confidence_score"] == {
        "maximum": 1.0,
        "minimum": 0.01,
        "title": "Confidence Score",
        "type": "number",
    }
    assert properties["confidence_reason"] == {
        "maxLength": 400,
        "title": "Confidence Reason",
        "type": "string",
    }


class Invoice(BaseModel):
    invoice_number: str
    total: float


def test_extract_with_out_of_range_verification_values_does_not_raise(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "invoice.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Invoice INV-7 Total 12.50", fontsize=11)
    document.save(pdf)
    document.close()
    requirements = ExtractionRequirements(
        use_case_name="Invoice",
        fields=[
            FieldSpec(field_name="invoice_number", field_type="str", description="Number"),
            FieldSpec(field_name="total", field_type="float", description="Total"),
        ],
    )
    # What the issue saw from Gemini, whose schema drops the bounds.
    canned = {
        "invoice_number": {
            "value": "INV-7",
            "confidence_score": 0.0,
            "confidence_reason": "x" * 401,
        },
        "total": {"value": 12.5, "confidence_score": 130, "confidence_reason": "Stated."},
    }
    extractor = VisionExtractor(
        api_config={"api_key": "unused", "model": "test-model"}, include_verification=True
    )
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (canned, None))

    result = extractor.extract(
        file_paths=[pdf],
        user_requirements="invoice number and total",
        extraction_model=Invoice,
        requirements=requirements,
    )

    number = result.data["invoice_number"]
    assert number["value"] == "INV-7"
    assert number["confidence_score"] == 0.01
    assert len(number["confidence_reason"]) == 400
    assert result.data["total"]["confidence_score"] == 1.0
    assert result.data["total"]["found_in_text"] is True


def test_gemini_still_gets_the_score_without_its_bounds():
    google = _prepare_google_schema(_wrap_model_for_verification(Invoice).model_json_schema())

    score = google["properties"]["total"]["properties"]["confidence_score"]
    assert score == {"type": "number"}
