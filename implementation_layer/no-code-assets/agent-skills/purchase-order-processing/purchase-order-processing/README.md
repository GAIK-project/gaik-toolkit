# Purchase Order Processing Skill for Claude Desktop

Transform your purchase orders and bills of material into accurate, priced sales orders — automatically.

---

## What Does This Skill Do?

This skill helps you **process purchase orders** and generate complete sales orders with accurate pricing. Simply point Claude to a folder containing your PO, BOMs, and price list, and it will:

- **Extract** order details from purchase orders (PDFs)
- **Match** material numbers with bills of material (BOMs)
- **Lookup** prices from your master price list
- **Calculate** volume discounts, fees (cutting, testing, certification), and taxes
- **Generate** a professional sales order document with complete pricing breakdown

### Example Use Cases

| Scenario | Input | Output |
|----------|-------|--------|
| Standard order processing | PO + BOMs + Price List | Sales Order with calculated pricing |
| Quick quote | PO only (no BOMs) | Sales Order using PO descriptions |
| Custom pricing | PO + BOMs + Custom Price List | Sales Order with your pricing |
| Audit trail | PO + BOMs + Price List | Sales Order + Calculation Breakdown |

### Supported File Types

| Type | Formats | Purpose |
|------|---------|---------|
| Purchase Orders | `.pdf` | Customer orders to process |
| Bills of Material | `.pdf` | Material specifications and requirements |
| Price Lists | `.xlsx`, `.csv` | Master pricing and fee information |
| Templates | `.docx` (optional) | Custom sales order format |

---

## Prerequisites

Before setting up, please install:

1. **Claude Desktop** — Download from [claude.ai/download](https://claude.ai/download)
2. **Node.js** — Download from [nodejs.org](https://nodejs.org/)
   - Required for filesystem access
---

## Setup

### Option A: Easy Setup (Recommended)

**Step 1: Configure Claude Desktop**

1. Open Claude Desktop's configuration file:
   - Press `Win + R`
   - Paste: `%APPDATA%\Claude\claude_desktop_config.json`
   - Press Enter

2. Add or update the `mcpServers` section:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\"]
    }
  }
}
```

3. Save and close the file

**Step 2: Restart Claude Desktop**

1. Close Claude Desktop completely (check the system tray icon)
2. Open Task Manager and end any "Claude" processes
3. Start Claude Desktop again

**Step 3: Install the Skill**

1. Zip the `purchase-order-processing` folder (this entire folder)
2. Open Claude Desktop
3. Click the **Settings** icon (gear) → **Capabilities**
4. Click **"+ Add"**
5. Select the zip file you just created

✅ **Setup complete!** You're ready to use the skill.

---

## How to Use

### Step 1: Organize Your Documents

Create a folder with this structure:

```
My-Order/
├── customer_data/           ← REQUIRED: Put PO and BOMs here
│   ├── PO.pdf
│   ├── BOM1.pdf
│   ├── BOM2.pdf
│   └── BOM3.pdf
├── price_list/              ← REQUIRED: Put your price list here
│   └── price_list.xlsx
└── sample_sales_order/      ← OPTIONAL: Put a sample SO format here
    └── sample_order.docx
```

**Required:**
- `customer_data/` — At least one PO.pdf (BOMs optional if PO has all details)
- `price_list/` — Your master price list (Excel or CSV)

**Optional:**
- `sample_sales_order/` — A sample sales order showing your desired format

### Step 2: Ask Claude to Process the Order

In Claude Desktop, upload the .zip file of the documents (same structure) and say:

```
Process these documents using purchase-order-processing skill
```

Or provide the local path of the documents:

```
Generate sales order from C:\Orders\NewCustomer using purchase-order-processing skill
```

### Step 3: Get Your Sales Order

Claude will:
1. Extract data from the PO and BOMs
2. Match materials and lookup prices
3. Calculate volume discounts, fees, and taxes
4. Create a sales order document
5. Generate a calculation breakdown for audit
6. Save both files in the input folder

---

## Examples

### Example 1: Full Workflow with BOMs

**Your request:**
```
Process the purchase order in C:\Orders\Project-Q4 using purchase-order-processing skill
```

**Your folder:**
```
Project-Q4/
├── customer_data/
│   ├── PO.pdf          # 3 line items
│   ├── BOM1.pdf        # MAT-2401
│   ├── BOM2.pdf        # MAT-3567
│   └── BOM3.pdf        # MAT-4829
└── price_list/
    └── price_list.xlsx
