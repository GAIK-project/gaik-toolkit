# Complete Examples

Working examples for common GAIK toolkit use cases.

## Example 1: Invoice Extraction from PDF

Extract structured invoice data using VisionParser.

```python
"""Extract invoice data from PDF using VisionParser + Extractor."""
import json
from pathlib import Path
from gaik.building_blocks.parsers import VisionParser, get_openai_config
from gaik.building_blocks.extractor import SchemaGenerator, DataExtractor

# Configuration
config = get_openai_config(use_azure=True)

# Step 1: Parse PDF to markdown
parser = VisionParser(openai_config=config, use_context=True)
pages = parser.convert_pdf("invoice.pdf", dpi=150, clean_output=True)
document_text = "\n\n".join(pages)

# Step 2: Generate schema from requirements
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(
    user_requirements="""
    Extract the following from the invoice:
    - Invoice number (string, required)
    - Invoice date (date, required)
    - Vendor name (string, required)
    - Line items (list of items with description and amount)
    - Subtotal (decimal)
    - Tax (decimal)
    - Total amount (decimal, required)
    """
)

# Step 3: Extract structured data
extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements="Extract invoice information",
    documents=[document_text],
    save_json=True,
    json_path="invoice_results.json",
)

print(json.dumps(results, indent=2, default=str))
```

---

## Example 2: Medical Consultation Transcription

Transcribe and extract structured data from a medical consultation recording.

```python
"""Transcribe medical consultation and extract patient data."""
from gaik.software_components.audio_to_structured_data import AudioToStructuredData

pipeline = AudioToStructuredData(use_azure=True)

result = pipeline.run(
    file_path="consultation.mp3",
    user_requirements="""
    Extract from this medical consultation:
    - Patient name (string)
    - Date of birth (date)
    - Chief complaint (string)
    - Symptoms (list of strings)
    - Diagnosis (string)
    - Treatment plan (string)
    - Medications prescribed (list with name, dosage, frequency)
    - Follow-up date (date, if mentioned)
    """,
    transcriber_ctor={
        "enhanced_transcript": True,
        "output_dir": "medical_transcripts/",
    },
    transcribe_options={
        "custom_context": "Medical consultation between doctor and patient",
    },
    extract_options={
        "save_json": True,
        "json_path": "patient_record.json",
    },
)

# Access results
print("--- Transcript ---")
print(result.transcription.enhanced_transcript or result.transcription.raw_transcript)
print("\n--- Extracted Data ---")
for record in result.extracted_fields:
    print(record)
```

---

## Example 3: Document Classification

Classify documents in a folder into predefined categories.

```python
"""Classify documents into categories."""
from pathlib import Path
from gaik.building_blocks.doc_classifier import DocumentClassifier, get_openai_config

config = get_openai_config(use_azure=True)
classifier = DocumentClassifier(config=config)

# Define classification categories
categories = [
    "invoice",
    "receipt",
    "contract",
    "report",
    "letter",
    "form",
]

# Classify single file
single_result = classifier.classify(
    file_or_dir="document.pdf",
    classes=categories,
)
print(f"Single file: {single_result}")

# Classify entire directory
dir_results = classifier.classify(
    file_or_dir="documents/",
    classes=categories,
    parser="auto",  # Auto-select parser based on file type
)

# Group by classification
from collections import defaultdict
grouped = defaultdict(list)
for filename, classification in dir_results.items():
    grouped[classification["class"]].append({
        "file": filename,
        "confidence": classification["confidence"],
    })

for category, files in grouped.items():
    print(f"\n{category.upper()}:")
    for f in sorted(files, key=lambda x: -x["confidence"]):
        print(f"  - {f['file']} ({f['confidence']:.0%})")
```

---

## Example 4: Batch Invoice Processing with Schema Reuse

Process multiple invoices efficiently by reusing the schema.

```python
"""Process multiple invoices with schema reuse for efficiency."""
import json
from pathlib import Path
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(use_azure=True)
invoice_dir = Path("invoices/")
schema_dir = Path("schemas/")
schema_dir.mkdir(exist_ok=True)
output_dir = Path("extracted/")
output_dir.mkdir(exist_ok=True)

all_invoices = list(invoice_dir.glob("*.pdf"))
all_results = []

# Try to load existing schema
existing = pipeline.load_schema(schema_dir, "invoice")

if existing:
    print("Using existing schema")
    schema, requirements = existing
else:
    print("Generating new schema from first invoice")
    # Generate schema from first invoice
    first_result = pipeline.run(
        file_path=str(all_invoices[0]),
        user_requirements="""
        Extract: invoice_number, invoice_date, vendor_name, vendor_address,
        line_items (description, quantity, unit_price, amount), subtotal,
        tax_rate, tax_amount, total_amount, payment_terms, due_date
        """,
        parser_choice="vision_parser",
    )

    schema = first_result.schema
    requirements = first_result.requirements
    all_results.append({
        "file": all_invoices[0].name,
        "data": first_result.extracted_fields,
    })

    # Save schema for future use
    pipeline.save_schema(schema, requirements, schema_dir, "invoice")
    all_invoices = all_invoices[1:]  # Skip first, already processed

# Process remaining invoices with pre-built schema
for pdf_path in all_invoices:
    print(f"Processing: {pdf_path.name}")

    result = pipeline.run(
        file_path=str(pdf_path),
        user_requirements="",
        schema=schema,
        requirements=requirements,
        parser_choice="vision_parser",
    )

    all_results.append({
        "file": pdf_path.name,
        "data": result.extracted_fields,
    })

# Save combined results
with open(output_dir / "all_invoices.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)

print(f"\nProcessed {len(all_results)} invoices")
print(f"Results saved to {output_dir / 'all_invoices.json'}")
```

