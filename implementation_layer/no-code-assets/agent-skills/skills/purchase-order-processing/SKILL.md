---
name: purchase-order-processing
description: Process Purchase Orders and Bills of Material to generate priced Sales Orders
---

# Purchase Order Processing Skill

## When to Use

Activate this skill when the user wants to:
- Process a purchase order (PO) and generate a sales order
- Match purchase order items with bills of material (BOM)
- Calculate pricing from a price list
- Generate a sales order document from PO data
- Extract and enrich order data from customer documents

**Trigger phrases:**
- "process purchase order", "process PO", "process this order"
- "generate sales order from PO"
- "calculate pricing for this order"
- "match BOM with purchase order"
- "create sales order"

---

## Inputs

### Required Folder Structure

The user provides a folder path containing:

```
input_folder/
├── customer_data/           # REQUIRED: Customer documents
│   ├── PO.pdf              # Purchase Order (required)
│   ├── BOM1.pdf            # Bill of Materials (optional)
│   ├── BOM2.pdf            # Additional BOMs as needed
│   └── ...
├── price_list/              # REQUIRED: Pricing information
│   └── price_list.xlsx     # Master price list (or .csv)
│
└── sample_sales_order/      # OPTIONAL: Sample for format inference
    └── sample_order.docx   #   (if not provided, use default text format)
```

### Input Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `input_folder` | Yes | Path to folder containing all input documents |
| `output_path` | No | Where to save the sales order (default: input_folder) |
| `tax_rate` | No | Tax rate to apply (default: from PO or 6%) |
| `include_fees` | No | Whether to include cutting/testing/cert fees (default: true) |

---

## Tooling Rules (Windows vs Linux Path Safety)

### Why this matters
On Windows, Claude Desktop + toolchains sometimes behave like they are in a POSIX shell, producing paths like `/mnt/c/...`.
Meanwhile, your MCP servers may run **native Windows Python**, expecting `C:\...`.
This mismatch can cause "file not found" or failing shell commands.

### Strict rules
1) **Prefer MCP filesystem tools for file/folder operations**
Use the filesystem server for listing and reading files instead of shell commands.

2) **Avoid bash commands on Windows**
If you must run a command on Windows, prefer **PowerShell**.

3) **Never assume the environment is Linux**
Treat the runtime as OS-ambiguous and enforce the above rules to stay stable.

4) **Never do the following:**
NEVER run pip install, python -c, pdfplumber, or any ad-hoc parsing code for .pdf/.pptx/.xlsx.

NEVER use /mnt/user-data/uploads/... paths; only use paths returned by the MCP filesystem listing or the user-provided Windows folder.

If you are about to do any of the above, STOP and switch to the built-in PDF/PPTX/XLSX skills.

- View /mnt/skills/public/docx/SKILL.md skill for reading and editing DOCX files.
- View /mnt/skills/public/pdf/SKILL.md skill for reading PDF files.
- View /mnt/skills/public/xlsx/SKILL.md skill for reading and editing XLSX files.


---

## Workflow

Execute these steps in order. Reference the files in `reference/` folder for field definitions and customization options.

### Step 0: Validate Input Folder (MCP filesystem only)

1. Verify the input folder exists
2. Check for required subfolders:
   - `customer_data/` - Must exist and contain at least one PDF (the PO)
   - `price_list/` - Must exist and contain price list file
3. Identify optional folders:
   - `sample_sales_order/` - Check if sample document exists
4. If required folders/files missing, ask user to provide them

**Output:** Inventory of available files

If `customer_data/` is missing or empty, stop and ask the user to add the source materials there.

### Step 1: Extract Fields from Purchase Order

Read the Purchase Order PDF from `customer_data/` and extract all fields as defined in `reference/EXTRACTION_FIELDS.md`.

