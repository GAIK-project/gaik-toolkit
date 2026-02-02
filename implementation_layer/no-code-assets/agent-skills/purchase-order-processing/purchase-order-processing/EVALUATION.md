# Evaluation Scenarios

This file contains test scenarios to validate the purchase-order-processing skill. Each scenario tests specific functionality and edge cases.

---

## Scenario 1: Full Workflow with BOMs

### Description
Process a complete purchase order with matching Bills of Material for all items.

**Output Mode:** Default (uses text format - no sample provided)

### Input
```
input_folder/
├── customer_data/
│   ├── PO.pdf          # 3 line items
│   ├── BOM1.pdf        # MAT-2401
│   ├── BOM2.pdf        # MAT-3567
│   └── BOM3.pdf        # MAT-4829
└── price_list/
    └── price_list.xlsx # Contains all 3 material types
```

### Expected Behavior
1. Extract all fields from PO (header, customer, 3 line items, summary)
2. Match each Material_Number with corresponding BOM
3. Enrich items with Type/Part Designation and Dimensions from BOMs
4. Lookup prices for all 3 items in price list
5. Calculate:
   - Subtotal: $25,567.50
   - Volume Discount (5%): -$1,278.38
   - Fees: $165.00
   - Tax (6%): $1,467.25
6. Generate sales order using default text format
7. No validation warnings

### Pass Criteria
- [ ] All 3 BOM matches found
- [ ] All 3 prices found
- [ ] Discount tier correctly identified (5%)
- [ ] Grand total calculated correctly
- [ ] Text format output generated correctly
- [ ] Processing summary shows 100% success

---

## Scenario 2: PO Without BOMs

### Description
Process a purchase order where all technical information is contained in the PO itself (no separate BOMs needed).

**Output Mode:** Default (uses text format - no template/sample provided)

### Input
```
input_folder/
├── customer_data/
│   └── PO.pdf          # Contains Type/Part Designation in Description column
└── price_list/
    └── price_list.xlsx
```

### Expected Behavior
1. Extract PO fields including full descriptions
2. Detect no BOM files present
3. Use PO descriptions for price lookup
4. Match prices using PO descriptions → Price List Type/Part Designation
5. Calculate pricing normally
6. Generate sales order with note: "PO-only mode - no BOMs required"

### Pass Criteria
- [ ] Skill detects no BOMs and proceeds
- [ ] Price lookup succeeds using PO descriptions
- [ ] No "BOM Not Found" errors
- [ ] Sales order generated successfully
- [ ] Processing summary notes "PO-only mode"

---

## Scenario 3: Partial BOM Match

### Description
Process a PO where some items have matching BOMs and others don't.

**Output Mode:** Default (uses text format - no template/sample provided)

### Input
```
input_folder/
├── customer_data/
│   ├── PO.pdf          # 5 line items
│   ├── BOM1.pdf        # MAT-2401
│   ├── BOM2.pdf        # MAT-3567
│   └── BOM3.pdf        # MAT-4829
│   # Missing: BOMs for MAT-5100 and MAT-6200
└── price_list/
    └── price_list.xlsx
```

### Expected Behavior
1. Match BOMs for items 1-3
2. Flag items 4-5: "BOM Not Found - Manual Review Required"
3. Attempt price lookup for all 5 items
4. For items 4-5: use PO description if available, else flag
5. Generate sales order with:
   - Complete data for items 1-3
   - Partial data for items 4-5 (flagged)
6. Include warnings section in output

### Pass Criteria
- [ ] Items 1-3 fully processed
- [ ] Items 4-5 flagged correctly
- [ ] Sales order includes warning section
- [ ] Processing summary shows "3 of 5 BOMs matched"
- [ ] User prompted to review flagged items

---

## Scenario 4: Price Not Found

### Description
Process a PO with items that don't exist in the price list.

**Output Mode:** Default (uses text format - no template/sample provided)

### Input
```
input_folder/
├── customer_data/
│   ├── PO.pdf          # Includes a custom/special item
│   └── BOM_custom.pdf  # BOM for custom item
└── price_list/
    └── price_list.xlsx # Does NOT contain the custom item
```

### Expected Behavior
1. Extract PO and BOM data successfully
2. Attempt price lookup
3. For unmatched item: Flag "Price Not Found - Manual Pricing Required"
4. Include item in sales order with Unit_Price = "TBD"
5. Grand total shows "[Incomplete - prices pending]"
6. Processing summary lists items needing manual pricing

