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
- OpenAI API key

### Setup

**Install dependencies:**

```bash
cd implementation_layer/toolkit_demo_app
bun install
pip install -r api/requirements.txt
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
- **AI:** OpenAI GPT-5.1, Whisper
