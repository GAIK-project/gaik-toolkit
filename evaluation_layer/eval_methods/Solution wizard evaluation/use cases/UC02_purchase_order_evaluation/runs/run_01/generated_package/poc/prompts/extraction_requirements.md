# Extraction Requirements — PurchaseOrderERPRecord

## Purpose

Extract a structured ERP-compatible purchase order record from a customer purchase order PDF.
The document may be a native digital PDF or a scanned PDF image. It may contain complex
multi-page tables, merged or hierarchical column headers, rows that continue across page breaks,
and free-text notes embedded inside table areas.

The extracted record must be faithful to what is written in the source document. Do not invent,
infer, or normalise any value that is not explicitly present. When a required field cannot be
found or is ambiguous, flag it for human review rather than guessing.

---

## Output Structure

The output is a single JSON object with the following top-level structure:

```
PurchaseOrderERPRecord
├── purchase_order_number   (required, str)
├── delivery_date           (required, str)
├── delivery_address        (required, str)
├── vendor_number           (required, str)
└── line_items              (required, list of LineItem objects)
    └── LineItem
        ├── item_number             (required, str)
        ├── article_code            (required, str)
        ├── dimensions              (required, str)
        ├── material_grade          (required, str)
        ├── quantity                (required, str)
        ├── product_form            (required, str — enum)
        ├── standard_designation    (optional, str or null)
        ├── cut_length              (optional, str or null)
        ├── temper_or_condition     (optional, str or null)
        ├── hardness_hv             (optional, float or null)
        ├── min_bend_radius         (optional, float or null)
        ├── delivery_length_note    (optional, str or null)
        ├── applicable_standard     (optional, str or null)
        └── special_flags           (optional, str or null)
```

---

## Header Fields

### purchase_order_number
- **What it is:** The customer's own purchase order reference number, typically labelled
  "Purchase Order No.", "PO No.", "Order No.", "Order Reference", or similar.
- **How to extract:** Copy the value exactly as it appears, including leading zeros, hyphens,
  and any alphanumeric characters. Do not reformat or pad.
- **Example values:** `PO-2024-00123`, `4500012345`, `00987/24`
- **If missing:** Flag for human review.

### delivery_date
- **What it is:** The requested delivery date stated on the purchase order, typically labelled
  "Delivery Date", "Required Delivery", "Requested Delivery", "Ship By", or similar.
- **Format required:** DD/MM/YYYY (e.g. `15/03/2025`). If the document uses a different date
  format (e.g. YYYY-MM-DD or written month), convert to DD/MM/YYYY.
- **If multiple dates exist** (e.g. one per line item): capture the header-level date here; per-item
  dates may appear in `delivery_length_note` on the line item if they differ.
- **If missing:** Flag for human review.

### delivery_address
- **What it is:** The address to which the goods should be delivered, typically labelled
  "Deliver To", "Ship To", "Delivery Address", or "Consignee".
- **How to extract:** Capture the full address block as a single string, preserving line breaks
  as spaces or commas. Include company name, street, city, postal code, and country if present.
- **Example value:** `ACME Manufacturing GmbH, Industriestrasse 42, 45678 Musterstadt, Germany`
- **If missing:** Flag for human review.

### vendor_number
- **What it is:** The identifier the customer uses internally to refer to the supplier/vendor,
  typically labelled "Vendor No.", "Supplier No.", "Vendor Code", "Our Vendor ID", or similar.
- **How to extract:** Copy exactly as written, preserving leading zeros and alphanumeric format.
- **Example values:** `V-00045`, `0012345`, `SUP-887`
- **If missing:** Flag for human review.

---

## Line Item Fields

Each row in the purchase order's item table corresponds to one LineItem object. A new LineItem
must be created for each distinct ordered item. Do not merge rows that represent separate items
even if they share the same material grade or article code.

When a table row is split across a page break, combine all parts of that row into a single
LineItem — do not create duplicate entries for the continuation.

### item_number
- **What it is:** The sequential line number or position identifier for the item within the PO,
  typically in a column labelled "Item", "Pos.", "Position", "Line", or "No.".
- **How to extract:** Copy exactly as written, including leading zeros.
- **Example values:** `001`, `010`, `1`, `A-01`
- **If missing:** Flag for human review.

### article_code
- **What it is:** The customer's own article or product code for the ordered item, typically
  labelled "Article No.", "Material No.", "Part No.", "Item Code", "Product Code", or similar.
- **How to extract:** Copy the value exactly as it appears. Preserve all characters including
  leading zeros, hyphens, dots, and any alphanumeric format. Never truncate or reformat.
- **Example values:** `0045-AL-001`, `123456789`, `Al-5083-H111-3x1500x3000`
- **If missing:** Flag for human review.

### dimensions
- **What it is:** The dimensions of the ordered material, typically expressed as thickness ×
  width × length, diameter, or similar, in a column labelled "Dimensions", "Size", "Thickness",
  "Gauge", or similar. Units (mm, cm, inch) may be in the same cell or in the column header.
- **How to extract:** Capture the full dimension string as written, including units if present
  in the same cell. If units are only in the column header, append them.
- **Example values:** `3 x 1500 x 3000 mm`, `Ø 50 mm`, `25x200x6000`, `4.5 mm`
- **If missing:** Flag for human review.