### Pass Criteria
- [ ] BOM match succeeds
- [ ] Price lookup fails gracefully (no error)
- [ ] Item appears in sales order with "TBD" price
- [ ] Total marked as incomplete
- [ ] Clear instruction for manual pricing

---

## Scenario 5: Volume Discount Threshold

### Description
Test discount tier calculation at exact boundaries.

**Output Mode:** Default (uses text format - no template/sample provided)

### Input
**Test A:** Subtotal = $4,999.99 (just under $5,000)
**Test B:** Subtotal = $5,000.00 (exactly at tier boundary)
**Test C:** Subtotal = $5,000.01 (just over $5,000)

### Expected Behavior
| Test | Subtotal | Expected Discount |
|------|----------|-------------------|
| A | $4,999.99 | 0% |
| B | $5,000.00 | 3% |
| C | $5,000.01 | 3% |

### Pass Criteria
- [ ] Test A: No discount applied
- [ ] Test B: 3% discount applied (boundary case)
- [ ] Test C: 3% discount applied
- [ ] Discount shown correctly in pricing summary

---

## Scenario 6: Sample-Style Output

### Description
Generate sales order by inferring format from a sample document.

**Output Mode:** Sample-Style (infers format from sample_order.docx)

### Input
```
input_folder/
├── customer_data/
│   └── PO.pdf
├── price_list/
│   └── price_list.xlsx
└── sample_sales_order/
    └── sample_order.docx
```

### Expected Behavior
1. Detect sample document exists
2. Analyze sample for:
   - Section structure
   - Table format
   - Heading styles
   - Footer content
3. Infer output format from sample
4. Generate sales order matching sample style
5. Populate with actual data from PO

### Pass Criteria
- [ ] Sample document analyzed
- [ ] Output structure matches sample
- [ ] Actual data used (not sample data)
- [ ] Formatting consistent with sample

---

## Scenario 7: Validation Warnings

### Description
Test validation rules for BOM-PO cross-references.

### Input
```
customer_data/
├── PO.pdf              # PO-2025-15903, Project PRJ-AT-2025-Q4B
└── BOM_mismatch.pdf    # References PO-2025-WRONG, Project PRJ-DIFFERENT
```

