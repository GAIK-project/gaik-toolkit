# GAIK - General AI Kit

AI toolkit for Python with structured data extraction, document parsing, and audio/video transcription using OpenAI/Azure OpenAI.

## Installation

```bash
# Extractor features (schema generation + extraction)
pip install gaik[extractor]

# PDF parsing (vision-based + PyMuPDF)
pip install gaik[parser]

# Audio/video transcription (Whisper + GPT)
pip install gaik[transcriber]
# Note: Video processing requires ffmpeg (optional system dependency)
# See "System Requirements" section below for installation instructions

# All features
pip install gaik[all]
```

## System Requirements

### Optional: FFmpeg (for Video Processing)

The transcriber module works without ffmpeg for basic audio transcription (.mp3, .wav, .m4a files).

**FFmpeg is only needed for:**
- 🎥 Processing video files (.mp4, .avi, .mov, .mkv, etc.) - extracts audio
- 📦 Compressing large audio files (>25MB) - reduces file size for Whisper API

**Installation by Platform:**

**Windows:**
```powershell
# Option 1: Using winget (Windows 10+)
winget install ffmpeg

# Option 2: Using Chocolatey
choco install ffmpeg

# Option 3: Manual installation
# 1. Download from https://ffmpeg.org/download.html
# 2. Extract to C:\ffmpeg
# 3. Add C:\ffmpeg\bin to PATH:
#    - Search "Environment Variables" in Windows
#    - Edit "Path" under System Variables
#    - Add new entry: C:\ffmpeg\bin
```

**macOS:**
```bash
# Using Homebrew (recommended)
brew install ffmpeg
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install ffmpeg

# Fedora/RHEL
sudo dnf install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

**Verify Installation:**
```bash
ffmpeg -version
```

If the command returns version information, ffmpeg is properly installed and in your PATH.

## Quick Start

### Schema-Based Data Extraction

```python
from gaik.extractor import SchemaGenerator, DataExtractor, get_openai_config

# Configure OpenAI (Azure or standard)
config = get_openai_config(use_azure=True)

# Step 1: Generate schema from natural language
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(
    user_requirements="Extract invoice number, total amount in USD, and vendor name"
)

# Step 2: Extract data using generated schema
extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=generator.item_requirements.use_case_name,
    documents=["Invoice #12345 from Acme Corp, Total: $1,500"],
    save_json=True,
    json_path="results.json"
)

print(results)  # [{'invoice_number': '12345', 'total_amount': 1500.0, 'vendor_name': 'Acme Corp'}]
```

### Vision-Based PDF Parsing

```python
from gaik.parsers import VisionParser, get_openai_config

# Set environment: AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT (or OPENAI_API_KEY)
config = get_openai_config(use_azure=True)
parser = VisionParser(
    openai_config=config,
    use_context=True,      # Multi-page continuity
)

pages = parser.convert_pdf("invoice.pdf", dpi=150, clean_output=True)
markdown = pages[0] if len(pages) == 1 else "\n\n".join(pages)
parser.save_markdown(pages, "invoice.md")
```

### Fast Local PDF Parsing

```python
from gaik.parsers import PyMuPDFParser

parser = PyMuPDFParser()
result = parser.parse_document("document.pdf")
print(result["text_content"])
print(result["metadata"])  # Page count, author, etc.
```

### Audio/Video Transcription

```python
from gaik.transcriber import Transcriber, get_openai_config

# Set environment: AZURE_API_KEY, AZURE_ENDPOINT (or OPENAI_API_KEY)
config = get_openai_config(use_azure=True)
transcriber = Transcriber(config)  # enhanced_transcript=True by default

# Transcribe audio/video file
result = transcriber.transcribe("meeting_recording.mp3")

# Save results
result.save("output/transcripts/")
print(result.enhanced_transcript)
```

## Features

### 🔍 Structured Data Extraction (`gaik.extractor`)

- **SchemaGenerator** - Automatically generates Pydantic schemas from natural language requirements
- **DataExtractor** - Extracts structured data using generated schemas
- **Smart Structure Detection** - Automatically detects nested vs flat data structures
- **Type-safe** - Full Pydantic validation with field types, enums, and patterns
- **Multi-provider** - OpenAI and Azure OpenAI support
- **JSON Export** - Save results to JSON files automatically

### 📄 Document Parsing (`gaik.parsers`)

- **VisionParser** - PDF to Markdown using OpenAI vision models (GPT-4V)
  - Multi-page context awareness
  - Table extraction and cleaning
  - Configurable DPI and custom prompts
  - Azure OpenAI support
- **PyMuPDFParser** - Fast local text extraction with metadata
- **DoclingParser** - Advanced document parsing with OCR and multi-format support
- **No external binaries** - Pure Python dependencies

### 🎤 Audio/Video Transcription (`gaik.transcriber`)

- **Transcriber** - High-level API for audio/video transcription
  - OpenAI Whisper integration for accurate speech-to-text
  - Automatic chunking for long audio files (handles files > 25MB)
  - Context-aware transcription across chunks
  - Optional GPT enhancement for improved formatting and structure
  - **Audio formats** (no ffmpeg required): mp3, wav, m4a, ogg
  - **Video formats** (requires ffmpeg): mp4, avi, mov, mkv, flv
  - **Audio compression** (requires ffmpeg): Automatic compression for large files
  - Batch processing capabilities
- **TranscriptionResult** - Container for raw and enhanced transcripts
  - Save to multiple formats
  - Preserve both raw Whisper output and GPT-enhanced versions
- **Azure OpenAI and OpenAI support** - Works with both platforms

## API Reference

### Extractor Module

#### SchemaGenerator

```python
from gaik.extractor import SchemaGenerator, get_openai_config

