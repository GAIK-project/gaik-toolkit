# Purchase Order ERP Record — Extraction Requirements

## Overview
Extract structured header and line-item data from customer purchase order (PO) PDF documents.
The output must conform to the `PurchaseOrderERPRecord` schema and be ready for ERP entry
after human review.

## Document Characteristics
- Input: PDF files (digital/native text or scanned image-based)
- Language: English
- Documents may contain:
  - Complex multi-column or multi-section tables
  - Merged or hierarchical table headers
  - Line-item rows that continue across page breaks
  - Notes, annotations, or commentary embedded within table areas
  - Alphanumeric product identifiers with mixed case and leading zeros

---

## Critical Preservation Rules (Non-Negotiable)

1. **Leading zeros** — Preserve all leading zeros in item numbers, article codes, vendor
   numbers, and any identifier field. Never strip leading zeros.
2. **Case sensitivity** — Preserve the exact letter case of article codes, material grades,
   and standard designations as they appear in the document.
3. **Punctuation** — Preserve hyphens, slashes, dots, plus signs, and other punctuation in
   codes and identifiers exactly as written.
4. **Units** — Preserve measurement units exactly as written (e.g., `pcs`, `kg`, `m`, `mm`).
   Never drop units from quantity or dimension fields.
5. **Dimensions** — Extract dimension strings exactly as written (e.g., `12x1500x3000 mm`,
   `Ø50 mm`, `50x50x5 mm`). Do not reformat or normalize.
6. **Dates** — Normalize all dates to DD/MM/YYYY format regardless of how they appear in the
   document (e.g., `15 March 2025` → `15/03/2025`).

---

## Header Fields (Required — extract once per document)

### `purchase_order_number`
- The PO's unique identifier, typically labelled "Purchase Order No.", "PO No.", "Order No.",
  or similar.
- Extract exactly as printed. Preserve leading zeros, hyphens, and alphanumeric formatting.
- Examples: `"0045231"`, `"PO-2024-00123"`

### `delivery_date`
- The requested delivery or shipment date.
- Commonly labelled "Delivery Date", "Required Date", "Ship Date", "Due Date".
- Normalize to DD/MM/YYYY format.
- If only month and year appear, record as `01/MM/YYYY`.
- Example: `"15 March 2025"` → `"15/03/2025"`

### `delivery_address`
- The full delivery / ship-to address as stated in the document.
- Include street, city, country, and postal code if present.
- Preserve as a single string; use commas to separate lines if needed.
- Do not substitute the billing or invoice address.

### `vendor_number`
- The supplier or vendor identifier assigned by the buyer.
- Commonly labelled "Vendor No.", "Supplier No.", "Vendor ID", or found near the buyer's
  company header block.
- Preserve leading zeros and punctuation exactly.
- Examples: `"00456"`, `"V-1023"`

---

## Line Items (Required — one entry per ordered item row)

Each row in the PO's line-item table must produce exactly one entry in `line_items`.
- Rows that **continue across a page break** must be **merged** into a single entry.
- **Repeated header rows** across pages are not data rows — ignore them.
- **Note rows** embedded between line items must NOT create a new entry; if the note
  applies to the preceding item, record it in `special_flags` or `delivery_length_note`.

### `item_number` (required)
- Sequential line number, typically in the first column.
- Must be a four-character string with leading zeros preserved.
- Examples: `"0010"`, `"0020"`, `"0030"`

### `article_code` (required)
- The buyer's or supplier's product / material code or part number.
- Commonly labelled "Article", "Part No.", "Material No.", "Item Code", "Product Code".
- **Case-sensitive** — preserve exactly as printed, including mixed case, hyphens, slashes,
  plus signs, and numeric suffixes.
- Examples: `"S355J2+N"`, `"EN-AW-6082-T6"`, `"X5CrNi18-10"`

### `dimensions` (required)
- The physical dimensions of the item as stated on the PO.
- Extract the full dimension string as written; do not reformat or convert units.
- Include all components: thickness × width × length, diameter, or cross-section as
  appropriate.
- Examples: `"12x1500x3000 mm"`, `"Ø50 mm"`, `"50x50x5 mm"`, `"3x1000 coil"`

