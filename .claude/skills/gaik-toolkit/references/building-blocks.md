# Building Blocks API Reference

Detailed API documentation for GAIK building blocks.

**Source:** `gaik.building_blocks.*`

## Configuration

### get_openai_config()

```python
from gaik.building_blocks.config import get_openai_config, create_openai_client

# Get configuration dict
config = get_openai_config(use_azure=True)

# Create OpenAI client from config
client = create_openai_client(config)
```

**Returns (Azure):**
```python
{
    "api_key": str,
    "azure_endpoint": str,
    "api_version": str,
    "model": str,  # Default: "gpt-4o"
    "transcription_model": str,  # Default: "whisper"
}
```

**Returns (OpenAI):**
```python
{
    "api_key": str,
    "model": str,  # Default: "gpt-4o"
    "transcription_model": str,  # Default: "whisper-1"
}
```

---

## Extractor Module

**Source:** `gaik.building_blocks.extractor`

### SchemaGenerator

Generates Pydantic models from natural language requirements.

```python
from gaik.building_blocks.extractor import SchemaGenerator

generator = SchemaGenerator(config=config)
schema = generator.generate_schema(user_requirements: str)
```

**Attributes after generation:**
- `generator.item_requirements` - `ExtractionRequirements` object
- `generator.item_requirements.use_case_name` - Generated name
- `generator.item_requirements.fields` - List of `FieldSpec`

### DataExtractor

Extracts structured data using generated schemas.

```python
from gaik.building_blocks.extractor import DataExtractor

extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model,      # Pydantic model from SchemaGenerator
    requirements,          # ExtractionRequirements from generator
    user_requirements,     # Original requirements string
    documents,             # List[str] of document texts
    save_json=False,       # Optional: save results to JSON
    json_path="out.json",  # Optional: output path
)
```

**Returns:** `List[dict]` - Extracted records matching schema

### ExtractionRequirements

Container for parsed extraction requirements.

```python
from gaik.building_blocks.extractor import ExtractionRequirements, FieldSpec

requirements = ExtractionRequirements(
    use_case_name="InvoiceExtraction",
    fields=[
        FieldSpec(
            field_name="invoice_number",
            field_type="str",
            description="Invoice identifier",
            required=True,
            pattern=r"INV-\d+",  # Optional regex
        ),
        FieldSpec(
            field_name="amount",
            field_type="float",
            description="Total amount",
            required=True,
        ),
    ]
)
```

### FieldSpec

Individual field specification.

| Attribute | Type | Description |
|-----------|------|-------------|
| `field_name` | str | Field name (snake_case) |
| `field_type` | str | `str`, `int`, `float`, `bool`, `list`, `date` |
| `description` | str | Field description |
| `required` | bool | Whether field is required |
| `enum` | list | Optional allowed values |
| `pattern` | str | Optional regex pattern |
| `format` | str | Optional output format |

---

## Parsers Module

**Source:** `gaik.building_blocks.parsers`

### VisionParser

LLM/vision-based PDF to markdown conversion.

```python
from gaik.building_blocks.parsers import VisionParser

parser = VisionParser(
    openai_config=config,
    use_context=True,      # Multi-page context awareness
    max_tokens=16000,      # Max output tokens
    temperature=0.0,       # Deterministic output
)

pages = parser.convert_pdf(
    pdf_path: str,
    dpi=150,               # Image resolution
    clean_output=True,     # Remove artifacts
    custom_prompt=None,    # Optional custom extraction prompt
)

parser.save_markdown(pages, "output.md")
```

**Returns:** `List[str]` - Markdown content per page

### PyMuPDFParser

Fast local PDF text extraction.

```python
from gaik.building_blocks.parsers import PyMuPDFParser, parse_pdf

parser = PyMuPDFParser()
result = parser.parse_document(file_path: str)

# Convenience function
text = parse_pdf(file_path: str)
```

**Returns:**
```python
{
    "text_content": str,
    "metadata": {
        "pages": int,
        "word_count": int,
    }
}
```

### DocxParser

Word document extraction.

```python
from gaik.building_blocks.parsers import DocxParser, parse_docx

parser = DocxParser()
result = parser.parse_document(file_path: str)

# Convenience function
text = parse_docx(file_path: str)
```

### DoclingParser

Advanced multi-format parsing with OCR. Requires `gaik[parser]` (not parser-cpu).

```python
from gaik.building_blocks.parsers import DoclingParser, parse_document

parser = DoclingParser()
result = parser.parse_document(file_path: str)

# Convenience function
text = parse_document(file_path: str)
```

**Supported formats:** PDF, images (.png, .jpg, .jpeg), Word docs

---

## Transcriber Module

**Source:** `gaik.building_blocks.transcriber`

### Transcriber

Audio/video transcription with optional GPT enhancement.

```python
from gaik.building_blocks.transcriber import Transcriber

transcriber = Transcriber(
    api_config=config,
    output_dir="workspace/",       # Working directory
    enhanced_transcript=True,      # GPT post-processing
    max_size_mb=25,                # Chunk threshold
    max_duration_seconds=1500,     # Max chunk duration
    default_prompt="",             # Whisper language hint
    compress_audio=True,           # Compress before API call
)

result = transcriber.transcribe(
    file_path: str,
    custom_context="",             # Optional domain context
)

result.save("output/")
```

### TranscriptionResult

Result container with save helpers.

| Attribute | Type | Description |
|-----------|------|-------------|
| `raw_transcript` | str | Direct Whisper output |
| `enhanced_transcript` | str | GPT-refined version (if enabled) |
| `job_id` | str | Unique job identifier |

**Methods:**
- `result.save(output_dir)` - Persist to disk with timestamp

**Supported formats:** .mp3, .wav, .m4a, .mp4, .webm, .ogg, .flac

---

## Document Classifier Module

**Source:** `gaik.building_blocks.doc_classifier`

### DocumentClassifier

Single-label document classification.

```python
from gaik.building_blocks.doc_classifier import DocumentClassifier

classifier = DocumentClassifier(config=config)

results = classifier.classify(
    file_or_dir: str,              # Single file or directory
    classes: List[str],            # Predefined class labels
    parser="auto",                 # Parser choice for text extraction
)
```

**Returns:**
```python
{
    "filename.pdf": {
        "class": str,              # Predicted class
        "confidence": float,       # 0.0-1.0
        "reasoning": str,          # Explanation
    }
}
```

**Parser options:** `auto`, `pymupdf`, `docx`, `vision`

---

## Import Patterns

```python
# Extractor
from gaik.building_blocks.extractor import (
    SchemaGenerator,
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
    get_openai_config,
)

# Parsers
from gaik.building_blocks.parsers import (
    VisionParser,
    PyMuPDFParser,
    DocxParser,
    DoclingParser,
    parse_pdf,
    parse_docx,
    parse_document,
    get_openai_config,
)

# Transcriber
from gaik.building_blocks.transcriber import (
    Transcriber,
    TranscriptionResult,
    get_openai_config,
)

# Classifier
from gaik.building_blocks.doc_classifier import (
    DocumentClassifier,
    get_openai_config,
)

# Shared config
from gaik.building_blocks.config import (
    get_openai_config,
    create_openai_client,
)
```
