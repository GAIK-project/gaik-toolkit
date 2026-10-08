# Extraction Fields Reference

This file defines which fields to extract from each document type. Customize this file to adapt the skill for your specific document formats.

---

## Purchase Order Fields

### PO Header Fields
Extract from the ORDER DETAILS section of the Purchase Order.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| PO_Number | ORDER DETAILS section | Yes | String | PO-2025-15903 |
| PO_Date | ORDER DETAILS section | Yes | Date | October 12, 2025 |
| Payment_Terms | ORDER DETAILS section | Yes | String | Net 30 |
| Shipping_Terms | ORDER DETAILS section | No | String | FOB Destination |
| Project_Code | ORDER DETAILS section | No | String | PRJ-AT-2025-Q4B |

### Customer Information Fields
Extract from the header/letterhead area.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| Customer_Name | Header/letterhead | Yes | String | AutoTech Manufacturing Corp. |
| Customer_Address | Header/letterhead | Yes | String | 2750 Industrial Parkway, Detroit, MI 48201 |
| Customer_Contact | Header or signature | No | String | Patricia Henderson |
| Customer_Phone | Header | No | String | +1 (313) 555-4200 |
| Customer_Email | Header | No | Email | purchasing@autotech-mfg.com |

### PO Line Item Fields
For EACH line item in the PO items table.

| Field | Column Header | Required | Type | Example |
|-------|---------------|----------|------|---------|
| Item_Number | ITEM | Yes | Integer | 1 |
| Material_Number | MATERIAL NUMBER | Yes | String | MAT-2401 |
| PO_Description | DESCRIPTION | Yes | String | Aluminum Angle Bar |
| Quantity | QUANTITY | Yes | Integer | 200 |
| Unit | UNIT | Yes | String | pcs |
| PO_Unit_Price | UNIT PRICE | No | Currency | $28.50 |
| Delivery_Date | DELIVERY DATE | Yes | Date | December 01, 2025 |
| PO_Line_Total | TOTAL | No | Currency | $5,700.00 |

**Note:** PO_Unit_Price and PO_Line_Total are for reference/validation only. DO NOT use these for sales order calculations.

### PO Summary Fields
Extract from the footer/totals section.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| PO_Subtotal | Footer | No | Currency | $25,567.50 |
| PO_Shipping | Footer | No | Currency | $450.00 |
| PO_Tax_Rate | Footer | No | Percentage | 6% |
| PO_Tax_Amount | Footer | No | Currency | $1,561.05 |
| PO_Total | Footer | No | Currency | $27,578.55 |

### Special Requirements Fields
Extract from special sections if present.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| Special_Instructions | Special Instructions section | No | Text | All materials must include mill test certificates |
| Documentation_Required | Technical Documentation section | No | Text | BOM for each Material Number |

---

## Bill of Materials (BOM) Fields

### BOM Header Fields
Extract from the BOM INFORMATION section.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| BOM_Revision | BOM INFORMATION | No | String | Rev 1.2 |
| BOM_Date | BOM INFORMATION | No | Date | October 10, 2025 |
| BOM_Status | BOM INFORMATION | No | String | Approved |

### Reference Information Fields
Extract from REFERENCE INFORMATION section.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| BOM_Customer_PO | REFERENCE INFORMATION | No | String | PO-2025-15903 |
| BOM_Project_Code | REFERENCE INFORMATION | No | String | PRJ-AT-2025-Q4B |
| BOM_Customer | REFERENCE INFORMATION | No | String | AutoTech Manufacturing Corp. |
| BOM_Prepared_By | REFERENCE INFORMATION | No | String | John Smith |

### Material Identification Fields (CRITICAL)
These fields are essential for matching and pricing.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| BOM_ID | MATERIAL IDENTIFICATION → ID | **Yes** | String | MAT-2401 |
| Type_Part_Designation | MATERIAL IDENTIFICATION → TYPE/PART DESIGNATION | **Yes** | String | Aluminum Angle - L Profile |
| Dimensions | MATERIAL IDENTIFICATION → DIMENSIONS | **Yes** | String | 50 x 50 x 5 mm x 6000 mm |
| Material_Grade | MATERIAL IDENTIFICATION → MATERIAL GRADE | No | String | 6061-T6 |

**CRITICAL:**
- `BOM_ID` must match `Material_Number` from the PO for matching
- `Type_Part_Designation` is used for price list lookup

### Technical Specification Fields
Extract from TECHNICAL SPECIFICATIONS table.

| Field | Source Location | Required | Type | Example |
|-------|-----------------|----------|------|---------|
| Material_Standard | TECHNICAL SPECIFICATIONS | No | String | ASTM B221 |
| Surface_Finish | TECHNICAL SPECIFICATIONS | No | String | Mill finish |
| Length | TECHNICAL SPECIFICATIONS | No | String | 6000 mm |
| Weight_Per_Unit | TECHNICAL SPECIFICATIONS | No | String | 1.33 kg/m |
| Testing_Required | TECHNICAL SPECIFICATIONS | No | String | Material certificate, dimensional inspection |
| Thickness_Tolerance | TECHNICAL SPECIFICATIONS | No | String | ±0.3 mm |
| Length_Tolerance | TECHNICAL SPECIFICATIONS | No | String | +10 mm / -0 mm |

