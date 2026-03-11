# Luvata Order Processing Demo - Implementation Plan

## Overview

Add a Luvata order processing demo to the GAIK toolkit demo app, showcasing ABB's purchase order workflow with BOM matching and automated pricing calculations.

---

## 1. Demo Scope & Objectives

### Goal
Create a simplified, demo-focused version of the Luvata ABB order processing workflow that showcases the GAIK toolkit's extraction capabilities.

### What to Include
- Upload: Purchase Order PDF, multiple BOM PDFs, Pricing CSV/Excel
- Process: Extract data from all documents, match BOMs to PO items, calculate prices
- Display: Show extracted items with calculated prices in a clean table format
- Export: Generate PDF order draft (same format as main app)

### What to Exclude (vs. main app)
- Manual field editing
- Multiple vendor support (ABB only)
- IndexedDB persistence/history
- Custom pricing row management
- Pricing overrides UI
- Advanced filtering/sorting

---

## 2. Technical Architecture

### Backend (FastAPI)

**New Router:** `api/routers/luvata_order.py`

```python
# Endpoints:
POST /luvata-order/process    # Process PO + BOMs + Pricing
GET  /luvata-order/pdf/{job_id}  # Download generated PDF
```

**Key Dependencies (reuse GAIK components):**
- `gaik.Extractor` - Extract structured data from PO and BOMs
- `gaik.SchemaGenerator` - Generate Pydantic schemas for extraction
- `gaik.Parser` (PyMuPDF/Vision) - Parse PDF documents
- CSV/Excel parsing - Read pricing table

**Data Flow:**
```
1. Parse PO PDF → Extract: po_number, customer, delivery_date, items[]
2. Parse each BOM PDF → Extract: document_id, type_designation, length_mm, weight_per_m
3. Parse Pricing CSV → Load: type_designation → pricing formula components
4. Match: PO item.material → BOM.document_id → Pricing.type_designation
5. Calculate: Per-item pricing using ABB formula
6. Generate: PDF order draft
```

### Frontend (Next.js)

**New Demo Page:** `app/(demos)/luvata-order/page.tsx`

**Component Structure:**
```tsx
LuvataOrderDemo/
├── UploadSection
│   ├── PurchaseOrderUpload (single PDF)
│   ├── BomUpload (multiple PDFs)
│   └── PricingUpload (CSV/Excel)
├── ProcessButton (triggers API call)
├── ProgressDisplay (SSE streaming status)
└── ResultsDisplay
    ├── ItemsTable (material, description, quantity, kg, price)
    ├── SummaryCard (total items, total kg, total EUR)
    └── DownloadPDFButton
```

---

## 3. Implementation Steps

### Phase 1: Backend API (FastAPI)

#### Step 1.1: Create ABB extraction schemas

```python
# api/routers/luvata_order.py - Pydantic models
class POItem(BaseModel):
    material: str
    description: str
    quantity: int
    delivery_date: str | None

class PurchaseOrder(BaseModel):
    po_number: str
    customer: str
    items: list[POItem]

class BOMData(BaseModel):
    document_id: str
    type_designation: str
    length_mm: float
    weight_per_m: float

class PricingRow(BaseModel):
    type_designation: str
    conversion: float
    packing: float
    machining: float
    energy_surcharge: float
    copper_price: float
```

#### Step 1.2: Implement extraction logic

```python
async def process_luvata_order(
    po_file: UploadFile,
    bom_files: list[UploadFile],
    pricing_file: UploadFile
) -> dict:
    # 1. Extract PO using GAIK Extractor
    po_schema = generate_po_schema()  # Using SchemaGenerator
    po_data = await extract_from_pdf(po_file, po_schema)

    # 2. Extract each BOM
    boms = []
    for bom_file in bom_files:
        bom_schema = generate_bom_schema()
        bom_data = await extract_from_pdf(bom_file, bom_schema)
        boms.append(bom_data)

    # 3. Parse pricing table (CSV/Excel)
    pricing_data = parse_pricing_table(pricing_file)

    # 4. Enrich products (match + calculate)
    enriched_items = enrich_abb_products(
        po_data.items,
        boms,
        pricing_data
    )

    return {
        "po_number": po_data.po_number,
        "customer": po_data.customer,
        "items": enriched_items,
        "totals": calculate_totals(enriched_items)
    }
```

#### Step 1.3: Add pricing calculation (ABB formula)

