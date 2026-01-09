# GAIK API

A lightweight REST API for audio transcription and document parsing. Uses [GAIK Toolkit](https://github.com/GAIK-project/gaik-toolkit) building blocks components.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcribe` | POST | Whisper transcription (mp3, wav, mp4, m4a, webm, ogg, flac) |
| `/parse` | POST | PDF/DOCX parsing (pymupdf, docx, vision) |
| `/health` | GET | Health check |

## Installation

```bash
# From project root
cd gaik-toolkit
pip install -e ".[all]"
pip install -r api/requirements.txt
```

## Usage

```bash
# Development mode
cp api/.env.example api/.env
# Edit .env and set API_KEY and Azure/OpenAI credentials

DEBUG=true uvicorn api.main:app --reload

# Production
uvicorn api.main:app --host 0.0.0.0 --port 8000
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

# DOCX parsing
curl -X POST http://localhost:8000/parse \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.docx"
```

## Docker

```bash
docker build -t gaik-api -f api/Dockerfile .
docker run -p 8000:8000 --env-file api/.env gaik-api
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

## Deployment (CSC Rahti 2)

Deploy as a container using the provided Dockerfile. Configure OpenShift manifests (Deployment, Service, Route, ConfigMap, Secret) according to your environment.