---

## Example 5: Meeting Notes Extraction

Transcribe a meeting and extract action items, decisions, and attendees.

```python
"""Extract structured meeting notes from audio recording."""
from gaik.software_components.audio_to_structured_data import AudioToStructuredData
import json

pipeline = AudioToStructuredData(use_azure=True)

result = pipeline.run(
    file_path="team_meeting.mp4",  # Works with video too
    user_requirements="""
    Extract from this meeting:
    - Meeting title or topic (string)
    - Date (date, if mentioned)
    - Attendees (list of names)
    - Agenda items discussed (list of strings)
    - Key decisions made (list of strings)
    - Action items (list with: description, assignee, due_date)
    - Next meeting date (date, if mentioned)
    - Open questions or parking lot items (list of strings)
    """,
    transcriber_ctor={
        "enhanced_transcript": True,
    },
    transcribe_options={
        "custom_context": "Business team meeting with multiple participants",
    },
)

# Save transcript
with open("meeting_transcript.txt", "w") as f:
    f.write(result.transcription.enhanced_transcript or result.transcription.raw_transcript)

# Save structured notes
with open("meeting_notes.json", "w") as f:
    json.dump(result.extracted_fields, f, indent=2, default=str)

# Pretty print action items
if result.extracted_fields:
    data = result.extracted_fields[0]
    print("\n=== ACTION ITEMS ===")
    for item in data.get("action_items", []):
        print(f"- [{item.get('assignee', 'TBD')}] {item.get('description')}")
        if item.get("due_date"):
            print(f"  Due: {item['due_date']}")
```

---

## Example 6: Custom Schema with Manual Field Definition

Define extraction schema manually without natural language generation.

```python
"""Use manually defined schema for precise control over extraction."""
from gaik.building_blocks.extractor import (
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
    get_openai_config,
)
from gaik.building_blocks.parsers import PyMuPDFParser

config = get_openai_config(use_azure=True)

# Define fields manually for precise control
fields = [
    FieldSpec(
        field_name="order_id",
        field_type="str",
        description="Order identifier, usually starts with ORD-",
        required=True,
        pattern=r"ORD-\d+",
    ),
    FieldSpec(
        field_name="customer_email",
        field_type="str",
        description="Customer email address",
        required=True,
    ),
    FieldSpec(
        field_name="order_date",
        field_type="date",
        description="Date the order was placed",
        required=True,
        format="%Y-%m-%d",
    ),
    FieldSpec(
        field_name="items",
        field_type="list",
        description="List of ordered items with SKU, name, quantity, price",
        required=True,
    ),
    FieldSpec(
        field_name="shipping_method",
        field_type="str",
        description="Shipping method selected",
        required=False,
        enum=["standard", "express", "overnight"],
    ),
    FieldSpec(
        field_name="total_amount",
        field_type="float",
        description="Total order amount in USD",
        required=True,
    ),
]

requirements = ExtractionRequirements(
    use_case_name="OrderExtraction",
    fields=fields,
)

# Create Pydantic model from requirements
from gaik.building_blocks.extractor.helpers import create_extraction_model
schema = create_extraction_model(requirements)

# Parse document
parser = PyMuPDFParser()
result = parser.parse_document("order_confirmation.pdf")
document_text = result["text_content"]

# Extract with manual schema
extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=requirements,
    user_requirements="Extract order details",
    documents=[document_text],
)

print(results)
```

---

## Example 7: FastAPI Integration

Basic FastAPI endpoint for document extraction.

```python
"""FastAPI endpoint for document extraction."""
from fastapi import FastAPI, UploadFile, HTTPException
from tempfile import NamedTemporaryFile
from pathlib import Path
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

app = FastAPI()
pipeline = DocumentsToStructuredData(use_azure=True)

@app.post("/extract")
async def extract_document(
    file: UploadFile,
    requirements: str,
    parser: str = "pymupdf",
):
    """Extract structured data from uploaded document."""
    # Validate file type
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".pdf", ".docx", ".png", ".jpg", ".jpeg"]:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    # Save to temp file
    content = await file.read()
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = pipeline.run(
            file_path=tmp_path,
            user_requirements=requirements,
            parser_choice=parser,
        )

        return {
            "filename": file.filename,
            "extracted": result.extracted_fields,
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)
```

---

## Tips

1. **Use schema persistence** for batch processing - generate once, reuse many times
2. **Choose the right parser**: `pymupdf` for simple PDFs, `vision_parser` for complex layouts
3. **Enable enhanced transcription** for better quality meeting notes
4. **Use custom_context** in transcription to improve accuracy for domain-specific terms
5. **Set `use_azure=True`** for production - Azure OpenAI typically has better rate limits