Extract:
- **PO Header:** Order number, date, payment terms, shipping terms, project code
- **Customer Information:** Name, address, contact details
- **Line Items:** Material numbers, descriptions, quantities, units, delivery dates
- **PO Summary:** Subtotal, shipping, tax, total
- **Special Requirements:** Instructions and documentation requirements

**See `reference/EXTRACTION_FIELDS.md`** for complete field specifications, source locations, and required/optional status.

**Output:** Structured PO data with all extracted fields

### Step 2: Extract Fields from Bills of Material

For EACH Material_Number found in the PO line items:

1. Search `customer_data/` for BOM files
2. Find the BOM where `BOM_ID` matches `Material_Number`
3. If match found, extract all fields as defined in `reference/EXTRACTION_FIELDS.md`

Extract:
- **BOM Header:** Revision, date, status, customer PO reference, project code
- **Material Identification:** BOM ID, Type/Part Designation (critical for price lookup), dimensions, material grade
- **Technical Specifications:** Material standard, surface finish, weight, testing requirements
- **Fee Calculation Fields:** Cutting_Required, Testing_Lots_Required, Certificates_Required (for determining applicable fees)

**See `reference/EXTRACTION_FIELDS.md`** for complete field specifications, source locations, and required/optional status.

**Decision Point:**
- If BOM found for all items → Continue to Step 3
- If some BOMs missing → Check if PO contains the Type/Part Designation info
- If PO has all info (no BOMs needed) → Mark as "PO-only mode" and continue
- If critical info missing → Flag items for manual review

**Output:** BOM data for each Material_Number, or flags for missing BOMs

### Step 3: Match PO Items with BOMs

Create enriched items by combining PO and BOM data:

```
FOR EACH PO Line Item:
    MATCH WHERE: PO.Material_Number = BOM.BOM_ID

    IF match found:
        CREATE Enriched_Item with:
        - Item_Number (from PO)
        - Material_Number (from PO, validated against BOM)
        - Type_Part_Designation (from BOM) ← CRITICAL for price lookup
        - Dimensions (from BOM)
        - Material_Grade (from BOM)
        - Quantity (from PO)
        - Unit (from PO)
        - Delivery_Date (from PO)
        - Weight_Per_Unit (from BOM)

    ELSE IF PO contains Type/Part info:
        CREATE Enriched_Item using PO data only

    ELSE:
        FLAG as "BOM Not Found - Manual Review Required"
```

#### Validation Rules
| Check | Rule | Action if Failed |
|-------|------|------------------|
| BOM Exists | BOM found for Material_Number | Flag for manual review |
| PO Reference | BOM.BOM_Customer_PO = PO.PO_Number | Warning - verify documents |
| Project Code | BOM.BOM_Project_Code = PO.Project_Code | Warning - verify documents |
| Status | BOM.BOM_Status = "Approved" | Flag if not approved |

**Output:** List of Enriched_Items ready for pricing

### Step 4: Lookup Prices from Master Price List

Read the price list from `price_list/` folder and match each enriched item using the matching logic defined in `reference/PRICING_RULES.md`.

For EACH Enriched_Item:
1. Match using Type/Part Designation (primary matching key). There should be an exact match. 
2. If match found, extract unit price and fees (cutting, testing, certification)
3. If no match found, flag item as "Price Not Found - Manual Pricing Required"

**See `reference/PRICING_RULES.md`** for:
- Price list column mapping
- Complete matching logic
- Fallback matching rules

**IMPORTANT:** Never use the PO's unit prices. Always use the Price List prices.

**Output:** Priced_Items with all pricing fields assigned

### Step 5: Calculate Pricing

Apply calculations as defined in `reference/CALCULATION_LOGIC.md` and `reference/PRICING_RULES.md`.

#### 5.1 Line Item Calculations
For EACH Priced_Item, calculate:
- Material_Cost = Quantity × Unit_Price
- Cutting_Cost (if applicable)
- Testing_Cost
- Cert_Cost
- Line_Total

