"""Tests for the Purchase Order demo's "Create your use case" extraction."""

import asyncio

import pytest
from api.routers import luvata_order
from api.routers.luvata_order import (
    MAX_PROMPT_CHARS,
    clean_requirements,
    combine_documents,
    describe_schema,
)
from api.utils.order_fees import parse_service_rates
from fastapi import HTTPException
from pydantic import BaseModel, Field


def test_clean_requirements_trims_and_keeps_the_prompt():
    cleaned = clean_requirements("  Extract purchase order data.  \n\n- PO number   \n")

    assert cleaned == "Extract purchase order data.\n\n- PO number"


@pytest.mark.parametrize("text", ["", "   ", "short", "x" * (MAX_PROMPT_CHARS + 1)])
def test_clean_requirements_rejects_empty_and_oversized_prompts(text):
    with pytest.raises(HTTPException) as error:
        clean_requirements(text)

    assert error.value.status_code == 400


def test_combined_text_labels_each_document_by_role():
    text = combine_documents("PO body", [("BOM1.pdf", "first"), ("BOM2.pdf", "second")])

    assert text.startswith("=== PURCHASE ORDER ===\n\nPO body")
    assert "=== BILL OF MATERIALS 1 (BOM1.pdf) ===\n\nfirst" in text
    assert "=== BILL OF MATERIALS 2 (BOM2.pdf) ===\n\nsecond" in text
    assert text.index("BILL OF MATERIALS 1") < text.index("BILL OF MATERIALS 2")


def test_combined_text_for_a_single_po_has_no_bom_sections():
    assert "BILL OF MATERIALS" not in combine_documents("PO body", [])


def test_describe_schema_lists_nested_record_fields():
    class Line(BaseModel):
        quantity: int = Field(description="Ordered quantity")

    class Order(BaseModel):
        po_number: str = Field(description="PO number")
        note: str | None = Field(default=None, description="Free text")
        line_items: list[Line]

    described = {f["name"]: f for f in describe_schema(Order)}

    assert described["po_number"]["required"] is True
    assert described["note"]["required"] is False
    assert described["line_items"]["type"] == "list"
    assert [c["name"] for c in described["line_items"]["children"]] == ["quantity"]


def test_custom_schemas_are_cached_in_memory_only(monkeypatch):
    class Generated(BaseModel):
        po_number: str | None = None

    calls = []

    class FakeGenerator:
        item_requirements = object()

        def __init__(self, *args, **kwargs):
            pass

        def generate_schema(self, user_requirements):
            calls.append(user_requirements)
            return Generated

    monkeypatch.setattr(luvata_order, "SchemaGenerator", FakeGenerator)
    monkeypatch.setattr(luvata_order, "get_api_config", lambda: {"model": "m"})
    monkeypatch.setattr(luvata_order, "get_model_options", lambda config: {})
    monkeypatch.setattr(luvata_order, "_custom_schema_cache", {})
    monkeypatch.setattr(
        luvata_order,
        "save_schema",
        lambda *a, **k: pytest.fail("custom schemas must not be persisted"),
    )

    first_id, _, _ = asyncio.run(luvata_order._custom_schema("Extract PO number"))
    second_id, _, _ = asyncio.run(luvata_order._custom_schema("Extract PO number"))

    assert first_id == second_id
    assert calls == ["Extract PO number"]

    # Regenerating builds a new schema and replaces the cached one.
    asyncio.run(luvata_order._custom_schema("Extract PO number", regenerate=True))
    assert calls == ["Extract PO number"] * 2


