# GAIK API

Lightweight REST API built with FastAPI for audio transcription, document parsing, and structured data extraction. Wraps the [GAIK Toolkit](https://github.com/GAIK-project/gaik-toolkit) building blocks and end-to-end pipelines.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Kubernetes health check |
| `/` | GET | API info (endpoint list) |
| `/transcribe` | POST | Whisper / gpt-4o-transcribe transcription for audio + video |
| `/parse` | POST | PDF/DOCX parsing (pymupdf, docx, vision, multimodal) |
| `/pipeline/diary` | POST | Finnish *Työmaapäiväkirja* from audio → structured JSON + optional PDF |
| `/pipeline/incident-report` | POST | Incident report from audio / text / document → structured JSON + optional PDF |
| `/pipeline/pdf/{job_id}` | GET | Download a previously generated PDF |

All non-health endpoints require the `X-API-Key` header.

## Installation

```bash
# From repository root
pip install -e ".[all]"
pip install -r implementation_layer/api/requirements.txt
```

See the [top-level README](../../README.md) for toolkit install extras.

## Configuration

```bash
cp implementation_layer/api/.env.example implementation_layer/api/.env
# Edit .env and set at minimum API_KEY + Azure/OpenAI credentials
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *(empty)* | **Required in production.** Value expected in `X-API-Key` header |
| `USE_AZURE` | `true` | Use Azure OpenAI (`true`) or standard OpenAI (`false`) |
| `AZURE_API_KEY` | — | Required when `USE_AZURE=true` |
| `AZURE_ENDPOINT` | — | Azure resource endpoint, e.g. `https://<resource>.openai.azure.com/` |
| `AZURE_API_VERSION` | `2025-04-01-preview` | Azure OpenAI API version |
| `AZURE_DEPLOYMENT` | `gpt-5.1` | Chat/completion deployment name |
| `AZURE_TRANSCRIPTION_MODEL` | `gpt-4o-transcribe` | Whisper-compatible transcription deployment |
| `OPENAI_API_KEY` | — | Required when `USE_AZURE=false` |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Enables `/docs`, `/redoc`, `/openapi.json` and loosens auth when `API_KEY` is empty |
| `CORS_ORIGINS` | `[]` | Comma-separated list of allowed origins |
| `MAX_FILE_SIZE_MB` | `100` | Upload size limit |
| `ALLOWED_AUDIO_EXTENSIONS` | `.mp3, .wav, .m4a, .mp4, .webm, .ogg, .flac` | Accepted audio/video suffixes |
| `ALLOWED_DOC_EXTENSIONS` | `.pdf, .docx` | Accepted document suffixes |

## Running

```bash
# Development (hot reload + /docs enabled)
DEBUG=true uvicorn implementation_layer.api.main:app --reload

# Production
uvicorn implementation_layer.api.main:app --host 0.0.0.0 --port 8000
```

When `DEBUG=true`, interactive docs live at `http://localhost:8000/docs`.

## Endpoint reference

### `POST /transcribe`

Transcribes audio/video. Optional two-pass LLM enhancement via `TranscriptEnhancer`.

| Form field | Type | Default | Description |
|---|---|---|---|
| `file` | file | **required** | Audio/video file (see `ALLOWED_AUDIO_EXTENSIONS`) |
| `custom_context` | string | `""` | Free-form context to bias Whisper (e.g. domain vocabulary) |
| `enhanced` | bool | `true` | Run LLM enhancement on raw transcript |

```bash
curl -X POST http://localhost:8000/transcribe \
  -H "X-API-Key: $API_KEY" \
  -F "file=@audio.mp3" \
  -F "enhanced=true" \
  -F "custom_context=Construction site supervisor report"
```

### `POST /parse`

Extracts text content from PDF or DOCX.

| Form field | Type | Default | Description |
|---|---|---|---|
| `file` | file | **required** | PDF or DOCX |
| `parser_type` | enum | `auto` | `auto` \| `pymupdf` \| `docx` \| `vision` \| `multimodal` |

Parser matrix:

| Parser | Input | Requires | Notes |
|---|---|---|---|
| `auto` | PDF/DOCX | — | PDF → `pymupdf`, DOCX → `docx` |
| `pymupdf` | PDF | PyMuPDF | Fast, text-only |
| `docx` | DOCX | python-docx | Local |
| `vision` | PDF | OpenAI/Azure | Page-by-page Markdown via vision model |
| `multimodal` | PDF | OpenAI/Azure | Layout-aware single-shot Markdown (newer, cleaner output + token metadata) |

```bash
# Fast local PDF
curl -X POST http://localhost:8000/parse \
  -H "X-API-Key: $API_KEY" \
  -F "file=@document.pdf" \
  -F "parser_type=pymupdf"

# High-quality LLM Markdown
curl -X POST http://localhost:8000/parse \
  -H "X-API-Key: $API_KEY" \
  -F "file=@document.pdf" \
  -F "parser_type=multimodal"
```

### `POST /pipeline/diary`

Transcribes site-supervisor audio and extracts the 20-field Finnish *Työmaapäiväkirja*.

| Form field | Type | Default | Description |
|---|---|---|---|
| `file` | file | **required** | Audio file |
| `generate_pdf` | bool | `true` | Render a PDF diary (downloadable via `/pipeline/pdf/{job_id}`) |
| `enhanced` | bool | `true` | Enhance transcript before extraction |
| `custom_requirements` | string | — | Override the default Finnish diary field list |

```bash
curl -X POST http://localhost:8000/pipeline/diary \
  -H "X-API-Key: $API_KEY" \
  -F "file=@site_report.mp3" \
  -F "generate_pdf=true"
```

### `POST /pipeline/incident-report`

Generates an incident report from audio, text, **or** a document. Provide exactly one of `file` or `text`.

| Form field | Type | Default | Description |
|---|---|---|---|
| `file` | file | — | Audio or document (.pdf/.docx) |
| `text` | string | — | Free-text description |
| `generate_pdf` | bool | `false` | Render a PDF report |
| `enhanced` | bool | `true` | Enhance transcript (audio input only) |
| `parser_type` | enum | `auto` | `auto` \| `pymupdf` \| `docx` \| `vision` (document input only) |
| `custom_requirements` | string | — | Override default extraction requirements |

```bash
# From text
curl -X POST http://localhost:8000/pipeline/incident-report \
  -H "X-API-Key: $API_KEY" \
  -F "text=Employee slipped on wet floor in warehouse area B" \
  -F "generate_pdf=true"

# From audio
curl -X POST http://localhost:8000/pipeline/incident-report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@report.mp3"

# From document
curl -X POST http://localhost:8000/pipeline/incident-report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@report.pdf" \
  -F "parser_type=pymupdf"
```

### `GET /pipeline/pdf/{job_id}`

Download the PDF produced by a previous `diary` or `incident-report` call.

```bash
curl -OJ -H "X-API-Key: $API_KEY" \
  http://localhost:8000/pipeline/pdf/<job_id>
```

> PDFs are kept in the running container's temp directory. In horizontally scaled deployments, back `PDF_STORAGE` with shared storage (S3, object storage, or a volume).

## Docker

```bash
docker build -t gaik-api -f implementation_layer/api/Dockerfile .
docker run -p 8000:8000 --env-file implementation_layer/api/.env gaik-api
```

The Dockerfile installs `gaik[transcriber,multimodal-parser]` plus PyMuPDF + python-docx. `auto`, `pymupdf`, `docx`, `vision`, and `multimodal` parsers all work out of the box. **`docling` / `visionPlus` parsers are not included** (pulls in `docling` + `torch`) — extend the image if you need them.

## Adding a new component to the API

The API follows a repeatable three-file pattern. To expose a new toolkit component (e.g. `TextToSpeech`, `DocumentClassifier`, `RAGWorkflow`):

1. **Create a schema** in `schemas/<feature>.py` (Pydantic request/response models).
2. **Create a router** in `routers/<feature>.py`:

   ```python
   from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
   from implementation_layer.api.config import get_openai_config, settings
   from implementation_layer.api.dependencies import verify_api_key
   from implementation_layer.api.schemas.tts import TTSResponse
   from implementation_layer.api.utils import temp_file, validate_upload, validate_file_size

   router = APIRouter()

   @router.post(
       "/",
       response_model=TTSResponse,
       dependencies=[Depends(verify_api_key)],
       summary="Synthesize speech from text",
   )
   async def synthesize(text: str = Form(...), voice: str = Form(default="alloy")):
       from gaik.software_components.text_to_speech import TextToSpeech

       tts = TextToSpeech(api_config=get_openai_config())
       result = tts.synthesize(text=text, voice=voice)
       return TTSResponse(audio_url=result.audio_path, duration_s=result.duration)
   ```

3. **Register the router** in `main.py`:

   ```python
   from implementation_layer.api.routers import tts
   app.include_router(tts.router, prefix="/tts", tags=["TTS"])
   ```

### Conventions

- **Auth**: always add `dependencies=[Depends(verify_api_key)]`.
- **Config**: use `get_openai_config()` from `config.py` — it honours `USE_AZURE`.
- **Uploads**: use `validate_upload`, `validate_file_size`, and the `temp_file` context manager from `utils/`. This guarantees extension checks, size limits (`MAX_FILE_SIZE_MB`), and cleanup.
- **Schemas**: add Pydantic response models with `json_schema_extra` examples so `/docs` stays useful.
- **Imports**: import heavy toolkit modules *inside* the handler (deferred import). Keeps startup fast and lets the Dockerfile stay slim.
- **Errors**: raise `HTTPException` for validation issues; catch unexpected errors and return generic messages in production (never leak stack traces).
- **Pipelines returning artifacts**: generate a `job_id = str(uuid.uuid4())` and store the result path in a module-level `dict`, then expose a `GET /.../{job_id}` download route (see [`pipeline.py`](routers/pipeline.py)).

### Handy building blocks already importable

| Component | Import |
|---|---|
| Transcriber | `from gaik.software_components.transcriber import Transcriber` |
| ParallelTranscriber | `from gaik.software_components.parallel_transcriber import ParallelTranscriber` |
| TranscriptEnhancer | `from gaik.software_components.enhance_transcript import TranscriptEnhancer` |
| TextToSpeech | `from gaik.software_components.text_to_speech import TextToSpeech` |
| PyMuPDFParser / DocxParser / VisionParser / MultimodalParser | `from gaik.software_components.parsers import ...` |
| SchemaGenerator / DataExtractor | `from gaik.software_components.extractor import SchemaGenerator, DataExtractor` |
| DocumentClassifier | `from gaik.software_components.doc_classifier import DocumentClassifier` |
| AudioToStructuredData / DocumentsToStructuredData / RAGWorkflow | `from gaik.software_modules.<module> import ...` |

## Deployment

Rahti 2 (OpenShift) deploy scripts live in [`openshift/`](../../openshift/). The Dockerfile is OpenShift-compatible (non-root UID 1001) and exposes a `/health` endpoint for liveness/readiness probes.
