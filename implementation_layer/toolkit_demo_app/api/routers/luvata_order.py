"""
Luvata Order Processing API Router
Handles ABB purchase order processing with BOM matching and pricing calculations.
Demonstrates GAIK toolkit's extraction capabilities for real-world manufacturing workflows.
"""

import asyncio
import io
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from fpdf import FPDF
from openpyxl import load_workbook
from pydantic import BaseModel, Field

try:
    from utils import (
        get_api_config,
        get_model_options,
        load_schema,
        save_schema,
        schema_id_from_requirements,
        sse_event,
        wrap_schema_with_numeric_normalizers,
    )
except ImportError:
    from api.utils import (
        get_api_config,
        get_model_options,
        load_schema,
        save_schema,
        schema_id_from_requirements,
        sse_event,
        wrap_schema_with_numeric_normalizers,
    )

try:
    from utils.model_settings import provider_error_detail
except ImportError:
    from api.utils.model_settings import provider_error_detail

try:
    from utils.order_fees import (
        BomFee,
        FeeCharge,
        ServiceRate,
        parse_service_rates,
        price_fees,
    )
except ImportError:
    from api.utils.order_fees import (
        BomFee,
        FeeCharge,
        ServiceRate,
        parse_service_rates,
        price_fees,
    )

try:
    from utils.order_extraction import OrderParts, pick, split_order, text_of, to_number
except ImportError:
    from api.utils.order_extraction import OrderParts, pick, split_order, text_of, to_number

from gaik.software_components.extractor import (
    DataExtractor,
    SchemaGenerator,
)
from gaik.software_components.parsers import PyMuPDFParser
from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/luvata-order", tags=["luvata-order"])
# Schema directory
SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
SCHEMA_DIR.mkdir(exist_ok=True)


# In-memory storage for generated PDFs with TTL cleanup
PDF_TTL_SECONDS = 3600  # 1 hour
pdf_storage: dict[str, tuple[bytes, float]] = {}  # job_id -> (pdf_bytes, created_at)


def _cleanup_expired_pdfs() -> None:
    """Remove PDFs older than TTL."""
    now = datetime.now().timestamp()
    expired = [k for k, (_, ts) in pdf_storage.items() if now - ts > PDF_TTL_SECONDS]
    for k in expired:
        del pdf_storage[k]


# ============================================================================
# Pydantic Models
# ============================================================================
class PricingRow(BaseModel):
    """Pricing table row"""

    material_id: str | None = Field(
        default=None, description="Material/item identifier from the pricing table"
    )
    type_designation: str = Field(description="Product type designation")
    unit_price: float = Field(description="Base unit price (USD)")
    cutting_fee: float = Field(default=0.0, description="Cutting fee (USD)")
    testing_fee: float = Field(default=0.0, description="Testing fee (USD)")
    cert_fee: float = Field(default=0.0, description="Certificate fee (USD)")


class EnrichedItem(BaseModel):
    """Enriched order item with calculated pricing"""

    material: str
    description: str
    type_designation: str | None = None
    quantity: int
    unit_price: float | None = None
    material_subtotal: float | None = None
    cutting_fee: float = 0.0
    testing_fee: float = 0.0
    cert_fee: float = 0.0
    other_fees: float = 0.0
    fee_lines: list[FeeCharge] = []
    bom_dimensions: str | None = None
    bom_material_grade: str | None = None
    notes: list[str] = []
    total_fees: float = 0.0
    line_total: float | None = None
    delivery_date: str | None = None
    bom_match: bool = False
    price_match: bool = False
    error: str | None = None


class OrderSummary(BaseModel):
    """Order summary totals"""

    total_items: int
    total_quantity: int
    material_subtotal: float
    total_fees: float
    shipping: float = 0.0
    tax_rate: float | None = None  # percent
    tax: float = 0.0
    grand_total: float


class ProcessOrderResponse(BaseModel):
    """Response from order processing"""

    success: bool
    po_number: str | None = None
    customer: str | None = None
    # The header fields of the PO, in the order of the multi-file prompt.
    header: dict[str, Any] = {}
    items: list[EnrichedItem] = []
    summary: OrderSummary | None = None
    errors: list[str] = []
    warnings: list[str] = []
    pdf_job_id: str | None = None


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


