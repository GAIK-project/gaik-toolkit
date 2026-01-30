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

- Node.js 22+
- Python 3.10+
- bun
- OpenAI API key

### Development

1. **Install frontend dependencies:**

```bash
bun install
```

2. **Install API dependencies:**

```bash
cd ../../implementation_layer/api
pip install -r requirements.txt
```

3. **Set environment variables:**

```bash
export OPENAI_API_KEY=your-key-here
```

4. **Run both servers:**

```bash
# Terminal 1: Frontend
bun dev

# Terminal 2: API
cd ../../implementation_layer/api
uvicorn main:app --reload
```

- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

### Docker

```bash
# Set your API key
export OPENAI_API_KEY=your-key-here

# Run both services
docker compose up --build
```

## Project Structure

```
toolkit_demo_app/
├── app/                    # Next.js pages
│   ├── page.tsx           # Landing page
│   ├── extractor/         # Extractor demo
│   ├── parser/            # Parser demo
│   ├── classifier/        # Classifier demo
│   ├── transcriber/       # Transcriber demo
│   └── rag/               # RAG Builder demo
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   └── routers/           # API endpoints
├── components/            # React components
└── docker-compose.yml     # Docker setup
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
- **Backend:** FastAPI, Python 3.11
- **AI:** OpenAI GPT-4, Whisper
