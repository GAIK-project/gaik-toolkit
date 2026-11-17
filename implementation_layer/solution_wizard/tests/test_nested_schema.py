"""Repeated child records survive schema generation.

A purchase order's line items became a single text field, and the row fields
were flattened into the parent as scalars, so the schema could not represent
more than one row. `dict` and `object` mapped to `str` because Azure OpenAI's
structured output rejects a bare dict. A `nested` block in the spec now gives a
named row model with extra='forbid', and the requirements use gaik's own
`CompositeExtractionRequirements` shape.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.schema_designer import (  # noqa: E402
    _child_model_name,
    _model_from_spec,
    build_pydantic_model,
    build_requirements_json,
    build_requirements_text,
    write_schema_files,
)

PO_SPEC = {
    "schema_name": "PurchaseOrder",
    "fields": ["po_number", "supplier_name", "line_items", "total_amount"],
    "field_types": {"total_amount": "decimal"},
    "required_fields": ["po_number", "line_items"],
    "field_descriptions": {"line_items": "One entry per order line"},
    "nested": {
        "line_items": {
            "fields": ["item_number", "article_code", "quantity", "unit_price"],
            "field_types": {"item_number": "int", "quantity": "int", "unit_price": "decimal"},
            "required_fields": ["item_number", "quantity"],
        }
    },
}

FLAT_SPEC = {
    "schema_name": "IncidentReport",
    "fields": ["incident_date", "location", "severity"],
    "required_fields": ["incident_date"],
}


def _model(spec, name=None):
    namespace: dict = {}
    exec(compile(build_pydantic_model(spec, name), "output_schema.py", "exec"), namespace)
    return namespace


def _po(**rows) -> dict:
    """PO_SPEC whose line_items rows are ``rows``; the parent fields are all required."""
    return dict(
        PO_SPEC,
        fields=["po_number", "line_items"],
        required_fields=["po_number", "line_items"],
        field_types={},
        nested={"line_items": rows},
    )


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def test_the_child_class_is_named_after_one_row():
    assert _child_model_name("line_items") == "LineItem"
    assert _child_model_name("invoice_rows") == "InvoiceRow"
    assert _child_model_name("participants") == "Participant"


@pytest.mark.parametrize(
    ("container", "name"),
    [
        ("address", "Address"),
        ("status", "Status"),
        ("analysis", "Analysis"),
        ("time_series", "TimeSeries"),
        ("bus", "Bus"),
    ],
)
def test_a_container_that_is_already_singular_keeps_its_name(container, name):
    assert _child_model_name(container) == name


def test_an_ies_plural_becomes_a_y_singular():
    assert _child_model_name("delivery_entries") == "DeliveryEntry"


# ---------------------------------------------------------------------------
# The generated model
# ---------------------------------------------------------------------------


def test_the_generated_module_is_valid_python_and_builds_the_models():
    ns = _model(PO_SPEC)

    assert "PurchaseOrder" in ns
    assert "LineItem" in ns


def test_many_rows_survive_where_one_text_field_used_to_be():
    ns = _model(PO_SPEC)

    po = ns["PurchaseOrder"](
        po_number="PO-1",
        line_items=[
            {"item_number": 1, "quantity": 5, "unit_price": "12.50"},
            {"item_number": 2, "quantity": 3, "article_code": "A-9"},
        ],
    )

    assert len(po.line_items) == 2
    assert po.line_items[0].quantity == 5
    assert po.line_items[1].article_code == "A-9"


def test_the_row_fields_are_not_flattened_into_the_parent():
    ns = _model(PO_SPEC)

    assert "quantity" not in ns["PurchaseOrder"].model_fields
    assert "quantity" in ns["LineItem"].model_fields


def test_a_row_forbids_extra_properties():
    """SKILL.md's rule for every nested object: a named model with extra='forbid'."""
    schema = _model(PO_SPEC)["PurchaseOrder"].model_json_schema()

    assert schema["$defs"]["LineItem"]["additionalProperties"] is False


def test_the_decimal_helper_is_emitted_once_even_when_both_levels_need_it():
    source = build_pydantic_model(PO_SPEC)

    assert source.count("def _clean_decimal_string") == 1