**See `reference/CALCULATION_LOGIC.md`** for detailed formulas, defaults, and examples.

#### 5.2 Material Subtotal
Calculate the sum of all Material_Cost values across all items.

**See `reference/CALCULATION_LOGIC.md`** for calculation details.

#### 5.3 Volume Discount
Determine the applicable discount tier based on the material subtotal amount and apply the discount rate.

**See `reference/PRICING_RULES.md`** for complete discount tier table and rules.

#### 5.4 Fees, Shipping, Tax, and Grand Total
Aggregate all fees (cutting, testing, certification), add shipping from PO, calculate tax on the taxable base, and compute the grand total.

**See `reference/CALCULATION_LOGIC.md`** for detailed formulas and tax rules.

**Output:** Complete pricing breakdown for all items and order totals

### Step 6: Generate Sales Order

Create the Sales Order document using format from `reference/OUTPUT_FORMAT.md`.

#### 6.1 Determine Output Format
- IF `sample_sales_order/sample_order.docx` exists:
  1. Use DOCX skill to READ the sample document
  2. Extract the EXACT pricing summary structure:
     - Field labels (verbatim)
     - Field order (must be preserved)
     - Currency formatting rules
     - Punctuation (colons, parentheses)
  3. Use this as the TEMPLATE for output
  4. MATCH every detail: labels, order, formatting
- ELSE → Use default format from `reference/OUTPUT_FORMAT.md`

#### 6.2 Generate Document Sections

Create the following sections as specified in `reference/OUTPUT_FORMAT.md`:
- **Header:** SO number, order date, customer PO reference, payment/shipping terms
- **Customer Information:** Bill To and Ship To addresses
- **Line Items Table:** All items with enriched details from BOMs
- **Special Instructions:** Copy verbatim ALL special instructions and/or requirements from the Purchase Order. Include every instruction exactly as written in the PO. DO NOT paraphrase, summarize, or omit any instructions. 
- **Approval Section:** Signature lines (if using template)

**PRICING SUMMARY:**

Generate pricing summary as specified in `reference/OUTPUT_FORMAT.md` (lines 82-93).

If sample_order.docx exists, extract and match its exact format.
Otherwise, use the default format from OUTPUT_FORMAT.md.

**CRITICAL CURRENCY FORMATTING REQUIREMENT:**
ALL currency values MUST include comma separators for thousands.
- ✓ Correct: $25,567.50, $1,278.38, $26,398.37
- ✗ Wrong: $25567.50, $1278.38, $26398.37 (missing commas)

**Requirements:**
- Include all required fields in exact order (see OUTPUT_FORMAT.md template)
- Match field labels exactly (including punctuation)
- Apply currency formatting rules (see OUTPUT_FORMAT.md lines 146-168)
- DO NOT skip, add, or rearrange fields

**See `reference/OUTPUT_FORMAT.md`** for:
- Complete pricing summary template (lines 82-93)
- Currency formatting requirements (lines 146-168)
- Field descriptions and formatting rules 

#### 6.3 Save Output
- Filename format: `SO-[number]_[Customer_Name]_[Date].[extension]`
  - Use `.docx` extension if sample-based format was used
  - Use appropriate extension based on OUTPUT_FORMAT.md if no sample
- Save in input folder or specified output path

**See `reference/OUTPUT_FORMAT.md`** for:
- Complete section specifications
- Field formatting rules
- Conditional display logic
- Template placeholder mappings

**Output:** Complete Sales Order document

---

## Output Files

The skill generates the following files:

### 1. Sales Order Document

**Format:**  `.docx` 

**Filename:** `SO-{SO_Number}_{Customer_Name}_{Date}.[docx]`
view /mnt/skills/public/docx/SKILL.md skill to generate the docx files.

