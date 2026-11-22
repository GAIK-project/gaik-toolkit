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


@pytest.fixture
def ticket() -> ExtractionRequirements:
    return _requirements(
        FieldSpec(field_name="status", field_type="str", description="S", enum=["open", "closed"]),
        FieldSpec(field_name="amount", field_type="float", description="Amount"),
        FieldSpec(field_name="owner", field_type="str", description="Owner"),
    )


def test_an_empty_list_on_a_scalar_field_of_a_flat_record_is_that_fields_value(ticket, event_rows):
    answer = {"status": [], "amount": ""}

    assert not _holds_items("status", [], ticket, answer)
    # The record is just the container: a container named like a row field, empty.
    assert _holds_items("event", [], event_rows, {"event": []})


@pytest.mark.parametrize("extractor", ["vision", "data"])
def test_an_empty_list_on_a_scalar_field_keeps_the_record_policies(ticket, extractor):
    answer = {"status": [], "amount": ""}

    if extractor == "vision":
        result = VisionExtractor._post_process(None, dict(answer), ticket)
    else:
        result = _extract_one(answer, ticket)

    # The record's policies ran: the choice falls back, the blank number is None and
    # the missing required field is filled in.
    assert result == {"status": "", "amount": None, "owner": ""}


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


# ---------------------------------------------------------------------------
# #141 item 4: a list[dict] field in a flat parse becomes a child collection
# ---------------------------------------------------------------------------


def _structure(kind: str, **extra):
    from gaik.software_components.extractor.schema import StructureAnalysis

    return StructureAnalysis(
        structure_type=kind,
        parent_container_name="",
        parent_description="",
        item_description="",
        reasoning="test",
        **extra,
    )


def _generate(monkeypatch, analysis, flat_fields, row_fields):
    """parse_nested_requirements with the structure and both parses canned."""
    from gaik.software_components.extractor import schema as schema_module

    calls = []

    def parse(task, *, parse_mode="normal", **kwargs):
        calls.append(parse_mode)
        row = parse_mode == "repeated_item"
        return ExtractionRequirements(
            use_case_name="line item" if row else "invoice",
            fields=[f.model_copy(deep=True) for f in (row_fields if row else flat_fields)],
        )

    monkeypatch.setattr(schema_module, "detect_structure_type", lambda *a, **k: analysis)
    monkeypatch.setattr(schema_module, "parse_user_requirements", parse)
    model, requirements, analysis = schema_module.parse_nested_requirements(
        "Extract the invoice number and the table of line items.",
        client=object(),
        model="test-model",
    )
    return model, requirements, analysis, calls


def _open_objects(node) -> list:
    """Every object node a strict schema refuses: additionalProperties left open."""
    found = []
    if isinstance(node, dict):
        if node.get("additionalProperties") is True:
            found.append(node)
        for value in node.values():
            found += _open_objects(value)
    elif isinstance(node, list):
        for value in node:
            found += _open_objects(value)
    return found


_LINE_ITEMS = FieldSpec(
    field_name="line_items", field_type="list[dict]", description="Line items with product, qty"
)
_ROW = [
    FieldSpec(field_name="product", field_type="str", description="Product"),
    FieldSpec(field_name="qty", field_type="int", description="Quantity"),
]
_NUMBER = FieldSpec(field_name="invoice_number", field_type="str", description="Number")


def test_a_flat_parse_with_a_list_dict_field_gets_a_typed_child_collection(monkeypatch):
    from gaik.software_components.extractor import CompositeExtractionRequirements

    model, requirements, analysis, calls = _generate(
        monkeypatch, _structure("flat"), [_NUMBER, _LINE_ITEMS], _ROW
    )

    # The flat fields are kept as parsed, not parsed again.
    assert calls == ["normal", "repeated_item"]
    assert isinstance(requirements, CompositeExtractionRequirements)
    assert [f.field_name for f in requirements.parent_requirements.fields] == ["invoice_number"]
    [child] = requirements.children
    assert child.container_name == "line_items"
    assert child.nullable is False
    assert [f.field_name for f in child.requirements.fields] == ["product", "qty"]
    assert analysis.structure_type == "parent_with_nested_list"
    assert [c.container_name for c in analysis.child_containers] == ["line_items"]
    assert _open_objects(model.model_json_schema()) == []
    record = model.model_validate(
        {"invoice_number": "1", "line_items": [{"product": "Bolt", "qty": 3}]}
    ).model_dump()
    assert record == {"invoice_number": "1", "line_items": [{"product": "Bolt", "qty": 3}]}


