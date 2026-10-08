# Calculation Breakdown Template

This template defines the format for the `Calculation_Breakdown.txt` file that is generated alongside the Sales Order document.

## Format Consistency

**Important:** The Calculation Breakdown and Sales Order documents use consistent text formatting:
- Both use plain text format (`.txt` files, UTF-8 encoding)
- Both follow 80-character width standard
- Both use `=` characters for major sections, `-` for subsections
- Both use consistent currency formatting ($X,XXX.XX format)
- Both use right-aligned numeric values
- This ensures a professional, uniform appearance across all skill outputs

When no template or sample is provided, the Sales Order will use the same formatting style as this Calculation Breakdown document, creating a cohesive document set.

## Purpose

The Calculation Breakdown file helps users:
- Understand exactly where each value came from (which source document, which field)
- Verify that prices were correctly matched from the price list
- Validate all calculation steps
- Audit the pricing logic for accuracy

## File Format

**Filename:** `Calculation_Breakdown.txt`

**Format:** Plain text file with clear section headers and formatting

## Template Structure

```
================================================================================
                    SALES ORDER CALCULATION BREAKDOWN
                  SO-{SO_NUMBER} for {Customer_Name}
                          Generated: {Date}
================================================================================

SOURCE DOCUMENTS
--------------------------------------------------------------------------------
Purchase Order:     {PO_Number} ({PO_Date})
BOM Files:          {List of BOM files with revisions}
Price List:         {Price list filename} ({Effective dates})
All BOMs Status:    {Status - e.g., Approved}


ITEM {N}: {Material_Number} - {Type/Part Designation}
================================================================================
Extracted from {BOM_filename}:
  - Type/Part: {Type_Part_Designation}
  - Dimensions: {Dimensions}
  - Grade: {Material_Grade}

Extracted from PO.pdf:
  - Quantity: {Quantity} {Unit}

Matched in Price List ({Price_List_Item_No}):
  - Unit Price: ${Unit_Price}
  - Testing Fee: ${Testing_Fee}
  - Cert Fee: ${Cert_Fee}

Calculations:
  Material Cost  = {Quantity} × ${Unit_Price}        = ${Material_Cost}
  Testing Fee    = ${Testing_Fee} × {Lots}           = ${Testing_Cost}
  Cert Fee       = ${Cert_Fee} × {Certs}             = ${Cert_Cost}
  --------------------------------------------------------
  Line Total                                         = ${Line_Total}


[Repeat for each item...]


ORDER-LEVEL CALCULATIONS
================================================================================
Material Subtotal:
  Item 1 + Item 2 + ... + Item N
  = ${Item1_Material} + ${Item2_Material} + ... + ${ItemN_Material}
  = ${Material_Subtotal}

Volume Discount ({Discount_Rate}% applied for orders ${Range_Min}-${Range_Max}):
  = ${Material_Subtotal} × {Discount_Rate}%
  = -${Volume_Discount}

Net Material Cost:
  = ${Material_Subtotal} - ${Volume_Discount}
  = ${Net_Material_Cost}

Testing Fees:
  = ${Item1_Testing} + ${Item2_Testing} + ... + ${ItemN_Testing}
  = ${Total_Testing_Fees}

Certification Fees:
  = ${Item1_Cert} + ${Item2_Cert} + ... + ${ItemN_Cert}
  = ${Total_Cert_Fees}

Shipping (from PO):
  = ${Shipping}

Subtotal (before tax):
  = ${Net_Material_Cost} + ${Total_Testing_Fees} + ${Total_Cert_Fees} + ${Shipping}
  = ${Subtotal_Before_Tax}

Tax ({Tax_Rate}%):
  = ${Subtotal_Before_Tax} × {Tax_Rate_Decimal}
  = ${Tax_Amount}

--------------------------------------------------------------------------------
GRAND TOTAL = ${Grand_Total}
--------------------------------------------------------------------------------


================================================================================
End of Calculation Breakdown
================================================================================
```

## Customization Guidelines

### Section Headers
- Use `=` characters for major section separators (80 characters wide)
- Use `-` characters for subsection separators (80 characters wide)

### Formatting Rules
- Align numeric values to the right for easy scanning
- Use consistent spacing for formulas (e.g., "  = " for alignment)
- Keep currency values formatted with $ and 2 decimal places
- Use clear indentation (2 spaces) for nested information

### Optional Sections

You can add these optional sections if needed:

#### Price Comparison (if PO prices differ from calculated)
```
PRICE COMPARISON
================================================================================
| Item | PO Unit Price | SO Unit Price | Difference |
|------|---------------|---------------|------------|
| 1    | ${PO_Price}   | ${SO_Price}   | ${Diff}    |
...
```

#### Validation Warnings
```
WARNINGS/NOTES
================================================================================
- [Any validation warnings]
- [Items flagged for manual review]
- [Special instructions from PO]
```

#### BOM Validation Details
```
BOM VALIDATION
================================================================================
Item 1: MAT-{Material_Number}
  ✓ BOM Status: Approved
  ✓ PO Reference matches: {PO_Number}
  ✓ Project Code matches: {Project_Code}
  ✓ Price List match found

[Repeat for each item...]
```

## Usage in Skill

The skill should:
1. Follow this template structure when generating `Calculation_Breakdown.txt`
2. Replace all `{placeholders}` with actual extracted/calculated values
3. Include all items from the purchase order
4. Show all calculation steps explicitly
5. Save the file in the same directory as the Sales Order document

## Example Variable Mapping

| Placeholder | Source | Example |
|-------------|--------|---------|
| `{SO_Number}` | Generated | SO-2025-15903 |
| `{Customer_Name}` | PO header | AutoTech Manufacturing Corp. |
| `{PO_Number}` | PO header | PO-2025-15903 |
| `{Material_Number}` | PO line item | MAT-2401 |
| `{Type_Part_Designation}` | BOM | Aluminum Angle - L Profile |
| `{Dimensions}` | BOM | 50x50x5mm x 6000mm |
| `{Material_Grade}` | BOM | 6061-T6 |
| `{Quantity}` | PO line item | 200 |
| `{Unit}` | PO line item | pcs |
| `{Price_List_Item_No}` | Price List match | AL-001 |
| `{Unit_Price}` | Price List | 28.50 |
| `{Testing_Fee}` | Price List | 15.00 |
| `{Cert_Fee}` | Price List | 25.00 |
| `{Discount_Rate}` | Price List rules | 5 |
| `{Tax_Rate}` | PO or default | 6 |

---

*Users can modify this template to customize the format of the calculation breakdown output.*