**Contents:**
- Header with SO number and customer PO reference
- Customer billing and shipping information
- Line items table with enriched details from BOMs
- Calculated pricing using Price List (never PO prices)
- Volume discounts applied based on subtotal tiers
- Fees (Testing/Cert combined), shipping, and tax breakdown
- Grand total

**Format details:** See `reference/OUTPUT_FORMAT.md` for complete specification.

### 2. Calculation Breakdown Document

**Format:** `.txt` (always plain text)

**Filename:** `Calculation_Breakdown.txt`

**Contents:**
- Source documents used (PO, BOMs, Price List)
- For EACH line item:
  - Extracted data from BOM (Type/Part, Dimensions, Grade)
  - Extracted quantity from PO
  - Matched price list entry with unit price and fees
  - Step-by-step calculations (Material Cost, Testing Fee, Cert Fee, Line Total)
- Order-level calculations:
  - Material Subtotal
  - Volume Discount calculation with applicable rate and tier
  - Net Material Cost
  - Total Testing and Certification Fees
  - Shipping, Tax, and Grand Total

**Purpose:** Helps users understand, verify, and audit the pricing logic.

**Format details:** See `reference/CALCULATION_BREAKDOWN_TEMPLATE.md` for complete specification and customization options.
---

## Guardrails

### DO:
- Always use Price List prices for calculations, never PO prices
- Validate BOM references match PO references
- Flag unmatched items clearly for manual review
- Show price comparison if PO prices differ significantly from calculated
- Copy verbatim ALL special instructions from PO (do not paraphrase or omit)
- Generate unique SO numbers

### DO NOT:
- Use customer's PO unit prices for the sales order calculations
- Skip items that don't have matching BOMs (flag them instead)
- Assume missing data - ask user for clarification
- Modify the original input documents
- Generate sales order if critical data is missing

### Error Handling:
- Missing BOM → Flag item, continue with other items
- Price not found → Flag item, show "PRICE TBD"
- Invalid data format → Report specific error, ask for correction
- Calculation discrepancy → Show warning with details

### Sample Format Compliance:
- When sample_order.docx exists, STRICTLY match its format
- Extract exact field labels including:
  - Punctuation (colons, parentheses, hyphens)
  - Capitalization (Material Subtotal vs material subtotal)
  - Abbreviations (Cert vs Certificate)
- Preserve field order exactly as shown in sample
- Match currency formatting:
  - Dollar signs, commas, decimal places
  - Negative value formatting
- DO NOT skip fields present in sample
- DO NOT add fields not in sample
- DO NOT rearrange field order
- If unsure, read the sample again to verify

---

## Examples

### Example 1: Full Workflow with BOMs
**User:** "Process the purchase order in C:\Orders\Project-Q4"
**Action:**
1. Read PO.pdf - extract 3 line items
2. Read BOM1.pdf, BOM2.pdf, BOM3.pdf - match by Material Number
3. Lookup prices in price_list.xlsx
4. Calculate: Subtotal $25,567.50 → 5% discount → fees → tax
5. Generate SO-2025-08472.docx

### Example 2: PO Without BOMs
**User:** "Generate sales order from this PO - no BOMs needed"
**Action:**
1. Read PO.pdf - extract line items with full descriptions
2. Use PO's Type/Part Designation for price lookup
3. Skip BOM matching step
4. Calculate pricing and generate sales order

### Example 3: Partial BOM Match
**User:** "Process order in C:\Orders\NewCustomer"
**Action:**
1. Read PO with 5 items
2. Find BOMs for 3 items, 2 items have no BOM
3. Flag 2 items: "BOM Not Found - Manual Review Required"
4. Complete pricing for 3 matched items
5. Generate sales order with warnings section

### Example 4: Using Sample Document
**User:** "Generate sales order matching our company format"
**Action:**
1. Process PO and BOMs as normal
2. Detect sample_order.docx in sample_sales_order/ folder
3. Analyze sample structure and infer format
4. Generate new sales order matching sample's style
5. Save as formatted Word document
