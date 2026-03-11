# Building Blocks API Reference

Detailed API documentation for GAIK building blocks.

**Source:** `gaik.software_components.*`

## Contents

- [Configuration](#configuration)
- [Extractor Module](#extractor-module) (SchemaGenerator, DataExtractor, FieldSpec)
- [Parsers Module](#parsers-module) (VisionParser, PyMuPDFParser, DocxParser, DoclingParser)
- [Transcriber Module](#transcriber-module) (Transcriber, TranscriptionResult)
- [Parallel Transcriber Module](#parallel-transcriber-module) (ParallelTranscriber, TranscriptionConfig)
- [Document Classifier Module](#document-classifier-module)
- [Import Patterns](#import-patterns)

## Configuration

### get_openai_config()

```python
from gaik.software_components.config import get_openai_config, create_openai_client

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

**Source:** `gaik.software_components.extractor`

### SchemaGenerator

Generates Pydantic models from natural language requirements.

```python
from gaik.software_components.extractor import SchemaGenerator

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
from gaik.software_components.extractor import DataExtractor

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
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec

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

**Source:** `gaik.software_components.parsers`

### VisionParser

LLM/vision-based PDF to markdown conversion.

```python
from gaik.software_components.parsers import VisionParser, get_openai_config

config = get_openai_config(use_azure=True)
parser = VisionParser(openai_config=config, clean_output=True)

pages = parser.convert_pdf("document.pdf")
# pages is a list of markdown strings, one per page
```

**Returns:** `List[str]` - Markdown content per page

### PyMuPDFParser

Fast local PDF text extraction.

```python
from gaik.software_components.parsers import PyMuPDFParser, parse_pdf

parser = PyMuPDFParser()
text = parser.parse_pdf("document.pdf")

# Or convenience function
text = parse_pdf("document.pdf")
```

**Returns:** `str` - Extracted text content

### DocxParser

Word document extraction.

```python
from gaik.software_components.parsers import DocxParser, parse_docx

parser = DocxParser()
text = parser.parse_docx("document.docx")

# Or convenience function
text = parse_docx("document.docx")
```

**Returns:** `str` - Extracted text content

### DoclingParser

Advanced multi-format parsing with OCR. Requires `gaik[parser]` (not parser-cpu).

```python
from gaik.software_components.parsers import DoclingParser, parse_document

parser = DoclingParser()
text = parse_document("complex_document.pdf")
```

**Returns:** `str` - Extracted text content

**Supported formats:** PDF, images (.png, .jpg, .jpeg), Word docs

---

## Transcriber Module

**Source:** `gaik.software_components.transcriber`

### Transcriber

Audio/video transcription with optional GPT enhancement.

```python
from gaik.software_components.transcriber import Transcriber

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

## Parallel Transcriber Module

**Source:** `gaik.software_components.parallel_transcriber`

**Install:** `pip install "gaik[parallel-transcriber]"`

**System dependency:** `ffmpeg` + `ffprobe` on `$PATH`

### ParallelTranscriber

Production-grade parallel transcription using FFmpeg chunking and Azure OpenAI Whisper / GPT-4o Transcribe.

```python
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber, TranscriptionConfig, TranscriptionModel,
    SimpleCancellation,
)
from gaik.software_components.config import get_openai_config

api_cfg = get_openai_config(use_azure=True)
config = TranscriptionConfig(
    chunk_duration_minutes=15,
    transcription_workers=3,
    model=TranscriptionModel.WHISPER,
)
transcriber = ParallelTranscriber(api_cfg, config)

result = transcriber.transcribe("interview.mp4")
print(result.plain_text)
result.save("output/")
```

**transcribe() parameters:**
- `file_path` - Path to audio/video file
- `check_cancelled` - Callable that raises `TranscriptionCancelled` to abort (optional)
- `progress_callback` - `(stage, current, total, message)` callback. Stages: `"extracting"`, `"splitting"`, `"transcribing"`, `"merging"`, `"complete"`

### TranscriptionConfig

All tuneable parameters with sensible defaults.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `chunk_duration_minutes` | int | 20 | Chunk duration for splitting |
| `chunk_overlap_seconds` | float | 15.0 | Overlap between chunks |
| `max_single_file_mb` | float | 24.0 | Max file size for single-pass |
| `gpt4o_chunk_duration_minutes` | int | 23 | Chunk duration for GPT-4o (25 min API limit) |
| `transcription_workers` | int | 3 | Parallel transcription threads |
| `ffmpeg_split_workers` | int | 3 | Parallel FFmpeg split threads |
| `api_timeout_seconds` | int | 180 | API call timeout |
| `max_retries` | int | 2 | Max retry attempts |
| `max_429_retries` | int | 4 | Max rate-limit retries |
| `audio_bitrate` | str | `"128k"` | Audio encoding bitrate |
| `audio_sample_rate` | int | 16000 | Audio sample rate |
| `response_format` | str | `"srt"` | Output: `text`, `srt`, `vtt`, `json`, `verbose_json` |
| `language` | str\|None | None | Language (None for auto-detect) |
| `model` | TranscriptionModel | WHISPER | WHISPER or GPT4O_DIARIZE |

**Class method:** `TranscriptionConfig.from_env()` - Build config from environment variables.

### TranscriptionModel

```python
class TranscriptionModel(StrEnum):
    WHISPER = "whisper"
    GPT4O_DIARIZE = "gpt-4o-transcribe-diarize"
```

### TranscriptionResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `content` | str | Raw transcription content (SRT/text/VTT) |
| `format` | str | Output format used |
| `language` | str | Detected or specified language |
| `model_used` | str | Model that was used |
| `total_chunks` | int | Number of chunks processed |
| `total_duration_seconds` | float | Total audio duration |

**Properties:**
- `result.plain_text` - Extract plain text, stripping SRT/VTT formatting

**Methods:**
- `result.save(path, encoding="utf-8")` - Save to file (auto-selects extension). Returns `Path`.

### SimpleCancellation

Thread-safe cancellation for long-running transcriptions.

```python
cancel = SimpleCancellation()
result = transcriber.transcribe("file.mp4", check_cancelled=cancel.check)
# From another thread:
cancel.cancel()
```

---

## Document Classifier Module

**Source:** `gaik.software_components.doc_classifier`

### DocumentClassifier

Single-label document classification.

```python
from gaik.software_components.doc_classifier import DocumentClassifier

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
from gaik.software_components.extractor import (
    SchemaGenerator,
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
    get_openai_config,
)

# Parsers
from gaik.software_components.parsers import (
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
from gaik.software_components.transcriber import (
    Transcriber,
    TranscriptionResult,
    get_openai_config,
)

# Classifier
from gaik.software_components.doc_classifier import (
    DocumentClassifier,
    get_openai_config,
)

# Parallel Transcriber
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber,
    TranscriptionConfig,
    TranscriptionModel,
    TranscriptionResult,
    SimpleCancellation,
    TranscriptionCancelled,
)

# Shared config
from gaik.software_components.config import (
    get_openai_config,
    create_openai_client,
)
```
