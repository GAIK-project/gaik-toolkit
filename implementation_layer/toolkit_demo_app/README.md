# GAIK Toolkit Demo

Interactive demo application for the [GAIK Toolkit](https://pypi.org/project/gaik/) components.

## Features

- **Extractor** - Extract structured data from documents using natural language
- **Parser** - Parse PDFs and Word documents with multiple backends
- **Classifier** - Classify documents into predefined categories
- **Transcriber** - Transcribe audio/video with Whisper and GPT enhancement
- **RAG Builder** - Document upload, indexing, Q&A with citations and debug tools
- **Audio Structured** - Audio to structured data pipeline
- **Document Structured** - Document to structured data pipeline
- **Incident Report** - Voice to structured incident report
- **Diary** - Voice notes to construction diary
- **Dental Transcription** - Audio/video to SRT/VTT subtitles
- **Video Search** - Semantic video search with pgvector
- **Text-to-Speech** - Text to downloadable speech audio

## Quick Start

### Prerequisites

- Node.js 22+ / bun
- Python 3.11+
- OpenAI API key

### Setup

**Install dependencies:**

```bash
cd implementation_layer/toolkit_demo_app
bun install
uv pip install -r api/requirements.txt
```

**Configure environment:**

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```bash
BACKEND_URL=http://localhost:8000
OPENAI_API_KEY=sk-xxxxx
BYPASS_AUTH=true
```

**Run both servers:**

```bash
# Terminal 1: Frontend
bun dev

# Terminal 2: API
cd api
uvicorn main:app --reload
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
| `/transcribe` | Transcribe audio/video |
| `/rag` | RAG pipeline (indexing, Q&A with SSE, debug) |
| `/pipeline` | End-to-end pipelines (audio/document to structured data) |
| `/diary` | Construction diary workflow |
| `/dental-transcribe` | Dental transcription with SRT/VTT |
| `/video-search` | Semantic dental video search |
| `/text-to-speech` | Text-to-speech audio generation |

API docs: <http://localhost:8000/docs> (Swagger UI)

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS v4, shadcn/ui
- **Backend:** FastAPI, Python 3.11+, GAIK toolkit (PyPI)
- **Package managers:** bun (frontend), uv (backend)
- **Auth:** Supabase
- **Deployment:** CSC Rahti 2 (OpenShift) — see `openshift/README.md`