def _parse_document_markdown(file_path: str, original_filename: str | None, prefix: str) -> str:
    """Parse a document via remote Docling client when configured, otherwise fallback locally."""
    api_base = os.getenv("DOCLING_API_BASE") or os.getenv("API_BASE")
    password = os.getenv("DOCLING_API_PASSWORD") or os.getenv("PASSWORD")
    if api_base and password:
        try:
            remote_parser = DoclingApiClientParser(api_base=api_base, password=password)
            result = remote_parser.parse_document(file_path)
            markdown = (result.get("parsed_markdown") or "").strip()
            if markdown:
                logger.info("Parsed %s via Docling API client", original_filename or file_path)
                return markdown
            logger.warning(
                "Docling API client returned empty markdown for %s; falling back to PyMuPDFParser",
                original_filename or file_path,
            )
        except Exception as exc:
            logger.warning(
                "Docling API client unavailable for %s; falling back to PyMuPDFParser: %s",
                original_filename or file_path,
                exc,
            )
    local_parser = PyMuPDFParser()
    markdown = local_parser.parse_pdf(file_path, use_markdown=True)
    return markdown


def match_type_to_pricing(
    type_designation: str, pricing_rows: list[PricingRow]
) -> PricingRow | None:
    """
    Match type designation to pricing table row.
    Supports both generic and ABB-style type strings.
    """
    normalized_type = normalize_type_designation(type_designation)
    if not normalized_type:
        return None  # an empty string would match every row
    for row in pricing_rows:
        if normalize_type_designation(row.type_designation) == normalized_type:
            return row
    for row in pricing_rows:
        normalized_row = normalize_type_designation(row.type_designation)
        if normalized_type in normalized_row or normalized_row in normalized_type:
            return row
    return None


def match_pricing(
    material: str, type_designation: str, pricing_rows: list[PricingRow]
) -> PricingRow | None:
    """Match pricing primarily by material/item id, then by type designation."""
    material_upper = material.upper().strip()
    for row in pricing_rows:
        if row.material_id and row.material_id.upper().strip() == material_upper:
            return row
    return match_type_to_pricing(type_designation, pricing_rows)


def _line_field(row: dict[str, Any], *patterns: str) -> Any:
    """The value of the first field that matches the first pattern that matches any."""
    for pattern in patterns:
        value = pick(row, pattern)
        if value is not None:
            return value
    return None


def price_order(
    parts: OrderParts,
    pricing_rows: list[PricingRow],
    service_rates: dict[str, ServiceRate],
) -> tuple[list[EnrichedItem], list[str], list[str]]:
    """Price the order lines: the material from the price list, the fees from the fee entries.

    Each fee that applies is priced as rate x quantity. Returns the priced lines, the
    errors, and warnings about anything that could not be priced.
    """
    fees_by_material: dict[str, list[BomFee]] = {}
    for fee in parts.fees:
        name = text_of(_line_field(fee, r"fee.*name", r"^fee$", r"^name$"))
        material = text_of(_line_field(fee, r"material.*(number|no|id|code)", r"material")) or ""
        if name and material:
            fees_by_material.setdefault(material.upper(), []).append(
                BomFee(
                    name=name,
                    applies=True,
                    basis=text_of(pick(fee, r"basis")),
                    quantity=to_number(pick(fee, r"quantity|qty")),
                )
            )

    items: list[EnrichedItem] = []
    errors: list[str] = []
    warnings: list[str] = []
    priced: set[str] = set()
    for line in parts.lines:
        material = text_of(_line_field(line, r"material.*(number|no|id|code)", r"material")) or ""
        type_designation = text_of(pick(line, r"type|designation"))
        dimensions = text_of(pick(line, r"dimension"))
        grade = text_of(pick(line, r"grade"))
        quantity = round(to_number(_line_field(line, r"quantity", r"qty")) or 0)
        details = {
            "material": material,
            "description": text_of(pick(line, r"description")) or "",
            "type_designation": type_designation,
            "bom_dimensions": dimensions,
            "bom_material_grade": grade,
            "quantity": quantity,
            "delivery_date": text_of(pick(line, r"deliver")),
            "bom_match": bool(type_designation or dimensions or grade),
        }
        if not details["bom_match"]:
            warnings.append(f"No BOM details were found for material {material}")

        pricing = match_pricing(material, type_designation or "", pricing_rows)
        if pricing is None:
            message = (
                f"No pricing found for material '{material}' "
                f"or type designation '{type_designation}'"
            )
            errors.append(message)
            items.append(EnrichedItem(**details, price_match=False, error=message))
            continue

        key = material.upper()
        priced.add(key)
        fee_lines, notes = price_fees(
            fees_by_material.get(key, []),
            cutting_rate=pricing.cutting_fee,
            testing_rate=pricing.testing_fee,
            certificate_rate=pricing.cert_fee,
            service_rates=service_rates,
        )

        def fees_of(kind: str, fee_lines: list[FeeCharge] = fee_lines) -> float:
            return round(sum(fee.amount for fee in fee_lines if fee.kind == kind), 2)

        material_subtotal = quantity * pricing.unit_price
        total_fees = round(sum(fee.amount for fee in fee_lines), 2)
        items.append(
            EnrichedItem(
                **details,
                unit_price=round(pricing.unit_price, 2),
                material_subtotal=round(material_subtotal, 2),
                cutting_fee=fees_of("cutting"),
                testing_fee=fees_of("testing"),
                cert_fee=fees_of("certificate"),
                other_fees=fees_of("other"),
                fee_lines=fee_lines,
                notes=notes,
                total_fees=total_fees,
                line_total=round(material_subtotal + total_fees, 2),
                price_match=True,
            )
        )
    for key in fees_by_material:
        if key not in priced:
            warnings.append(
                f"Fees listed for {key}, which is not a priced order line, were not charged"
            )
    return items, errors, warnings


