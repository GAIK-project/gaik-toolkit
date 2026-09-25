# GAIK Toolkit Demo

Interactive demo application for the [GAIK Toolkit](https://pypi.org/project/gaik/) components.

## Features

### Software Components

- **Extractor** - Extract structured data from documents using natural language
- **Vision Extractor** - One-call PDF/image → structured data (multi-doc, no intermediate parse)
- **Parser** - Parse PDFs and Word documents with multiple backends
- **Classifier** - Classify documents into predefined categories
- **Transcriber** - Transcribe audio/video with Whisper and GPT enhancement
- **Text-to-Speech** - Text to downloadable speech audio
- **PostgreSQL Agent** - Plain-language → read-only SQL with a sandboxed demo DB
- **Tabular Agent** - Upload a CSV/Excel file and ask it questions — read-only SQL over DuckDB, messy report sheets cleaned up automatically
- **LLM-as-Judge** - Score extractor output, detect hallucinations, run a multi-model judge panel

### Software Modules

- **RAG Builder** - Document upload, indexing, Q&A with citations and debug tools
- **Audio Structured** - Audio to structured data pipeline
- **Document Structured** - Document to structured data pipeline

### Use Cases

- **Incident Report** - Voice to structured incident report
- **Construction Diary** - Voice notes to construction diary
- **Dental Transcription** - Audio/video to SRT/VTT subtitles
- **Semantic Video Search** - Vector search across indexed video transcripts (pgvector)
- **Purchase Order Processing** - PO + BOMs + price list → line-item prices and order draft (`luvata-order` route)
- **Report Writer** - Mixed-source report generation from documents, spreadsheets, images, audio/video, text, and an optional sample report/template

### Solution Wizard

- **Solution Configuration Wizard** - Natural-language use case → validated blueprint, BPMN diagram, Mermaid flow, and runnable PoC. Access is gated separately from the regular demos: anonymous visitors are sent to `/sign-in`, approved users need a per-user `wizard_access` grant from `/admin`, and the optional team shortcut `/solution-wizard?key=<WIZARD_ACCESS_SECRET>` sets a temporary access cookie.

## Quick Start

The **Model settings** button lets signed-in users optionally select their own OpenAI,
Azure OpenAI or CSC Aitta account. Enter the model/deployment and key; Azure also needs
its public resource endpoint. **Test connection** makes one small chat request. **Use
settings** activates it for this browser tab until refresh, navigation away or sign-out.
**Use server defaults** clears it.

Own settings apply to Extractor, Schema Generator, Classifier, LLM-based Parser modes,
Vision Extractor, PostgreSQL Agent questions, single LLM Judge tasks and Solution Wizard
image attachments. Wizard text/document attachments keep their existing local parsing
or server Docling fallback; audio attachments require clearing own model settings to
use the server transcription deployment. The conversation uses the hosted Claude Agent SDK.
The judge panel, RAG/Tabular sessions, audio workflows and Report Writer use server
settings; their page notice makes this explicit. Select a vision-capable model for
images, and use the server settings for mixed-provider workflows.

Keys stay in browser memory and travel only on supported same-origin POST requests,
through the existing authenticated proxy. They are not saved to browser storage,
cookies, application sessions, generated projects, or the process environment. The
API creates and closes a request-specific HTTP client, including streaming requests.
OpenAI and Aitta endpoints are fixed. Azure accepts public HTTPS resource hosts under
`openai.azure.com` or `services.ai.azure.com`; private endpoints and redirects are rejected.

Server defaults accept `DEMO_LLM_PROVIDER` and `DEMO_LLM_MODEL`; otherwise the toolkit's
provider environment model is preserved. The default OpenAI/Azure model is `gpt-6-luna`.
Azure model values are deployment names. `gpt-6-sol`, `gpt-6-astra`, and the `gpt-5.6`
family can be selected where available. Vision Extractor's server-side menu can be set
with comma-separated `DEMO_OPENAI_MODELS`, `DEMO_CLAUDE_MODELS`, and `DEMO_GOOGLE_MODELS`.
Aitta defaults to `google/gemma-4-31b-it`, which passed the integration's text, schema,
extraction and vision checks. Cold starts can take several minutes.

### Prerequisites

- Node.js 22+ / bun
- Python 3.11+
- Azure OpenAI access (or another supported provider)

### Setup

**Install dependencies:**

```bash
cd implementation_layer/toolkit_demo_app
bun install
uv sync    # API dependencies; gaik comes from this repository as an editable install
```

**Configure environment:**

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```bash
BACKEND_URL=http://localhost:8000
AZURE_API_KEY=...
AZURE_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_API_VERSION=latest
BYPASS_AUTH=true
```

**Run both servers** (from `implementation_layer/toolkit_demo_app`):

```bash
bun dev:all        # frontend + API together

# or separately
bun dev            # frontend
bun dev:api        # API: uv run uvicorn api.main:app --reload
```

- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

### Docker

```bash
docker compose up --build
```

## Project Structure

```
toolkit_demo_app/
├── app/                    # Next.js pages
│   ├── (home)/             # Landing page, privacy
│   ├── (auth)/             # sign-in, sign-up, access-pending
│   ├── (demos)/            # All demo pages
│   └── admin/              # Admin dashboard
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── routers/            # One module per feature
│   └── scripts/            # Seed and verification scripts
├── components/             # React components (shadcn/ui, ai-elements)
├── lib/                    # API client, SSE, Supabase
├── proxy.ts                # API proxy (Next.js 16)
├── openshift/              # Rahti/OpenShift deployment configs
└── docker-compose.yml
```

## API Endpoints

| Prefix | Description |
| --- | --- |
| `/health` | Health check |
| `/parse` | Parse PDF/DOCX documents |
| `/classify` | Classify documents |
| `/extract` | Extract structured data |
| `/extract-vision` | One-call vision extraction for PDFs/images |
| `/transcribe` | Transcribe audio/video |
| `/text-to-speech` | Text-to-speech audio generation |
| `/pipeline` | End-to-end pipelines (audio/document to structured data) |
| `/rag` | RAG pipeline (indexing, Q&A with SSE, debug) |
| `/postgres-agent` | Natural-language SQL agent against the demo DB |
| `/tabular-agent` | CSV/Excel upload → session → natural-language SQL over DuckDB |
| `/llm-judge` | LLM-as-judge: text-pair, hallucination, validate, multi-model panel |
| `/diary` | Construction diary workflow |
| `/dental-transcribe` | Dental transcription with SRT/VTT |
| `/video-search` | Semantic dental video search |
| `/luvata-order` | Purchase order processing with BOM matching and line-item pricing |
| `/report-writer` | Mixed-source report generation |
| `/wizard` | Solution Configuration Wizard (optional; needs the Azure Foundry env vars) |

API docs: <http://localhost:8000/docs> (Swagger UI)

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS v4, shadcn/ui
- **Backend:** FastAPI, Python 3.11+, GAIK toolkit (PyPI)
- **Package managers:** bun (frontend), uv (backend)
- **Auth:** Supabase
- **Deployment:** CSC Rahti 2 (OpenShift) — see `openshift/README.md`