```python
def calculate_abb_pricing(item, bom, pricing_row):
    """
    ABB Pricing Formula:
    kg_per_pc = weight_per_m × (length_mm / 1000)
    total_kg = kg_per_pc × quantity
    margin = conversion + packing + machining + energy
    total_price = margin + copper_price
    line_total = total_kg × total_price
    """
    kg_per_pc = pricing_row.weight_per_m * (bom.length_mm / 1000)
    total_kg = kg_per_pc * item.quantity
    margin = (pricing_row.conversion + pricing_row.packing +
              pricing_row.machining + pricing_row.energy_surcharge)
    total_price = margin + pricing_row.copper_price
    line_total = total_kg * total_price

    return {
        "material": item.material,
        "description": item.description,
        "quantity": item.quantity,
        "kg_per_pc": round(kg_per_pc, 3),
        "total_kg": round(total_kg, 2),
        "price_per_kg": round(total_price, 4),
        "line_total": round(line_total, 2)
    }
```

#### Step 1.4: Add PDF generation

```python
from fpdf2 import FPDF  # Reuse existing PDF generator pattern

def generate_abb_pdf(order_data: dict) -> bytes:
    """Generate PDF order draft matching Luvata format"""
    pdf = FPDF()
    pdf.add_page()
    # Header with PO number, customer
    # Table with items
    # Footer with totals
    return pdf.output(dest='S').encode('latin1')
```

---

### Phase 2: Frontend Demo Page

#### Step 2.1: Create demo page structure

```tsx
// app/(demos)/luvata-order/page.tsx
export default function LuvataOrderDemo() {
  const [poFile, setPoFile] = useState<File | null>(null);
  const [bomFiles, setBomFiles] = useState<File[]>([]);
  const [pricingFile, setPricingFile] = useState<File | null>(null);
  const [result, setResult] = useState<OrderResult | null>(null);
  const [processing, setProcessing] = useState(false);

  const handleProcess = async () => {
    const formData = new FormData();
    formData.append('po_file', poFile);
    bomFiles.forEach(f => formData.append('bom_files', f));
    formData.append('pricing_file', pricingFile);

    // Stream SSE events (similar to other demos)
    const response = await fetch('/api/luvata-order/process', {
      method: 'POST',
      body: formData
    });

    // Handle streaming...
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <Header />
      <UploadSection />
      <ProcessButton />
      {processing && <ProgressDisplay />}
      {result && <ResultsDisplay data={result} />}
    </div>
  );
}
```

#### Step 2.2: Create upload components

```tsx
// Reuse existing file upload patterns from other demos
<FileUpload
  label="Purchase Order PDF"
  accept=".pdf"
  onChange={setPoFile}
  maxFiles={1}
/>

<FileUpload
  label="BOM PDFs"
  accept=".pdf"
  onChange={setBomFiles}
  maxFiles={10}
  multiple
/>

<FileUpload
  label="Pricing Table (CSV/Excel)"
  accept=".csv,.xlsx"
  onChange={setPricingFile}
  maxFiles={1}
/>
```

#### Step 2.3: Create results table

```tsx
// Similar to extraction demo results table
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Material</TableHead>
      <TableHead>Description</TableHead>
      <TableHead>Qty</TableHead>
      <TableHead>kg/pc</TableHead>
      <TableHead>Total kg</TableHead>
      <TableHead>Price/kg (EUR)</TableHead>
      <TableHead>Total (EUR)</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {result.items.map(item => (
      <TableRow key={item.material}>
        <TableCell>{item.material}</TableCell>
        <TableCell>{item.description}</TableCell>
        <TableCell>{item.quantity}</TableCell>
        <TableCell>{item.kg_per_pc}</TableCell>
        <TableCell>{item.total_kg}</TableCell>
        <TableCell>{item.price_per_kg}</TableCell>
        <TableCell>{item.line_total}</TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

---

### Phase 3: Demo Data Setup

#### Step 3.1: Copy ABB example data to demo app

```bash
# From Luvata app to toolkit_demo_app
toolkit_demo_app/data/luvata-order/
├── PO_4512560923.pdf
├── bom/
│   ├── 3AFP201773229A-BOM.pdf
│   ├── 3AFP201773267A-BOM.pdf
│   └── 3AFP201773305A-BOM.pdf
└── abb-pricing-table-clean.csv
```

Source files: `C:\Users\h02317\Tools and apps\Luvata\data\abb\examples\example-1\`

#### Step 3.2: Add "Load Example" button

```tsx
<Button onClick={loadExampleData}>
  Load ABB Example
</Button>

