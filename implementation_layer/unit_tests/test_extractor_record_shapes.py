"""How DataExtractor and VisionExtractor read the shape of a record (issue #141).

Offline: the model call is replaced by a canned answer.
"""

from __future__ import annotations

from unittest import mock

import pytest
from gaik.software_components.extractor import (
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.extractor.schema import _holds_items
from gaik.software_components.vision_extractor import VisionExtractor


def _requirements(*fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="test", fields=list(fields))


def _extract_one(record: dict, requirements) -> dict:
    """DataExtractor._extract_one with the model's answer replaced by ``record``."""
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.config = {"model": "test-model"}
    extractor.client = object()
    extractor.model = "test-model"
    extractor.temperature = 0.0
    extractor.reasoning_effort = None
    parsed = type("P", (), {"model_dump": lambda self: dict(record)})()
    message = type("M", (), {"parsed": parsed})()
    resp = type("R", (), {"choices": [type("C", (), {"message": message})()], "usage": None})()
    with mock.patch("gaik.software_components.extractor.extractor._parse_with", return_value=resp):
        result, _ = extractor._extract_one(
            doc="d", extraction_model=object, requirements=requirements, user_requirements="u"
        )
    return result


@pytest.fixture
def invoice() -> ExtractionRequirements:
    return _requirements(
        FieldSpec(field_name="invoice_number", field_type="str", description="Number"),
        FieldSpec(field_name="invoice_date", field_type="date", description="Invoice date"),
        FieldSpec(field_name="total", field_type="float", description="Total"),
        FieldSpec(field_name="line_items", field_type="list[dict]", description="Rows"),
    )


@pytest.fixture
def answer() -> dict:
    return {
        "invoice_number": None,
        "invoice_date": "11/05/2026",
        "total": 3.0,
        "line_items": [{"product": "Bolt", "qty": 3}],
    }


def test_a_flat_records_own_list_dict_field_is_not_read_as_its_items(invoice, answer):
    result = _extract_one(answer, invoice)

    # The rows come back as the model wrote them, without the record's fields.
    assert result["line_items"] == [{"product": "Bolt", "qty": 3}]
    # And the record's own policies run: a null in a required text field is "".
    assert result["invoice_number"] == ""
    assert result["invoice_date"] == "2026-05-11"
    assert result["total"] == 3.0


def test_vision_post_process_reads_a_flat_list_dict_field_the_same_way(invoice, answer):
    result = VisionExtractor._post_process(None, answer, invoice)

    assert result["line_items"] == [{"product": "Bolt", "qty": 3}]
    assert result["invoice_number"] == ""
    assert result["invoice_date"] == "2026-05-11"


def test_vision_blank_numbers_in_a_flat_list_dict_field_are_left_as_written():
    requirements = _requirements(
        FieldSpec(field_name="qty", field_type="int", description="Quantity"),
        FieldSpec(field_name="rows", field_type="list[dict]", description="Rows"),
    )
    raw = {"qty": "", "rows": [{"qty": ""}]}

    repaired = VisionExtractor._normalize_numeric_placeholders(raw, requirements)

    assert repaired == {"qty": None, "rows": [{"qty": ""}]}


@pytest.fixture
def event_rows() -> ExtractionRequirements:
    # A nested-list schema whose container is named like one of its row fields.
    return _requirements(
        FieldSpec(field_name="event", field_type="str", description="What happened"),
        FieldSpec(field_name="when", field_type="date", description="Date"),
    )


def test_a_container_named_like_a_row_field_still_holds_the_items(event_rows):
    assert _holds_items("event", [{"event": "Fire", "when": "2026-01-02"}], event_rows)
    assert _holds_items("event", [], event_rows)

    result = _extract_one({"event": [{"event": None, "when": "02.01.2026"}]}, event_rows)

    assert result == {"event": [{"event": "", "when": "2026-01-02"}]}


def test_empty_and_scalar_lists_of_a_flat_record_are_its_own_fields(invoice):
    tagged = _requirements(
        FieldSpec(field_name="tags", field_type="list[str]", description="Tags"),
    )
    assert not _holds_items("line_items", [], invoice)
    assert not _holds_items("line_items", [{"product": "Bolt"}], invoice)
    assert not _holds_items("tags", [], tagged)
    assert not _holds_items("tags", ["a"], tagged)
    assert not _holds_items("total", 3.0, invoice)
    # A container the record does not name is recognised whether or not it has items.
    assert _holds_items("records", [], invoice)
    assert _holds_items("records", [{"invoice_number": "1"}], invoice)


def _pdf(path, text: str):
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    document.new_page().insert_text((72, 72), text, fontsize=11)
    document.save(path)
    document.close()
    return path


def _wrapped(value) -> dict:
    return {"value": value, "confidence_score": 0.9, "confidence_reason": "Stated."}


def test_vision_repairs_blank_numbers_in_every_child_collection(tmp_path, monkeypatch):
    from gaik.software_components.extractor import (
        ChildRequirements,
        CompositeExtractionRequirements,
    )
    from gaik.software_components.extractor.schema import _create_parent_with_nested_list_model

    children = [
        ChildRequirements(
            container_name="line_items",
            container_description="Lines",
            requirements=_requirements(
                FieldSpec(field_name="qty", field_type="int", description="Quantity")
            ),
        ),
        ChildRequirements(
            container_name="payments",
            container_description="Payment terms",
            requirements=_requirements(
                FieldSpec(field_name="days", field_type="int", description="Days")
            ),
        ),
    ]
    parent = _requirements(
        FieldSpec(field_name="order_number", field_type="str", description="Order number")
    )
    requirements = CompositeExtractionRequirements(parent_requirements=parent, children=children)
    model = _create_parent_with_nested_list_model(parent_requirements=parent, children=children)
    canned = {
        "order_number": _wrapped("PO-1"),
        "line_items": [{"qty": _wrapped("")}],
        "payments": [{"days": _wrapped("")}],
    }
    extractor = VisionExtractor(
        api_config={"api_key": "unused", "model": "test-model"}, include_verification=True
    )
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (canned, None))

    result = extractor.extract(
        file_paths=[_pdf(tmp_path / "po.pdf", "Order PO-1")],
        user_requirements="order",
        extraction_model=model,
        requirements=requirements,
    )

    assert result.data["line_items"][0]["qty"]["value"] is None
    assert result.data["payments"][0]["days"]["value"] is None
