# GAIK Toolkit Demo

Interactive demo application for the [GAIK Toolkit](https://pypi.org/project/gaik/) components.

## Features

- **Extractor** - Extract structured data from documents using natural language
- **Parser** - Parse PDFs and Word documents with multiple backends
- **Classifier** - Classify documents into predefined categories
- **Transcriber** - Transcribe audio/video with Whisper and GPT enhancement

## Quick Start

### Prerequisites

- Node.js 22+
- Python 3.10+
- pnpm
- OpenAI API key

### Development

1. **Install frontend dependencies:**

```bash
pnpm install
```

2. **Install API dependencies:**

```bash
cd api
pip install -r requirements.txt
```

3. **Set environment variables:**

```bash
export OPENAI_API_KEY=your-key-here
```

4. **Run both servers:**

```bash
# Terminal 1: Frontend
pnpm dev

# Terminal 2: API
cd api
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
demo/
├── app/                    # Next.js pages
│   ├── page.tsx           # Landing page
│   ├── extractor/         # Extractor demo
│   ├── parser/            # Parser demo
│   ├── classifier/        # Classifier demo
│   └── transcriber/       # Transcriber demo
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   └── routers/           # API endpoints
├── components/            # React components
└── docker-compose.yml     # Docker setup
```

## API Endpoints

| Endpoint      | Method | Description              |
| ------------- | ------ | ------------------------ |
| `/health`     | GET    | Health check             |
| `/parse`      | POST   | Parse PDF/DOCX documents |
| `/classify`   | POST   | Classify documents       |
| `/extract`    | POST   | Extract structured data  |
| `/transcribe` | POST   | Transcribe audio/video   |

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI, Python 3.11
- **AI:** OpenAI GPT-4, Whisper