generator = SchemaGenerator(
    config: dict,              # From get_openai_config()
    model: str | None = None   # Optional model override
)
```

**Methods:**
- `generate_schema(user_requirements: str) -> type[BaseModel]` - Generate Pydantic schema
- `analyze_structure(user_requirements: str) -> StructureAnalysis` - Detect nested/flat structure
- `get_schema_info() -> str` - Get human-readable schema information

**Attributes:**
- `extraction_model` - Generated Pydantic model
- `item_requirements` - Parsed field requirements
- `structure_analysis` - Structure type analysis

#### DataExtractor

```python
from gaik.extractor import DataExtractor

extractor = DataExtractor(
    config: dict,              # From get_openai_config()
    model: str | None = None   # Optional model override
)
```

**Methods:**
- `extract(extraction_model, requirements, user_requirements, documents, save_json=False, json_path=None) -> list[dict]`
  - `extraction_model`: Pydantic model from SchemaGenerator
  - `requirements`: ExtractionRequirements from SchemaGenerator
  - `user_requirements`: Original requirements string
  - `documents`: List of document strings to extract from
  - `save_json`: Whether to save results to JSON
  - `json_path`: Path for JSON output file

#### Configuration

```python
from gaik.extractor import get_openai_config, create_openai_client

config = get_openai_config(use_azure: bool = True) -> dict
client = create_openai_client(config: dict) -> OpenAI | AzureOpenAI
```

### Parser Module

#### VisionParser

```python
from gaik.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)  # Returns OpenAIConfig dataclass
parser = VisionParser(
    openai_config: OpenAIConfig,   # From get_openai_config()
    custom_prompt: str | None = None,
    use_context: bool = True,      # Multi-page context
    max_tokens: int = 16_000,
    temperature: float = 0.0
)
```

**Methods:**
- `convert_pdf(pdf_path: str, *, dpi: int = 200, clean_output: bool = True) -> list[str]` - Convert PDF to markdown pages
- `save_markdown(markdown_pages: Sequence[str], output_path: str, *, separator: str = "\n\n---\n\n") -> None` - Save markdown to file

#### PyMuPDFParser

```python
from gaik.parsers import PyMuPDFParser

parser = PyMuPDFParser()
```

**Methods:**
- `parse_document(file_path: str) -> dict` - Extract text and metadata
  - Returns: `{"text_content": str, "metadata": dict}`

#### DoclingParser

```python
from gaik.parsers import DoclingParser

parser = DoclingParser(
    ocr_engine: str = "easyocr",  # or "tesseract", "rapid"
    use_gpu: bool = False
)
```

**Methods:**
- `parse_document(file_path: str) -> dict` - Parse document with OCR
- `convert_to_markdown(file_path: str) -> str` - Convert to markdown

### Transcriber Module

#### Transcriber

```python
from gaik.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)
transcriber = Transcriber(
    api_config: dict,                      # From get_openai_config()
    output_dir: str | Path = "transcriber_workspace",
    *,
    compress_audio: bool = True,           # Compress large audio files
    enhanced_transcript: bool = True,      # Enable GPT enhancement
    max_size_mb: int = 25,                 # Max file size for Whisper
    max_duration_seconds: int = 1500,      # Max duration per chunk
    default_prompt: str = DEFAULT_PROMPT   # Custom Whisper prompt
)
```

**System Requirements:**
- Basic audio transcription (.mp3, .wav, .m4a): No additional dependencies
- Video processing (.mp4, .avi, .mov, etc.): Requires ffmpeg (see [System Requirements](#system-requirements))
- Audio compression (files >25MB): Requires ffmpeg (optional, improves performance)

**Methods:**
- `transcribe(file_path: str | Path, *, custom_context: str = "", use_case_name: str | None = None, compress_audio: bool | None = None) -> TranscriptionResult`
  - `file_path`: Path to audio/video file
  - `custom_context`: Additional context for transcription
  - `use_case_name`: Optional name for organizing output
  - `compress_audio`: Override instance setting for this call
  - Returns: `TranscriptionResult` with raw and/or enhanced transcripts

#### TranscriptionResult

Container for transcription outputs with save capabilities.

**Attributes:**
- `raw_transcript: str` - Original Whisper output
- `enhanced_transcript: str | None` - GPT-enhanced version
- `job_id: str` - Unique identifier for this transcription

**Methods:**
- `save(directory: str, save_raw: bool = True, save_enhanced: bool = True) -> dict[str, Path]`
  - Saves transcripts to files
  - Returns: Mapping of artifact type to file path

## Environment Variables

### For All Modules (Extractors, Parsers, and Transcribers)

| Provider | Required Variables | Optional |
|----------|-------------------|----------|
| **OpenAI** | `OPENAI_API_KEY` | - |
| **Azure OpenAI** | `AZURE_API_KEY`<br>`AZURE_ENDPOINT`<br>`AZURE_DEPLOYMENT` | `AZURE_API_VERSION` (default: 2024-02-15-preview) |

**Note:** Set `use_azure=True` in `get_openai_config()` for Azure, or `use_azure=False` for standard OpenAI. All modules (extractor, parsers, transcriber) use the same configuration pattern.

## Default Models

| Provider | Default Model | Notes |
|----------|---------------|-------|
| **OpenAI** | `gpt-4.1` | For extraction and vision parsing |
| **Azure OpenAI** | User's deployment | Specified via `AZURE_DEPLOYMENT` env variable |

## Extraction Examples

### Batch Document Processing

```python
from gaik.extractor import SchemaGenerator, DataExtractor, get_openai_config