// Loads the 3 example files automatically
```

---

### Phase 4: Integration & Polish

#### Step 4.1: Add to demos navigation

```typescript
// Add to app/(demos) navigation or meta.json
{
  "title": "Luvata Order Processing",
  "description": "Process purchase orders with BOMs and pricing",
  "path": "/luvata-order"
}
```

#### Step 4.2: Add SSE streaming for progress

```python
# Similar to RAG demo streaming pattern
async def process_with_progress(files):
    yield sse_event("status", {"message": "Parsing purchase order..."})
    po_data = await extract_po(files.po)

    yield sse_event("status", {"message": "Extracting BOMs..."})
    boms = await extract_boms(files.boms)

    yield sse_event("status", {"message": "Calculating prices..."})
    enriched = enrich_products(po_data, boms, pricing)

    yield sse_event("complete", {"result": enriched})
```

#### Step 4.3: Error handling

```python
# Validate files before processing
if not po_file:
    raise HTTPException(400, "Purchase order required")
if len(bom_files) == 0:
    raise HTTPException(400, "At least one BOM required")
if not pricing_file:
    raise HTTPException(400, "Pricing table required")
```

---

## 4. File Checklist

### New Files to Create

**Backend:**
- [ ] `api/routers/luvata_order.py` (~300 lines)
- [ ] `api/utils/luvata_pricing.py` (~150 lines - pricing calculations)
- [ ] `data/luvata-order/` (example files directory)

**Frontend:**
- [ ] `app/(demos)/luvata-order/page.tsx` (~200 lines)
- [ ] `app/(demos)/luvata-order/components/upload-section.tsx` (~100 lines)
- [ ] `app/(demos)/luvata-order/components/results-table.tsx` (~150 lines)
- [ ] `lib/types/luvata.ts` (~50 lines - TypeScript types)

---

## 5. Testing Strategy

### Unit Tests (Python)
- Test extraction schemas
- Test pricing calculations
- Test BOM matching logic

### Integration Test
- Upload example files → verify correct extraction → verify pricing

### Manual Testing
- Load example → process → verify table display → download PDF

---

## 6. Key Differences from Main App

| Feature | Main App | Demo App |
|---------|----------|----------|
| Vendors | 3 (ABB, MC, C&B) | 1 (ABB only) |
| Manual Edits | Full editing | View only |
| Persistence | IndexedDB | Session only |
| History | Save/load | None |
| Pricing Overrides | Custom pricing | Auto only |
| File Management | Complex caching | Simple upload |

---

## 7. Estimated Effort

- Backend API: **4-6 hours**
- Frontend Components: **4-6 hours**
- PDF Generation: **2-3 hours**
- Data Setup & Testing: **2-3 hours**
- **Total: 12-18 hours**

---

## 8. Success Criteria

- [ ] User can upload PO + BOMs + Pricing
- [ ] System extracts and matches data automatically
- [ ] Table displays all items with calculated prices
- [ ] PDF generation matches Luvata format
- [ ] SSE progress updates work smoothly
- [ ] Error handling for missing/invalid files
- [ ] Example data loads instantly

---

## 9. ABB Workflow Reference

### BOM Matching Logic

| PO Material   | BOM Doc ID     | Match |
| ------------- | -------------- | ----- |
| 3AFP201773229 | 3AFP201773229A | ✓     |
| 3AFP201773267 | 3AFP201773267B | ✓     |

**Type Designation Matching:**

| BOM Type            | Pricing Type | Normalized  | Match |
| ------------------- | ------------ | ----------- | ----- |
| BKMJ 50X10/7,00     | BKMJ 50X10/7 | bkmj50x10/7 | ✓     |
| BKMJ (BKMF) 50X10/7 | BKMJ 50X10/7 | bkmj50x10/7 | ✓     |

### Pricing Formula

```
kg_per_pc   = weight_per_meter × (length_mm / 1000)
total_kg    = kg_per_pc × pcs
margin      = conversion + packing + machining + energy_surcharge  (EUR/kg)
metal_price = copper column from pricing Excel                     (EUR/kg)
small_qty   = 350/total_kg (≤300kg) | 250/total_kg (301-500kg) | 0
total_price = margin + metal_price + small_qty_fee                 (EUR/kg)
line_total  = total_kg × total_price                               (EUR)
```

### Rounding Rules

| Value        | Decimals |
| ------------ | -------- |
| kg_per_pc    | 3        |
| total_kg     | 2        |
| margin       | 3        |
| total_price  | 4        |
| line_total   | 5        |
| price_per_pc | 4        |

---

## References

- **Luvata Main App:** `C:\Users\h02317\Tools and apps\Luvata\`
- **Demo App Location:** `c:\Users\h02317\gaik-toolkit\implementation_layer\toolkit_demo_app\`
- **Example Data:** `C:\Users\h02317\Tools and apps\Luvata\data\abb\examples\example-1\`
- **Luvata README:** Contains full vendor documentation and pricing formulas