### `material_grade` (required)
- The material grade or alloy designation.
- Preserve exactly as written, including standard prefix codes, numeric codes, suffixes,
  and delivery conditions attached to the grade.
- Examples: `"S355J2+N"`, `"1.4301"`, `"AlMgSi1 T6"`, `"DC01"`

### `quantity` (required)
- The ordered quantity including the numeric value and its unit of measure.
- Preserve the unit exactly as written; never drop it.
- Examples: `"10 pcs"`, `"500 kg"`, `"2 sheets"`, `"1500 m"`

### `product_form` (required)
- The physical form or shape of the product.
- **Must be exactly one of:** `Flat`, `round`, `rectangular bar`
- Mapping guidance for common document terms:
  - `Flat`: plate, sheet, strip, coil, blanks
  - `round`: rod, round bar, circle, round tube (solid), round wire
  - `rectangular bar`: square bar, flat bar, RHS (rectangular hollow section), SHS
    (square hollow section), angle, channel
- If the product form is ambiguous, choose the closest match and flag it in `special_flags`.

---

## Optional Line-Item Fields
Set to `null` when the field is not present in the document.
**Never use an empty string `""` or placeholder text such as `"N/A"` for absent optional fields.**

### `standard_designation`
Material or product standard reference (e.g., `"EN 10025-2"`, `"ASTM A36"`).
`null` if not stated for this line item.

### `cut_length`
Cut-to-length specification if the item is ordered to a specific cut length
(e.g., `"3000 mm"`, `"cut to 500 mm"`).
`null` if not stated.

### `temper_or_condition`
Temper, heat treatment, or delivery condition stated separately from the material grade
(e.g., `"T6"`, `"annealed"`, `"+A"`, `"H34"`).
`null` if not stated separately.

### `hardness_hv`
Required hardness in Vickers (HV) as a **numeric value only** — do not include the unit.
Example: `180` (not `"180 HV"`).
`null` if not stated.

### `min_bend_radius`
Minimum bend radius as a **numeric value only** — do not include the unit.
`null` if not stated.

### `delivery_length_note`
Any note about delivery length, cut tolerances, or length-related constraints
(e.g., `"length tolerance ±5 mm"`, `"random lengths 3–6 m"`).
`null` if not stated.

### `applicable_standard`
An additional applicable standard reference beyond `standard_designation` if present
(e.g., a testing or certification standard).
`null` if not stated.

### `special_flags`
Any special requirements, quality notes, or flags on the line item
(e.g., `"mill certificate required"`, `"100% ultrasonic inspection"`, `"RoHS compliant"`).
`null` if not stated.

---

## Multi-Page and Complex Table Handling

- If a line-item row is split across a page break, combine all parts before extracting fields.
- If table headers repeat on a new page, do not treat them as data rows.
- If a note appears between two line items, determine whether it applies to the preceding item
  (→ `special_flags` or `delivery_length_note`) or is a document-level note (→ ignore or
  record in the nearest applicable header field).
- Merged or hierarchical header cells define column semantics — use them to assign field
  values correctly but do not extract them as item rows.

---

## Hallucination Prevention

- Do **not** invent, estimate, or guess values for any field not present in the document.
- Do **not** alter, normalize, or "correct" article codes, material grades, or identifiers —
  extract them character-for-character.
- Do **not** convert units or reformat dimension strings.
- Do **not** carry a field value from one line item to another (e.g., do not repeat the
  material grade from item `0010` into item `0020` if it is not explicitly stated for `0020`).
- For optional fields absent from the document: `null`, not `""`, not `"N/A"`.

---

## Output Format

Return a single JSON object conforming to `PurchaseOrderERPRecord`:

```json
{
  "purchase_order_number": "...",
  "delivery_date": "DD/MM/YYYY",
  "delivery_address": "...",
  "vendor_number": "...",
  "line_items": [
    {
      "item_number": "0010",
      "article_code": "...",
      "dimensions": "...",
      "material_grade": "...",
      "quantity": "...",
      "product_form": "Flat",
      "standard_designation": null,
      "cut_length": null,
      "temper_or_condition": null,
      "hardness_hv": null,
      "min_bend_radius": null,
      "delivery_length_note": null,
      "applicable_standard": null,
      "special_flags": null
    }
  ]
}
```

All optional fields not present in the document must appear explicitly as `null`.