### Expected Behavior
1. BOM_ID matches Material_Number ✓
2. BOM_Customer_PO ≠ PO_Number → Warning
3. BOM_Project_Code ≠ Project_Code → Warning
4. Continue processing (don't fail)
5. Include warnings in output and summary

### Pass Criteria
- [ ] Processing completes despite mismatches
- [ ] Both warnings captured
- [ ] Warnings shown in sales order
- [ ] Processing summary lists warnings
- [ ] User prompted to verify documents

---

## Scenario 8: Missing Required Folder

### Description
Handle case where required input folder is missing.

### Input
```
input_folder/
├── customer_data/
│   └── PO.pdf
└── # Missing: price_list/ folder
```

### Expected Behavior
1. Detect missing price_list/ folder
2. Stop processing
3. Clear error message: "Required folder 'price_list/' not found"
4. Ask user to provide price list location

### Pass Criteria
- [ ] Missing folder detected early
- [ ] Clear error message
- [ ] No partial processing attempted
- [ ] User prompted for correction

---

## Scenario 9: Empty Price Comparison

### Description
Verify that PO prices are NEVER used for calculations.

### Input
PO with prices different from price list:
| Item | PO Price | Price List Price |
|------|----------|------------------|
| MAT-2401 | $30.00 | $28.50 |
| MAT-3567 | $200.00 | $195.75 |

### Expected Behavior
1. Extract PO prices (for reference only)
2. Lookup prices from price list
3. Use ONLY price list prices for calculations
4. Show price comparison in summary:
   - "MAT-2401: PO $30.00 vs Calculated $28.50"
5. Grand total based on price list prices

### Pass Criteria
- [ ] Calculations use price list prices
- [ ] PO prices not used anywhere in calculations
- [ ] Price comparison shown in summary
- [ ] Significant differences flagged for review

---

## Scenario 10: Large Order Processing

### Description
Test performance with a large purchase order.

### Input
- PO with 50+ line items
- 50+ BOM files
- Large price list (500+ products)

### Expected Behavior
1. Process all items without timeout
2. Match all BOMs efficiently
3. Lookup all prices
4. Generate complete sales order
5. Processing summary shows all items

### Pass Criteria
- [ ] All items processed
- [ ] No performance degradation
- [ ] Output file not corrupted
- [ ] All calculations accurate

---

## Scenario 11: Special Characters in Data

### Description
Handle special characters in company names, addresses, and descriptions.

### Input
PO with:
- Company: "O'Brien & Associates, LLC"
- Address: "123 Main St., Suite #456"
- Description: "Aluminum Angle (50×50×5mm)"

### Expected Behavior
1. Extract data with special characters intact
2. No encoding errors
3. Output displays correctly
4. File names sanitized for filesystem

### Pass Criteria
- [ ] Apostrophes preserved
- [ ] Ampersands preserved
- [ ] Unicode characters (×) handled
- [ ] File name uses safe characters

---

## Scenario 12: Calculation Breakdown Output

### Description
Verify that the skill generates a detailed calculation breakdown showing extraction, matching, and calculation steps for each item.

### Input
Standard input with 3 items and matching BOMs.

### Expected Behavior
1. Process order normally
2. Generate Calculation Breakdown document (or print to CLI)
3. For EACH item, breakdown shows:
   - **Extraction**: Source document, field locations, extracted values
   - **BOM Match**: Lookup key, matched BOM file, BOM ID confirmation
   - **Price Match**: Price list file, matched row, unit price found
   - **Calculation**: Formula with actual values, result
4. Order-level breakdown shows:
   - Subtotal calculation (sum of material costs)
   - Discount tier lookup and calculation
   - Fees aggregation
   - Tax calculation
   - Grand total assembly

### Expected Output Format
```
ITEM 1: MAT-2401 (Aluminum Angle - L Profile)
┌─────────────────────────────┬────────────────────────────────────────┐
│ Extraction                  │ PO.pdf → MAT-2401, Qty: 200            │
│ BOM Match                   │ BOM1.pdf → ID: MAT-2401 ✓              │
│ Price Match                 │ price_list.xlsx Row 2 → $28.50         │
│ Material Cost               │ 200 × $28.50 = $5,700.00               │
│ Fees                        │ Cut: $0 + Test: $15 + Cert: $25 = $40  │
│ LINE TOTAL                  │ $5,740.00                              │
└─────────────────────────────┴────────────────────────────────────────┘
```

### Pass Criteria
- [ ] Breakdown generated for each item
- [ ] Extraction shows source document and field location
- [ ] BOM matching shows lookup key and result
- [ ] Price matching shows row number and price found
- [ ] Calculations show formula with actual values
- [ ] Order totals show step-by-step aggregation
- [ ] Discount tier lookup is visible
- [ ] Tax calculation base and rate are shown
- [ ] Output is formatted as 2-column table
- [ ] Can be printed to CLI or saved as file

---

## Scenario 13: Calculation Breakdown with Errors

### Description
Verify that the calculation breakdown clearly shows where issues occurred.

### Input
PO with items where:
- Item 1: Full match (BOM + price)
- Item 2: BOM not found
- Item 3: Price not found

### Expected Behavior
Breakdown shows clear status for each step:

```
ITEM 1: MAT-2401
│ BOM Match                   │ BOM1.pdf → ID: MAT-2401 ✓              │
│ Price Match                 │ price_list.xlsx Row 2 → $28.50 ✓       │

ITEM 2: MAT-9999
│ BOM Match                   │ ❌ NOT FOUND - No BOM with ID MAT-9999 │
│ Price Match                 │ (skipped - no Type/Part Designation)   │

ITEM 3: MAT-CUSTOM
│ BOM Match                   │ BOM_custom.pdf → ID: MAT-CUSTOM ✓      │
│ Price Match                 │ ❌ NOT FOUND - "Custom Widget" not in price list │
```

### Pass Criteria
- [ ] Successful steps show ✓
- [ ] Failed steps show ❌ with reason
- [ ] Skipped steps show explanation
- [ ] Breakdown still generated despite errors
- [ ] Clear indication of what needs manual review

---

## Scenario 14: Default Text Format Validation

### Description
Comprehensive validation of default text format output when no template or sample is provided.

**Output Mode:** Default (uses text format - no template/sample provided)

### Input
```
input_folder/
├── customer_data/
│   ├── PO.pdf          # 3 line items with special instructions
│   ├── BOM1.pdf        # MAT-2401
│   ├── BOM2.pdf        # MAT-3567
│   └── BOM3.pdf        # MAT-4829
└── price_list/
    └── price_list.xlsx
# Note: NO template/ or sample_sales_order/ folders
```

### Expected Behavior
1. Process PO and BOMs normally
2. Detect no template or sample provided
3. Generate Sales Order using default text format:
   - **File Extension:** `.txt` (plain text)
   - **Encoding:** UTF-8
   - **Line Width:** 80 characters maximum
   - **Format:** Professional structured text matching specification
4. Include all required sections:
   - Company Header (centered, with separator lines)
   - ORDER INFORMATION (SO number, date, PO reference, payment/shipping terms)
   - CUSTOMER INFORMATION (Bill To / Ship To side-by-side)
   - ORDER DETAILS table (pipe-separated, aligned columns)
   - PRICING SUMMARY (right-aligned currency values)
   - SPECIAL INSTRUCTIONS (if present in PO)
   - APPROVAL section (signature lines)
   - TERMS & CONDITIONS
5. Generate `Calculation_Breakdown.txt` with matching format

### Formatting Validation

#### Section Separators
- [ ] Major sections use 80 `=` characters
- [ ] Subsections use 80 `-` characters
- [ ] Consistent spacing (one blank line before/after headers)

#### Table Formatting
- [ ] Pipe `|` separators used
- [ ] Headers aligned with data
- [ ] Numeric values right-aligned
- [ ] Text values left-aligned
- [ ] Total width ≤ 80 characters

#### Currency Formatting
- [ ] All currency values have `$` symbol
- [ ] Comma separators for thousands (e.g., `$1,234.56`)
- [ ] Exactly 2 decimal places always shown
- [ ] Negative values use minus prefix (e.g., `-$1,278.38`)
- [ ] Right-aligned in tables

#### Date Formatting
- [ ] Consistent format: "Month DD, YYYY"
- [ ] Example: "November 15, 2025"

#### Conditional Display
- [ ] Volume Discount row hidden if discount is 0%
- [ ] Ship To shows "SAME AS BILL TO" if no separate address
- [ ] Special Instructions section omitted if none in PO

### Text Editor Compatibility
Test the generated `.txt` file in multiple editors:
- [ ] **Notepad (Windows):** Displays correctly, no encoding issues
- [ ] **VSCode:** Proper line breaks, no special character errors
- [ ] **Terminal/CLI:** Readable with proper alignment
- [ ] **Email client:** Copy-paste preserves formatting
- [ ] **Word Import:** Can be imported cleanly into Word document

### File Specifications
- [ ] Filename format: `SO-{number}_{customer}_{date}.txt`
- [ ] UTF-8 encoding (no BOM)
- [ ] Platform-appropriate line endings (CRLF on Windows, LF on Unix)
- [ ] No trailing whitespace on lines
- [ ] Exactly 80 characters per line maximum

### Content Validation
- [ ] All extracted PO data present and accurate
- [ ] All BOM enrichment data included
- [ ] Prices from Price List (not PO)
- [ ] Volume discount calculated and displayed correctly
- [ ] Grand total matches Calculation_Breakdown.txt

### Output Comparison
Compare Sales Order output with:
- [ ] `reference/OUTPUT_FORMAT.md` specification
- [ ] `Calculation_Breakdown.txt` format (should be consistent style)
- [ ] Verify no deviation from specified format

### Pass Criteria
- [ ] All formatting rules followed
- [ ] 80-character width enforced
- [ ] UTF-8 encoding correct
- [ ] Readable in all tested editors
- [ ] Professional appearance
- [ ] Matches specification in `reference/OUTPUT_FORMAT.md`
- [ ] Consistent style with Calculation_Breakdown.txt

---

## Running Evaluations

### Manual Testing
1. Copy scenario input to a test folder
2. Invoke skill with test folder path
3. Compare output against expected results
4. Check all pass criteria

### Automated Testing (Future)
```python
def test_scenario_1():
    result = run_skill("test_data/scenario_1/")
    assert result.bom_matches == 3
    assert result.price_matches == 3
    assert abs(result.grand_total - 26371.37) < 0.01
    assert len(result.warnings) == 0
```