config = get_openai_config(use_azure=True)

# Generate schema once
generator = SchemaGenerator(config=config)
schema = generator.generate_schema("""
Extract from invoices:
- invoice_number: Invoice ID (string)
- amount: Total in USD (number)
- vendor: Company name (string)
""")

# Extract from multiple documents
extractor = DataExtractor(config=config)
documents = [
    "Invoice #12345 from Acme Corp. Total: $1,500",
    "INV-67890, Supplier: TechCo, Amount: $2,750"
]

results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=generator.item_requirements.use_case_name,
    documents=documents
)

for result in results:
    print(f"Invoice: {result['invoice_number']}, Amount: ${result['amount']}")
```

### Nested Data Extraction

```python
# The SchemaGenerator automatically detects nested structures
generator = SchemaGenerator(config=config)
schema = generator.generate_schema("""
Extract purchase orders with multiple line items.
For each PO, extract:
- PO number
- Vendor name
- Items (multiple):
  - Item description
  - Quantity
  - Unit price
""")

# Returns nested Pydantic model with list of items
print(generator.structure_analysis.structure_type)  # 'nested'
```

### Schema Inspection

```python
# After generating schema
generator = SchemaGenerator(config=config)
schema = generator.generate_schema("Extract name, age, and email")

# View schema information
print(generator.get_schema_info())

# Access field requirements
for field in generator.item_requirements.fields:
    print(f"{field.field_name}: {field.field_type} - {field.description}")

# JSON schema
json_schema = schema.model_json_schema()
print(json_schema)
```

## Parsing Examples

### Custom Prompt for Vision Parser

```python
from gaik.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)

custom_prompt = """
Convert document to markdown:
- Preserve all tables with proper formatting
- Include headers and footers
- Maintain layout structure
- Extract form fields
"""

parser = VisionParser(
    openai_config=config,
    custom_prompt=custom_prompt,
    use_context=True,
    dpi=200
)

pages = parser.convert_pdf("complex_form.pdf")
```

### Multi-PDF Processing with Classification

```python
from gaik.parsers import VisionParser, get_openai_config
from pathlib import Path

config = get_openai_config(use_azure=True)
parser = VisionParser(openai_config=config, use_context=True, clean_output=True)

pdf_files = Path("documents/").glob("*.pdf")
for pdf_path in pdf_files:
    print(f"Processing: {pdf_path}")

    # Parse PDF
    pages = parser.convert_pdf(str(pdf_path))
    markdown = pages[0] if len(pages) == 1 else "\n\n".join(pages)

    # Save with same name as PDF
    output_path = pdf_path.with_suffix(".md")
    parser.save_markdown(markdown, str(output_path))
    print(f"Saved: {output_path}")
```

### Combined Extraction + Parsing Pipeline

```python
from gaik.parsers import VisionParser, get_openai_config
from gaik.extractor import SchemaGenerator, DataExtractor

config = get_openai_config(use_azure=True)

# Step 1: Parse PDF to markdown
parser = VisionParser(openai_config=config, clean_output=True)
pages = parser.convert_pdf("invoice.pdf")
markdown_text = pages[0]

# Step 2: Generate extraction schema
generator = SchemaGenerator(config=config)
schema = generator.generate_schema("""
Extract invoice details:
- Invoice number
- Date
- Total amount
- Vendor name
""")

# Step 3: Extract structured data from parsed markdown
extractor = DataExtractor(config=config)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=generator.item_requirements.use_case_name,
    documents=[markdown_text]
)

print(results[0])  # {'invoice_number': '...', 'date': '...', ...}
```

## Resources

- **Examples**: [examples/](../../examples/)
- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Contributing**: [CONTRIBUTING.md](../../../CONTRIBUTING.md)

## License

MIT - see [LICENSE](../../../LICENSE)