def test_a_flat_collection_the_task_lets_be_null_stays_nullable(monkeypatch, tmp_path):
    from gaik.software_components.extractor.saved_schema import (
        build_model,
        describe_model,
        rebuild_from_requirements,
    )
    from gaik.software_components.vision_extractor.vision_extractor import (
        _make_schema_strict,
        _prepare_google_schema,
        _save_schema_to_python,
        _wrap_model_for_verification,
    )

    nullable_items = _LINE_ITEMS.model_copy(update={"nullable": True})
    model, requirements, _, _ = _generate(
        monkeypatch, _structure("flat"), [_NUMBER, nullable_items], _ROW
    )

    assert requirements.children[0].nullable is True
    assert model.model_validate({"invoice_number": "1", "line_items": None}).line_items is None
    assert model.model_validate({"invoice_number": "1"}).line_items is None
    rows = model.model_validate(
        {"invoice_number": "1", "line_items": [{"product": "Bolt", "qty": 3}]}
    ).line_items
    assert rows[0].qty == 3
    # Every provider schema still has typed rows.
    assert _open_objects(_make_schema_strict(model.model_json_schema())) == []
    google = _prepare_google_schema(model.model_json_schema())
    assert google["properties"]["line_items"]["nullable"] is True
    assert set(google["properties"]["line_items"]["items"]["properties"]) == {"product", "qty"}
    # The saved schema and a rebuild from the requirements give the same model.
    assert build_model(describe_model(model)).model_json_schema() == model.model_json_schema()
    rebuilt = rebuild_from_requirements(model.__name__, requirements)
    assert rebuilt.model_json_schema() == model.model_json_schema()
    # Verification wraps each row's fields, as for any other collection.
    wrapped = _wrap_model_for_verification(model)
    checked = wrapped.model_validate(
        {
            "invoice_number": _wrapped("1"),
            "line_items": [{"product": _wrapped("Bolt"), "qty": _wrapped(3)}],
        }
    )
    assert checked.line_items[0].qty.value == 3
    assert wrapped.model_validate({"invoice_number": _wrapped("1"), "line_items": None})
    # The readable schema.py defines the row class too.
    _save_schema_to_python(model, tmp_path / "schema.py")
    source = (tmp_path / "schema.py").read_text(encoding="utf-8")
    assert source.count("\nclass ") == 2, source
    assert "Optional[list[" in source


def test_a_null_collection_passes_the_policies_and_post_processing(monkeypatch):
    nullable_items = _LINE_ITEMS.model_copy(update={"nullable": True})
    _, requirements, _, _ = _generate(
        monkeypatch, _structure("flat"), [_NUMBER, nullable_items], _ROW
    )
    record = {"invoice_number": None, "line_items": None}

    assert _extract_one(record, requirements) == {"invoice_number": "", "line_items": None}
    assert VisionExtractor._post_process(None, dict(record), requirements) == {
        "invoice_number": "",
        "line_items": None,
    }


def test_a_flat_collection_without_row_fields_stays_a_flat_list_and_keeps_its_null(monkeypatch):
    nullable_items = _LINE_ITEMS.model_copy(update={"nullable": True})
    model, requirements, analysis, _ = _generate(
        monkeypatch, _structure("flat"), [_NUMBER, nullable_items], []
    )

    assert isinstance(requirements, ExtractionRequirements)
    by_name = {f.field_name: f for f in requirements.fields}
    assert by_name["line_items"].field_type == "list[str]"
    assert by_name["line_items"].nullable is True
    assert analysis.structure_type == "flat"
    assert model.model_validate({"invoice_number": "1", "line_items": None}).line_items is None


def test_a_leaked_parent_collection_keeps_its_null_policy(monkeypatch):
    from gaik.software_components.extractor.schema import ChildContainerSpec

    analysis = _structure(
        "parent_with_nested_list",
        child_containers=[
            ChildContainerSpec(container_name="payments", container_description="Payments")
        ],
    )
    nullable_items = _LINE_ITEMS.model_copy(update={"nullable": True})
    _, requirements, _, _ = _generate(monkeypatch, analysis, [_NUMBER, nullable_items], _ROW)

    by_name = {c.container_name: c for c in requirements.children}
    assert by_name["payments"].nullable is False
    assert by_name["line_items"].nullable is True


def test_the_schema_diff_reports_a_collection_that_may_now_be_null(monkeypatch):
    from gaik.software_components.extractor import compare_requirements

    _, approved, _, _ = _generate(monkeypatch, _structure("flat"), [_NUMBER, _LINE_ITEMS], _ROW)
    nullable_items = _LINE_ITEMS.model_copy(update={"nullable": True})
    _, new, _, _ = _generate(monkeypatch, _structure("flat"), [_NUMBER, nullable_items], _ROW)

    diff = compare_requirements(approved, new)

    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("line_items[]", {"nullable": (False, True)})
    ]
