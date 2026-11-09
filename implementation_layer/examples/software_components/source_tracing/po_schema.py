"""What the source tracing examples extract from the sample purchase orders.

``PO.pdf`` and ``PO2.pdf`` in this folder are the same purchase orders the VisionExtractor
example uses. The schema is written out here, so the examples show how to add evidence to a
schema you already have; it is not generated.
"""

from __future__ import annotations

from gaik.software_components.extractor import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
)
from pydantic import BaseModel, Field

TASK = """
Extract the purchase order data from the document.

Header: the purchase order (document) number, the order date and the delivery date, both as
written in the document, and the vendor or supplier number.

For every line item: the item number, a short description of the material, and the quantity
as written, with its unit.
"""


class PurchaseOrderLine(BaseModel):
    item_number: str | None = Field(None, description="Item number of the line")
    description: str | None = Field(None, description="Short description of the material")
    quantity: str | None = Field(None, description="Quantity as written, with its unit")


class PurchaseOrder(BaseModel):
    document_number: str | None = Field(None, description="Purchase order (document) number")
    order_date: str | None = Field(None, description="Order date as written")
    delivery_date: str | None = Field(None, description="Delivery date as written")
    vendor_number: str | None = Field(None, description="Vendor or supplier number")
    lines: list[PurchaseOrderLine] = Field(default_factory=list, description="Line items")


def _spec(name: str, description: str) -> FieldSpec:
    return FieldSpec(field_name=name, field_type="str", description=description)


REQUIREMENTS = CompositeExtractionRequirements(
    parent_requirements=ExtractionRequirements(
        use_case_name="purchase_order",
        fields=[
            _spec("document_number", "Purchase order (document) number"),
            _spec("order_date", "Order date as written"),
            _spec("delivery_date", "Delivery date as written"),
            _spec("vendor_number", "Vendor or supplier number"),
        ],
    ),
    children=[
        ChildRequirements(
            container_name="lines",
            container_description="Line items",
            requirements=ExtractionRequirements(
                use_case_name="purchase_order_line",
                fields=[
                    _spec("item_number", "Item number of the line"),
                    _spec("description", "Short description of the material"),
                    _spec("quantity", "Quantity as written, with its unit"),
                ],
            ),
        )
    ],
)


def print_report(report) -> None:
    """Print what the check found: one line per value, then the totals."""
    print("\nEvidence check")
    print("-" * 78)
    for item in report.items:
        where = f"doc {item.document} p.{item.page}"
        print(f"{item.verdict:<10} {item.field:<22} {str(item.value)[:24]:<24} {where}")
        print(f"{'':<10} quote: {' '.join(item.quote.split())[:60]}")
    summary = report.summary()
    coverage = "n/a" if summary["coverage"] is None else f"{summary['coverage']:.0%}"
    print("-" * 78)
    print(
        f"verified {summary['verified']}, check {summary['check']}, "
        f"reworded {summary['reworded']}, unchecked {summary['unchecked']}; "
        f"evidence for {coverage} of the values"
    )