```

**Result:**
- `SO-2025-15903_AutoTech_Manufacturing_2025-11-15.docx` — Complete sales order
- `Calculation_Breakdown.txt` — Detailed pricing calculations

---

### Example 2: Quick Quote (No BOMs)

**Your request:**
```
Generate sales order from C:\Orders\QuickQuote using purchase-order-processing skill
```

**Your folder:**
```
QuickQuote/
├── customer_data/
│   └── PO.pdf          # Contains all material details
└── price_list/
    └── price_list.xlsx
```

**Result:** Sales order generated using descriptions from the PO itself.

---

### Example 3: Custom Format with Sample

**Your request:**
```
Create sales order matching our format from C:\Orders\NewCustomer using purchase-order-processing skill
```

**Your folder:**
```
NewCustomer/
├── customer_data/
│   ├── PO.pdf
│   ├── BOM1.pdf
│   └── BOM2.pdf
├── price_list/
│   └── price_list.xlsx
└── sample_sales_order/
    └── our-format.docx   ← Your company's format
```

**Result:** Sales order matching your sample document's format and style.

---

## What Gets Calculated?

The skill automatically calculates and includes:

| Calculation | Description | Source |
|-------------|-------------|--------|
| **Material Cost** | Quantity × Unit Price | PO quantity × Price List |
| **Cutting Fees** | Cutting Fee × Cuts Required | Price List × BOM field |
| **Testing Fees** | Testing Fee × Test Lots | Price List × BOM field |
| **Certification Fees** | Cert Fee × Certificates | Price List × BOM field |
| **Volume Discount** | Tiered discount on materials | Based on subtotal |
| **Tax** | Tax on materials + fees | Configurable rate (default 6%) |
| **Grand Total** | All components combined | Complete pricing |

**Important:** The skill ALWAYS uses Price List prices, NEVER the prices from the customer's PO.

---

## Customizing the Skill

The skill is highly customizable to match your business processes. Here's what you can change:

### 1. Price List Structure

**File to edit:** `reference/EXTRACTION_FIELDS.md` (Lines 137-135)

**What to change:** Column names in your price list

**Default columns expected:**
```
- Type/Part Designation (required)
- Unit Price (required)
- Cutting Fee
- Testing Fee
- Cert Fee
```

**Example customization:**
If your price list uses "Product Name" instead of "Type/Part Designation":
1. Edit line 126 in EXTRACTION_FIELDS.md
2. Change `PL_Type_Part_Designation` mapping to your column name

---

### 2. Volume Discount Tiers

**File to edit:** `reference/PRICING_RULES.md`

**What to change:** Discount percentages and threshold amounts

**Default tiers:**
```
< $5,000:     0% discount
$5,000-$15,000:   3% discount
$15,000-$30,000:  5% discount
$30,000-$50,000:  7% discount
> $50,000:        10% discount
```

**How to customize:**
1. Open `reference/PRICING_RULES.md`
2. Find the "Volume Discount Tiers" section
3. Update the amounts and percentages to match your pricing policy

---

### 3. Fee Calculation Defaults

**File to edit:** `reference/CALCULATION_LOGIC.md` (Lines 45-106)

**What to change:** Default quantities for fees when BOM doesn't specify

**Default behavior:**
```
Cutting: 0 cuts (no cutting fee unless BOM specifies)
Testing: 1 lot (one test lot per material)
Certificates: 1 certificate (one cert per material)
```

**How to customize:**
1. Open `reference/CALCULATION_LOGIC.md`
2. Find the "Cutting Cost", "Testing Cost", or "Certification Cost" sections
3. Change the default value in the "Default:" line

Example: Change testing default to 2 lots:
```
**Default:** `Lots_Per_Item = 2` (two lots per material type)
```

---

### 4. BOM Field Names

**File to edit:** `reference/EXTRACTION_FIELDS.md` (Lines 116-133)

**What to change:** Field names to match your BOM format

**Default fields:**
```
Cutting_Required
Testing_Lots_Required
Certificates_Required
```

**Alternative names supported:**
The skill already recognizes variations like:
- "Cuts Needed", "Number of Cuts" (for cutting)
- "Test Lots", "Testing Quantity" (for testing)
- "Certificates Needed", "Cert Quantity" (for certificates)

**How to add more alternatives:**
1. Open `reference/EXTRACTION_FIELDS.md`
2. Find the "Alternative Field Names" section (line 130)
3. Add your field name variations to the list

---

### 5. Tax Rate

**File to edit:** `reference/CALCULATION_LOGIC.md` (Line 233)

**What to change:** Default tax rate

**Default:** 6%

**How to customize:**
1. Open `reference/CALCULATION_LOGIC.md`
2. Find "Default Tax Rate:" line
3. Change the percentage

Or specify at runtime:
```
Process this order with 8% tax rate using purchase-order-processing skill
```

---

### 6. Sales Order Format

**Files to edit:** `reference/OUTPUT_FORMAT.md`

**What to change:** Document structure, sections, formatting

**Options:**

**A) Use a Sample Document (Recommended):**
- Place a sample sales order in `sample_sales_order/` folder
- Skill will infer and match the format automatically
- No code changes needed

**B) Modify Default Format:**
1. Open `reference/OUTPUT_FORMAT.md`
2. Edit the "Default Text Format" section
3. Customize:
   - Section headers
   - Field labels
   - Table structure
   - Company information

**C) Change Section Content:**
Edit `OUTPUT_FORMAT.md` lines 199-240 to:
- Add new sections
- Remove optional sections
- Change field order
- Modify text content

---

### 7. Extraction Fields from PO/BOM

**File to edit:** `reference/EXTRACTION_FIELDS.md`

**What to change:** Which fields to extract from documents

**Common customizations:**

**Add a new PO field:**
1. Go to "PO Header Fields" section (line 9)
2. Add a new row to the table with:
   - Field name
   - Source location in your PO
   - Whether it's required
   - Type and example

**Add a new BOM field:**
1. Go to "BOM Technical Specification Fields" (line 103)
2. Add a new row with field details

**Example:**
To extract "Supplier Code" from BOM:
```markdown
| Supplier_Code | TECHNICAL SPECIFICATIONS | No | String | SUP-12345 |
```

---

### 8. Calculation Formulas

**File to edit:** `reference/CALCULATION_LOGIC.md`

**What to change:** How costs are calculated

**Common customizations:**

**Change tax calculation base:**
- Default: Tax on (Materials + Fees), NOT on shipping
- To include shipping in tax:
  ```
  Line 223: Change to:
  Taxable_Amount = Net_Material_Cost + Total_Fees + Shipping
  ```

**Change discount application:**
- Default: Discount on materials only
- To discount everything:
  ```
  Line 139: Change to:
  Total_Before_Discount = Subtotal + Total_Fees
  Volume_Discount = Total_Before_Discount × Discount_Rate
  ```

**Add a new fee type:**
1. Add fee field in `EXTRACTION_FIELDS.md` (price list section)
2. Add calculation formula in `CALCULATION_LOGIC.md`
3. Update line total formula to include new fee

---

### 9. Validation Rules

**File to edit:** `SKILL.md` (Lines 243-247)

**What to change:** Validation checks performed

**Default validations:**
- BOM exists for each material
- PO reference in BOM matches PO number
- Project codes match
- BOM status is "Approved"

**How to customize:**
1. Open `SKILL.md`
2. Find the "Validation Rules" table
3. Add, remove, or modify validation rules
4. Change "Action if Failed" behavior

---

### 10. Company Information

**File to edit:** `reference/OUTPUT_FORMAT.md` (Lines 39-44)

**What to change:** Your company details in the output

**Default placeholder:**
```
[COMPANY NAME]
[Company Address Line 1]
[Company Address Line 2]
Phone: [Phone] | Email: [Email]
```

**How to customize:**
Replace placeholders with your actual company information.

---

## BOM Requirements for Fee Calculations

To enable accurate fee calculations, your BOMs should include these fields:

**Required Fee Fields:**
```
Cutting_Required: [number]        # e.g., 2 (for 2 cuts)
Testing_Lots_Required: [number]   # e.g., 1 (for 1 test lot)
Certificates_Required: [number]   # e.g., 1 (for 1 certificate)
```

**Where to add:**
- In the "TECHNICAL SPECIFICATIONS" section of your BOM, OR
- As a separate "FEE REQUIREMENTS" section

**Template available:**
See `reference/BOM_TEMPLATE_WITH_FEES.md` for a complete example of how to structure your BOMs with fee fields.

**If BOMs don't include these fields:**
- Cutting: Defaults to 0 (no cutting fee)
- Testing: Defaults to 1 lot
- Certificates: Defaults to 1 certificate

---

## Price List Requirements

Your price list Excel/CSV file should include these columns:

**Required Columns:**
```
Type/Part Designation    # Must match BOM Type/Part exactly
Unit Price              # Base price per unit
```

**Optional but Recommended:**
```
Cutting Fee             # Cost per cut
Testing Fee             # Cost per test lot
Cert Fee               # Cost per certificate
Min Order Qty          # Minimum order quantity
Lead Time (Days)       # Delivery time
```

**Example Row:**
```
Type/Part: Aluminum Angle - L Profile
Unit Price: $28.50
Cutting Fee: $5.00
Testing Fee: $15.00
Cert Fee: $25.00
```

**Important:** The "Type/Part Designation" in the Price List must EXACTLY match the "Type/Part Designation" from the BOM for accurate matching.

---

## Troubleshooting

### "MCP server not found" error

- Make sure Claude Desktop is fully closed (check system tray)
- Verify `claude_desktop_config.json` has the filesystem server configured
- Restart Claude Desktop

### "File not found" errors

- Use the full Windows path (e.g., `C:\Orders\...`)
- Make sure your files are in the correct subfolders:
  - PO and BOMs in `customer_data/`
  - Price list in `price_list/`
- Check that the folder path has no typos

### "Price not found" errors

- Check that Type/Part Designation in BOM matches Price List exactly
- Verify price list has required columns (Type/Part Designation, Unit Price)
- Check for typos in material names
- Review matching logic in `reference/PRICING_RULES.md`

### "BOM not found" warnings

- Check that Material_Number from PO matches BOM_ID in BOM
- Verify BOM files are named correctly (e.g., BOM1.pdf, BOM2.pdf)
- If PO has all details, you can skip BOMs (skill will use PO descriptions)

### Claude doesn't recognize the skill

- Go to Settings → Capabilities and verify the skill is listed
- Try removing and re-adding the skill
- Make sure to mention "purchase-order-processing skill" in your request
- Restart Claude Desktop

### Incorrect calculations

- Review the `Calculation_Breakdown.txt` file for step-by-step details
- Verify fee fields in BOMs are numeric (not text)
- Check volume discount tiers in `reference/PRICING_RULES.md`
- Ensure price list has all required fee columns

### PDF reading issues

- Ensure PDFs are not password-protected
- Check that PDFs are text-based (not scanned images)
- For scanned PDFs, use OCR software first to make them text-searchable

---

## Sample Data for Testing

A `sample_data/` folder with example files is added to help you test the skill.

The output for the sample data can be found in `output` folder.
---

## Tips for Best Results

1. **Use consistent naming** — Name BOMs as BOM1.pdf, BOM2.pdf, etc.
2. **Match Type/Part exactly** — Ensure BOM and Price List use identical product names
3. **Include fee fields in BOMs** — Add Cutting_Required, Testing_Lots_Required, Certificates_Required
4. **Keep price list current** — Update your master price list regularly
5. **Provide a sample** — If you want a specific format, include a sample sales order
6. **Review calculations** — Always check the Calculation_Breakdown.txt for accuracy
7. **Test with one order first** — Process a simple order before handling complex ones

---

## Output Files

The skill generates two files:

### 1. Sales Order Document
**Format:** `.docx` (Word document)
**Filename:** `SO-{number}_{Customer}_{Date}.docx`

Contains:
- Order header (SO number, date, PO reference)
- Customer information
- Line items with enriched BOM details
- Complete pricing breakdown
- Volume discount applied
- Fees, shipping, and tax
- Grand total

### 2. Calculation Breakdown
**Format:** `.txt` (plain text)
**Filename:** `Calculation_Breakdown.txt`

Contains:
- Source documents used
- Extraction details for each item
- BOM matching results
- Price lookup results
- Step-by-step calculations
- Fee calculations with formulas
- Order-level aggregations
- Volume discount calculation
- Tax calculation
- Grand total assembly

**Purpose:** Provides complete transparency and audit trail for all pricing decisions.

---

## Getting Help

- **Issues:** Create an issue in the GitHub repository
- **Documentation:** Review files in `reference/` folder for detailed specifications
- **Customization:** See the "Customizing the Skill" section above
- **Verification:** Check `VERIFICATION_REPORT.md` for extraction/calculation strategy

---

## 5. Data Flow Diagram

```
┌─────────────────┐
│   PO.pdf        │
│  - MAT-2401     │──┐
│  - Quantity:200 │  │
└─────────────────┘  │
                     │