def test_a_flat_spec_generates_no_row_model():
    source = build_pydantic_model(FLAT_SPEC)

    assert "List[" not in source and "ConfigDict" not in source
    assert _model(FLAT_SPEC)["IncidentReport"](incident_date="2026-09-28")


def test_a_nested_block_for_an_unlisted_field_is_ignored():
    """A model nobody references is a spec error, not something to generate."""
    spec = dict(FLAT_SPEC, nested={"line_items": {"fields": ["a"]}})

    assert "LineItem" not in build_pydantic_model(spec)


@pytest.mark.parametrize(
    ("rows", "row"),
    [
        # Only the row has an optional field: the parent's fields are all required.
        (
            {"fields": ["item_number", "note"], "required_fields": ["item_number"]},
            {"item_number": "1"},
        ),
        # Only the row has allowed values.
        (
            {
                "fields": ["item_number", "kind"],
                "required_fields": ["item_number", "kind"],
                "allowed_values": {"kind": ["goods", "service"]},
            },
            {"item_number": "1", "kind": "goods"},
        ),
    ],
    ids=["optional", "enum"],
)
def test_what_only_a_row_needs_is_imported(rows, row):
    """The row model's imports were dropped with its module header (NameError)."""
    ns = _model(_po(**rows))

    assert ns["PurchaseOrder"](po_number="PO-1", line_items=[row]).line_items[0].item_number


def test_a_parent_and_a_row_field_of_one_name_keep_their_own_allowed_values():
    """Both used to be `class StatusEnum`; the row's replaced the parent's."""
    spec = {
        "schema_name": "Order",
        "fields": ["status", "rows"],
        "required_fields": ["status", "rows"],
        "allowed_values": {"status": ["open", "closed"]},
        "nested": {
            "rows": {
                "fields": ["status"],
                "required_fields": ["status"],
                "allowed_values": {"status": ["ok", "bad"]},
            }
        },
    }
    order = _model(spec)["Order"]

    parsed = order(status="open", rows=[{"status": "ok"}])

    assert parsed.status.value == "open" and parsed.rows[0].status.value == "ok"
    with pytest.raises(ValueError):
        order(status="ok", rows=[])
    assert _model_from_spec(spec, "Order").model_json_schema() == order.model_json_schema()


@pytest.mark.parametrize(
    ("container", "taken_by"),
    [("orders", "the parent model"), ("fields", "pydantic's Field"), ("lists", "typing's List")],
)
def test_a_row_model_never_takes_a_name_the_module_already_uses(container, taken_by):
    spec = {
        "schema_name": "Order",
        "fields": ["number", container],
        "required_fields": ["number"],
        "field_descriptions": {"number": "The order number"},
        "nested": {container: {"fields": ["sku"], "required_fields": ["sku"]}},
    }

    order = _model(spec)["Order"]

    assert order(number="1", **{container: [{"sku": "A"}]})
    assert order.model_fields["number"].description == "The order number"


def test_rows_inside_rows_are_refused():
    """gaik's requirements for a child collection are flat."""
    spec = dict(
        FLAT_SPEC,
        fields=["rows"],
        nested={"rows": {"fields": ["sub"], "nested": {"sub": {"fields": ["z"]}}}},
    )

    with pytest.raises(ValueError, match="one level of nested rows"):
        build_pydantic_model(spec)
    with pytest.raises(ValueError, match="one level of nested rows"):
        build_requirements_json(spec)


# ---------------------------------------------------------------------------
# The runtime contract
# ---------------------------------------------------------------------------


def test_the_requirements_json_uses_the_nested_shape_gaik_already_reads():
    payload = build_requirements_json(PO_SPEC, use_case_name="Purchase orders")

    assert payload["requirements_type"] == "parent_with_nested_list"
    req = payload["requirements"]
    assert req["structure_type"] == "parent_with_nested_list"
    assert [f["field_name"] for f in req["parent_requirements"]["fields"]] == [
        "po_number",
        "supplier_name",
        "total_amount",
    ]
    child = req["children"][0]
    assert child["container_name"] == "line_items"
    assert [f["field_name"] for f in child["requirements"]["fields"]] == [
        "item_number",
        "article_code",
        "quantity",
        "unit_price",
    ]


