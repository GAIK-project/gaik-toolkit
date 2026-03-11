#!/usr/bin/env python3
"""
Script to update luvata_order.py with real GAIK extraction
Run from toolkit_demo_app directory: python scripts/apply_luvata_real_extraction.py
"""

import os
from pathlib import Path

# Changedirectory to toolkit_demo_app
os.chdir(Path(__file__).parent.parent)

router_file = Path("api/routers/luvata_order.py")

# Read the current file
with open(router_file, "r") as f:
    content = f.read()

# 1. Update imports
old_imports = '''import io
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from api.utils.sse import sse_event'''

new_imports = '''import csv
import io
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from fpdf import FPDF
from pydantic import BaseModel, Field

from api.utils.sse import sse_event
from gaik import Extractor, SchemaGenerator
from gaik.parsers import PyMuPDFParser'''

content = content.replace(old_imports, new_imports)

# 2. Add pdf_job_id to ProcessOrderResponse
old_response = '''class ProcessOrderResponse(BaseModel):
    """Response from order processing"""

    success: bool
    po_number: str | None = None
    customer: str | None = None
    items: list[EnrichedItem] = []
    summary: OrderSummary | None = None
    errors: list[str] = []
    warnings: list[str] = []'''

new_response = '''class ProcessOrderResponse(BaseModel):
    """Response from order processing"""

    success: bool
    po_number: str | None = None
    customer: str | None = None
    items: list[EnrichedItem] = []
    summary: OrderSummary | None = None
    errors: list[str] = []
    warnings: list[str] = []
    pdf_job_id: str | None = None'''

content = content.replace(old_response, new_response)

# 3. Add extraction functions before the API endpoints section
extraction_functions = '''

async def extract_po_data(po_file: UploadFile) -> PurchaseOrder:
    """Extract purchase order data from PDF using GAIK"""
    parser = PyMuPDFParser()
    pdf_bytes = await po_file.read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        parsed_doc = parser.parse(tmp_path)
        text = parsed_doc.text_content

        # Generate schema for PO extraction
        schema_gen = SchemaGenerator()
        requirements = """
        Extract the following from the purchase order:
        - po_number: The purchase order number (e.g., "4512560923")
        - customer: Customer name (e.g., "ABB")
        - items: List of line items, each with:
          - material: Material/part number
          - description: Item description
          - quantity: Order quantity (integer)
          - delivery_date: Delivery date if mentioned
        """

        schema_result = schema_gen.generate_schema(requirements)

        # Extract structured data
        extractor = Extractor()
        result = extractor.extract(text, schema=schema_result.schema)

        # Convert to PurchaseOrder model
        po_data = result[0] if result else {}
        return PurchaseOrder(**po_data)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def extract_bom_data(bom_file: UploadFile) -> BOMData:
    """Extract BOM data from PDF using GAIK"""
    parser = PyMuPDFParser()
    pdf_bytes = await bom_file.read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        parsed_doc = parser.parse(tmp_path)
        text = parsed_doc.text_content

        # Generate schema for BOM extraction
        schema_gen = SchemaGenerator()
        requirements = """
        Extract the following from the BOM (Bill of Materials):
        - document_id: BOM document ID/number (e.g., "3AFP201773229A")
        - type_designation: Product type designation (e.g., "BKMJ 50X10/7")
        - length_mm: Length in millimeters (numeric value)
        - weight_per_m: Weight per meter in kg (numeric value)
        """

        schema_result = schema_gen.generate_schema(requirements)

        # Extract structured data
        extractor = Extractor()
        result = extractor.extract(text, schema=schema_result.schema)

        # Convert to BOMData model
        bom_data = result[0] if result else {}
        return BOMData(**bom_data)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def parse_pricing_csv(pricing_file: UploadFile) -> list[PricingRow]:
    """Parse pricing CSV file"""
    content_bytes = await pricing_file.read()
    text = content_bytes.decode("utf-8")

    pricing_rows = []
    reader = csv.DictReader(io.StringIO(text))

    for row in reader:
        pricing_rows.append(
            PricingRow(
                type_designation=row.get("type_designation", ""),
                conversion=float(row.get("conversion", 0)),
                packing=float(row.get("packing", 0)),
                machining=float(row.get("machining", 0)),
                energy_surcharge=float(row.get("energy_surcharge", 0)),
                copper_price=float(row.get("copper_price", 0)),
            )
        )

    return pricing_rows


def generate_pdf(
    po_number: str, customer: str, items: list[EnrichedItem], summary: OrderSummary
) -> bytes:
    """Generate PDF order draft using fpdf2"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)

    # Header
    pdf.cell(0, 10, "ABB Order Draft", ln=True, align="C")
    pdf.ln(5)

    # Order info
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"PO Number: {po_number}", ln=True)
    pdf.cell(0, 8, f"Customer: {customer}", ln=True)
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(5)

    # Table header
    pdf.set_font("Arial", "B", 9)
    pdf.cell(30, 8, "Material", border=1)
    pdf.cell(60, 8, "Description", border=1)
    pdf.cell(20, 8, "Qty", border=1, align="R")
    pdf.cell(20, 8, "kg/pc", border=1, align="R")
    pdf.cell(25, 8, "Total kg", border=1, align="R")
    pdf.cell(30, 8, "Price/kg", border=1, align="R")
    pdf.cell(30, 8, "Total EUR", border=1, align="R", ln=True)

    # Table rows
    pdf.set_font("Arial", "", 8)
    for item in items:
        pdf.cell(30, 7, item.material[:15], border=1)
        pdf.cell(60, 7, item.description[:30], border=1)
        pdf.cell(20, 7, str(item.quantity), border=1, align="R")
        pdf.cell(
            20,
            7,
            f"{item.kg_per_pc:.3f}" if item.kg_per_pc else "-",
            border=1,
            align="R",
        )
        pdf.cell(
            25,
            7,
            f"{item.total_kg:.2f}" if item.total_kg else "-",
            border=1,
            align="R",
        )
        pdf.cell(
            30,
            7,
            f"€{item.price_per_kg:.4f}" if item.price_per_kg else "-",
            border=1,
            align="R",
        )
        pdf.cell(
            30,
            7,
            f"€{item.line_total:.2f}" if item.line_total else "-",
            border=1,
            align="R",
            ln=True,
        )

    # Summary
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 8, f"Total Items: {summary.total_items}", ln=True)
    pdf.cell(0, 8, f"Total Quantity: {summary.total_quantity}", ln=True)
    pdf.cell(0, 8, f"Total Weight: {summary.total_kg:.2f} kg", ln=True)
    pdf.cell(0, 8, f"Total Price: €{summary.total_eur:.2f}", ln=True)

    return pdf.output(dest="S").encode("latin1")


'''