async def extract_order(po_text: str, boms: list[tuple[str, str]]) -> dict[str, Any]:
    """One extraction over the PO and its BOMs, with the example's saved schema."""
    schema, requirements, task, _ = await _persisted_schema(
        ORDER_EXAMPLE_KEY, ORDER_EXAMPLE_TASK_PATH
    )
    config = get_api_config()
    extractor = DataExtractor(config, model=config["model"], **get_model_options(config))
    results = await run_in_threadpool(
        extractor.extract,
        extraction_model=schema,
        requirements=requirements,
        user_requirements=task,
        documents=[combine_documents(po_text, boms)],
    )
    if not results or not results[0]:
        raise ValueError("No data could be extracted from the documents")
    return dict(results[0])


def calculate_summary(
    items: list[EnrichedItem], shipping: float = 0.0, tax_rate: float | None = None
) -> OrderSummary:
    """Calculate the order totals.

    Tax applies to the material, the additional fees and the shipping.
    """
    total_items = len(items)
    total_quantity = sum(item.quantity for item in items)
    material_subtotal = round(sum(item.material_subtotal or 0 for item in items), 2)
    total_fees = round(sum(item.total_fees for item in items), 2)
    taxable = material_subtotal + total_fees + shipping
    tax = round(taxable * tax_rate / 100, 2) if tax_rate else 0.0
    return OrderSummary(
        total_items=total_items,
        total_quantity=total_quantity,
        material_subtotal=material_subtotal,
        total_fees=total_fees,
        shipping=round(shipping, 2),
        tax_rate=tax_rate,
        tax=tax,
        grand_total=round(taxable + tax, 2),
    )


async def read_service_rates(pricing_file: UploadFile) -> dict[str, ServiceRate]:
    """The flat service rates (hydrostatic testing, packaging...) of the price list."""
    content = await pricing_file.read()
    if not content:
        return {}
    try:
        workbook = load_workbook(io.BytesIO(content), data_only=True)
        try:
            sheet = workbook[workbook.sheetnames[0]]
            return parse_service_rates(list(sheet.iter_rows(values_only=True)))
        finally:
            workbook.close()
    except Exception:
        logger.warning("Could not read service rates from the price list", exc_info=True)
        return {}


