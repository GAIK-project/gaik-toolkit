# Software Components Reference

End-to-end pipelines that compose building blocks into workflows.

**Source:** `gaik.software_components.*`

## AudioToStructuredData

Complete audio extraction pipeline: Audio -> Transcript -> Schema -> Structured JSON

**Source:** `gaik.software_components.audio_to_structured_data`

### Constructor

```python
from gaik.software_components.audio_to_structured_data import AudioToStructuredData

pipeline = AudioToStructuredData(
    api_config=None,       # Optional: pass config dict
    use_azure=True,        # Use Azure (True) or OpenAI (False)
)
```

### run() Method

```python
result = pipeline.run(
    file_path: str,                    # Audio/video file path
    user_requirements: str,            # Natural language field requirements

    # Optional: Transcriber configuration
    transcriber_ctor={                 # Constructor args for Transcriber
        "enhanced_transcript": True,
        "compress_audio": True,
        "output_dir": "workspace/",
    },
    transcribe_options={               # Call-time args for transcription
        "custom_context": "Medical consultation",
    },

    # Optional: Extractor configuration
    extractor_ctor={},                 # Constructor args for DataExtractor
    extract_options={                  # Call-time args for extraction
        "save_json": True,
        "json_path": "output.json",
    },

    # Optional: Reuse existing schema
    schema=None,                       # Pre-generated Pydantic model
    requirements=None,                 # Pre-generated ExtractionRequirements
)
```

### PipelineResult

```python
@dataclass
class PipelineResult:
    transcription: TranscriptionResult   # raw_transcript, enhanced_transcript
    extracted_fields: List[dict]         # Extracted data records
    schema: Type[BaseModel]              # Generated Pydantic model
    requirements: ExtractionRequirements # Field specifications
```

### Workflow

```
Audio File
    |
    v
Transcriber (Whisper + optional GPT enhancement)
    |
    v
Transcript Text
    |
    v
SchemaGenerator (if no schema provided)
    |
    v
Pydantic Model
    |
    v
DataExtractor
    |
    v
Structured JSON Records
```

---

## DocumentsToStructuredData

Complete document extraction pipeline: PDF/Image/DOCX -> Parsed Text -> Schema -> Structured JSON

**Source:** `gaik.software_components.documents_to_structured_data`

### Constructor

```python
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(
    api_config=None,       # Optional: pass config dict
    use_azure=True,        # Use Azure (True) or OpenAI (False)
)
```

### run() Method

```python
result = pipeline.run(
    file_path: str,                    # Document file path
    user_requirements: str,            # Natural language field requirements

    # Parser selection
    parser_choice: str = "vision_parser",  # Parser to use

    # Optional: Parser configuration
    parser_ctor={                      # Constructor args for parser
        "use_context": True,           # VisionParser: multi-page context
        "max_tokens": 16000,           # VisionParser: max output
    },
    parse_options={                    # Call-time args for parsing
        "dpi": 150,                    # VisionParser: image resolution
        "clean_output": True,
    },

    # Optional: Extractor configuration
    extractor_ctor={},
    extract_options={
        "save_json": True,
        "json_path": "output.json",
    },

    # Optional: Reuse existing schema
    schema=None,
    requirements=None,
)
```

### Parser Choices

| Value | Parser | Use Case |
|-------|--------|----------|
| `vision_parser` | VisionParser | Complex layouts, tables, LLM-based |
| `docling` | DoclingParser | OCR, multi-format, requires GPU |
| `pymupdf` | PyMuPDFParser | Fast local PDF extraction |
| `docx` | DocxParser | Word documents |

### Workflow

```
Document (PDF/Image/DOCX)
    |
    v
Parser (vision_parser/docling/pymupdf/docx)
    |
    v
Parsed Text/Markdown
    |
    v
SchemaGenerator (if no schema provided)
    |
    v
Pydantic Model
    |
    v
DataExtractor
    |
    v
Structured JSON Records
```

---

## Schema Persistence

Both pipelines support saving and loading schemas for reuse.

### Saving Schema

```python
from pathlib import Path

result = pipeline.run(file_path, user_requirements)

# Save schema and requirements
if result.schema and result.requirements:
    pipeline.save_schema(
        schema=result.schema,
        requirements=result.requirements,
        directory=Path("schemas/"),
        name="invoice",
    )
```

**Creates files:**
- `schemas/invoice_schema.json` - Pydantic model definition
- `schemas/invoice_requirements.json` - ExtractionRequirements

### Loading Schema

```python
existing = pipeline.load_schema(
    directory=Path("schemas/"),
    name="invoice",
)

if existing:
    schema, requirements = existing

    # Run with pre-existing schema (faster, no schema generation)
    result = pipeline.run(
        file_path="new_invoice.pdf",
        user_requirements="",  # Not needed when schema provided
        schema=schema,
        requirements=requirements,
    )
```

---

## Common Patterns

### Batch Processing with Schema Reuse

```python
from pathlib import Path
from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

pipeline = DocumentsToStructuredData(use_azure=True)
schema_dir = Path("schemas/")
all_results = []

# First document: generate schema
first_result = pipeline.run(
    file_path="invoices/invoice_001.pdf",
    user_requirements="Extract invoice number, date, vendor, line items, total",
    parser_choice="vision_parser",
)

# Save schema for reuse
pipeline.save_schema(
    first_result.schema,
    first_result.requirements,
    schema_dir,
    "invoice",
)
all_results.append(first_result.extracted_fields)

# Load schema for remaining documents
schema, requirements = pipeline.load_schema(schema_dir, "invoice")

# Process remaining invoices with pre-built schema
for pdf in Path("invoices/").glob("invoice_*.pdf"):
    if pdf.name == "invoice_001.pdf":
        continue

    result = pipeline.run(
        file_path=str(pdf),
        user_requirements="",
        schema=schema,
        requirements=requirements,
        parser_choice="vision_parser",
    )
    all_results.append(result.extracted_fields)
```

### Custom Schema Definition

```python
from gaik.building_blocks.extractor import ExtractionRequirements, FieldSpec
from pydantic import create_model

# Define fields manually
fields = [
    FieldSpec(field_name="patient_name", field_type="str", description="Patient full name", required=True),
    FieldSpec(field_name="symptoms", field_type="list", description="List of symptoms", required=True),
    FieldSpec(field_name="diagnosis", field_type="str", description="Medical diagnosis", required=False),
]

requirements = ExtractionRequirements(
    use_case_name="MedicalRecord",
    fields=fields,
)

# Create Pydantic model from requirements
# (Usually done by SchemaGenerator, but can be manual)
from gaik.building_blocks.extractor.helpers import create_extraction_model
schema = create_extraction_model(requirements)

# Use in pipeline
result = pipeline.run(
    file_path="consultation.mp3",
    user_requirements="",
    schema=schema,
    requirements=requirements,
)
```

---

## Import Patterns

```python
# Audio pipeline
from gaik.software_components.audio_to_structured_data import (
    AudioToStructuredData,
    PipelineResult,
)

# Document pipeline
from gaik.software_components.documents_to_structured_data import (
    DocumentsToStructuredData,
    PipelineResult,
)
```
