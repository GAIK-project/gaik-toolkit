# Purchase Order Processing Prompt (PO → Sales Order)

This repository contains a **prompt-only workflow** you can use in ChatGPT to process a customer **Purchase Order (PO)** and generate:

1) a **price matching table**  
2) a **calculation breakdown** (audit trail)  
3) a **Sales Order** in a consistent, professional format (Markdown/text)  
4) a list of **flags/assumptions** for anything missing or ambiguous  

It is designed as a **demo / prototype** approach: no file server, no code, no external tools required. You upload the documents directly in ChatGPT and paste the prompt.

---

## What this prompt does

This prompt automates purchase order processing in two scenarios:

### Scenario A: PO + multiple BOMs
If the PO references multiple items and each item has a separate **Bill of Materials (BOM)**, the prompt:

- Extracts from the PO:
  - Line items: **Material Number, Quantity, Unit, Delivery Date**
  - Customer info: **Name, Address, Contact**
  - Order details: **PO Number, Payment Terms, Shipping Terms, Project Code**
  - Special requirements / instructions

- For each line item, extracts from the matching BOM:
  - **Type/Part Designation**
  - **Dimensions**
  - **Material Grade**
  - **Technical/spec notes** (if present)
  - Fee calculation fields:
    - `cutting_required`
    - `num_cuts`
    - `testing_lots_required`
    - `certificates_required`

- Matches pricing from a master price list:
  - Uses **lookup key / item key** (preferred) or “best match” logic as defined in the prompt
  - Retrieves:
    - **unit price**
    - **cutting fee**
    - **testing fee**
    - **certification fee**

- Calculates:
  - Per-line costs:
    - Material cost
    - Cutting cost
    - Testing cost
    - Certification cost
  - Order totals:
    - Material subtotal
    - **Volume discount** based on subtotal tiers
    - Net material cost after discount
    - Aggregated fees
    - Shipping
    - Tax
    - Grand total

- Produces a final **Sales Order** in Markdown/text format using your `sample_order.docx` / `sample_report.md` as the formatting reference.

### Scenario B: PO contains all information (no BOMs)
If the PO itself includes the fields normally found in BOMs (type/part designation, dimensions, etc.), the prompt uses the PO as the source for those fields. Missing values are left blank (null) and flagged.

---

## Key design rules (important)

- **PO unit prices are treated as reference only** (not used for calculations).
- **Only the price list values** are used for unit prices and fees.
- **No guessing**: if a numeric value is missing (e.g., `num_cuts`) the prompt flags it instead of inventing it.
- **Discount applies only to the material subtotal** (not to fees/shipping/tax).
- **Tax base** = Net material cost (after discount) + fees (shipping excluded), unless you change the rules in the prompt.
- Output always includes an **audit trail** so you can verify calculations.

---

## Repository contents (suggested)

- `prompt.txt` (or `custom_gpt_prompt.txt`)  
  The combined prompt you paste into ChatGPT or Custom GPT instructions.

- `sample_report.md`  
  The sample Markdown output format (used to mimic layout).

- `sample_order.docx`  
  Optional format reference (structure/wording/layout cues).

- `examples/` (optional)  
  Example input files and an example generated output.

---

## How to use (ChatGPT, prompt-paste workflow)

### Step 1: Upload documents
Upload the following files in ChatGPT:

- `PO.pdf`
- `BOM1.pdf, BOM2.pdf, ...` (as many as you have)
- `price_list.md`
- `sample_report.md` and/or `sample_order.docx`

> Tip: Always upload `sample_report.md` for the most consistent formatting.

### Step 2: Paste the prompt
Copy the content of `prompt.txt` and paste it into ChatGPT.

### Step 3: Run the task
In the next message, write something short like:

- “Process these files and generate the Sales Order.”

ChatGPT will return the output in this strict order:
1) PRICE_MATCHING  
2) CALCULATION BREAKDOWN  
3) SALES ORDER (Markdown)  
4) FLAGS / ASSUMPTIONS  

---

## How to use (Custom GPT)

1. Create a new Custom GPT in ChatGPT.
2. Paste the full prompt into the **Instructions** field.
3. Save the Custom GPT.
4. In each run:
   - Upload `PO.pdf`, BOMs, `price_list.md`, and `sample_report.md` (recommended).
   - Ask: “Process the uploaded PO and generate the Sales Order.”

> If you do not upload the sample output files in a run, the GPT will still follow the described structure, but formatting may drift slightly.

---

## Inputs expected

### Purchase Order (PO)
The prompt expects the PO to contain (where available):
- PO number, PO date
- Customer details (name/address/contact)
- Line items with material numbers and quantities
- Delivery dates
- Payment/shipping terms
- Tax rate and shipping amount (if present)
- Special instructions

### Bills of Material (BOMs)
Each BOM should be identifiable by a `BOM_ID` or equivalent field matching the PO material number.

### Price list
The price list (`price_list.md`) should include, per item:
- Lookup key (item/material key)
- Unit price
- Cutting fee
- Testing fee
- Certification fee
- A row identifier (row number or key)

---

## Output format

The prompt outputs:

- **Price matching table**
  - Shows which price list row was used per material and what fees/prices were applied

- **Calculation breakdown**
  - Step-by-step per-line calculations and full order totals (audit-friendly)

- **Sales order (Markdown/text)**
  - Professional layout mimicking the sample template

- **Flags/assumptions**
  - Missing fields, ambiguous matches, non-computable items, and any inconsistencies

---

## Known limitations (prototype scope)

This is a **prompt-based** system. It is suitable for demos and early prototypes, but note:

- Very large price lists may reduce accuracy unless the prompt extracts only the relevant rows.
- Scanned PDFs or complex tables may lead to extraction errors.
- If BOMs differ in Bill To / Ship To data, the prompt chooses the most complete and flags inconsistencies.
- For production automation, you would typically add:
  - deterministic parsing (PDF table extraction)
  - programmatic calculations
  - validation rules and unit tests

---

## License / disclaimer

This repository provides a prompt-only workflow for demonstration and prototyping. Always verify pricing and terms before using outputs in real customer transactions.