┌─────────────────┐  │   ┌──────────────────────────┐
│  BOM1.pdf       │  ├──→│  MATCHING STEP           │
│  - BOM_ID:      │  │   │  MAT-2401 = MAT-2401 ✓   │
│    MAT-2401     │──┘   └──────────────────────────┘
│  - Type/Part:   │                   │
│    Alu Angle    │                   │
│  - Cutting: 2   │◄─┐                │
│  - Testing: 1   │  │                │
│  - Certs: 1     │  │                ▼
└─────────────────┘  │   ┌──────────────────────────┐
                     │   │  PRICE LOOKUP            │
┌─────────────────┐  │   │  Match: "Alu Angle"      │
│ price_list.xlsx │  │   │  Unit: $28.50            │
│  - Type/Part:   │──┤   │  Cutting Fee: $5.00      │
│    Alu Angle    │  │   │  Testing Fee: $15.00     │
│  - Unit: $28.50 │  │   │  Cert Fee: $25.00        │
│  - Cutting: $5  │  │   └──────────────────────────┘
│  - Testing: $15 │  │                │
│  - Cert: $25    │  │                │
└─────────────────┘  │                ▼
                     │   ┌──────────────────────────┐
                     └──→│  CALCULATION             │
                         │  Material: 200×$28.50    │
                         │  Cutting: $5×2 = $10     │
                         │  Testing: $15×1 = $15    │
                         │  Cert: $25×1 = $25       │
                         │  ─────────────────────   │
                         │  Total: $5,750.00        │
                         └──────────────────────────┘
```
## License

This skill is provided as-is for use with Claude Desktop. Customize it to fit your business needs.