### Fee Calculation Fields (NEW)
Extract from TECHNICAL SPECIFICATIONS or REQUIREMENTS section. These fields determine which fees should be applied in calculations.

| Field | Source Location | Required | Type | Example | Usage |
|-------|-----------------|----------|------|---------|-------|
| Cutting_Required | TECHNICAL SPECIFICATIONS / REQUIREMENTS | No | Integer | 2 | Number of cuts needed (0 = no cutting, used for Cutting_Cost calculation) |
| Testing_Lots_Required | TECHNICAL SPECIFICATIONS / REQUIREMENTS | No | Integer | 1 | Number of test lots required (default: 1, used for Testing_Cost calculation) |
| Certificates_Required | TECHNICAL SPECIFICATIONS / REQUIREMENTS | No | Integer | 1 | Number of certificates required (default: 1, used for Cert_Cost calculation) |

**Calculation Impact:**
- `Cutting_Cost = Cutting_Fee × Cutting_Required` (default: 0 cuts)
- `Testing_Cost = Testing_Fee × Testing_Lots_Required` (default: 1 lot)
- `Cert_Cost = Cert_Fee × Certificates_Required` (default: 1 certificate)

**Alternative Field Names:** These fields may also appear as:
- "Cuts Needed", "Number of Cuts", "Cutting: Yes/No"
- "Test Lots", "Testing Quantity", "Testing: Required"
- "Certificates Needed", "Cert Quantity", "Certificate: Required"

---

## Price List Fields

### Product Catalog Fields
Extract from the price list Excel/CSV file.

| Field | Column Header | Required | Type | Example |
|-------|---------------|----------|------|---------|
| Item_No | Item No. | No | String | AL-001 |
| PL_Type_Part_Designation | Type/Part Designation | **Yes** | String | Aluminum Angle - L Profile |
| PL_Material_Grade | Material Grade | No | String | 6061-T6 |
| Standard_Unit | Standard Unit | No | String | 6m length |
| Unit_Price | Unit Price | **Yes** | Currency | $28.50 |
| Min_Order_Qty | Min Order Qty | No | Integer | 50 |
| Cutting_Fee | Cutting Fee | No | Currency | $5.00 |
| Testing_Fee | Testing Fee | No | Currency | $15.00 |
| Cert_Fee | Cert Fee | No | Currency | $25.00 |
| Lead_Time_Days | Lead Time (Days) | No | Integer | 7 |

---

## Customization Guide

### To adapt for your documents:

1. **Add/Remove Fields**
   - Add new rows for fields specific to your document format
   - Remove rows for fields that don't apply
   - Mark new required fields appropriately

2. **Update Source Locations**
   - Change "Source Location" to match your document's section names
   - Use exact text that appears in your documents

3. **Modify Field Names**
   - Keep internal field names consistent for the skill to work
   - Change "Column Header" to match your document's actual headers

4. **Adjust Data Types**
   - String: Text values
   - Integer: Whole numbers
   - Currency: Money values (with or without $ symbol)
   - Date: Date values (specify expected format)
   - Percentage: Percentage values (with or without % symbol)
   - Email: Email addresses

### Example: Adding a Custom Field

If your PO has a "Buyer Code" field:

```markdown
| Buyer_Code | ORDER DETAILS section | No | String | BC-2025-001 |
```

### Example: Different Column Names

If your PO uses "PART NO." instead of "MATERIAL NUMBER":

```markdown
| Material_Number | PART NO. | Yes | String | MAT-2401 |
```

The skill will look for "PART NO." column but store it as Material_Number internally.

---

## Sample Order Format Fields (Optional)

When `sample_sales_order/sample_order.docx` exists, extract these format specifications:

### Pricing Summary Format
| Field | Extract From Sample | Required | Purpose |
|-------|---------------------|----------|---------|
| Field_Labels | Pricing summary section | Yes | Exact label text to use |
| Field_Order | Pricing summary section | Yes | Sequence of fields top to bottom |
| Currency_Format | All price fields | Yes | $ placement, commas, decimals |
| Punctuation | Field labels | Yes | Colons, parentheses, hyphens |
| Alignment | Table structure | Yes | Left/right alignment |

**Extraction Method:**
1. Read sample_order.docx using DOCX skill
2. Locate "PRICING SUMMARY" or equivalent section
3. Extract each field label verbatim (including punctuation)
4. Note field order (preserve exactly)
5. Observe currency formatting pattern (dollar signs, commas, decimals)
6. Use as template for output generation

**Required Fields to Extract:**
- Material Subtotal
- Volume Discount (with percentage in parentheses)
- Net Material Cost
- Total Testing/Cert Fees
- Shipping
- Tax (with percentage in parentheses)
- TOTAL

**Format Specifications to Preserve:**
- Label capitalization (e.g., "Material Subtotal" not "material subtotal")
- Colon placement after field labels
- Percentage notation in parentheses: (5%), (6%)
- Currency alignment (right-aligned values)
- Separator lines between sections