def test_gaik_validates_the_generated_requirements():
    schema = pytest.importorskip("gaik.software_components.extractor.schema")

    parsed = schema.CompositeExtractionRequirements.model_validate(
        build_requirements_json(PO_SPEC)["requirements"]
    )

    assert parsed.children[0].container_name == "line_items"
    assert len(parsed.children[0].requirements.fields) == 4


def test_gaik_still_validates_a_flat_spec_the_old_way():
    schema = pytest.importorskip("gaik.software_components.extractor.schema")

    payload = build_requirements_json(FLAT_SPEC)

    assert "requirements_type" not in payload
    assert schema.ExtractionRequirements.model_validate(payload["requirements"])


def test_gaik_loads_the_written_schema_of_a_nested_spec(tmp_path):
    """write_schema_files saves the model as data; the PoC's load_schema reads it back."""
    pytest.importorskip("gaik.software_components.extractor.saved_schema")
    pipeline = pytest.importorskip("gaik.software_modules.documents_to_structured_data.pipeline")
    spec = dict(_po(**PO_SPEC["nested"]["line_items"]), allowed_values={"po_number": ["PO-1"]})
    spec["nested"]["line_items"] = dict(
        spec["nested"]["line_items"], allowed_values={"article_code": ["PO-1"]}
    )

    written = write_schema_files(spec, "PurchaseOrder", tmp_path)
    loaded = pipeline.DocumentsToStructuredData.load_schema(
        None, tmp_path / "schemas", "output_schema"
    )

    assert "output_schema_model.json" in written
    model, requirements = loaded
    assert model.model_json_schema() == _model(spec)["PurchaseOrder"].model_json_schema()
    assert requirements.children[0].container_name == "line_items"


def test_the_extraction_prompt_lists_the_row_fields():
    """The prompt is sent with the schema and a schema is regenerated from it: a list
    of rows described as one string field contradicts both."""
    text = build_requirements_text(PO_SPEC)

    assert "line_items (list of rows, REQUIRED): One entry per order line. Each row has:" in text
    assert "   - quantity (int, REQUIRED)" in text
    assert "   - article_code (string, OPTIONAL)" in text
    assert "line_items (string" not in text


def test_a_flat_prompt_is_written_as_before():
    spec = dict(
        FLAT_SPEC,
        field_types={"severity": "enum"},
        field_descriptions={"location": "Where it happened"},
        allowed_values={"severity": ["low", "high"]},
    )

    lines = [line for line in build_requirements_text(spec).splitlines() if line[:1].isdigit()]

    assert lines == [
        "1. incident_date (string, REQUIRED)",
        "2. location (string, OPTIONAL): Where it happened",
        "3. severity (enum, OPTIONAL) -- allowed values: low, high",
    ]


def test_the_row_blocks_own_description_reaches_every_file(tmp_path):
    """SKILL.md's example puts the description in the row block, not in
    field_descriptions; the schema and the requirements carry the same text."""
    spec = dict(PO_SPEC, field_descriptions={})
    spec["nested"] = {"line_items": dict(PO_SPEC["nested"]["line_items"], description="Rows")}

    schema = _model(spec)["PurchaseOrder"].model_json_schema()
    requirements = build_requirements_json(spec)["requirements"]

    assert schema["properties"]["line_items"]["description"] == "Rows"
    assert requirements["children"][0]["container_description"] == "Rows"
    assert _model_from_spec(spec, "PurchaseOrder").model_json_schema() == schema


def test_allowed_values_on_a_container_make_no_enum():
    spec = dict(PO_SPEC, allowed_values={"line_items": ["a"], "po_number": ["PO-1"]})

    source = build_pydantic_model(spec)

    assert "LineItemsEnum" not in source and "class PoNumberEnum" in source
    assert _model_from_spec(spec, "PurchaseOrder").model_json_schema() == (
        _model(spec)["PurchaseOrder"].model_json_schema()
    )
