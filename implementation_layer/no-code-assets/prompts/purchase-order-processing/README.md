# Purchase Order Processing Prompts

A prompt-only workflow for processing customer purchase orders in ChatGPT. No code, no file server, no external tools required. Upload the documents, paste a prompt, and get structured JSON output with extracted fields and calculated pricing.

---

## Two prompt types

### `prompt_single_document_PO.txt` — Single PDF purchase order

Use this when the purchase order is a **single PDF** that contains all required information (item descriptions, quantities, material numbers) without accompanying Bill of Material files.

**What it does:**
- Extracts PO header fields: order date, delivery date, PO number, supplier number, shipping address, payment terms
- Extracts line items: item number, description, quantity, material number
- Matches each line item against the price list to retrieve unit price and fee rates
- Calculates per-line costs: material cost, cutting cost, testing cost, certification cost
- Computes order totals: material subtotal, volume discount, net material cost, total fees, tax, and grand total
- Returns everything as a single JSON object

**Files to upload in ChatGPT:**
- `PO.pdf` — the purchase order
- Price list content — paste the full content of `price_list.md` directly in your message, or upload the file

**Sample data:** `data/single document PO/`
```
single document PO/
├── customer_data/
│   └── PO.pdf
└── price_list/
    └── price_list.md
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
- Price list content — paste the full content of `price_list.md` directly in your message, or upload the file

**Sample data:** `data/multi document PO/`
```
multi document PO/
├── customer_data/
│   ├── PO.pdf
│   ├── BOM1.pdf
│   ├── BOM2.pdf
│   └── BOM3.pdf
└── price_list/
    └── price_list.md
```

---

## Pricing logic (same in both prompts)

Both prompts apply the following calculation rules:

**Per line item:**
- `material_cost = quantity × unit_price`
- `cutting_cost = cutting_fee × num_cuts` (0 if cutting not required; flagged if num_cuts unknown)
- `testing_cost = testing_fee × testing_lots` (default: 1 lot if not stated)
- `cert_cost = cert_fee × certificates` (default: 1 cert if not stated)
- `line_total = material_cost + cutting_cost + testing_cost + cert_cost`

**Order totals:**

| Material Subtotal | Volume Discount |
|-------------------|----------------|
| $0 – $4,999 | 0% |
| $5,000 – $14,999 | 3% |
| $15,000 – $29,999 | 5% |
| $30,000 – $49,999 | 7.5% |
| $50,000+ | 10% |

- Discount applies to material subtotal only (not fees, shipping, or tax)
- `tax_base = net_material_cost + total_fees` (shipping excluded)
- `grand_total = net_material_cost + total_fees + shipping + tax`

**Key rules:**
- PO unit prices are reference only — only price list values are used for calculations
- Missing numeric values are never invented; they are set to `null` and flagged
- All assumptions (e.g., default fee counts) are recorded in the `flags` field

---

## How to use

### Step 1 — Open ChatGPT (GPT-4o recommended)

### Step 2 — Upload documents
- For single-document PO: upload `PO.pdf`
- For multi-document PO: upload `PO.pdf` and all BOM PDFs together

### Step 3 — Paste the price list
Copy the full content of `price_list.md` and paste it in the same message as the prompt, or upload the file directly.

### Step 4 — Paste the prompt
Copy the full content of the relevant prompt file and paste it into ChatGPT.

### Step 5 — Send
ChatGPT will return a single JSON object with all extracted fields, calculated line costs, order totals, and a `flags` list for any missing or ambiguous values.

---

## Output format

Both prompts return a JSON object with this structure:

```json
{
  "order_summary": { ... },
  "line_items": [
    {
      "material_number": "...",
      "description": "...",
      "unit_price": 28.50,
      "material_cost": 5700.00,
      "cutting_cost": 0,
      "testing_cost": 15.00,
      "cert_cost": 25.00,
      "line_total": 5740.00,
      "flags": []
    }
  ],
  "totals": {
    "material_subtotal": 25567.50,
    "volume_discount_rate": "5%",
    "volume_discount_amount": 1278.38,
    "net_material_cost": 24289.12,
    "total_fees": 165.00,
    "tax_base": 24454.12,
    "tax_amount": 1467.25,
    "grand_total": 26371.37
  },
  "flags": []
}
```

---

## Known limitations

This is a prompt-based prototype suitable for demos and early evaluation:
- Very large price lists may reduce match accuracy; paste only the relevant section if needed
- Scanned or complex-layout PDFs may lead to extraction errors — the multimodal parser in the GAIK code-based pipeline handles these cases more robustly
- For production automation, use the code-based pipeline in `implementation_layer/src/gaik/`
