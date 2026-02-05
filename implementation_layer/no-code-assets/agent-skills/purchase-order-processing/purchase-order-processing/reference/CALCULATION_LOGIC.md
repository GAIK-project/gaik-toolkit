# Calculation Logic Reference

This file defines the formulas and calculation steps for pricing. Customize this file to adapt the skill for your calculation requirements.

---

## Overview

The calculation follows this flow:

```
1. Line Item Calculations (per item)
   ↓
2. Order Subtotals (aggregate)
   ↓
3. Volume Discount (applied to material cost)
   ↓
4. Fees Aggregation
   ↓
5. Tax Calculation
   ↓
6. Grand Total
```

---

## Line Item Calculations

For EACH priced item, calculate the following:

### Material Cost
```
Material_Cost = Quantity × Unit_Price
```

**Variables:**
- `Quantity`: From PO line item
- `Unit_Price`: From Price List lookup

**Example:**
```
Material_Cost = 200 × $28.50 = $5,700.00
```

### Cutting Cost
```
Cutting_Cost = Cutting_Fee × Cuts_Per_Item
```

**Variables:**
- `Cutting_Fee`: From Price List
- `Cuts_Per_Item`: From BOM field `Cutting_Required` or default (0)

**Default:** `Cuts_Per_Item = 0` (no cutting)

**Source Priority:**
1. BOM field: `Cutting_Required` (if specified in BOM)
2. User parameter (if provided)
3. Default: 0

**Example:**
```
Cutting_Cost = $5.00 × 2 = $10.00
```

### Testing Cost
```
Testing_Cost = Testing_Fee × Lots_Per_Item
```

**Variables:**
- `Testing_Fee`: From Price List
- `Lots_Per_Item`: From BOM field `Testing_Lots_Required` or default (1)

**Default:** `Lots_Per_Item = 1` (one lot per material type)

**Source Priority:**
1. BOM field: `Testing_Lots_Required` (if specified in BOM)
2. User parameter (if provided)
3. Default: 1

**Example:**
```
Testing_Cost = $15.00 × 1 = $15.00
```

### Certification Cost
```
Cert_Cost = Cert_Fee × Certs_Per_Item
```

**Variables:**
- `Cert_Fee`: From Price List
- `Certs_Per_Item`: From BOM field `Certificates_Required` or default (1)

**Default:** `Certs_Per_Item = 1` (one certificate per material type)

**Source Priority:**
1. BOM field: `Certificates_Required` (if specified in BOM)
2. User parameter (if provided)
3. Default: 1

**Example:**
```
Cert_Cost = $25.00 × 1 = $25.00
```

### Line Total
```
Line_Total = Material_Cost + Cutting_Cost + Testing_Cost + Cert_Cost
```

**Example:**
```
Line_Total = $5,700.00 + $10.00 + $15.00 + $25.00 = $5,750.00
```

---

## Order-Level Calculations

### Subtotal (Material Cost Only)
```
Subtotal = Σ Material_Cost (for all items)
```

**Example:**
```
Item 1: $5,700.00
Item 2: $9,787.50
Item 3: $10,080.00
─────────────────
Subtotal = $25,567.50
```

### Volume Discount Calculation

**Step 1: Determine Discount Tier**
```
IF Subtotal < $5,000:
    Discount_Rate = 0%
ELSE IF Subtotal < $15,000:
    Discount_Rate = 3%
ELSE IF Subtotal < $30,000:
    Discount_Rate = 5%
ELSE IF Subtotal < $50,000:
    Discount_Rate = 7%
ELSE:
    Discount_Rate = 10%
```

**Step 2: Calculate Discount Amount**
```
Volume_Discount = Subtotal × Discount_Rate
```

**Step 3: Calculate Net Material Cost**
```
Net_Material_Cost = Subtotal - Volume_Discount
```

**Example:**
```
Subtotal = $25,567.50
Discount_Rate = 5% (tier $15,000-$30,000)
Volume_Discount = $25,567.50 × 0.05 = $1,278.38
Net_Material_Cost = $25,567.50 - $1,278.38 = $24,289.12
```

**IMPORTANT - OUTPUT FIELD:**
This is a REQUIRED field that MUST appear in the pricing summary output.
- **Label:** "Net Material Cost:"
- **Purpose:** Shows the material cost after applying volume discount
- **Display:** Always include this field between "Volume Discount" and "Total Testing/Cert Fees" in the pricing summary

---

## Fees Aggregation

### Total Cutting Fees
```
Total_Cutting_Fees = Σ Cutting_Cost (for all items)
```

### Total Testing Fees
```
Total_Testing_Fees = Σ Testing_Cost (for all items)
```

### Total Certification Fees
```
Total_Cert_Fees = Σ Cert_Cost (for all items)
```

### Combined Fees
```
Total_Fees = Total_Cutting_Fees + Total_Testing_Fees + Total_Cert_Fees
```

**Example:**
```
Total_Cutting_Fees = $30.00
Total_Testing_Fees = $45.00
Total_Cert_Fees = $75.00
─────────────────────────
Total_Fees = $150.00
```

---

## Shipping Calculation

### Option 1: From PO
```
Shipping = PO.PO_Shipping
```

### Option 2: Weight-Based
```
Total_Weight = Σ (Quantity × Weight_Per_Unit) for all items
Shipping = Total_Weight × Rate_Per_KG
```