### material_grade
- **What it is:** The alloy or material grade designation, typically in a column labelled
  "Material", "Alloy", "Grade", "Material Grade", or "Specification".
- **How to extract:** Copy exactly as written. Common formats include EN designations
  (e.g. `EN AW-5083`, `EN AW-6082`), steel grades (e.g. `S355J2`, `DC01`), or proprietary
  designations. Preserve hyphens, spaces, and case exactly.
- **Example values:** `EN AW-5083`, `S355J2+N`, `6061-T6`, `AlMg4.5Mn`
- **If missing:** Flag for human review.

### quantity
- **What it is:** The ordered quantity, typically in a column labelled "Quantity", "Qty", "Order
  Qty", "Pieces", or "Weight (kg)".
- **How to extract:** Capture the numeric value together with the unit of measure if it appears
  in the same cell (e.g. `500 kg`, `10 pcs`, `2500`). Do not drop the unit. If the unit is only
  in the column header, append it to the value.
- **Example values:** `500 kg`, `10 pcs`, `2500 kg`, `3 sheets`
- **If missing:** Flag for human review.

### product_form
- **What it is:** The physical form (shape) of the ordered material.
- **Allowed values (exact match required):**
  - `Flat` — sheet, plate, strip, or any flat-rolled product
  - `round` — round bar, rod, wire, tube with circular cross-section
  - `rectangular bar` — rectangular or square bar, flat bar, rectangular hollow section
- **How to extract:** Read the product description, dimensions, or any "Form" / "Shape" column.
  Map to the closest allowed value. Use contextual clues: a product described as a sheet or
  plate maps to `Flat`; a rod or round bar maps to `round`; a flat bar or square bar maps to
  `rectangular bar`.
- **If the form cannot be determined with confidence:** Flag for human review rather than guessing.
- **If missing:** Flag for human review.

---

## Optional Line Item Fields

These fields must be extracted when present; set to **null** when absent. Do not invent values.

### standard_designation
- Material or product standard designation found in the line item, e.g. `EN 485-2`, `EN 573-3`,
  `ASTM B209`. Typically in a "Standard", "Norm", or "Spec." column. Null if absent.

### cut_length
- Specific cut length requested by the customer, if different from the standard mill length,
  e.g. `2450 mm`, `cut to 1200`. Null if absent.

### temper_or_condition
- Material temper, heat treatment, or delivery condition, e.g. `H111`, `T6`, `O`, `annealed`,
  `as-rolled`. May appear in a "Temper", "Condition", or "Delivery Condition" column, or
  embedded in the article description. Null if absent.

### hardness_hv
- Required hardness in Vickers units (HV), expressed as a numeric value.
  Extract only the numeric part (e.g. if the document says "max. 95 HV", extract `95.0`).
  Null if absent.

### min_bend_radius
- Minimum bend radius requirement, as a numeric value. Extract only the number; units
  may be noted in `special_flags`. Null if absent.

### delivery_length_note
- Any free-text note about delivery length, cut tolerance, straightness, or packaging
  length constraints found in or near the line item. Null if absent.

### applicable_standard
- Any additional standard or specification reference relevant to the line item beyond
  `standard_designation`, e.g. a quality or testing standard (`EN 10204 3.1`, `ISO 6892`).
  Null if absent.

### special_flags
- Any special instructions, quality requirements, customer-specific notes, or flags found
  within or immediately adjacent to the line item (e.g. "First Article Inspection required",
  "No weld repair", "Customer hold"). Null if absent. If multiple notes exist, concatenate
  them as a comma-separated string.

---

## General Extraction Rules

1. **Fidelity over normalisation:** Copy values exactly as they appear. Do not correct spelling,
   reformat codes, or apply unit conversions unless explicitly instructed above.

2. **No hallucination:** Never invent a value that is not explicitly present in the source
   document. If a required field is absent or unreadable, flag it for human review; do not guess.

3. **Leading zeros:** Preserve all leading zeros in identifiers (order numbers, article codes,
   item numbers, vendor numbers). They are semantically significant.

4. **Multi-page tables:** When a table continues across page breaks, treat continuation rows as
   part of the same table. Do not create duplicate line items for rows split across pages.

5. **Notes in table areas:** Free-text notes embedded inside the item table (e.g. below a line
   item row) should be captured in `special_flags` or `delivery_length_note` on the relevant
   line item, not discarded.

6. **Merged/hierarchical headers:** When column headers span multiple rows (e.g. "Dimensions"
   spans sub-columns "Thickness", "Width", "Length"), combine the relevant sub-values into a
   single `dimensions` string for each line item.

7. **Missing optional fields:** Set to null. Do not use empty string `""` as a substitute for null.

8. **Required fields missing or uncertain:** Flag for human review using the confidence/verification
   mechanism. Set confidence to a low value and provide a short reason (e.g. "field not found in
   document" or "value ambiguous — two candidate values found").

9. **product_form enum enforcement:** The value must be exactly one of `Flat`, `round`, or
   `rectangular bar`. No other values are permitted. If the product form cannot be determined
   with high confidence, flag for human review.

10. **delivery_date format:** Always output in DD/MM/YYYY. Convert from any other format found
    in the document.
