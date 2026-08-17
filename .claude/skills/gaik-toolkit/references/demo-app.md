# Demo App Reference

Interactive web application for the GAIK toolkit at `implementation_layer/toolkit_demo_app/`.

**Live:** https://gaik-demo.2.rahtiapp.fi/ (registration required)

## Contents
- [Tech Stack](#tech-stack)
- [Dev Commands](#dev-commands)
- [Conventions](#conventions)
- [Project Structure](#project-structure)
- [Demo Pages](#demo-pages)
- [API Routes](#api-routes)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)

## Tech Stack

- **Frontend:** Next.js 16, React 19, TypeScript
- **Backend:** FastAPI, Python 3.11+, GAIK toolkit (PyPI)
- **Package managers:** bun (frontend), uv (backend) -- not npm/pip
- **Styling:** Tailwind CSS v4 with `globals.css` theme variables
- **UI components:** shadcn/ui (Radix UI primitives)
- **Auth:** Supabase (auth + database)
- **Rate limiting:** Upstash Redis
- **Analytics:** PostHog
- **Animations:** Motion (Framer Motion alternative)

## Dev Commands

```bash
cd implementation_layer/toolkit_demo_app

# Run both frontend + API concurrently
bun run dev:all

# Frontend only (Next.js at localhost:3000)
bun dev

# API only (FastAPI at localhost:8000)
bun run dev:api
# Or directly: cd api && uvicorn main:app --reload

# Linting
bun run lint

# DB tunnel (port-forward to Rahti pgvector)
bun run db:tunnel

# Docker
docker compose up --build
```

## Conventions

From `implementation_layer/toolkit_demo_app/CLAUDE.md`:

1. **Use gaik toolkit** from PyPI -- backend API uses `gaik` package components
2. **Use bun and uv**, not npm/pip
3. **API proxy:** `proxy.ts` handles Next.js 16 API proxying to FastAPI backend (replaced middleware.ts)
4. **Tailwind v4:** Use `globals.css` theme variables for styling
5. **UI components:** Prefer shadcn/ui components (Accordion, Card, Button, Select, etc.)

## Access model

- **Public:** `(home)` (`/`, `/privacy`) and `(auth)` (`/sign-in`, `/sign-up`, `/access-pending`).
- **All demos** (everything under `(demos)`) require **login + admin approval** — enforced by `PROTECTED_ROUTES` in `lib/supabase/proxy.ts` (pages) plus a login+approval gate on heavy `/api` POSTs in `proxy.ts`. When adding a new demo route, add it to `PROTECTED_ROUTES`.
- **Report Writer** additionally enforces a per-user quota (`REPORT_WRITER_MAX_REPORTS`, default 5) in `app/api/report-writer/run/route.ts`. Admins manage it in the `/admin` "Report Writer Usage" tab: per-user counts/tokens, **Reset**, and a per-user **limit override** (`access_requests.report_limit_override`; e.g. demo/team accounts → Unlimited).
- **Solution Wizard** needs a per-user `wizard_access` grant (or team `?key=`), independent of approval.
- `BYPASS_AUTH=true` opens everything in local dev.

## Project Structure

```
toolkit_demo_app/
├── app/
│   ├── (home)/              # Landing page, privacy
│   ├── (auth)/              # sign-in, sign-up, access-pending
│   ├── (demos)/             # All demo pages (see below)
│   ├── admin/               # Admin dashboard
│   └── layout.tsx           # Root layout
├── api/
│   ├── main.py              # FastAPI app with all routers
│   ├── routers/             # One module per feature
│   ├── config.py            # Backend config
│   ├── pdf_generator.py     # PDF output generation
│   └── sse.py               # Server-sent events helper
├── components/
│   ├── ui/                  # shadcn/ui components
│   ├── ai-elements/         # AI chat components (message, streamdown)
│   ├── demo/                # Demo-specific shared components
│   │   ├── demo-page-header.tsx  # Shared Back + title header
│   │   ├── how-it-works-card.tsx # Shared accordion "How It Works"
│   │   ├── file-upload.tsx       # File upload widget
│   │   ├── result-card.tsx       # Result/loading/empty state cards
│   │   └── example-preview-dialog.tsx
│   ├── layout/              # Header, footer, nav, main-layout
│   └── feedback/            # Feedback widgets
├── lib/
│   ├── api-client.ts        # Typed API client
│   ├── sse.ts               # SSE streaming client
│   └── supabase/            # Supabase client setup
├── proxy.ts                 # API proxy (Next.js 16 pattern)
├── openshift/               # Rahti/OpenShift deployment configs
├── docker-compose.yml
└── package.json
```

## Demo Pages

All under `app/(demos)/`:

| Route | Feature | Toolkit Components |
|-------|---------|-------------------|
| `/extractor` | Schema-free structured extraction | SchemaGenerator, DataExtractor |
| `/vision-extractor` | Single-pass PDF/image -> structured data | VisionExtractor |
| `/parser` | Multi-backend PDF/DOCX parsing | VisionParser, PyMuPDFParser, DoclingParser, DocxParser |
| `/classifier` | Zero-shot document classification | DocumentClassifier |
| `/transcriber` | Whisper + GPT enhancement | Transcriber |
| `/rag` | Document upload, indexing, Q&A with citations | RAGWorkflow |
| `/postgres-agent` | Plain-language questions -> read-only SQL over the demo DB | PostgresAgent |
| `/tabular-agent` | Upload CSV/Excel, ask questions -> read-only SQL (DuckDB) | TabularAgent |
| `/llm-judge` | Text-pair judging, hallucination detection, judge panel | LLMJudge, LLMJudgePanel |
| `/audio-structured` | Audio -> structured data pipeline | AudioToStructuredData |
| `/document-structured` | Document -> structured data pipeline | DocumentsToStructuredData |
| `/incident-report` | Voice -> structured incident report | AudioToStructuredData |
| `/diary` | Voice notes -> construction diary | AudioToStructuredData |
| `/dental-transcription` | Audio/video -> SRT/VTT subtitles | ParallelTranscriber, srt_utils |
| `/video-search` | Semantic video search (pgvector) | Embedder, PgVectorStore, video_search_helpers |
| `/text-to-speech` | Text to downloadable speech audio | TextToSpeech |
| `/luvata-order` | PDF order -> structured Luvata data | DocumentsToStructuredData |
| `/report-writer` | Mixed source files -> sectioned Markdown report | MultiSourceReportGenerator |
| `/solution-wizard` | Use-case description -> validated blueprint + PoC | (Claude Agent SDK, wizard skill) |

## API Routes

FastAPI backend at `api/main.py`, routers in `api/routers/`:

| Prefix | Router | Description |
|--------|--------|-------------|
| `/parse` | `parser.py` | Document parsing (PDF, DOCX) |
| `/classify` | `classifier.py` | Document classification |
| `/extract` | `extractor.py` | Structured data extraction |
| `/extract-vision` | `vision_extractor.py` | Single-pass vision extraction (PDF/image -> structured data) |
| `/transcribe` | `transcriber.py` | Audio/video transcription |
| `/pipeline` | `pipeline.py` | End-to-end pipelines (audio/document -> structured data) |
| `/rag` | `rag.py` | RAG pipeline (indexing, Q&A with SSE, debug endpoint) |
| `/postgres-agent` | `postgres_agent.py` | Text-to-SQL agent against the fixed demo DB |
| `/tabular-agent` | `tabular_agent.py` | CSV/Excel upload -> session -> text-to-SQL over DuckDB |
| `/llm-judge` | `llm_judge.py` | LLM-as-judge: text-pair, hallucinations, validate, panel |
| `/diary` | `diary.py` | Construction diary workflow |
| `/dental-transcribe` | `dental_transcription.py` | Dental transcription with SRT/VTT subtitles |
| `/video-search` | `video_search.py` | Semantic dental video search (pgvector) |
| `/luvata-order` | `luvata_order.py` | Purchase order processing with BOM matching |
| `/report-writer` | `report_writer.py` | Mixed-source report generation |
| `/wizard` | `solution_wizard.py` | Solution Configuration Wizard (needs Azure Foundry env vars) |
| `/text-to-speech` | `text_to_speech.py` | Text-to-speech audio generation |
| `/health` | (in main.py) | Health check |

API docs available at `http://localhost:8000/docs` (Swagger UI).

## Environment Variables

Create `.env.local` from `.env.example`:

```bash
# Backend URL (frontend -> API proxy)
BACKEND_URL=http://localhost:8000

# Auth bypass (local dev)
BYPASS_AUTH=true

# Azure OpenAI (for toolkit components)
AZURE_API_KEY=your-key
AZURE_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_DEPLOYMENT=gpt-5.1
AZURE_API_VERSION=2025-03-01-preview

# Or standard OpenAI
OPENAI_API_KEY=your-key

# Supabase (auth + database)
NEXT_PUBLIC_SUPABASE_URL=your-url
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-key
SUPABASE_SECRET_KEY=your-key

# Text-to-Speech
AZURE_TTS_MODEL=gpt-4o-mini-tts
TTS_ENDPOINT=azure  # or "openai"

# Local Transcriber (optional, for local Whisper)
LOCAL_TRANSCRIBER_API_BASE=http://your-whisper-host/v1
LOCAL_TRANSCRIBER_API_KEY=your-key

# PostgreSQL (for PgVectorStore / video search)
DATABASE_URL=postgresql://user:pass@host:5432/db

# Upstash Redis (rate limiting)
UPSTASH_REDIS_REST_URL=your-url
UPSTASH_REDIS_REST_TOKEN=your-token

# Report Writer per-user abuse limits (defaults shown; unset = these values)
REPORT_WRITER_MAX_REPORTS=5
REPORT_WRITER_MAX_TOKENS_PER_REPORT=32000
REPORT_WRITER_MAX_UPLOAD_MB=25
REPORT_WRITER_MAX_SECTIONS=12
REPORT_WRITER_MAX_EVIDENCE_CHARS=200000

# PostHog (analytics, optional)
NEXT_PUBLIC_POSTHOG_KEY=your-key
NEXT_PUBLIC_POSTHOG_HOST=your-host
```

## Deployment

- **Docker:** `docker-compose.yml` builds both frontend and API
- **OpenShift/Rahti:** Configs in `openshift/` directory
  - `deployment-api.yaml` - API deployment (uses placeholder values -- real secrets managed in Rahti)
  - Route: `gaik-demo.2.rahtiapp.fi` with annotations:
    - `haproxy.router.openshift.io/timeout: 15m` (for long-running RAG indexing)
    - `haproxy.router.openshift.io/proxy-body-size: 50m` (for large PDF uploads)
    - `haproxy.router.openshift.io/response-buffering: "off"` (for SSE streaming)
- **Deploy script:** `deploy.sh api|frontend|all` for building and pushing to Rahti registry
- **Docling API:** External parsing service at `DOCLING_API_BASE` (env var in Rahti secret)
