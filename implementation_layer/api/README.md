# GAIK API

Lightweight REST API for audio transcription, document parsing, and structured data extraction. Uses [GAIK Toolkit](https://github.com/GAIK-project/gaik-toolkit) building blocks.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcribe` | POST | Whisper transcription (mp3, wav, mp4, m4a, webm, ogg, flac) |
| `/parse` | POST | PDF/DOCX parsing (pymupdf, docx, vision) |
| `/pipeline/diary` | POST | Generate construction diary from audio |
| `/pipeline/incident-report` | POST | Generate incident report from audio/text/document |
| `/pipeline/pdf/{job_id}` | GET | Download generated PDF |
| `/health` | GET | Health check |

## Installation

```bash
cd gaik-toolkit
pip install -e ".[all]"
pip install -r implementation_layer/api/requirements.txt
```

## Usage

```bash
cp implementation_layer/api/.env.example implementation_layer/api/.env
# Edit .env and set API_KEY and Azure/OpenAI credentials

# Development
DEBUG=true uvicorn implementation_layer.api.main:app --reload

# Production
uvicorn implementation_layer.api.main:app --host 0.0.0.0 --port 8000
```

## API Calls

```bash
# Transcription
curl -X POST http://localhost:8000/transcribe \
  -H "X-API-Key: your-api-key" \
  -F "file=@audio.mp3" \
  -F "enhanced=true"

# PDF parsing
curl -X POST http://localhost:8000/parse \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.pdf" \
  -F "parser_type=pymupdf"

# Construction diary from audio
curl -X POST http://localhost:8000/pipeline/diary \
  -H "X-API-Key: your-api-key" \
  -F "file=@site_report.mp3"

# Incident report from text
curl -X POST http://localhost:8000/pipeline/incident-report \
  -H "X-API-Key: your-api-key" \
  -F "text=Employee slipped on wet floor in warehouse area B"
```

## Docker

```bash
docker build -t gaik-api -f implementation_layer/api/Dockerfile .
docker run -p 8000:8000 --env-file implementation_layer/api/.env gaik-api
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `API_KEY` | X-API-Key authentication | Yes |
| `USE_AZURE` | Use Azure OpenAI (true/false) | No (default: true) |
| `AZURE_API_KEY` | Azure API key | If USE_AZURE=true |
| `AZURE_ENDPOINT` | Azure endpoint | If USE_AZURE=true |
| `OPENAI_API_KEY` | OpenAI API key | If USE_AZURE=false |
| `DEBUG` | Debug mode, shows /docs | No (default: false) |
