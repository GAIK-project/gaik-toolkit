# GAIK Toolkit Demo

Interactive demo application for the [GAIK Toolkit](https://pypi.org/project/gaik/) components.

## Features

- **Extractor** - Extract structured data from documents using natural language
- **Parser** - Parse PDFs and Word documents with multiple backends
- **Classifier** - Classify documents into predefined categories
- **Transcriber** - Transcribe audio/video with Whisper and GPT enhancement
- **RAG Builder** - Build retrieval-augmented generation pipelines with document upload and Q&A

## Quick Start

### Prerequisites

- Node.js 22+ / bun
- Python 3.11+
- Azure OpenAI API key (or OpenAI API key)

### Setup

1. **Clone and install frontend dependencies:**

```bash
cd implementation_layer/toolkit_demo_app
bun install
```

2. **Install API dependencies:**

```bash
cd api
pip install -r requirements.txt
```

3. **Configure environment:**

```bash
cp .env.example .env.local
```

Edit `.env.local` with your settings. Minimal setup for local development:

```bash
# Backend API
BACKEND_URL=http://localhost:8000

# Azure OpenAI (required for AI features)
AZURE_API_KEY=your-key
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_API_VERSION=2025-03-01-preview

# Development mode - bypass Supabase auth
BYPASS_AUTH=true
```

See `.env.example` for all available options (Supabase auth, Redis rate limiting, PostHog analytics).

4. **Run both servers:**

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
│   ├── (demos)/            # Demo pages
│   │   ├── extractor/
│   │   ├── parser/
│   │   ├── classifier/
│   │   ├── transcriber/
│   │   └── rag/
│   └── admin/              # Admin dashboard
├── api/                    # FastAPI backend
│   ├── main.py
│   └── routers/
├── components/             # React components
└── docker-compose.yml
```

## API Endpoints

| Endpoint      | Method | Description                     |
| ------------- | ------ | ------------------------------- |
| `/health`     | GET    | Health check                    |
| `/parse`      | POST   | Parse PDF/DOCX documents        |
| `/classify`   | POST   | Classify documents              |
| `/extract`    | POST   | Extract structured data         |
| `/transcribe` | POST   | Transcribe audio/video          |
| `/rag`        | POST   | RAG pipeline with SSE streaming |

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI, Python 3.11, GAIK toolkit
- **AI:** Azure OpenAI GPT-4, Whisper