def test_order_processing_reports_parsing_extracting_and_preparing_in_order(monkeypatch):
    """The example's progress steps follow the real stages of processing."""
    import io
    import json

    from fastapi import UploadFile

    def upload(name):
        return UploadFile(file=io.BytesIO(b"x"), filename=name)

    seen = []

    async def parse(upload_file, prefix):
        seen.append(("parse", upload_file.filename))
        return f"text of {upload_file.filename}"

    async def extract(po_text, boms):
        seen.append(("extract", [name for name, _ in boms]))
        return {"po_number": "P1", "customer": "C", "po_items": [], "additional_fees": []}

    async def pricing(_file):
        seen.append(("pricing", None))
        return []

    async def rates(_file):
        return {}

    monkeypatch.setattr(luvata_order, "_parse_upload", parse)
    monkeypatch.setattr(luvata_order, "extract_order", extract)
    monkeypatch.setattr(luvata_order, "parse_pricing_file", pricing)
    monkeypatch.setattr(luvata_order, "read_service_rates", rates)

    async def run():
        response = await luvata_order.process_order(
            upload("PO.pdf"), [upload("BOM1.pdf"), upload("BOM2.pdf")], upload("price.xlsx")
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(run())
    events = [c.split("\n")[0].removeprefix("event: ") for c in chunks]
    messages = [
        json.loads(c.split("data: ", 1)[1])["message"]
        for c in chunks
        if c.startswith("event: status")
    ]

    assert messages == ["Parsing documents...", "Extracting information...", "Preparing results..."]
    assert events[-1] == "complete"
    kinds = [kind for kind, _ in seen]
    # Every document is parsed first; then one extraction gets the BOMs in order.
    assert kinds == ["parse", "parse", "parse", "extract", "pricing"]
    assert ("extract", ["BOM1.pdf", "BOM2.pdf"]) in seen


PRICES = [
    luvata_order.PricingRow(
        material_id="MAT-2401",
        type_designation="Aluminum Angle - L Profile",
        unit_price=28.5,
        cutting_fee=5.0,
        testing_fee=15.0,
        cert_fee=25.0,
    ),
    luvata_order.PricingRow(
        material_id="MAT-4829",
        type_designation="Seamless Carbon Steel Pipe",
        unit_price=67.2,
        cutting_fee=8.0,
        testing_fee=20.0,
        cert_fee=30.0,
    ),
]
SERVICES = parse_service_rates([("Hydrostatic Testing", "$35.00/pipe", None)])


def _order(lines, fees):
    from api.utils.order_extraction import split_order

    return split_order({"po_number": "P1", "po_items": lines, "additional_fees": fees})


def test_lines_are_priced_with_the_fees_the_extraction_lists():
    parts = _order(
        [
            {
                "material_number": "MAT-2401",
                "quantity": 200,
                "description": "Aluminum Angle Bar",
                "type_part_designation": "Aluminum Angle - L Profile",
                "dimensions": "50 x 50 x 5 mm x 6000 mm",
                "material_grade": "6061-T6",
                "delivery_date": "01/12/2025",
            },
            {
                "material_number": "MAT-4829",
                "quantity": 150,
                "description": "Steel Pipe",
                "type_part_designation": "Seamless Carbon Steel Pipe",
                "dimensions": 'NPS 2"',
                "material_grade": "ASTM A106 Grade B",
            },
        ],
        [
            {"material_number": "MAT-2401", "fee_name": "Cutting Fee", "quantity": 200},
            {"material_number": "MAT-2401", "fee_name": "Cert Fee (MTC 3.1)", "quantity": 1},
            {"material_number": "MAT-4829", "fee_name": "Hydrostatic Testing", "quantity": 150},
        ],
    )

    items, errors, warnings = luvata_order.price_order(parts, PRICES, SERVICES)

    assert (errors, warnings) == ([], [])
    first, second = items
    assert first.material_subtotal == 5700.0
    assert (first.cutting_fee, first.cert_fee, first.testing_fee) == (1000.0, 25.0, 0.0)
    assert first.total_fees == 1025.0
    assert first.line_total == 6725.0
    assert first.bom_dimensions == "50 x 50 x 5 mm x 6000 mm"
    assert first.bom_material_grade == "6061-T6"
    assert first.delivery_date == "01/12/2025"
    # No testing fee: the extraction lists none for the lines.
    assert second.other_fees == 5250.0
    assert second.line_total == 10080.0 + 5250.0
    assert [fee.name for fee in second.fee_lines] == ["Hydrostatic Testing"]


def test_a_line_without_a_price_is_reported_and_unpriced():
    parts = _order([{"material_number": "MAT-9999", "quantity": 3, "description": "Odd"}], [])

    items, errors, _ = luvata_order.price_order(parts, PRICES, SERVICES)

    assert items[0].price_match is False
    assert items[0].line_total is None
    assert errors == ["No pricing found for material 'MAT-9999' or type designation 'None'"]


def test_fees_for_a_material_that_is_not_an_order_line_are_reported():
    parts = _order(
        [{"material_number": "MAT-2401", "quantity": 1, "type_part_designation": "x"}],
        [{"material_number": "MAT-7777", "fee_name": "Cutting Fee", "quantity": 2}],
    )

    items, _, warnings = luvata_order.price_order(parts, PRICES, SERVICES)

    assert items[0].total_fees == 0.0
    assert any("MAT-7777" in warning and "not charged" in warning for warning in warnings)


def test_a_line_with_no_bom_details_is_flagged():
    parts = _order([{"material_number": "MAT-2401", "quantity": 1}], [])

    items, _, warnings = luvata_order.price_order(parts, PRICES, SERVICES)

    assert items[0].bom_match is False
    assert items[0].price_match is True  # still priced by its material number
    assert warnings == ["No BOM details were found for material MAT-2401"]


def _line(material_subtotal, fees):
    return luvata_order.EnrichedItem(
        material="M",
        description="d",
        quantity=1,
        material_subtotal=material_subtotal,
        total_fees=fees,
        line_total=material_subtotal + fees,
    )


def test_summary_taxes_material_fees_and_shipping():
    items = [_line(25567.5, 1025.0), _line(0.0, 5695.0)]  # 6,720 of fees in all

    summary = luvata_order.calculate_summary(items, shipping=450.0, tax_rate=6.0)

    assert summary.material_subtotal == 25567.5
    assert summary.total_fees == 6720.0
    assert summary.shipping == 450.0
    # 6% of 25,567.50 + 6,720.00 + 450.00
    assert summary.tax == 1964.25
    assert summary.grand_total == 34701.75


def test_summary_without_shipping_and_tax_is_material_plus_fees():
    summary = luvata_order.calculate_summary([_line(100.0, 10.0)])

    assert (summary.shipping, summary.tax, summary.tax_rate) == (0.0, 0.0, None)
    assert summary.grand_total == 110.0


def test_the_saved_order_schema_matches_its_prompt_and_keeps_the_corrections():
    """The schema is generated once and corrected by hand; this keeps it so."""
    from api.utils import load_schema

    task = luvata_order.clean_requirements(
        luvata_order.ORDER_EXAMPLE_TASK_PATH.read_text(encoding="utf-8")
    )

    # A schema for another prompt would not load, and would be generated again.
    schema, requirements = load_schema(luvata_order.ORDER_EXAMPLE_KEY, task)

    fields = schema.model_fields
    assert fields["po_number"].is_required()
    assert fields["customer"].is_required()
    # Things a document may leave out are optional, so the model need not invent them.
    for name in ("order_date", "buyer", "sales_person", "shipping_address", "payment_terms"):
        assert not fields[name].is_required(), name
    assert not fields["shipping_cost"].is_required()
    assert not fields["tax_rate"].is_required()

    from api.utils.order_extraction import split_order

    sample = {name: None for name in fields}
    sample["po_number"], sample["customer"] = "P1", "C"
    for name, field in fields.items():
        if field.annotation is not None and "list" in str(field.annotation):
            sample[name] = []
    parts = split_order(sample)
    assert (parts.po_number, parts.customer) == ("P1", "C")
    # The two lists of the schema: the order lines, and the fees.
    list_fields = [n for n, f in fields.items() if "list" in str(f.annotation)]
    assert len(list_fields) == 2
    assert any("fee" in name for name in list_fields)
    assert len(schema.__name__) < 60
