"""
Luvata Order Processing API Router

Handles ABB purchase order processing with BOM matching and pricing calculations.
Demonstrates GAIK toolkit's extraction capabilities for real-world manufacturing workflows.
"""

import logging
from typing import Annotated

from api.utils.sse import sse_event
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/luvata-order", tags=["luvata-order"])

# In-memory storage for generated PDFs (temporary, with cleanup)
pdf_storage: dict[str, bytes] = {}


# ============================================================================
# Pydantic Models
# ============================================================================


class POItem(BaseModel):
    """Purchase Order line item"""

    material: str = Field(description="Material number/code")
    description: str = Field(description="Item description")
    quantity: int = Field(description="Order quantity")
    delivery_date: str | None = Field(None, description="Requested delivery date")


class PurchaseOrder(BaseModel):
    """Purchase Order data"""

    po_number: str = Field(description="Purchase order number")
    customer: str = Field(description="Customer name")
    items: list[POItem] = Field(description="Order line items")


class BOMData(BaseModel):
    """Bill of Materials data"""

    document_id: str = Field(description="BOM document identifier")
    type_designation: str = Field(description="Product type designation")
    length_mm: float = Field(description="Length in millimeters")
    weight_per_m: float = Field(description="Weight per meter in kg")


class PricingRow(BaseModel):
    """Pricing table row"""

    type_designation: str = Field(description="Product type designation")
    conversion: float = Field(description="Conversion cost (EUR/kg)")
    packing: float = Field(description="Packing cost (EUR/kg)")
    machining: float = Field(description="Machining cost (EUR/kg)")
    energy_surcharge: float = Field(description="Energy surcharge (EUR/kg)")
    copper_price: float = Field(description="Copper price (EUR/kg)")


class EnrichedItem(BaseModel):
    """Enriched order item with calculated pricing"""

    material: str
    description: str
    quantity: int
    bom_document_id: str | None = None
    type_designation: str | None = None
    length_mm: float | None = None
    weight_per_m: float | None = None
    kg_per_pc: float | None = None
    total_kg: float | None = None
    margin_per_kg: float | None = None
    copper_per_kg: float | None = None
    price_per_kg: float | None = None
    line_total: float | None = None
    delivery_date: str | None = None
    error: str | None = None


class OrderSummary(BaseModel):
    """Order summary totals"""

    total_items: int
    total_quantity: int
    total_kg: float
    total_eur: float


class ProcessOrderResponse(BaseModel):
    """Response from order processing"""

    success: bool
    po_number: str | None = None
    customer: str | None = None
    items: list[EnrichedItem] = []
    summary: OrderSummary | None = None
    errors: list[str] = []
    warnings: list[str] = []


# ============================================================================
# Helper Functions
# ============================================================================


def normalize_type_designation(type_des: str) -> str:
    """
    Normalize type designation for matching.
    Example: "BKMJ 50X10/7,00" → "bkmj50x10/7"
    """
    normalized = type_des.lower()
    # Remove spaces, commas, parentheses
    normalized = normalized.replace(" ", "").replace(",", "").replace("(", "").replace(")", "")
    # Remove trailing zeros after slash
    if "/" in normalized:
        parts = normalized.split("/")
        if len(parts) == 2 and parts[1].replace("0", "").replace(".", "") == "":
            normalized = parts[0] + "/" + parts[1].rstrip("0").rstrip(".")
    return normalized


def match_material_to_bom(material: str, boms: list[BOMData]) -> BOMData | None:
    """
    Match PO material number to BOM document ID.
    Example: "3AFP201773229" matches "3AFP201773229A"
    """
    material_prefix = material.strip()
    for bom in boms:
        if bom.document_id.startswith(material_prefix):
            return bom
    return None


def match_type_to_pricing(
    type_designation: str, pricing_rows: list[PricingRow]
) -> PricingRow | None:
    """Match type designation to pricing table row"""
    normalized_type = normalize_type_designation(type_designation)

    for row in pricing_rows:
        normalized_row_type = normalize_type_designation(row.type_designation)
        if normalized_type == normalized_row_type:
            return row

    return None


def calculate_abb_pricing(item: POItem, bom: BOMData, pricing: PricingRow) -> EnrichedItem:
    """
    Calculate ABB pricing using the formula:
    kg_per_pc = weight_per_m × (length_mm / 1000)
    total_kg = kg_per_pc × quantity
    margin = conversion + packing + machining + energy_surcharge
    total_price = margin + copper_price
    line_total = total_kg × total_price
    """
    kg_per_pc = pricing.weight_per_m * (bom.length_mm / 1000)
    total_kg = kg_per_pc * item.quantity
    margin = pricing.conversion + pricing.packing + pricing.machining + pricing.energy_surcharge
    total_price = margin + pricing.copper_price
    line_total = total_kg * total_price

    return EnrichedItem(
        material=item.material,
        description=item.description,
        quantity=item.quantity,
        bom_document_id=bom.document_id,
        type_designation=bom.type_designation,
        length_mm=round(bom.length_mm, 2),
        weight_per_m=round(pricing.weight_per_m, 3),
        kg_per_pc=round(kg_per_pc, 3),
        total_kg=round(total_kg, 2),
        margin_per_kg=round(margin, 3),
        copper_per_kg=round(pricing.copper_price, 3),
        price_per_kg=round(total_price, 4),
        line_total=round(line_total, 2),
        delivery_date=item.delivery_date,
    )


