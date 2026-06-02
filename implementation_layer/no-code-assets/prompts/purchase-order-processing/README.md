# Purchase Order Processing Prompts

A prompt-only workflow for processing customer purchase orders in ChatGPT. No code, no file server, no external tools required. Upload the documents, paste a prompt, and receive structured JSON output with all extracted fields and calculated pricing.

---

## Two prompt types

### `prompt_single_document_PO.txt` — Single PDF purchase order

Use this when the purchase order is a **single PDF** that contains all required information (item descriptions, quantities, material numbers) without accompanying Bill of Material files.

**What it does:**
- Extracts PO header fields: order date, delivery date, PO number, supplier number, shipping address, payment terms
- Extracts line items: item number, description, quantity, material number
- Matches each line item against the price list by material number or description
- Calculates per-line costs: material cost, cutting cost, testing cost, certification cost
- Computes order totals: material subtotal, volume discount, net material cost, total fees, tax, and grand total
- Returns everything as a single JSON object

**Files to upload in ChatGPT:**
- `PO.pdf` — the purchase order
- `price_list.pdf` — the supplier price list

**Sample data:** `data/single document PO/`
```
single document PO/
├── customer_data/
│   └── PO.pdf
└── price_list/
    └── price_list.pdf
```

---

### `prompt_multi_document_PO.txt` — Purchase order with multiple Bills of Material

Use this when the purchase order is accompanied by **one or more BOM PDFs**. Each PO line item is linked to a BOM via a material number, and the BOM provides the technical details (part designation, dimensions, fee flags) needed for pricing.

**What it does:**
- Extracts PO header fields: order date, buyer, sales person, shipping address, payment terms
- Extracts PO line items: material number, quantity, description, delivery date
- Reads each BOM and extracts: BOM ID, part designation, part dimension, cutting/testing/cert fee flags
- Cross-references PO line items with BOMs by matching material number to BOM ID
- Matches each enriched line item against the price list
- Calculates per-line costs and order totals (same pricing logic as single-document prompt)
- Returns everything as a single JSON object

**Files to upload in ChatGPT:**
- `PO.pdf` — the purchase order
- `BOM1.pdf`, `BOM2.pdf`, `BOM3.pdf`, ... — all BOM files (upload all at once)
- `price_list.pdf` — the supplier price list

**Sample data:** `data/multi document PO/`
```
multi document PO/
├── customer_data/
│   ├── PO.pdf
│   ├── BOM1.pdf
│   ├── BOM2.pdf
│   └── BOM3.pdf
└── price_list/
    └── price_list.pdf
```

---

## How to use

### Step 1 — Open ChatGPT (GPT-4o recommended)

Use GPT-4o or a later model. Earlier models may struggle with multi-document cross-referencing.

### Step 2 — Upload all files in one message

Click the paperclip icon and upload all files together **before** pasting the prompt:

- **Single-document PO:** upload `PO.pdf` + `price_list.pdf`
- **Multi-document PO:** upload `PO.pdf` + all `BOM*.pdf` files + `price_list.pdf`

Upload everything in the same message — this gives the model the full context before it starts processing.

### Step 3 — Paste the prompt

Open the relevant prompt file (`prompt_single_document_PO.txt` or `prompt_multi_document_PO.txt`), copy the full content, and paste it into the same ChatGPT message as the uploaded files.

### Step 4 — Send

ChatGPT will return a single JSON object containing:
- `order_summary` — extracted header fields
- `line_items` — one entry per PO line, enriched with BOM data (multi-doc only), price list match, and calculated costs
- `totals` — material subtotal, volume discount, net material cost, fees, tax, and grand total
- `flags` — list of any missing values, assumed defaults, or ambiguous matches

If a value cannot be calculated (e.g. tax rate not stated in the PO), it is set to `null` and explained in `flags` rather than invented.

---

## Pricing logic (same in both prompts)

### Per line item

```
material_cost = quantity × unit_price
cutting_cost  = cutting_fee × num_cuts      (0 if cutting not required)
testing_cost  = testing_fee × testing_lots  (default: 1 lot if not stated in BOM/PO)
cert_cost     = cert_fee × certificates     (default: 1 cert if not stated in BOM/PO)
line_total    = material_cost + cutting_cost + testing_cost + cert_cost
```

- Unit prices and fee rates always come from the price list, never from the PO
- Fee counts (cuts, lots, certs) come from the BOM in the multi-document prompt, or from the PO in the single-document prompt; if not stated, defaults of 1 are applied and flagged

### Order totals

| Material Subtotal | Volume Discount |
|-------------------|-----------------|
| $0 – $4,999 | 0% |
| $5,000 – $14,999 | 3% |
| $15,000 – $29,999 | 5% |
| $30,000 – $49,999 | 7.5% |
| $50,000+ | 10% |

- Discount applies to the **material subtotal only** (not fees, shipping, or tax)
- `tax_base = net_material_cost + total_fees` (shipping excluded from tax base)
- `grand_total = net_material_cost + total_fees + shipping + tax`

