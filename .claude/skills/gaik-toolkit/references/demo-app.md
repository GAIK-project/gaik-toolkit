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

- **Public:** `(home)` (`/`, `/privacy`, `/desktop-app`, `/prompts`, `/skills`) and `(auth)` (`/sign-in`, `/sign-up`, `/access-pending`).
- **Demo pages** under `(demos)` are open to look at; running one needs a signed-in, approved account, or a pending one within the trial allowance (`lib/trial.ts`) or on the user's own model key, enforced on the API requests in `proxy.ts` (`lib/api-access.ts`). Visitors who cannot run see a "View only" notice.
- **Report Writer** additionally enforces a per-user quota (`REPORT_WRITER_MAX_REPORTS`, default 5) in `app/api/report-writer/run/route.ts`. Admins manage it in the `/admin` "Report Writer Usage" tab: per-user counts/tokens, **Reset**, and a per-user **limit override** (`access_requests.report_limit_override`; e.g. demo/team accounts → Unlimited).
- **Solution Wizard**: `/solution-wizard` links to Wizard V2 (`WIZARD_V2_URL`) and offers the first wizard in the browser (`/solution-wizard/first`). Its API `/api/wizard` needs the per-user `wizard_access` grant from `/admin`, for reads too (`lib/api-access.ts`, `wizardRefusal`), and the API answers 503 without `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_FOUNDRY_API_KEY` and `ANTHROPIC_FOUNDRY_RESOURCE` (`api/routers/solution_wizard.py`).
- **Model settings** let a user run supported demos on their own OpenAI/Azure/Aitta key. The key lives only in the tab's memory and travels as the `x-gaik-model-settings` header to the POST paths allowlisted in both `api/utils/model_settings.py` (`_PATHS`) and `lib/model-settings.ts` (`SUPPORTED_PATHS`); routers pick it up through `get_api_config()`.
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
│   └── utils/               # config.py, pdf_generator.py, sse.py and other helpers
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

One folder per demo under `app/(demos)/`; the Solution Wizard page is in `app/(wizard)/`.

## API Routes

`api/main.py` mounts one router per feature from `api/routers/`, and each `include_router`
line names its prefix (`luvata_order` sets its own in the router). Read the router to see which
gaik components a demo calls.

API docs at `http://localhost:8000/docs` when `DEMO_API_DOCS=true` is set in `.env.local` (as in `.env.example`).

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
AZURE_DEPLOYMENT=gpt-6-luna
AZURE_API_VERSION=2025-03-01-preview

# Or standard OpenAI / CSC Aitta
OPENAI_API_KEY=your-key
AITTA_API_KEY=your-token

# Optional server model override (else the provider's defaults apply)
DEMO_LLM_PROVIDER=azure
DEMO_LLM_MODEL=gpt-6-luna

# Supabase (auth + database)
NEXT_PUBLIC_SUPABASE_URL=your-url
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-key
SUPABASE_SECRET_KEY=your-key

# Text-to-Speech (Azure; see api/.env.example)
AZURE_TTS_MODEL=tts-hd
TTS_ENDPOINT=https://<resource>.cognitiveservices.azure.com/openai/deployments/tts-hd/audio/speech?api-version=2025-03-01-preview

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
    - `haproxy.router.openshift.io/proxy-body-size: 128m` (for large uploads)
    - `haproxy.router.openshift.io/response-buffering: "off"` (for SSE streaming)
- **Deploy:** push main to the deploy branch, `git push origin main:deploy/demo-app`. A GitHub
  webhook starts the BuildConfigs in `openshift/buildconfigs.yaml`, and the deployments roll
  out when the new images land. `openshift/deploy.sh api|frontend|all` is the local fallback.
- **Never `oc apply` the deployment manifests:** the live deployments carry env vars set with
  `oc set env` (Allas, `DATABASE_URL`, TTS, report-writer limits) that the manifests lack, and
  applying them drops those.
- **gaik comes from PyPI:** the API image installs the released gaik, not this repository's
  source, so a library fix reaches the demo only after a PyPI release.
- **Docling API:** External parsing service at `DOCLING_API_BASE` (env var in Rahti secret)
