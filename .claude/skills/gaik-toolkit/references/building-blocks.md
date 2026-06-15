# Building Blocks API Reference

Detailed API documentation for GAIK building blocks.

**Source:** `gaik.software_components.*`

## Contents

- [Configuration](#configuration)
- [Multi-Provider Configuration (`llm/`)](#multi-provider-configuration-llm)
- [Extractor Module](#extractor-module) (SchemaGenerator, DataExtractor, FieldSpec)
- [Vision Extractor Module](#vision-extractor-module) (VisionExtractor, VisionExtractionResult, VerifiableField)
- [Parsers Module](#parsers-module) (VisionParser, PyMuPDFParser, DocxParser, DoclingParser, VisionPlusParser, DoclingApiClientParser, MultimodalParser)
- [Transcriber Module](#transcriber-module) (Transcriber, TranscriptionResult)
- [Enhance Transcript Module](#enhance-transcript-module) (TranscriptEnhancer)
- [Parallel Transcriber Module](#parallel-transcriber-module) (ParallelTranscriber, TranscriptionConfig)
- [Text-to-Speech Module](#text-to-speech-module) (TextToSpeech)
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
    "model": str,  # Default: "gpt-5.4"
    "transcription_model": str,  # Default: "gpt-4o-transcribe"
}
```

**Returns (OpenAI):**
```python
{
    "api_key": str,
    "model": str,  # Default: "gpt-5.4-2026-03-05"
    "transcription_model": str,  # Default: "gpt-4o-transcribe"
}
```

---

## Multi-Provider Configuration (`llm/`)

Available since `gaik>=0.3.21`. The `gaik.software_components.llm` package provides a `ProviderClient` adapter that lets the same component code call OpenAI, Azure, Anthropic, or Google through a uniform interface — without breaking the legacy `get_openai_config()` path. Components detect the config shape and route automatically.

### get_llm_config()

```python
from gaik.software_components.llm import get_llm_config, create_llm_client

config = get_llm_config("google")        # or "openai", "azure", "anthropic",
                                         #    "anthropic_foundry", "vertex"
client = create_llm_client(config)       # ProviderClient
```

**Returns (always includes `provider` and `model`):**
```python
# google: {"provider": "google", "api_key": str, "model": "gemini-2.5-flash",
#          "embedding_model": "gemini-embedding-001"}
# anthropic: {"provider": "anthropic", "api_key": str, "model": "claude-sonnet-4-6",
#             "max_tokens": 4096}
# azure: {"provider": "azure", "use_azure": True, "api_key": str,
#         "azure_endpoint": str, "api_version": str, "model": str, ...}
```

### ProviderClient interface

| Method | Purpose |
|--------|---------|
| `chat(messages, **kwargs)` | Single chat completion. Returns `ChatResponse(text, model, provider, raw, usage)`. |
| `chat_parsed(messages, response_format, **kwargs)` | Pydantic structured output. OpenAI uses `beta.chat.completions.parse()`, Anthropic uses forced tool_use, Google uses `response_json_schema`. |
| `chat_stream(messages, **kwargs)` | `Iterator[str]` of text deltas, normalized across providers. |
| `embed(texts, **kwargs)` | Batch embeddings. Anthropic raises `NotImplementedError` (Voyage AI is recommended). |

### Provider resolution priority

1. Explicit `provider` argument to `get_llm_config()`
2. `config["provider"]` field
3. Env `LLM_PROVIDER`
4. Legacy `config["use_azure"]` → `azure` or `openai`
5. Default `azure`

### Helpers

- `build_compat_client(config)` — used by every component constructor: returns the raw `OpenAI`/`AzureOpenAI` for legacy configs (preserves bit-for-bit deterministic behavior), `ProviderClient` for `anthropic`/`google` configs.
- `assert_openai_or_azure(config, component=...)` — guard used by audio components (transcriber, parallel_transcriber, text_to_speech) to reject Anthropic/Google with a clear error message.

### Provider support matrix

| Component | OpenAI/Azure | Anthropic native | Google native | Gemini-via-OpenAI-compat |
|---|---|---|---|---|
| Extractor, Doc Classifier, Enhance Transcript, Answer Generator | ✅ | ✅ | ✅ | ✅ |
| Embedder | ✅ | ❌ → Voyage | ✅ (`gemini-embedding-001`) | ✅ |
| Vision Parser | ✅ | → `MultimodalParser` | → `MultimodalParser` | ✅ |
| Transcriber, Parallel Transcriber, TextToSpeech | ✅ | ❌ NotImplementedError | ❌ NotImplementedError | ✅ (separate audio client) |

### Extras

```toml
gaik[llm-anthropic]   # adds anthropic SDK
gaik[llm-google]      # adds google-genai + google-auth
gaik[llm-all]         # both
```

### Example: same code, three providers

```python
from gaik.software_components.extractor import DataExtractor
from gaik.software_components.llm import get_llm_config

for provider in ["azure", "anthropic", "google"]:
    extractor = DataExtractor(config=get_llm_config(provider))
    results = extractor.extract(extraction_model=MyModel, ...)
```

See `examples/software_components/llm/example_multi_provider_extractor.py`.

---

## Extractor Module

**Source:** `gaik.software_components.extractor`

### SchemaGenerator

Generates Pydantic models from natural language requirements.

```python
from gaik.software_components.extractor import SchemaGenerator

generator = SchemaGenerator(config=config)
schema = generator.generate_schema(user_requirements="Extract invoice number, total, vendor name.")
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

## Vision Extractor Module

**Source:** `gaik.software_components.vision_extractor`

**Install:** `pip install "gaik[vision-extract]"`

Single-pass PDF/image → structured data via a vision LLM. Skips the
intermediate markdown step that `DocumentsToStructuredData` produces; the
model sees the full visual context across one or more documents in a single
API call (e.g. a Purchase Order + several BOMs).

Use when accuracy on visually-laid-out documents (tables, stamps, signatures,
forms) matters more than throughput, or when several related files must be
extracted together as one logical record.

### VisionExtractor

```python
from gaik.software_components.vision_extractor import VisionExtractor

extractor = VisionExtractor(
    api_config=None,                  # Optional explicit provider config
    model_provider="openai",          # "openai" | "claude" | "google"
    model=None,                       # Optional model override
    reasoning_effort="medium",        # "minimal" | "low" | "medium" | "high"
    merge_table=False,                # Merge multi-page tables into one record
    use_azure=True,                   # OpenAI provider: use Azure deployment
    vertex_ai=True,                   # Google provider: use Vertex AI
    additional_instructions=None,     # Extra task-specific guidance
    include_verification=False,       # Wrap each field in VerifiableField
)

result = extractor.extract(
    file_paths=["PO.pdf", "BOM1.pdf", "BOM2.pdf"],
    user_requirements="Extract purchase order header and line items ...",
    extraction_model=None,            # Optional pre-built Pydantic model
    requirements=None,                # Optional pre-built ExtractionRequirements
    schema_dir=None,                  # Persist/load schema.py + requirements.json
)
```

**Supported input formats:** `.pdf`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`,
`.tiff`, `.bmp`. All file paths are sent in one call.

**Schema resolution order:**

1. Both `extraction_model` and `requirements` passed → use directly.
2. `schema_dir` set and `schema.py` + `requirements.json` exist → load from disk.
3. Otherwise → generate via `SchemaGenerator` (one text LLM call).

### VisionExtractionResult

```python
result.data            # dict[str, Any] — extracted fields (or VerifiableField-wrapped dict)
result.verification    # Optional verification metadata (include_verification=True)
result.usage           # UsageRecord — token counts, duration, cost (observability)
result.model_dump()    # Serialize to dict
```

### VerifiableField (opt-in per-field metadata)

When `include_verification=True`, each leaf field is wrapped:

```python
{
    "value": <extracted value>,
    "confidence_score": 0.0..1.0,
    "reasoning": "short why-this-value note",
}
```

Use for human-in-the-loop QA pipelines where the operator needs to know which
fields the model was unsure about.

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

### VisionPlusParser

Docling + vision hybrid — returns markdown plus per-element metadata (no chunking).
Requires `gaik[parser]` + OpenAI-compatible credentials.

```python
from gaik.software_components.parsers import VisionPlusParser, parse_document_with_vision_plus

result = parse_document_with_vision_plus("document.pdf")
```

**Returns:** markdown string + metadata for downstream RAG pipelines.

### DoclingApiClientParser

Client that calls a remote Docling parsing service instead of running Docling locally.
Use when you want Docling-quality parsing without the local install overhead.

```python
from gaik.software_components.parsers import DoclingApiClientParser, parse_document_via_api

result = parse_document_via_api("document.pdf", api_url=...)
```

### MultimodalParser

Multi-provider PDF-to-markdown parser (OpenAI, Claude, Google Gemini). Produces
raw markdown with layout metadata, cleaned markdown, and optional styled HTML.
Requires `gaik[multimodal-parser]`.

```python
from gaik.software_components.parsers import MultimodalParser, ParseResult

parser = MultimodalParser(config=config, model_provider="openai", create_html=True)
result: ParseResult = parser.parse("document.pdf")
result.save("output/")
```

**Returns:** `ParseResult` with `raw_markdown`, `clean_markdown`, and optional `html`.
Tracks token usage and cost per run.

---

## Transcriber Module

**Source:** `gaik.software_components.transcriber`

### Transcriber

Audio/video transcription with configurable backends and optional transcript error correction.

```python
from gaik.software_components.transcriber import Transcriber

transcriber = Transcriber(
    api_config=config,
    output_dir="workspace/",                    # Working directory
    enhanced_transcript=True,                   # Run TranscriptEnhancer on raw output
    enhanced_transcript_instructions=None,      # Optional domain instructions for enhancement
    max_size_mb=25,                             # Chunk threshold
    max_duration_seconds=1500,                  # Max chunk duration
    default_prompt="",                          # Whisper language hint
    transcription_model=None,                   # "whisper", "gpt-4o-transcribe", or "whisper_local"
    language="auto",                            # Language code ("fi", "en", "auto")
    local_api_base=None,                        # Required for whisper_local
    local_api_key=None,                         # Required for whisper_local
    diarization=False,                          # whisper_local only
    speaker_count=None,                         # whisper_local only
    min_speakers=None,                          # whisper_local only
    max_speakers=None,                          # whisper_local only
    initial_prompt=None,                        # whisper_local only
)

result = transcriber.transcribe(
    file_path: str,
    custom_context="",             # Optional domain context
    use_case_name=None,            # Optional label for logging
)

result.save("output/")
```

### Transcription Models

`transcription_model` accepts: `"whisper"`, `"gpt-4o-transcribe"`, `"whisper_local"`.

- Not provided: uses the model from `api_config` (default `gpt-4o-transcribe` for both Azure and OpenAI)
- `"whisper"`: Azure resolves to configured deployment (typically `whisper-1`), OpenAI uses `whisper`
- `"gpt-4o-transcribe"`: both Azure/OpenAI use `gpt-4o-transcribe`
- `"whisper_local"`: routes to local Whisper server via `local_api_base`/`local_api_key`

### Local Whisper (`whisper_local`)

The `language` parameter selects the ASR model on the remote server:
- `language="fi"` — Finnish fine-tuned model (`Finnish-NLP/whisper-large-finnish-v3-ct2`)
- `language="en"` or `language="auto"` — `whisper-large-v3`

Local-only parameters (`diarization`, `speaker_count`, etc.) are silently ignored when not using `whisper_local`.

### Transcript Error Correction

When `enhanced_transcript=True`, the Transcriber runs the raw transcript through the standalone `TranscriptEnhancer` component (see Enhance Transcript Module below). The `enhanced_transcript_instructions` parameter is forwarded as `additional_instructions` to the second pass.

### TranscriptionResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `raw_transcript` | str | Direct Whisper output |
| `enhanced_transcript` | str \| None | Corrected version from TranscriptEnhancer (if enabled) |
| `job_id` | str | Unique job identifier |
| `segments` | list[dict] \| None | Whisper segments with start/end/text (whisper_local only) |
| `srt_content` | str \| None | SRT subtitle content (whisper_local only) |
| `vtt_content` | str \| None | VTT subtitle content (whisper_local only) |

**Methods:**
- `result.save(directory, *, save_raw=True, save_enhanced=True, encoding="utf-8")` - Persist to disk. Returns `dict[str, Path | None]` mapping `"raw"` and `"enhanced"` to saved file paths.

**Supported formats:** .mp3, .wav, .m4a, .mp4, .webm, .ogg, .flac

---

## Enhance Transcript Module

**Source:** `gaik.software_components.enhance_transcript`

**Install:** `pip install "gaik[enhance-transcript]"`

Two-pass LLM transcript error correction, currently tuned for Finnish. Pass 1: spelling cleanup and consistency. Pass 2: context-based ASR repair with optional custom instructions.

### TranscriptEnhancer

```python
from gaik.software_components.enhance_transcript import TranscriptEnhancer, get_openai_config

config = get_openai_config(use_azure=True)
enhancer = TranscriptEnhancer(
    api_config=config,         # Optional; uses get_openai_config() if omitted
    use_azure=True,            # Used only when api_config is omitted
    model=None,                # Optional model override
    reasoning_effort=None,     # Optional: "minimal" | "low" | "medium" | "high"
                               #   Forwarded to gpt-5.x reasoning models;
                               #   provider-agnostic — silently ignored by
                               #   models that don't accept it.
)

# From string
result = enhancer.enhance_text(
    transcript_text="...",
    generate_summary=False,           # Include change count summary
    diff_chunks=False,                # Include list of changed spans
    additional_instructions=None,     # Extra instructions for Pass 2
    progress_callback=None,           # Optional: Callable[[str, dict], None]
                                      #   Emits events: pass1_started,
                                      #   pass1_completed, pass2_started,
                                      #   pass2_completed. Exceptions from the
                                      #   callback are swallowed with a
                                      #   warning so enhancement still
                                      #   completes.
)

# From file
result = enhancer.enhance_file(
    file_path="transcript.txt",
    generate_summary=True,
    diff_chunks=True,
    additional_instructions="Keep company names exactly as written.",
)
```

### TranscriptEnhancerResult

```python
result.enhanced_text           # Corrected transcript
result.original_text           # Input transcript
result.source_file             # File path (if enhance_file was used)
result.correction_summary      # CorrectionSummary (if generate_summary=True)
result.diff_chunks             # List[DiffChunk] (if diff_chunks=True)
result.model_dump()            # Serialize to dict
```

**Default models:** Azure: `gpt-5.4`, OpenAI: `gpt-5.4-2026-03-05`

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
| `api_timeout_seconds` | int | 600 | API call timeout (keep ≥ ~25s × `gpt4o_chunk_duration_minutes`) |
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

## Text-to-Speech Module

**Source:** `gaik.software_components.text_to_speech`

**Install:** `pip install "gaik[text-to-speech]"`

Generate spoken audio from text using OpenAI or Azure OpenAI TTS.

### TextToSpeech

```python
from gaik.software_components.text_to_speech import TextToSpeech, get_openai_config

config = get_openai_config(use_azure=True)
tts = TextToSpeech(
    api_config=config,
    model="tts-hd",
    language="fi",                   # "fi" or "en"
    voice="alloy",
    response_format="mp3",
    speed=1.0,
    default_instructions=None,
)

result = tts.synthesize(
    text="Tama on tekstista puheeksi.",
    language="fi",    # optional override
    voice="alloy",    # optional override
)
saved_path = result.save("tts_outputs")
```

### SpeechSynthesisResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `audio_bytes` | bytes | Raw audio data |
| `job_id` | str | Unique job identifier |
| `model` | str | Model used |
| `voice` | str | Voice used |
| `language` | str | Language code |
| `response_format` | str | Audio format |
| `content_type` | str | MIME type |

**Methods:**
- `result.save(output_dir)` - Save audio file, returns path

**Azure env vars:** `AZURE_API_KEY`, `TTS_ENDPOINT`, `AZURE_TTS_MODEL`
**OpenAI env var:** `OPENAI_TTS_MODEL` (optional override)

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

# Vision Extractor
from gaik.software_components.vision_extractor import (
    VisionExtractor,
    VisionExtractionResult,
    VerifiableField,
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

# Enhance Transcript
from gaik.software_components.enhance_transcript import (
    TranscriptEnhancer,
    TranscriptEnhancerResult,
    CorrectionSummary,
    DiffChunk,
    get_openai_config,
)

# Text-to-Speech
from gaik.software_components.text_to_speech import (
    TextToSpeech,
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
