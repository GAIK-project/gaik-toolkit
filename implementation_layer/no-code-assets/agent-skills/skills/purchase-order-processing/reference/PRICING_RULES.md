# Pricing Rules Reference

This file defines pricing rules, discount tiers, and fee structures. Customize this file to adapt the skill for your pricing model.

---

## Price List Column Mapping

Map your price list columns to the expected fields.

| Internal Field | Your Column Name | Description | Example Value |
|----------------|------------------|-------------|---------------|
| Item_No | Item No. | Internal catalog/SKU number | AL-001 |
| PL_Type_Part_Designation | Type/Part Designation | **KEY** - Used to match with BOM | Aluminum Angle - L Profile |
| PL_Material_Grade | Material Grade | Material specification | 6061-T6 |
| Standard_Unit | Standard Unit | Unit basis for pricing | 6m length |
| Unit_Price | Unit Price | Base price per unit | $28.50 |
| Min_Order_Qty | Min Order Qty | Minimum order quantity | 50 |
| Cutting_Fee | Cutting Fee | Fee per cut | $5.00 |
| Testing_Fee | Testing Fee | Testing/inspection fee per lot | $15.00 |
| Cert_Fee | Cert Fee | Certification fee per certificate | $25.00 |
| Lead_Time_Days | Lead Time (Days) | Standard delivery time | 7 |

---

## Price Matching Logic

### Primary Matching Rule
Match price list items using Type/Part Designation:

```
MATCH WHERE:
    PL_Type_Part_Designation CONTAINS BOM.Type_Part_Designation
    OR
    BOM.Type_Part_Designation CONTAINS PL_Type_Part_Designation
```

### Secondary Matching (if primary fails)
Try matching with Material Grade:

```
MATCH WHERE:
    PL_Type_Part_Designation SIMILAR TO BOM.Type_Part_Designation
    AND
    PL_Material_Grade = BOM.Material_Grade
```

### Match Not Found
If no price match is found:
- Flag the item with "PRICE NOT FOUND"
- Include in output with Unit_Price = "TBD"
- Add to manual review list

---

## Volume Discount Tiers

Discounts applied to material subtotal (sum of all Material_Cost before fees).

| Tier | Min Amount | Max Amount | Discount Rate | Notes |
|------|------------|------------|---------------|-------|
| 1 | $0 | $4,999.99 | 0% | Standard pricing |
| 2 | $5,000 | $14,999.99 | 3% | Small volume discount |
| 3 | $15,000 | $29,999.99 | 5% | Medium volume discount |
| 4 | $30,000 | $49,999.99 | 7% | Large volume discount |
| 5 | $50,000+ | - | 10% | Enterprise discount |

### Discount Application Rules
- Discount applies to **Material Cost only** (not fees, shipping, or tax)
- Discount is calculated on the subtotal before any fees
- Only one tier applies (no stacking)

### Custom Discount Override
If a customer has negotiated special pricing:
- Check if customer has a custom discount rate
- Override tier-based discount if custom rate is higher
- Note: Custom rates should be specified by user if applicable

---

## Fee Structure

### Cutting Fees
Applied when items require custom cutting.

| Material Category | Base Fee per Cut | Notes |
|-------------------|------------------|-------|
| Aluminum Products | $4.50 - $6.00 | Varies by profile complexity |
| Stainless Steel Products | $8.00 - $25.00 | Higher for sheets and plates |
| Carbon Steel Products | $6.00 - $35.00 | Plates have highest fees |
| Structural Steel | $8.00 - $45.00 | H-beams require special equipment |

**Cutting Fee Calculation:**
```
Cutting_Cost = Cutting_Fee × Number_of_Cuts
```

Default: `Number_of_Cuts = 0` (no cutting unless specified)

### Testing Fees
Applied for quality testing and inspection.

| Material Category | Testing Fee per Lot | Notes |
|-------------------|---------------------|-------|
| Aluminum Products | $15.00 | Standard dimensional + material check |
| Stainless Steel Products | $35.00 | Includes chemical analysis |
| Carbon Steel Products | $20.00 - $25.00 | Includes hydrostatic for pipes |
| Structural Steel | $25.00 - $30.00 | Load testing available |