### Option 3: Flat Rate
```
IF Subtotal < $5,000:
    Shipping = $150.00
ELSE IF Subtotal < $15,000:
    Shipping = $350.00
ELSE IF Subtotal < $30,000:
    Shipping = $550.00
ELSE:
    Shipping = [Custom quote required]
```

**Default:** Use PO shipping if provided, otherwise flat rate.

---

## Tax Calculation

### Taxable Amount
```
Taxable_Amount = Net_Material_Cost + Total_Fees + Shipping
```

**Note:** Tax is applied to the net material cost (after discount), all fees, and shipping.

### Tax Amount
```
Tax_Amount = Taxable_Amount × Tax_Rate
```

**Default Tax Rate:** 6%

**Example:**
```
Net_Material_Cost = $24,289.12
Total_Fees = $165.00
Shipping = $450.00
Taxable_Amount = $24,289.12 + $165.00 + $450.00 = $24,904.12
Tax_Rate = 6%
Tax_Amount = $24,904.12 × 0.06 = $1,494.25
```

---

## Grand Total

### Final Calculation
```
Grand_Total = Net_Material_Cost + Total_Fees + Shipping + Tax_Amount
```

**Example:**
```
Net_Material_Cost = $24,289.12
Total_Fees = $150.00
Shipping = $450.00
Tax_Amount = $1,466.35
────────────────────────
Grand_Total = $26,355.47
```

---

## Complete Calculation Example

### Input Data
```
PO Line Items:
1. MAT-2401: Aluminum Angle Bar, Qty: 200, Price List: $28.50
2. MAT-3567: Stainless Steel Sheet, Qty: 50, Price List: $195.75
3. MAT-4829: Steel Pipe Seamless, Qty: 150, Price List: $67.20

Fees (from Price List):
- Item 1: Cutting $5, Testing $15, Cert $25
- Item 2: Cutting $25, Testing $35, Cert $40
- Item 3: Cutting $8, Testing $20, Cert $30

Parameters:
- Cuts per item: 0 (no cutting)
- Lots per item: 1
- Certs per item: 1
- Tax Rate: 6%
- Shipping: $450.00 (from PO)
```

### Line Item Calculations
```
Item 1:
  Material_Cost = 200 × $28.50 = $5,700.00
  Cutting_Cost = $5.00 × 0 = $0.00
  Testing_Cost = $15.00 × 1 = $15.00
  Cert_Cost = $25.00 × 1 = $25.00
  Line_Total = $5,740.00

Item 2:
  Material_Cost = 50 × $195.75 = $9,787.50
  Cutting_Cost = $25.00 × 0 = $0.00
  Testing_Cost = $35.00 × 1 = $35.00
  Cert_Cost = $40.00 × 1 = $40.00
  Line_Total = $9,862.50

Item 3:
  Material_Cost = 150 × $67.20 = $10,080.00
  Cutting_Cost = $8.00 × 0 = $0.00
  Testing_Cost = $20.00 × 1 = $20.00
  Cert_Cost = $30.00 × 1 = $30.00
  Line_Total = $10,130.00
```

### Order Totals
```
Subtotal (Materials):
  $5,700.00 + $9,787.50 + $10,080.00 = $25,567.50

Volume Discount:
  Tier: $15,000 - $30,000 → 5%
  Discount = $25,567.50 × 5% = $1,278.38

Net Material Cost:
  $25,567.50 - $1,278.38 = $24,289.12

Total Fees:
  Cutting: $0.00
  Testing: $15.00 + $35.00 + $20.00 = $70.00
  Cert: $25.00 + $40.00 + $30.00 = $95.00
  Total Fees = $165.00

Taxable Amount:
  $24,289.12 + $165.00 = $24,454.12

Tax (6%):
  $24,454.12 × 0.06 = $1,467.25

Grand Total:
  $24,289.12 + $165.00 + $450.00 + $1,467.25 = $26,371.37
```

---

## Customization Guide

### To change discount application:

**Current:** Discount on material cost only
**Alternative:** Discount on everything including fees

```markdown
# Change this:
Volume_Discount = Subtotal × Discount_Rate

# To this:
Total_Before_Discount = Subtotal + Total_Fees
Volume_Discount = Total_Before_Discount × Discount_Rate
```

### To add new fee types:

1. Add new fee field in EXTRACTION_FIELDS.md
2. Add calculation formula here:
```markdown
### New Fee Cost
```
New_Fee_Cost = New_Fee × Quantity_Applicable
```
3. Include in Total_Fees calculation

### To change tax calculation base:

**To include shipping in tax:**
```markdown
Taxable_Amount = Net_Material_Cost + Total_Fees + Shipping
```

**To exclude fees from tax:**
```markdown
Taxable_Amount = Net_Material_Cost
```

### To add rounding rules:

```markdown
# Round to 2 decimal places
Material_Cost = ROUND(Quantity × Unit_Price, 2)
Tax_Amount = ROUND(Taxable_Amount × Tax_Rate, 2)
```

### To handle multiple currencies:

```markdown
# Add currency conversion step
IF PO.Currency ≠ "USD":
    Exchange_Rate = [Lookup current rate]
    Unit_Price_USD = Unit_Price × Exchange_Rate
```