def enrich_products(
    po: PurchaseOrder, boms: list[BOMData], pricing_rows: list[PricingRow]
) -> tuple[list[EnrichedItem], list[str]]:
    """
    Enrich PO items with BOM data and pricing calculations.
    Returns (enriched_items, errors)
    """
    enriched_items: list[EnrichedItem] = []
    errors: list[str] = []

    for item in po.items:
        # Match to BOM
        bom = match_material_to_bom(item.material, boms)
        if not bom:
            error_msg = f"No BOM found for material {item.material}"
            errors.append(error_msg)
            enriched_items.append(
                EnrichedItem(
                    material=item.material,
                    description=item.description,
                    quantity=item.quantity,
                    delivery_date=item.delivery_date,
                    error=error_msg,
                )
            )
            continue

        # Match to pricing
        pricing = match_type_to_pricing(bom.type_designation, pricing_rows)
        if not pricing:
            error_msg = f"No pricing found for type designation '{bom.type_designation}'"
            errors.append(error_msg)
            enriched_items.append(
                EnrichedItem(
                    material=item.material,
                    description=item.description,
                    quantity=item.quantity,
                    bom_document_id=bom.document_id,
                    type_designation=bom.type_designation,
                    delivery_date=item.delivery_date,
                    error=error_msg,
                )
            )
            continue

        # Calculate pricing
        enriched_item = calculate_abb_pricing(item, bom, pricing)
        enriched_items.append(enriched_item)

    return enriched_items, errors


def calculate_summary(items: list[EnrichedItem]) -> OrderSummary:
    """Calculate order summary totals"""
    total_items = len(items)
    total_quantity = sum(item.quantity for item in items)
    total_kg = sum(item.total_kg or 0 for item in items)
    total_eur = sum(item.line_total or 0 for item in items)

    return OrderSummary(
        total_items=total_items,
        total_quantity=total_quantity,
        total_kg=round(total_kg, 2),
        total_eur=round(total_eur, 2),
    )


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/process")
async def process_order(
    po_file: Annotated[UploadFile, File(description="Purchase Order PDF")],
    bom_files: Annotated[list[UploadFile], File(description="BOM PDF files")],
    pricing_file: Annotated[UploadFile, File(description="Pricing CSV/Excel file")],
) -> StreamingResponse:
    """
    Process Luvata ABB order with streaming progress updates.

    Steps:
    1. Extract PO data from PDF
    2. Extract BOM data from PDFs
    3. Parse pricing table
    4. Match and calculate pricing
    5. Return enriched order data
    """

    async def generate():
        try:
            # Validate inputs
            if not po_file:
                yield sse_event("error", {"message": "Purchase order file required"})
                return

            if not bom_files or len(bom_files) == 0:
                yield sse_event("error", {"message": "At least one BOM file required"})
                return

            if not pricing_file:
                yield sse_event("error", {"message": "Pricing file required"})
                return

            yield sse_event("status", {"message": "Starting order processing..."})

            # TODO: Implement actual extraction using GAIK toolkit
            # For now, return mock data structure
            yield sse_event("status", {"message": "Extracting purchase order data..."})

            # Mock PO data
            po = PurchaseOrder(
                po_number="4512560923",
                customer="ABB Oy",
                items=[
                    POItem(
                        material="3AFP201773229",
                        description="Busbar profile",
                        quantity=100,
                        delivery_date="2025-04-15",
                    ),
                    POItem(
                        material="3AFP201773267",
                        description="Busbar profile",
                        quantity=50,
                        delivery_date="2025-04-15",
                    ),
                ],
            )

            yield sse_event("status", {"message": f"Extracting {len(bom_files)} BOMs..."})

            # Mock BOM data
            boms = [
                BOMData(
                    document_id="3AFP201773229A",
                    type_designation="BKMJ 50X10/7",
                    length_mm=3000.0,
                    weight_per_m=4.44,
                ),
                BOMData(
                    document_id="3AFP201773267A",
                    type_designation="BKMJ 60X10/7",
                    length_mm=2500.0,
                    weight_per_m=5.32,
                ),
            ]

            yield sse_event("status", {"message": "Parsing pricing table..."})

            # Mock pricing data
            pricing_rows = [
                PricingRow(
                    type_designation="BKMJ 50X10/7",
                    conversion=2.5,
                    packing=0.3,
                    machining=0.2,
                    energy_surcharge=0.15,
                    copper_price=8.5,
                ),
                PricingRow(
                    type_designation="BKMJ 60X10/7",
                    conversion=2.7,
                    packing=0.35,
                    machining=0.25,
                    energy_surcharge=0.18,
                    copper_price=8.5,
                ),
            ]

            yield sse_event("status", {"message": "Calculating prices..."})

            # Enrich products
            enriched_items, errors = enrich_products(po, boms, pricing_rows)

            # Calculate summary
            summary = calculate_summary(enriched_items)

            # Build response
            response = ProcessOrderResponse(
                success=True,
                po_number=po.po_number,
                customer=po.customer,
                items=enriched_items,
                summary=summary,
                errors=errors,
            )

            yield sse_event("complete", response.model_dump())

        except Exception as e:
            logger.exception("Error processing order")
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/pdf/{job_id}")
async def download_pdf(job_id: str) -> Response:
    """Download generated order draft PDF"""
    pdf_bytes = pdf_storage.get(job_id)

    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF not found")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=order_draft_{job_id}.pdf"},
    )