# Insert extraction functions before API endpoints section
api_section_marker = "# ============================================================================\n# API Endpoints\n# ============================================================================"
content = content.replace(api_section_marker, extraction_functions + api_section_marker)

# 4. Replace mock data in process_order
old_generate = '''            yield sse_event("status", {"message": "Starting order processing..."})

            # TODO: Implement actual extraction using GAIK toolkit
            # For now, return mock data structure
            yield sse_event(
                "status", {"message": "Extracting purchase order data..."}
            )

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

            yield sse_event("complete", response.model_dump())'''

new_generate = '''            yield sse_event("status", {"message": "Starting order processing..."})

            # 1. Extract PO data
            yield sse_event("status", {"message": "Extracting purchase order data..."})
            po = await extract_po_data(po_file)
            logger.info(f"Extracted PO: {po.po_number} with {len(po.items)} items")

            # 2. Extract BOM data
            yield sse_event("status", {"message": f"Extracting {len(bom_files)} BOMs..."})
            boms = []
            for bom_file in bom_files:
                bom_data = await extract_bom_data(bom_file)
                boms.append(bom_data)
                logger.info(f"Extracted BOM: {bom_data.document_id}")

            # 3. Parse pricing table
            yield sse_event("status", {"message": "Parsing pricing table..."})
            pricing_rows = await parse_pricing_csv(pricing_file)
            logger.info(f"Parsed {len(pricing_rows)} pricing rows")

            # 4. Enrich products
            yield sse_event("status", {"message": "Calculating prices..."})
            enriched_items, errors = enrich_products(po, boms, pricing_rows)

            # 5. Calculate summary
            summary = calculate_summary(enriched_items)

            # 6. Generate PDF
            yield sse_event("status", {"message": "Generating PDF..."})
            job_id = str(uuid.uuid4())
            pdf_bytes = generate_pdf(po.po_number, po.customer, enriched_items, summary)
            pdf_storage[job_id] = pdf_bytes
            logger.info(f"Generated PDF with job_id: {job_id}")

            # Build response
            response = ProcessOrderResponse(
                success=True,
                po_number=po.po_number,
                customer=po.customer,
                items=enriched_items,
                summary=summary,
                errors=errors,
                pdf_job_id=job_id,
            )

            yield sse_event("complete", response.model_dump())'''

content = content.replace(old_generate, new_generate)

# Write the updated file
with open(router_file, "w") as f:
    f.write(content)

print(f"✅ Updated {router_file}")
print("\nNext steps:")
print("1. Ensure fpdf2 is installed: pip install fpdf2")
print("2. Update frontend page.tsx to enable PDF download button")
print("3. Test with: bun run dev:all")