---

## Adapting the prompts for your own use case

The prompts are plain text files — open them in any text editor and edit the relevant sections.

### 1. Change the extraction fields

Both prompts have a clearly labelled **PHASE 1 — EXTRACTION** section listing which fields to extract from the PO (and BOMs, for multi-document). Edit this list to match your documents.

For example, to add a "project code" field to the single-document prompt, find:
```
Header fields:
- Payment terms (as stated; else "")
```
and add:
```
- Project code (as stated; else "")
```

Then add the corresponding field to the JSON schema in **PHASE 4 — OUTPUT**.

### 2. Change the price list format

The prompts expect a price list PDF with these columns:

| Column | Purpose |
|--------|---------|
| Item No. | Primary match key — used to find the row for a given material number |
| Type/Part Designation | Secondary match key — used for description-based fallback |
| Material Grade | Used for fallback matching if Item No. and designation both fail |
| Standard Unit | The unit that matches your quantity format (e.g. per pcs, per kg, USD/1,000 kg) |
| Unit Price | Price per standard unit |
| Cutting Fee | Fee per cut (applied only when cutting is required) |
| Testing Fee | Fee per testing lot |
| Cert Fee | Fee per certificate |

Replace the sample `price_list.pdf` with your own price list. The columns do not need to have the exact same names as above — the model will identify them by content.

### 3. Change the pricing calculation rules

The pricing rules are in **PHASE 3 — PRICE CALCULATION**. The volume discount tiers and tax base formula are defined there as plain text. Edit them to match your business rules.

For example, to remove the volume discount entirely, change:
```
- volume_discount_rate: 0–4,999.99 → 0%, ...
```
to:
```
- volume_discount_rate: always 0% (no volume discount applied)
- volume_discount_amount: 0
- net_material_cost = material_subtotal
```

To change the tax base to include shipping, change:
```
- tax_base = net_material_cost + total_fees (shipping excluded)
```
to:
```
- tax_base = net_material_cost + total_fees + shipping_amount
```

### 4. Change the output JSON schema

The output schema is defined at the top of **PHASE 4 — OUTPUT**. Add, remove, or rename fields to match what your downstream system needs. For example, to add a `delivery_date` to the order summary:

```json
"order_summary": {
  "purchase_order_date": "",
  "delivery_date": "",        ← add this
  ...
}
```

### 5. Use your own PO and BOM documents

Replace the sample PDFs in `data/` with your own:
- For **single-document PO**: put your PO PDF in `customer_data/` and replace `price_list.pdf`
- For **multi-document PO**: put your PO PDF and all BOM PDFs in `customer_data/`, and replace `price_list.pdf`

The prompts contain no hardcoded paths or filenames — they work with any documents you upload.

### 6. Handle different pricing units

If your price list uses a different unit than the sample (e.g. per metre, per tonne, per sheet), update the unit column in your price list and add a note in **PHASE 3** explaining how to interpret the quantity:

```
- Parse the numeric part of the quantity string and convert to the price list unit before multiplying.
  Example: if quantity is "4.200 kg" and unit is "USD/1,000 kg", compute 4.200 × unit_price.
```

---

## Output format

Both prompts return a JSON object with this structure:

```json
{
  "order_summary": {
    "purchase_order_date": "05/02/2025",
    "delivery_date": "10/07/2025",
    "purchase_order_number": "5604-7182-3",
    "supplier_number": "518834",
    "shipping_address": "...",
    "payment_terms": "60 days net",
    "tax_rate": null,
    "shipping_amount": null
  },
  "line_items": [
    {
      "material_number": "7041832",
      "description": "Flat Bar 10×80mm HR Steel Mill Finish",
      "quantity": "4.200 kg",
      "unit_price": 680.00,
      "material_cost": 2856.00,
      "cutting_cost": 5.00,
      "testing_cost": 18.00,
      "cert_cost": 22.00,
      "line_total": 2901.00,
      "price_list_match": "7041832 Flat Bar 10×80mm — HR Steel Mill Finish ASTM A36",
      "flags": ["Cutting requirement not stated; applied one cutting fee by default."]
    }
  ],
  "totals": {
    "material_subtotal": 12521.00,
    "volume_discount_rate": "3%",
    "volume_discount_amount": 375.63,
    "net_material_cost": 12145.37,
    "total_fees": 351.00,
    "tax_base": 12496.37,
    "tax_amount": null,
    "grand_total": null
  },
  "flags": [
    "Tax rate not stated in the purchase order; tax amount and grand total cannot be fully calculated."
  ]
}
```

---

## Known limitations

This is a prompt-based prototype suitable for demos and early evaluation:
- Complex or scanned PDF layouts may lead to extraction errors — GAIK's multimodal parser in the code-based pipeline handles these more robustly
- Very large price lists (100+ rows) may reduce match accuracy; if needed, provide only the relevant rows
- Pricing logic is executed by the LLM, not by deterministic code — verify totals before use in real transactions
- For production automation, use the code-based pipeline in `implementation_layer/src/gaik/`