**Testing Fee Calculation:**
```
Testing_Cost = Testing_Fee × Number_of_Lots
```

Default: `Number_of_Lots = 1` per material type

### Certification Fees
Applied for mill test certificates and compliance documentation.

| Material Category | Cert Fee | Documentation Provided |
|-------------------|----------|------------------------|
| Aluminum Products | $25.00 | MTC 3.1 |
| Stainless Steel Products | $40.00 | MTC 3.1 + Chemical Analysis |
| Carbon Steel Products | $30.00 | MTC 3.1 |
| Structural Steel | $35.00 | MTC 3.1 + Mill Certificate |

**Certification Fee Calculation:**
```
Cert_Cost = Cert_Fee × Number_of_Certs
```

Default: `Number_of_Certs = 1` per material type

---

## Tax Rules

### Default Tax Rate
```
Tax_Rate = 6%
```

### Tax Calculation Base
Tax is applied to:
- Net Material Cost (after discount)
- Total Fees (cutting + testing + certification)
- Shipping

### Tax Formula
```
Taxable_Amount = Net_Material_Cost + Total_Fees + Shipping
Tax_Amount = Taxable_Amount × Tax_Rate
```

### Tax Override
If PO specifies a different tax rate:
- Use PO's tax rate
- Note the override in the sales order

If tax-exempt:
- Set Tax_Rate = 0%
- Add note: "Tax Exempt - [Reason]"

---

## Shipping Rules

### Shipping Calculation Options

**Option 1: Use PO Shipping (Default)**
```
Shipping = PO.PO_Shipping (if provided)
```

**Option 2: Weight-Based Calculation**
```
Total_Weight = Σ (Quantity × Weight_Per_Unit)
Shipping = Total_Weight × Shipping_Rate_Per_KG
```

**Option 3: Flat Rate by Order Size**
| Order Total | Shipping Rate |
|-------------|---------------|
| < $5,000 | $150.00 |
| $5,000 - $15,000 | $350.00 |
| $15,000 - $30,000 | $550.00 |
| > $30,000 | Custom quote |

### Shipping Terms Impact
- **FOB Origin**: Buyer pays shipping, calculated at their expense
- **FOB Destination**: Seller pays shipping, included in total

---

## Additional Services & Surcharges

### Rush Processing
| Service Level | Surcharge | Lead Time |
|---------------|-----------|-----------|
| Standard | 0% | As per price list |
| Rush (< 5 days) | +25% | 3-5 days |
| Same-Day | +50% | Same day |

### Packaging Options
| Package Type | Fee | Description |
|--------------|-----|-------------|
| Standard | $25.00/pallet | Shrink-wrapped pallet |
| Export Grade | $75.00/crate | Wooden crate with moisture barrier |
| Custom | Quote | Special packaging requirements |

---

## Customization Guide

### To modify discount tiers:

1. Edit the "Volume Discount Tiers" table
2. Adjust Min/Max amounts for your pricing model
3. Update discount percentages
4. Add or remove tiers as needed

**Example: Simpler tier structure**
```markdown
| Tier | Min Amount | Max Amount | Discount Rate |
|------|------------|------------|---------------|
| 1 | $0 | $9,999.99 | 0% |
| 2 | $10,000+ | - | 5% |
```

### To modify fee structure:

1. Update the fee tables with your rates
2. Adjust material categories if different
3. Change default values for cuts/lots/certs

**Example: No certification fees**
```markdown
Cert_Fee = $0 (not applicable)
```

### To change tax rules:

1. Update default tax rate
2. Modify taxable items list
3. Add jurisdiction-specific rules if needed

**Example: Different tax rate**
```markdown
Tax_Rate = 8.25% (Texas state + local)
```

### To adjust shipping:

1. Choose calculation method
2. Update rate tables
3. Modify shipping terms logic