async def parse_pricing_file(pricing_file: UploadFile) -> list[PricingRow]:
    """Parse pricing Excel file with dynamic header detection.
    Supports both:
    - generic unit-price sheets
    - ABB sheets with Type/Conversion/Packing/Copper/KG Price/Weight columns
    """
    content_bytes = await pricing_file.read()
    if not content_bytes:
        return []

    def norm(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).lower())

    def to_float(value: object) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).strip()
        if not raw or raw.lower() in {"nan", "none"} or "#" in raw:
            return 0.0
        return float(raw.replace(",", "."))

    try:
        workbook = load_workbook(io.BytesIO(content_bytes), data_only=True)
        try:
            sheet = workbook[workbook.sheetnames[0]]
            rows = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
        finally:
            workbook.close()
        header_row_idx = None
        header_map: dict[str, int] = {}
        for idx, row in enumerate(rows):
            normalized = [norm(cell) for cell in row]
            row_map = {name: i for i, name in enumerate(normalized) if name}
            has_generic = any(
                k in row_map
                for k in (
                    "type",
                    "typedesignation",
                    "partdesignation",
                    "typepartdesignation",
                    "partnumber",
                    "partno",
                    "itemno",
                    "itemnumber",
                    "materialid",
                    "materialnumber",
                )
            ) and any(
                k in row_map
                for k in ("unitprice", "priceperunit", "price", "baseunitprice", "baseprice")
            )
            has_abb = "type" in row_map and "conversion" in row_map and "copper" in row_map
            if has_generic or has_abb:
                header_row_idx = idx
                header_map = row_map
                logger.info(f"Detected pricing header row at Excel row {idx + 1}")
                logger.info(f"Excel columns: {[str(v) for v in row]}")
                break
        if header_row_idx is None:
            logger.error("Could not find required columns in Excel file")
            return []

        def first_col(*names: str) -> int | None:
            for name in names:
                if name in header_map:
                    return header_map[name]
            return None

        item_col = first_col(
            "itemno", "itemnumber", "materialid", "materialnumber", "partnumber", "partno", "id"
        )
        type_col = first_col("type", "typedesignation", "partdesignation", "typepartdesignation")
        desc_col = first_col("description", "productdescription", "itemdescription")
        generic_price_col = first_col(
            "unitprice", "priceperunit", "price", "baseunitprice", "baseprice"
        )
        abb_price_col = first_col("kgpriceexclmachining", "kgprice", "total")
        cutting_col = first_col("cuttingfee", "cutting")
        testing_col = first_col("testingfee", "testing")
        cert_col = first_col("certificatefee", "certfee", "certificationfee")
        logger.info(
            "Matched columns - "
            f"Item: {item_col}, Type: {type_col}, "
            f"Generic Price: {generic_price_col}, "
            f"ABB Price: {abb_price_col}, "
            f"Cutting: {cutting_col}, "
            f"Testing: {testing_col}, Cert: {cert_col}"
        )
        pricing_rows: list[PricingRow] = []
        for row in rows[header_row_idx + 1 :]:
            material_id = (
                str(row[item_col] or "").strip()
                if item_col is not None and item_col < len(row)
                else ""
            )
            type_designation = (
                str(row[type_col] or "").strip()
                if type_col is not None and type_col < len(row)
                else ""
            )
            if not type_designation:
                # Price lists keyed only by part/material number have no type
                # column; fall back to the description (or the id) so the row is
                # still emitted and matchable by material_id.
                description = (
                    str(row[desc_col] or "").strip()
                    if desc_col is not None and desc_col < len(row)
                    else ""
                )
                type_designation = description or material_id
            if not type_designation or type_designation.lower() in {"nan", "none"}:
                continue
            try:
                if generic_price_col is not None and generic_price_col < len(row):
                    unit_price = to_float(row[generic_price_col])
                    cutting_fee = (
                        to_float(row[cutting_col])
                        if cutting_col is not None and cutting_col < len(row)
                        else 0.0
                    )
                    testing_fee = (
                        to_float(row[testing_col])
                        if testing_col is not None and testing_col < len(row)
                        else 0.0
                    )
                    cert_fee = (
                        to_float(row[cert_col])
                        if cert_col is not None and cert_col < len(row)
                        else 0.0
                    )
                else:
                    unit_price = (
                        to_float(row[abb_price_col])
                        if abb_price_col is not None and abb_price_col < len(row)
                        else 0.0
                    )
                    cutting_fee = 0.0
                    testing_fee = 0.0
                    cert_fee = 0.0
                if unit_price == 0:
                    continue
                pricing_rows.append(
                    PricingRow(
                        material_id=material_id or None,
                        type_designation=type_designation,
                        unit_price=unit_price,
                        cutting_fee=cutting_fee,
                        testing_fee=testing_fee,
                        cert_fee=cert_fee,
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping row due to parsing error: {e}")
                continue
        logger.info(f"Parsed {len(pricing_rows)} pricing rows from {pricing_file.filename}")
        return pricing_rows
    except Exception as e:
        logger.error(f"Error parsing pricing file: {e}", exc_info=True)
        return []


def generate_pdf(
    po_number: str,
    customer: str,
    items: list[EnrichedItem],
    summary: OrderSummary,
    customer_address: str | None = None,
    delivery_address: str | None = None,
    invoicing_address: str | None = None,
) -> bytes:
    """Generate a structured order-draft PDF with demo-specific branding."""
    logo_path = Path(__file__).parent.parent.parent / "public" / "logo.png"

    def money(value: float | None) -> str:
        if value is None:
            return "-"
        return f"USD {value:,.2f}"

    def split_text(pdf: FPDF, value: str, width: float) -> list[str]:
        text_value = str(value or "").replace("\r", "")
        paragraphs = text_value.split("\n")
        lines: list[str] = []
        for paragraph in paragraphs:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if pdf.get_string_width(candidate) <= width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines or [""]

    def ensure_space(pdf: FPDF, height: float) -> None:
        if pdf.get_y() + height > pdf.page_break_trigger:
            pdf.add_page()

    def render_info_block(
        pdf: FPDF, x: float, y: float, width: float, title: str, body: str
    ) -> float:
        pdf.set_xy(x, y)
        pdf.set_fill_color(245, 247, 250)
        pdf.set_draw_color(220, 225, 232)
        pdf.set_line_width(0.2)
        body_font_size = 9
        line_height = 4.3
        inner_width = width - 6
        body_lines: list[str] = []
        pdf.set_font("Helvetica", "", body_font_size)
        for paragraph in body.split("\n"):
            body_lines.extend(split_text(pdf, paragraph, inner_width))
        body_lines = body_lines or [""]
        box_height = 8 + len(body_lines) * line_height + 4
        pdf.rect(x, y, width, box_height, style="FD")
        pdf.set_xy(x + 3, y + 5)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(60, 70, 85)
        pdf.cell(inner_width, 0, title)
        pdf.set_xy(x + 3, y + 10)
        pdf.set_font("Helvetica", "", body_font_size)
        pdf.set_text_color(15, 23, 42)
        for line in body_lines:
            pdf.cell(inner_width, line_height, line, new_x="LMARGIN", new_y="NEXT")
            pdf.set_x(x + 3)
        return box_height

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    page_left = 12
    page_right = 198
    # Header
    if logo_path.exists():
        pdf.image(str(logo_path), x=page_left, y=12, w=48)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_xy(120, 15)
    pdf.cell(68, 9, "Order Draft", align="R")
    pdf.set_draw_color(210, 214, 220)
    pdf.set_line_width(0.4)
    pdf.line(page_left, 28, page_right, 28)
    left_x = page_left
    right_x = 125
    top_y = 34
    left_width = 104
    right_width = page_right - right_x
    buyer_body = customer or "Not available"
    delivery_body = delivery_address or customer_address or customer or "Not available"
    invoice_body = invoicing_address or customer_address or customer or "Not available"
    left_y = top_y
    left_y += render_info_block(pdf, left_x, left_y, left_width, "Buyer", buyer_body) + 4
    left_y += (
        render_info_block(pdf, left_x, left_y, left_width, "Delivery address", delivery_body) + 4
    )
    left_y += render_info_block(pdf, left_x, left_y, left_width, "Invoicing address", invoice_body)
    order_details = [
        ("Date", datetime.now().strftime("%d/%m/%Y")),
        ("Order draft no.", f"DRAFT-{po_number or 'N/A'}"),
        ("Your reference", po_number or "-"),
        ("Currency", "USD"),
        ("Total lines", str(summary.total_items)),
        ("Total quantity", f"{summary.total_quantity}"),
    ]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(60, 70, 85)
    details_height = 8 + len(order_details) * 6 + 4
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(220, 225, 232)
    pdf.rect(right_x, top_y, right_width, details_height, style="FD")
    pdf.set_xy(right_x + 3, top_y + 5)
    pdf.cell(right_width - 6, 0, "Order details")
    detail_y = top_y + 12
    for label, value in order_details:
        pdf.set_xy(right_x + 3, detail_y)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(28, 4.5, label)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(right_width - 35, 4.5, value)
        detail_y = pdf.get_y() + 1
    y = max(left_y, top_y + details_height) + 8
    ensure_space(pdf, 18)
    pdf.set_xy(page_left, y)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(236, 240, 244)
    pdf.set_text_color(20, 20, 20)
    col_widths = [20, 67, 12, 22, 28, 37]
    headers = ["Material", "Description", "Qty", "Unit Price", "Fees", "Line Total"]
    for width, label in zip(col_widths, headers):
        pdf.cell(width, 8, label, border=1, align="C", fill=True)
    pdf.ln(8)
    for item in items:
        pdf.set_font("Helvetica", "", 8)
        description_lines = split_text(
            pdf,
            "\n".join(
                [
                    item.description,
                    f"Type: {item.type_designation}" if item.type_designation else "",
                    f"Delivery: {item.delivery_date}" if item.delivery_date else "",
                    f"Error: {item.error}" if item.error else "",
                ]
            ).strip(),
            col_widths[1] - 4,
        )
        fee_text = "\n".join(f"{fee.name} {fee.amount:.2f}" for fee in item.fee_lines) or "-"
        fee_lines = split_text(pdf, fee_text, col_widths[4] - 4)
        row_line_count = max(1, len(description_lines), len(fee_lines))
        row_height = max(8, row_line_count * 4.3 + 2)
        ensure_space(pdf, row_height)
        x = page_left
        y = pdf.get_y()
        cells = [
            item.material,
            description_lines,
            str(item.quantity),
            money(item.unit_price),
            fee_lines,
            money(item.line_total),
        ]
        for idx, width in enumerate(col_widths):
            pdf.rect(x, y, width, row_height)
            pdf.set_xy(x + 2, y + 2)
            if idx == 1:
                for line in description_lines:
                    pdf.cell(width - 4, 4.2, line, new_x="LMARGIN", new_y="NEXT")
                    pdf.set_x(x + 2)
            elif idx == 4:
                pdf.set_font("Helvetica", "", 7.5)
                for line in fee_lines:
                    pdf.cell(width - 4, 4.0, line, new_x="LMARGIN", new_y="NEXT")
                    pdf.set_x(x + 2)
            else:
                align = "R" if idx in {2, 3, 5} else "L"
                pdf.set_font("Helvetica", "", 8)
                pdf.cell(width - 4, 4.5, str(cells[idx]), align=align)
            x += width
        pdf.set_y(y + row_height)
    y = pdf.get_y() + 8
    summary_rows = [
        ("Material subtotal", money(summary.material_subtotal)),
        ("Additional fees", money(summary.total_fees)),
    ]
    if summary.shipping:
        summary_rows.append(("Shipping", money(summary.shipping)))
    if summary.tax_rate:
        summary_rows.append((f"Tax ({summary.tax_rate:g}%)", money(summary.tax)))
    summary_rows.append(("Grand total", money(summary.grand_total)))
    box_height = 14 + 6.5 * len(summary_rows)
    ensure_space(pdf, box_height)
    summary_x = 118
    summary_w = page_right - summary_x
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(220, 225, 232)
    pdf.rect(summary_x, y, summary_w, box_height, style="FD")
    pdf.set_xy(summary_x + 3, y + 5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(summary_w - 6, 0, "Order summary")
    row_y = y + 12
    for label, value in summary_rows:
        pdf.set_xy(summary_x + 3, row_y)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(40, 5, label)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(summary_w - 46, 5, value, align="R")
        row_y += 6.5
    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin1")
    return bytes(output)


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
    Process a purchase order with streaming progress updates.
    Steps:
    1. Parse the PO and the BOMs
    2. Extract everything in one go with the example's saved schema: the PO header, the
       order lines with their BOM details, and the fees that apply
    3. Price the lines and fees from the price list, and total the order
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
            # 1. Parse every document to text
            yield sse_event("status", {"message": "Parsing documents..."})
            po_text, *bom_texts = await asyncio.gather(
                _parse_upload(po_file, "po"), *[_parse_upload(f, "bom") for f in bom_files]
            )
            # 2. Extract the header, the order lines and the fees
            yield sse_event("status", {"message": "Extracting information..."})
            parts = split_order(
                await extract_order(
                    po_text,
                    [(f.filename or "BOM", t) for f, t in zip(bom_files, bom_texts, strict=True)],
                )
            )
            logger.info(
                "Extracted PO %s: %d lines, %d fee entries",
                parts.po_number,
                len(parts.lines),
                len(parts.fees),
            )
            # 3. Read the price list, price the lines and write the order draft
            yield sse_event("status", {"message": "Preparing results..."})
            pricing_rows = await parse_pricing_file(pricing_file)
            logger.info(f"Parsed {len(pricing_rows)} pricing rows")
            await pricing_file.seek(0)
            service_rates = await read_service_rates(pricing_file)
            enriched_items, errors, warnings = price_order(parts, pricing_rows, service_rates)
            summary = calculate_summary(
                enriched_items, shipping=parts.shipping, tax_rate=parts.tax_rate
            )
            job_id = str(uuid.uuid4())
            pdf_bytes = generate_pdf(
                parts.po_number or "",
                parts.customer or "",
                enriched_items,
                summary,
                customer_address=None,
                delivery_address=parts.shipping_address,
                invoicing_address=None,
            )
            now = datetime.now().timestamp()
            _cleanup_expired_pdfs()
            pdf_storage[job_id] = (pdf_bytes, now)
            logger.info(f"Generated PDF with job_id: {job_id}")
            # Build response
            response = ProcessOrderResponse(
                success=True,
                po_number=parts.po_number,
                customer=parts.customer,
                header=parts.header,
                items=enriched_items,
                summary=summary,
                errors=errors,
                warnings=[
                    *warnings,
                    *[note for item in enriched_items for note in item.notes],
                ],
                pdf_job_id=job_id,
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
async def download_pdf(job_id: str, download: bool = False) -> Response:
    """Return generated order draft PDF for inline preview or download."""
    entry = pdf_storage.get(job_id)
    if not entry or (datetime.now().timestamp() - entry[1] > PDF_TTL_SECONDS):
        if entry:
            del pdf_storage[job_id]
        raise HTTPException(status_code=404, detail="PDF not found or expired")
    pdf_bytes = entry[0]
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disposition}; filename=order_draft_{job_id}.pdf"},
    )


# ============================================================================
# Custom use case: extraction described by the user, temporary schemas
# ============================================================================
# Unlike the fixed PO/BOM schemas above, the schema here is generated from a prompt
# the user writes or edits and is kept only in memory: nothing is written to SCHEMA_DIR.
MAX_CUSTOM_BOMS = 10
MAX_PROMPT_CHARS = 8000
_CUSTOM_SCHEMA_CACHE_SIZE = 64
_custom_schema_cache: dict[str, tuple[Any, Any]] = {}


class CustomSchemaRequest(BaseModel):
    requirements: str
    # Build a new schema even when one for the same prompt is already in memory.
    regenerate: bool = False


def clean_requirements(text: str) -> str:
    """The prompt to generate a schema from, or a 400 when it is unusable."""
    cleaned = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if len(cleaned) < 10:
        raise HTTPException(status_code=400, detail="Describe what to extract")
    if len(cleaned) > MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400, detail=f"The prompt is over {MAX_PROMPT_CHARS} characters"
        )
    return cleaned


def combine_documents(po_markdown: str, bom_markdowns: list[tuple[str, str]]) -> str:
    """One text for a single extraction, with each document labelled by its role."""
    parts = [f"=== PURCHASE ORDER ===\n\n{po_markdown.strip()}"]
    for index, (filename, markdown) in enumerate(bom_markdowns, start=1):
        parts.append(f"=== BILL OF MATERIALS {index} ({filename}) ===\n\n{markdown.strip()}")
    return "\n\n".join(parts)


def _type_label(annotation: Any) -> str:
    if get_origin(annotation) in (Union, UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            annotation = args[0]
    if get_origin(annotation) is list:
        return "list"
    return getattr(annotation, "__name__", str(annotation)).replace("typing.", "")


def _child_model(annotation: Any) -> Any:
    """The record model inside ``list[Model]`` / ``Model | None``, if there is one."""
    for arg in get_args(annotation):
        if arg is type(None):
            continue
        if hasattr(arg, "model_fields"):
            return arg
        nested = _child_model(arg)
        if nested is not None:
            return nested
    return None


def describe_schema(schema: Any) -> list[dict]:
    """Name, type and description of each field, with the fields of nested records."""
    described = []
    for name, info in schema.model_fields.items():
        entry: dict[str, Any] = {
            "name": name,
            "type": _type_label(info.annotation),
            "description": info.description or "",
            "required": info.is_required(),
        }
        child = _child_model(info.annotation)
        if child is not None:
            entry["children"] = describe_schema(child)
        described.append(entry)
    return described


# OpenAI rejects structured-output schema names longer than 64 characters, and the
# generator names the model after the start of the prompt.
_MAX_SCHEMA_NAME = 60


def _shorten_schema_name(schema: Any) -> Any:
    if len(schema.__name__) > _MAX_SCHEMA_NAME:
        schema.__name__ = schema.__name__[:_MAX_SCHEMA_NAME].rstrip("_")
        schema.__qualname__ = schema.__name__
    return schema


async def _custom_schema(
    requirements_text: str, *, regenerate: bool = False
) -> tuple[str, Any, Any]:
    """Generate (or reuse, within this process) the temporary schema for this prompt."""
    schema_id = schema_id_from_requirements(requirements_text)
    cached = None if regenerate else _custom_schema_cache.get(schema_id)
    if cached is None:
        config = get_api_config()
        generator = SchemaGenerator(config, model=config["model"], **get_model_options(config))
        schema = _shorten_schema_name(
            wrap_schema_with_numeric_normalizers(
                await run_in_threadpool(
                    generator.generate_schema, user_requirements=requirements_text
                )
            )
        )
        cached = (schema, generator.item_requirements)
        while len(_custom_schema_cache) >= _CUSTOM_SCHEMA_CACHE_SIZE:
            _custom_schema_cache.pop(next(iter(_custom_schema_cache)))
        _custom_schema_cache[schema_id] = cached
    return schema_id, cached[0], cached[1]


@router.post("/custom/schema")
async def generate_custom_schema(request: CustomSchemaRequest) -> dict:
    """Generate a temporary extraction schema from the user's prompt."""
    requirements = clean_requirements(request.requirements)
    try:
        schema_id, schema, _ = await _custom_schema(requirements, regenerate=request.regenerate)
        return {
            "schema_id": schema_id,
            "schema_name": schema.__name__,
            "fields": describe_schema(schema),
        }
    except Exception as exc:
        logger.exception("Custom schema generation failed")
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc


async def _parse_upload(upload: UploadFile, prefix: str) -> str:
    pdf_bytes = await upload.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        return await run_in_threadpool(_parse_document_markdown, tmp_path, upload.filename, prefix)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/custom/extract")
async def extract_custom(
    po_file: Annotated[UploadFile, File(description="Purchase order PDF")],
    requirements: Annotated[str, Form(description="What to extract, in plain language")],
    bom_files: Annotated[list[UploadFile] | None, File(description="Optional BOM PDFs")] = None,
) -> dict:
    """Extract what the prompt asks for from one PO and, optionally, its BOMs.

    The documents go to the model together, so a prompt can align each PO item with
    its BOM.
    """
    boms = bom_files or []
    if len(boms) > MAX_CUSTOM_BOMS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_CUSTOM_BOMS} BOMs")
    requirements = clean_requirements(requirements)
    try:
        _, schema, item_requirements = await _custom_schema(requirements)
        po_markdown, *bom_markdowns = await asyncio.gather(
            _parse_upload(po_file, "po"), *[_parse_upload(f, "bom") for f in boms]
        )
        combined = combine_documents(
            po_markdown,
            [(f.filename or "BOM", md) for f, md in zip(boms, bom_markdowns, strict=True)],
        )
        config = get_api_config()
        extractor = DataExtractor(config, model=config["model"], **get_model_options(config))
        results = await run_in_threadpool(
            extractor.extract,
            extraction_model=schema,
            requirements=item_requirements,
            user_requirements=requirements,
            documents=[combined],
        )
        if not results or not results[0]:
            raise ValueError("No data could be extracted from the documents")
        return {
            "data": results[0],
            "documents": [po_file.filename, *[f.filename for f in boms]],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Custom extraction failed")
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc


# ============================================================================
# Examples with a fixed prompt: the schema is generated once and kept
# ============================================================================
# Each example's prompt lives in a file, so that it does not depend on what the browser
# sends. The schema is saved next to the other schemas and reused; it is generated
# again only when the prompt changes.
SINGLE_EXAMPLE_KEY = "luvata_single_example"
SINGLE_EXAMPLE_TASK_PATH = SCHEMA_DIR / f"{SINGLE_EXAMPLE_KEY}_task.txt"
ORDER_EXAMPLE_KEY = "luvata_order_example"
ORDER_EXAMPLE_TASK_PATH = SCHEMA_DIR / f"{ORDER_EXAMPLE_KEY}_task.txt"
_schema_locks: dict[str, asyncio.Lock] = {}


async def _persisted_schema(key: str, task_path: Path) -> tuple[Any, Any, str, bool]:
    """A fixed-prompt schema and its requirements, the prompt, and whether it was saved."""
    task = clean_requirements(task_path.read_text(encoding="utf-8"))
    async with _schema_locks.setdefault(key, asyncio.Lock()):
        try:
            loaded = load_schema(key, task)
        except Exception:
            # A saved schema that cannot be imported is generated again.
            logger.warning("The saved schema '%s' is unusable", key, exc_info=True)
            loaded = None
        if loaded is not None:
            schema, requirements = loaded
            return schema, requirements, task, True
        config = get_api_config()
        generator = SchemaGenerator(config, model=config["model"], **get_model_options(config))
        generated = await run_in_threadpool(generator.generate_schema, user_requirements=task)
        schema = _shorten_schema_name(wrap_schema_with_numeric_normalizers(generated))
        requirements = generator.item_requirements
        try:
            # The generated model is saved as it is; loading wraps it again.
            save_schema(generated, requirements, key, task)
        except OSError:
            logger.warning("Could not save the schema '%s'", key, exc_info=True)
        return schema, requirements, task, False


async def _single_example_schema() -> tuple[Any, Any, str, bool]:
    return await _persisted_schema(SINGLE_EXAMPLE_KEY, SINGLE_EXAMPLE_TASK_PATH)


@router.post("/example/single/schema")
async def single_example_schema() -> dict:
    """Make sure the example's schema exists, generating and saving it on first use."""
    try:
        schema, _, _, cached = await _single_example_schema()
        return {
            "cached": cached,
            "schema_name": schema.__name__,
            "fields": describe_schema(schema),
        }
    except Exception as exc:
        logger.exception("Single-file example schema failed")
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc


@router.post("/example/single/extract")
async def single_example_extract(
    po_file: Annotated[UploadFile, File(description="The example purchase order PDF")],
) -> dict:
    """Extract the example's fields from the purchase order with the saved schema."""
    try:
        schema, requirements, task, _ = await _single_example_schema()
        text = await _parse_upload(po_file, "po")
        config = get_api_config()
        extractor = DataExtractor(config, model=config["model"], **get_model_options(config))
        results = await run_in_threadpool(
            extractor.extract,
            extraction_model=schema,
            requirements=requirements,
            user_requirements=task,
            documents=[text],
        )
        if not results or not results[0]:
            raise ValueError("No data could be extracted from the document")
        return {"data": results[0], "documents": [po_file.filename]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Single-file example extraction failed")
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc
