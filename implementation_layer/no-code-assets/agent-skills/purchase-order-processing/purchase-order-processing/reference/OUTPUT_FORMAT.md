# Output Format Reference

This file defines the structure and format of the Sales Order output. Customize this file to adapt the skill for your output requirements.

---

## Output Modes

The skill supports two output modes:

| Mode | Trigger | Description |
|------|---------|-------------|
| Sample-Style | `sample_sales_order/sample_order.docx` exists | Infer and match the sample's format and style |
| Default | No sample provided | Use standard text format specified below |

---

## Default Text Format (When No Sample Provided)

When the `sample_sales_order/` folder is not provided, use this professional text format.

### File Specifications
- **Format:** Plain text file (UTF-8 encoding)
- **Extension:** `.txt`
- **Width:** 80 characters maximum per line
- **Line Endings:** Platform-appropriate (CRLF on Windows, LF on Unix/Mac)

### Structure Overview

The default Sales Order uses a clean, structured text format that:
- Is readable in any text editor, email client, or terminal
- Can be easily imported into Word or PDF converters
- Matches the style of the Calculation Breakdown document
- Uses consistent formatting for professional appearance

### Complete Default Format

```
================================================================================
                           [COMPANY NAME]
                      [Company Address Line 1]
                      [Company Address Line 2]
                    Phone: [Phone] | Email: [Email]
================================================================================
                                SALES ORDER
================================================================================

ORDER INFORMATION
--------------------------------------------------------------------------------
SO Number:           {SO_Number}
Order Date:          {SO_Date}
Customer PO:         {Customer_PO_Number}
Payment Terms:       {Payment_Terms}
Shipping Terms:      {Shipping_Terms}
Project Code:        {Project_Code}


CUSTOMER INFORMATION
--------------------------------------------------------------------------------
BILL TO:                            SHIP TO:
{Customer_Name}                     {Ship_To_Name or "SAME AS BILL TO"}
{Customer_Address_Line1}
{Customer_Address_Line2}

Contact: {Customer_Contact}
Phone:   {Customer_Phone}
Email:   {Customer_Email}


ORDER DETAILS
================================================================================
| Item | Mat. No.  | Type/Part Designation      | Qty | Unit Price | Total    |
|------|-----------|----------------------------|-----|------------|----------|
| 1    | MAT-2401  | Aluminum Angle - L Profile | 200 | $28.50     | $5,700.00|
| 2    | MAT-2402  | Steel Plate - Flat         | 150 | $45.00     | $6,750.00|
| 3    | MAT-2403  | Copper Bar - Round         | 100 | $82.50     | $8,250.00|
================================================================================


PRICING SUMMARY
--------------------------------------------------------------------------------
Subtotal:                                                        ${Subtotal}
Volume Discount ({Discount_Rate}%):                            -${Discount}
Total Testing/Cert:                                              ${Fees}
Total Shipping Cost:                                             ${Shipping}
Tax ({Tax_Rate}%):                                               ${Tax}
────────────────────────────────────────────────────────────────────────────
TOTAL:                                                           ${Grand_Total}
────────────────────────────────────────────────────────────────────────────


SPECIAL INSTRUCTIONS
--------------------------------------------------------------------------------
{Special_Instructions_from_PO}

Documentation Required:
  - {Doc_Requirement_1}
  - {Doc_Requirement_2}


APPROVAL
--------------------------------------------------------------------------------
Prepared By: _______________________    Date: _______________

Authorized By: _____________________    Date: _______________


TERMS & CONDITIONS
================================================================================
1. All prices are in USD and are valid for 30 days from the order date.
2. Payment terms as specified above. Late payments subject to 1.5% monthly fee.
3. Delivery dates are estimated and subject to material availability.
4. All materials supplied meet specified grades and standards.
5. Testing and certification fees are non-refundable.
6. Title and risk pass to buyer upon shipment FOB origin unless otherwise noted.
7. Returns accepted only for defective materials within 30 days of delivery.
8. Buyer responsible for compliance with local regulations and standards.

For questions or concerns, please contact our sales team.
================================================================================
                           END OF SALES ORDER
================================================================================
```

### Formatting Rules

#### Section Headers
- **Major sections:** Use 80 `=` characters with centered text above
- **Subsections:** Use 80 `-` characters with left-aligned text above
- **Spacing:** One blank line before and after section headers

#### Text Alignment
- **Labels:** Left-aligned with consistent indentation (typically 2 spaces)
- **Values:** Aligned to colons for field-value pairs
- **Currency:** Right-aligned in tables, always 2 decimal places with $ symbol
- **Dates:** Format as "Month DD, YYYY" (e.g., "November 15, 2025")

#### Tables
- Use pipe `|` separators for columns
- Align headers with data
- Right-align numeric values (quantities, prices, totals)
- Left-align text values (descriptions, material numbers)
- Keep total table width within 80 characters
- Add separators (═══) above and below table content

#### Currency Formatting
- Always include `$` symbol
- Use comma separators for thousands (e.g., `$1,234.56`)
- Always show exactly 2 decimal places
- Negative values use minus sign prefix (e.g., `-$1,278.38`)
- Right-align currency values in columns

#### Conditional Display
- **Volume Discount:** Hide the row entirely if discount is 0%
- **Ship To:** Use "SAME AS BILL TO" if no separate shipping address provided
- **Special Instructions:** Omit section if PO has no special instructions
- **Project Code:** Omit row if not provided in PO

### Example Variables

| Variable | Example Value |
|----------|---------------|
| `{SO_Number}` | SO-2025-15903 |
| `{SO_Date}` | November 15, 2025 |
| `{Customer_PO_Number}` | PO-2025-15903 |
| `{Payment_Terms}` | Net 30 |
| `{Shipping_Terms}` | FOB Origin |
| `{Project_Code}` | PROJ-Q4-2025 |
| `{Customer_Name}` | AutoTech Manufacturing Corp. |
| `{Subtotal}` | $25,567.50 |
| `{Discount_Rate}` | 5 |
| `{Discount}` | $1,278.38 |
| `{Fees}` | $165.00 |
| `{Shipping}` | $450.00 |
| `{Tax_Rate}` | 6 |
| `{Tax}` | $1,494.25 |
| `{Grand_Total}` | $26,398.37 |

### File Naming Convention

```
SO-{SO_Number}_{Customer_Name}_{Date}.txt
```

**Example:**
```
SO-2025-15903_AutoTech_Manufacturing_2025-11-15.txt
```

### Notes

- This format ensures consistency across all Sales Order outputs when templates are not provided
- The format matches the style used in `Calculation_Breakdown.txt` for consistency
- Text format is portable and can be easily shared via email, git, or imported into Word
- All sections are clearly separated for easy reading and scanning

---

## Sales Order Sections

### Section Overview

| Section | Required | Description |
|---------|----------|-------------|
| Header | Yes | SO number, date, customer PO reference |
| Customer Information | Yes | Bill To and Ship To details |
| Order Details Table | Yes | Line items with pricing |
| Pricing Summary | Yes | Subtotal, discounts, fees, tax, total |
| Special Instructions | If present | Requirements from PO |
| Approval Section | Optional | Signature lines |
| Footer | Optional | Terms and conditions |

---

## Section 1: Header

### Fields
| Field | Source | Format |
|-------|--------|--------|
| SO_Number | Generated | SO-YYYY-NNNNN |
| SO_Date | System date | Month DD, YYYY |
| Customer_PO | PO.PO_Number | As provided |
| Payment_Terms | PO.Payment_Terms | As provided |
| Shipping_Terms | PO.Shipping_Terms | As provided |
| Project_Code | PO.Project_Code | As provided (if exists) |

### SO Number Generation
```
Format: SO-[Year]-[5-digit sequence]
Example: SO-2025-08472
```

### Layout Example
```
╔════════════════════════════════════════════════════════════════╗
║  PRECISION STEEL & COMPONENTS LTD.                             ║
║  1500 Steel Way, Pittsburgh, PA 15222                          ║
║  Tel: +1 (412) 555-8900 | Email: sales@precisionsteel.com     ║
╠════════════════════════════════════════════════════════════════╣
║                        SALES ORDER                              ║
╠════════════════════════════════════════════════════════════════╣
║  SO Number: SO-2025-08472         Order Date: November 15, 2025║
║  Customer PO: PO-2025-15903       Payment Terms: Net 30        ║
║  Project Code: PRJ-AT-2025-Q4B    Shipping: FOB Destination    ║
╚════════════════════════════════════════════════════════════════╝
```

---

## Section 2: Customer Information

### Bill To Fields
| Field | Source |
|-------|--------|
| Company Name | PO.Customer_Name |
| Address | PO.Customer_Address |
| Contact | PO.Customer_Contact |
| Phone | PO.Customer_Phone |
| Email | PO.Customer_Email |

### Ship To Fields
| Field | Source |
|-------|--------|
| Location Name | PO (if different from Bill To) |
| Address | PO.Shipping_Address (if provided) |
| Receiving Hours | PO (if provided) |
| Special Instructions | PO (if provided) |

### Layout Example
```
┌─────────────────────────────────┬─────────────────────────────────┐
│ BILL TO:                        │ SHIP TO:                        │
├─────────────────────────────────┼─────────────────────────────────┤
│ AutoTech Manufacturing Corp.    │ AutoTech Manufacturing Corp.    │
│ 2750 Industrial Parkway         │ Receiving Dock #3               │
│ Detroit, MI 48201               │ 2750 Industrial Parkway         │
│                                 │ Detroit, MI 48201               │
│ Contact: Patricia Henderson     │                                 │
│ Phone: +1 (313) 555-4200       │ Receiving: 7:00 AM - 4:00 PM    │
│ Email: purchasing@autotech.com  │                                 │
└─────────────────────────────────┴─────────────────────────────────┘
```

---

## Section 3: Order Details Table

### Column Structure
| Column | Width | Alignment | Source |
|--------|-------|-----------|--------|
| Item | 5% | Center | PO.Item_Number |
| Mat. No. | 10% | Left | PO.Material_Number |
| Type/Part Designation | 25% | Left | BOM.Type_Part_Designation |
| Dimensions | 20% | Left | BOM.Dimensions |
| Qty | 8% | Right | PO.Quantity |
| Unit Price | 10% | Right | Price_List.Unit_Price |
| Total | 12% | Right | Calculated.Line_Total |
| Ship Date | 10% | Center | PO.Delivery_Date |

### Table Format
```
┌──────┬───────────┬─────────────────────────┬────────────────────────┬───────┬────────────┬────────────┬─────────────┐
│ Item │ Mat. No.  │ Type/Part Designation   │ Dimensions             │  Qty  │ Unit Price │    Total   │  Ship Date  │
├──────┼───────────┼─────────────────────────┼────────────────────────┼───────┼────────────┼────────────┼─────────────┤
│  1   │ MAT-2401  │ Aluminum Angle - L      │ 50x50x5 mm x 6000 mm   │  200  │    $28.50  │  $5,700.00 │ Dec 01, 2025│
│  2   │ MAT-3567  │ SS Sheet - Grade 304    │ 1220x2440x3 mm         │   50  │   $195.75  │  $9,787.50 │ Dec 05, 2025│
│  3   │ MAT-4829  │ Seamless CS Pipe        │ NPS 2" SCH40 x 6000 mm │  150  │    $67.20  │ $10,080.00 │ Dec 10, 2025│
└──────┴───────────┴─────────────────────────┴────────────────────────┴───────┴────────────┴────────────┴─────────────┘
```

### Additional Columns (Optional)
| Column | When to Include |
|--------|-----------------|
| Material Grade | If significantly different between items |
| Lead Time | If delivery dates vary significantly |
| Weight | If shipping is weight-based |
| Notes | If item-specific instructions exist |

---

## Section 4: Pricing Summary

### Summary Fields
| Field | Label | Source | Format |
|-------|-------|--------|--------|
| Subtotal | Subtotal: | Calculated.Subtotal | $XX,XXX.XX |
| Volume_Discount | Volume Discount (X%): | Calculated | -$X,XXX.XX |
| Total_Testing_Cert | Total Testing/Cert: | Calculated (Testing + Cert) | $XXX.XX |
| Shipping | Total Shipping Cost: | Calculated or PO | $XXX.XX |
| Tax_Amount | Tax (X%): | Calculated | $X,XXX.XX |
| Grand_Total | **TOTAL:** | Calculated | **$XX,XXX.XX** |

### Layout Example (Matching Sample Format)
```
                                           ┌────────────────────────────────┐
                                           │ Subtotal:          $25,567.50 │
                                           │ Volume Discount (5%): -$1,278.38│
                                           │ Total Testing/Cert:   $165.00 │
                                           │ Total Shipping Cost:  $450.00 │
                                           │ Tax (6%):           $1,494.25 │
                                           ╞════════════════════════════════╡
                                           │ TOTAL:             $26,398.37 │
                                           └────────────────────────────────┘
```

### Conditional Display
- Hide "Volume Discount" line if discount is 0%
- Combine Testing + Certification fees into single "Total Testing/Cert" line
- Use "Total Shipping Cost:" label for consistency with sample format

---

## Section 5: Special Instructions

### Include If Present
- Mill Test Certificate requirements
- Delivery scheduling requirements
- Quality inspection requirements
- Packaging requirements
- Documentation requirements

### Layout Example
```
┌─────────────────────────────────────────────────────────────────────────┐
│ SPECIAL INSTRUCTIONS:                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ • Mill Test Certificates (MTC 3.1) required for all materials           │
│ • Delivery appointment required - contact receiving 48 hours in advance │
│ • Partial shipments accepted if communicated in advance                 │
│ • Bill of Materials (BOM) must accompany each shipment                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Section 6: Approval Section

### Fields
| Field | Description |
|-------|-------------|
| Prepared_By | Sales representative name and signature line |
| Prepared_Date | Date prepared |
| Approved_By | Sales manager name and signature line |
| Approved_Date | Date approved |

### Layout Example
```
┌─────────────────────────────────┬─────────────────────────────────┐
│ Prepared By:                    │ Approved By:                    │
│                                 │                                 │
│ _____________________________   │ _____________________________   │
│ Sales Representative            │ Sales Manager                   │
│                                 │                                 │
│ Date: _____________________     │ Date: _____________________     │
└─────────────────────────────────┴─────────────────────────────────┘
```

---

## Section 7: Footer

### Standard Footer Text
```
Terms & Conditions:
This Sales Order is subject to our standard terms and conditions available at
www.precisionsteel.com/terms. Prices valid for 30 days from order date.
Payment due within terms specified above.

Thank you for your business!
```

---

## Output File Naming

### Convention
```
SO-[number]_[customer]_[date].[ext]
```

### Examples
```
SO-2025-08472_AutoTech-Manufacturing_2025-11-15.docx
SO-2025-08472_AutoTech-Manufacturing_2025-11-15.md
```

---

## Processing Summary Output

In addition to the Sales Order, generate a processing summary:

### Summary Contents
```
═══════════════════════════════════════════════════════════════
PURCHASE ORDER PROCESSING SUMMARY
═══════════════════════════════════════════════════════════════

Input Documents:
  ✓ PO.pdf - Purchase Order PO-2025-15903
  ✓ BOM1.pdf - MAT-2401 matched
  ✓ BOM2.pdf - MAT-3567 matched
  ✓ BOM3.pdf - MAT-4829 matched
  ✓ price_list.xlsx - 20 products loaded

Processing Results:
  Items Processed: 3 of 3 (100%)
  BOMs Matched: 3 of 3 (100%)
  Prices Found: 3 of 3 (100%)

Validation Warnings:
  (none)

Price Comparison (PO vs Calculated):
  Item 1: PO $5,700.00 vs Calculated $5,700.00 ✓
  Item 2: PO $9,787.50 vs Calculated $9,787.50 ✓
  Item 3: PO $10,080.00 vs Calculated $10,080.00 ✓

Output Generated:
  SO-2025-08472_AutoTech-Manufacturing_2025-11-15.docx

═══════════════════════════════════════════════════════════════
```

---

## Customization Guide

### To add new sections:

1. Define the section in this file
2. Add corresponding fields to EXTRACTION_FIELDS.md
3. Update SKILL.md workflow to populate the section

### To modify column order:

1. Reorder columns in "Order Details Table" section
2. Update width percentages to total 100%

### To change number formats:

| Format | Example | Use For |
|--------|---------|---------|
| Currency | $1,234.56 | All monetary values |
| Percentage | 5% | Discount rates, tax rates |
| Quantity | 200 | Item quantities (no decimals) |
| Date | Dec 01, 2025 | Delivery dates |

### To add company branding:

1. Update header section with your company details
2. Modify footer with your terms and website
3. Add logo placeholder: `{{COMPANY_LOGO}}`

### To support multiple languages:

1. Create language-specific output format files
2. Add language parameter to skill
3. Use appropriate date/number formats for locale

---

## Calculation Breakdown Document

This document provides a detailed, step-by-step breakdown of how each item's price was calculated. It helps users understand, verify, and audit the pricing logic.

### Output Options

| Option | Description |
|--------|-------------|
| Print to CLI | Display in console/terminal during processing |
| Save as file | `Calculation_Breakdown_[SO-Number].md` |
| Both | Print AND save |

### Format: 2-Column Table

For EACH line item, generate a breakdown table:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  CALCULATION BREAKDOWN - Item 1: MAT-2401                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Step                              │ Details                                 ║
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  EXTRACTION                        │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Source Document                   │ PO.pdf                                  │
│  Material Number                   │ MAT-2401 (from Line Item table, col 2)  │
│  Quantity                          │ 200 (from Line Item table, col 4)       │
│  Delivery Date                     │ Dec 01, 2025 (from Line Item table)     │
│  PO Unit Price (reference only)    │ $28.50 (NOT used for calculation)       │
├────────────────────────────────────┼─────────────────────────────────────────┤
│  BOM Source                        │ BOM1.pdf                                │
│  BOM ID Match                      │ MAT-2401 = MAT-2401 ✓                   │
│  Type/Part Designation             │ "Aluminum Angle - L Profile"            │
│  Dimensions                        │ 50 x 50 x 5 mm x 6000 mm                │
│  Material Grade                    │ 6061-T6                                 │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  PRICE MATCHING                    │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Lookup Key                        │ "Aluminum Angle - L Profile"            │
│  Price List File                   │ price_list.xlsx                         │
│  Matched Row                       │ Row 2: AL-001                           │
│  Match Method                      │ CONTAINS match on Type/Part Designation │
│  Unit Price Found                  │ $28.50                                  │
│  Cutting Fee                       │ $5.00                                   │
│  Testing Fee                       │ $15.00                                  │
│  Cert Fee                          │ $25.00                                  │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  LINE ITEM CALCULATION             │                                         │
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Material Cost                     │ 200 × $28.50 = $5,700.00                │
│  Cutting Cost                      │ $5.00 × 0 cuts = $0.00                  │
│  Testing Cost                      │ $15.00 × 1 lot = $15.00                 │
│  Certification Cost                │ $25.00 × 1 cert = $25.00                │
│  ─────────────────────────────────────────────────────────────────────────── │
│  LINE TOTAL                        │ $5,700.00 + $0 + $15 + $25 = $5,740.00  │
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Order-Level Breakdown

After all items, show the order-level calculations:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ORDER TOTAL CALCULATION                                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Step                              │ Details                                 ║
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  MATERIAL SUBTOTAL                 │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Item 1 Material Cost              │ $5,700.00                               │
│  Item 2 Material Cost              │ $9,787.50                               │
│  Item 3 Material Cost              │ $10,080.00                              │
│  ─────────────────────────────────────────────────────────────────────────── │
│  SUBTOTAL                          │ $5,700 + $9,787.50 + $10,080 = $25,567.50│
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  VOLUME DISCOUNT                   │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Subtotal Amount                   │ $25,567.50                              │
│  Discount Tier Lookup              │ $15,000 - $29,999 → 5% discount         │
│  Discount Calculation              │ $25,567.50 × 5% = $1,278.38             │
│  ─────────────────────────────────────────────────────────────────────────── │
│  NET MATERIAL COST                 │ $25,567.50 - $1,278.38 = $24,289.12     │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  FEES AGGREGATION                  │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Total Cutting Fees                │ $0 + $0 + $0 = $0.00                    │
│  Total Testing Fees                │ $15 + $35 + $20 = $70.00                │
│  Total Cert Fees                   │ $25 + $40 + $30 = $95.00                │
│  ─────────────────────────────────────────────────────────────────────────── │
│  TOTAL FEES                        │ $0 + $70 + $95 = $165.00                │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  SHIPPING                          │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Source                            │ From PO (PO.PO_Shipping)                │
│  Shipping Amount                   │ $450.00                                 │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  TAX CALCULATION                   │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Taxable Base                      │ Net Material + Fees                     │
│  Taxable Amount                    │ $24,289.12 + $165.00 = $24,454.12       │
│  Tax Rate                          │ 6% (from PO)                            │
│  Tax Calculation                   │ $24,454.12 × 6% = $1,467.25             │
╠════════════════════════════════════╪═════════════════════════════════════════╣
║  GRAND TOTAL                       │                                         ║
├────────────────────────────────────┼─────────────────────────────────────────┤
│  Net Material Cost                 │ $24,289.12                              │
│  + Total Fees                      │ $165.00                                 │
│  + Shipping                        │ $450.00                                 │
│  + Tax                             │ $1,467.25                               │
│  ═══════════════════════════════════════════════════════════════════════════ │
│  GRAND TOTAL                       │ $26,371.37                              │
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Compact Format (Alternative)

For CLI output, a more compact format:

```
=== CALCULATION BREAKDOWN ===

ITEM 1: MAT-2401 (Aluminum Angle - L Profile)
┌─────────────────────────────┬────────────────────────────────────────┐
│ Extraction                  │ PO.pdf → MAT-2401, Qty: 200            │
│ BOM Match                   │ BOM1.pdf → ID: MAT-2401 ✓              │
│ Price Match                 │ price_list.xlsx Row 2 (AL-001) → $28.50│
│ Material Cost               │ 200 × $28.50 = $5,700.00               │
│ Fees                        │ Cut: $0 + Test: $15 + Cert: $25 = $40  │
│ LINE TOTAL                  │ $5,740.00                              │
└─────────────────────────────┴────────────────────────────────────────┘

ITEM 2: MAT-3567 (SS Sheet - Grade 304)
┌─────────────────────────────┬────────────────────────────────────────┐
│ Extraction                  │ PO.pdf → MAT-3567, Qty: 50             │
│ BOM Match                   │ BOM2.pdf → ID: MAT-3567 ✓              │
│ Price Match                 │ price_list.xlsx Row 7 (SS-001) → $195.75│
│ Material Cost               │ 50 × $195.75 = $9,787.50               │
│ Fees                        │ Cut: $0 + Test: $35 + Cert: $40 = $75  │
│ LINE TOTAL                  │ $9,862.50                              │
└─────────────────────────────┴────────────────────────────────────────┘

ITEM 3: MAT-4829 (Seamless CS Pipe)
┌─────────────────────────────┬────────────────────────────────────────┐
│ Extraction                  │ PO.pdf → MAT-4829, Qty: 150            │
│ BOM Match                   │ BOM3.pdf → ID: MAT-4829 ✓              │
│ Price Match                 │ price_list.xlsx Row 12 (CS-001) → $67.20│
│ Material Cost               │ 150 × $67.20 = $10,080.00              │
│ Fees                        │ Cut: $0 + Test: $20 + Cert: $30 = $50  │
│ LINE TOTAL                  │ $10,130.00                             │
└─────────────────────────────┴────────────────────────────────────────┘

ORDER TOTALS:
┌─────────────────────────────┬────────────────────────────────────────┐
│ Subtotal (Materials)        │ $5,700 + $9,787.50 + $10,080 = $25,567.50│
│ Volume Discount (5%)        │ $25,567.50 × 5% = -$1,278.38           │
│ Net Material Cost           │ $24,289.12                             │
│ Total Fees                  │ $40 + $75 + $50 = $165.00              │
│ Shipping                    │ $450.00 (from PO)                      │
│ Tax (6%)                    │ $24,454.12 × 6% = $1,467.25            │
├─────────────────────────────┼────────────────────────────────────────┤
│ GRAND TOTAL                 │ $26,371.37                             │
└─────────────────────────────┴────────────────────────────────────────┘
```

### Breakdown Table Columns

| Column | Description | Example |
|--------|-------------|---------|
| Step | What operation was performed | "Material Cost" |
| Details | Source, formula, and result | "200 × $28.50 = $5,700.00" |

### What to Show in Each Section

**EXTRACTION Section:**
- Source document filename
- Field name and location (column, row, section)
- Extracted value
- Note if value is "for reference only" (like PO prices)

**PRICE MATCHING Section:**
- Lookup key used
- Price list filename
- Matched row number and item code
- Match method (exact, contains, partial)
- All price fields found

**CALCULATION Section:**
- Formula in words
- Actual values substituted
- Result with proper formatting

### Customization

To customize the breakdown format:

1. **Change detail level:**
   - "verbose": Show all steps with full explanations
   - "compact": Show condensed 2-column format
   - "minimal": Show only key steps and totals

2. **Choose output method:**
   ```markdown
   Output: CLI         # Print to console only
   Output: File        # Save to file only
   Output: Both        # Print AND save
   ```

3. **Modify sections:**
   - Add custom calculation steps
   - Include/exclude specific fields
   - Change column headers
