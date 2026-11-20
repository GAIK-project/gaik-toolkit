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
- **Schema Generator** - Extraction requirements → reusable Pydantic models
- **Source Normalizer** - Documents, spreadsheets, recordings and images → Markdown that keeps each file's name
- **Web Scraper** - A website → clean Markdown and structured data
- **Knowledge Curator** - Verified facts per topic, each with its exact quote and location
- **Knowledge Synthesizer** - A reviewed, source-grounded report from curated facts

### Source tracing (Trace sources)

The Extractor and Vision Extractor pages have a **Trace sources** option. It is done by
the demo around the extractor components, not by the components themselves
(`api/utils/citations.py`):

1. The schema gets one more field, `field_sources`, and the prompt asks for one entry per
   value: field path, document, page and a short verbatim quote. The model never gives
   coordinates.
2. Plain code looks for the quote in the PDF's text layer (PyMuPDF, two reading orders;
   case, spacing and punctuation ignored, no fuzzy matching). The matched words give the
   highlight box. The page the model named is tried first.
3. The extracted value must be inside its quote; numbers and dates are compared as numbers
   and dates (`3.000 kg` = `3000`, `11.04.2025` = `2025-04-11`). Schema codes such as
   `not_ok` are left unchecked.
4. A quote missing from the PDF, or one that does not hold its value, is flagged on the
   Sources tab. Images have no text layer and are shown as unchecked; pasted text is
   checked without a page view.

It works with any extractor that returns those quotes, as long as the original PDF has a
text layer. It roughly triples the output tokens of an extraction.

### Software Modules

- **RAG Builder** - Document upload, indexing, Q&A with citations and debug tools
- **Audio Structured** - Audio to structured data pipeline
- **Document Structured** - Document to structured data pipeline
- **Report Writer v2** - A report in stages (normalize, curate, synthesize, review), every file editable in between

### Use Cases

- **Incident Report** - Voice to structured incident report
- **Construction Diary** - Voice notes to construction diary
- **Dental Transcription** - Audio/video to SRT/VTT subtitles
- **Semantic Video Search** - Vector search across indexed video transcripts (pgvector)
- **Purchase Order Processing** - PO + BOMs + price list → line-item prices and order draft (`luvata-order` route)
- **Report Writer** - Mixed-source report generation from documents, spreadsheets, images, audio/video, text, and an optional sample report/template
- **Helpdesk Chatbot** - Answers from your own services and FAQ, and hands over to a person

### Solution Wizard

`/solution-wizard` is open to every visitor and offers two wizards.

- **Wizard V2** runs as its own service, where each session's agent and PoC runs are
  kept apart from other services. The page links to `WIZARD_V2_URL` when that is set;
  the server reads it at run time, so a deployment sets it with `oc set env` and needs
  no rebuild.
- **The first wizard** runs in the browser at `/solution-wizard/first`, and on anyone's
  own computer as a Claude Code skill (the page shows the commands). In the browser its
  agent is a Claude Agent SDK session inside the demo API pod, with shell tools, so it
  is held tighter than the other demos:
  - `proxy.ts` forwards `/api/wizard/*`, reads included, only for a signed-in user an
    admin has granted the wizard in `/admin` (`wizard_access`), on top of the approval
    and rate limit every state-changing request meets. There is no shared key.
  - A session belongs to the user who started it: the proxy names the user to the API
    and another user's session answers 404.
  - At most `WIZARD_MAX_SESSIONS` (3) sessions run at once, one per user, each with at
    most `WIZARD_MAX_MESSAGES` (60) messages. A session idle for 30 minutes is ended.
  - `WIZARD_AGENT_MAX_BUDGET_USD`, off unless set, stops a session's agent when the CLI's
    estimated cost reaches it; the session then takes no more messages, and its files
    stay to download.
  - Attachments (5 per message, 10 MB each) are checked for type, size and content
    before a parser or a model reads them, and reach the agent marked as data.
  - A session's workspace and download archives are removed when it ends or goes idle.
    Sessions are not recorded: the Langfuse diagnostics were not brought back.
  - The agent's process does not inherit the API's other credentials. This is not a
    boundary: the agent runs as the same user in the same container as the API.

  It needs `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_FOUNDRY_API_KEY` and
  `ANTHROPIC_FOUNDRY_RESOURCE` on the API; without them the page says the wizard is
  not set up. The model is `ANTHROPIC_MODEL` or `ANTHROPIC_DEFAULT_SONNET_MODEL`.

### No-code Assets

- **Agent skills** (`/skills`) - Download each skill as a .zip, install the coding-agent plugin, and open a "try this" prompt in Claude, Claude Code or Cursor
- **Prompts** (`/prompts`) - Copy a prompt, or copy it and open ChatGPT or Claude
- **Desktop app** (`/desktop-app`) - Download the experimental desktop app and its install steps

Both pages are public and read `lib/no-code/catalog.generated.json` and `public/downloads/skills/*.zip`. Those are generated from `implementation_layer/no-code-assets`, because the image is built from this folder alone. After changing a skill, a prompt or `no-code-assets/catalog.json`, run:

```bash
uv run python implementation_layer/toolkit_demo_app/scripts/build_no_code_catalog.py
```

and commit the result; a unit test fails while the generated files are stale.

## Quick Start

The **model menu** in the nav shows which model runs the current demo. Signed-in users
can switch among the server's own models without a key. `GET /api/model-settings/server`
lists them, and the API checks the `x-gaik-server-model` header against that list.
By default these are GPT-6 Sol (the server default, set with `DEMO_LLM_MODEL`), GPT-6 Luna,
Claude Haiku 5.5, Claude Sonnet 5.5 and Gemini 3.8 Flash for everyone, and GPT-6.2 Sol, GPT-6.1 Sol,
GPT-6 Astra, Claude Opus 5.5, Gemini 4 Argon and Gemini 4 Carbon for the GAIK team only: the admin, the `DEMO_USER_NAME`
account, `haaga-helia.fi` addresses and anyone in `MODEL_STAFF_EMAILS`. The proxy
decides this from the session and tells the API in `x-gaik-model-tier`; a browser cannot
set it. A provider without credentials on the server is left out, and
`DEMO_SERVER_MODELS=provider:model[:staff],…` replaces the list. With Claude or Gemini
picked, the audio demos still transcribe on the server (local Whisper, else
`gpt-4o-transcribe`) and the picked model extracts. Results name both models.

With a GPT-6 model in use, on the server's key or the user's own, the menu also has a
**Reasoning** row: Auto, Low, Medium or High. Auto sends nothing, and each model keeps the
effort the API chooses for it. Another choice travels in `x-gaik-reasoning-effort` on the
routes that take a picked model; the API accepts `low`, `medium` and `high`, treats
anything else as Auto, and applies it to GPT-6 models only. The Report Writer and
Knowledge Curator steps keep their own effort settings, and so does the Vision Extractor
while it runs on its own model choice.

A route that takes a model name in the request runs only the models it offers, and a
team-only model only for the team, decided from the session as above. Which models are
team-only follows the list above (a `DEMO_SERVER_MODELS` entry decides for the model it
names), whatever credentials the server has. The LLM Judge and the Vision Extractor
offer the Vision Extractor's model list; the Report Writer, Report Writer v2, Source
Normalizer, Knowledge Curator and Knowledge Synthesis offer the server's model, the
listed models on the same provider and `DEMO_EXTRA_CHAT_MODELS` (default
`gpt-6-luna,gpt-5.5-deployment`, the Report Writer page's defaults), and for
transcription `DEMO_TRANSCRIPTION_MODELS` (default
`gpt-4o-transcribe,gpt-4o-mini-transcribe,whisper-1,whisper`).
Another name is refused with a 422, which lists the names that work, before any model call.

Gemini on Vertex AI: leave `GOOGLE_CLOUD_LOCATION` unset. gaik 0.10.0 and later then ask
the EU multi-region first and uses the global endpoint for a model the EU does not
serve, or for ten minutes after the EU failed to answer; each switch is a warning in
the API log. A location you set is used as given, with no fallback: on 2026-11-16 the
demo ran with `GOOGLE_CLOUD_LOCATION=eu` on gaik 0.9.1 and Gemini 4 Argon timed out on
every request, so it went back to `global`. The Vision Extractor's own Gemini calls
take a fixed `GOOGLE_GENERATE_CONTENT_URL` (see `.env.example`) and have no fallback.
The deployed demo calls GPT and Claude through an Azure resource in Sweden.

`DEMO_SERVER_MODELS_NOTE` is one sentence the menu shows under the server models,
for where they run (for example the Azure region). It has no default: that depends on
the cloud resources behind the keys.

With `AITTA_API_KEY` set, the menu also lists **CSC Aitta** models (Gemma 4 31B and
gpt-oss 120B by default): open models hosted in Finland. Picking one keeps the whole
run on Aitta: recordings are transcribed by Aitta's Whisper large v3
(`AITTA_TRANSCRIPTION_MODEL`), the Transcriber uses it too, and RAG embeds with
`intfloat/multilingual-e5-large` (`AITTA_EMBEDDING_MODEL`). Nothing falls back to
another provider. Aitta models are slower (a run takes from 20 seconds to minutes),
the menu marks a text-only model and an idle one, and a demo that sends page images
refuses a text-only model before the call. Aitta stops idle models, so a pick also
asks Aitta to start its speech and embedding models, and the page says when one is
still idle. On every demo page a notice says which
model runs it once the user has left the default, and says so when the demo does not
take the picked model. Aitta is a research service: its terms forbid personal data,
its token is bound to one CSC user and expires after 90 days, and its rate limit is
per user and minute. What was tested is in
[docs/MODEL_REQUIREMENTS.md](docs/MODEL_REQUIREMENTS.md).

**Use your own key…** in the same menu lets users select their own OpenAI, Azure OpenAI
or CSC Aitta account. Enter the model/deployment and key; Azure also needs its public
resource endpoint. **Test connection** makes one small chat request. **Use this key**
activates it for this browser tab until refresh, navigation away or sign-out. **Clear
own model** returns to the server models. A run on an own key needs a signed-in account,
approved, or pending with a confirmed e-mail address; it spends no trial run.

Own settings apply to Extractor, Schema Generator, Classifier, LLM-based Parser modes,
Vision Extractor, PostgreSQL Agent questions and single LLM Judge tasks.
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
provider environment model is preserved. The library default for OpenAI/Azure is `gpt-6-luna`; the demo server runs `gpt-6-sol` through `DEMO_LLM_MODEL`.
Azure model values are deployment names. `gpt-6-sol`, `gpt-6-astra`, and the `gpt-5.6`
family can be selected where available. Vision Extractor's server-side menu can be set
with comma-separated `DEMO_OPENAI_MODELS`, `DEMO_CLAUDE_MODELS`, and `DEMO_GOOGLE_MODELS`
(default `gemini-3.8-flash,gemini-4-argon,gemini-4-carbon`, the Gemini 4 models for the team
only). With a CSC Aitta model picked, the Vision Extractor refuses to run: on 2026-11-19 Gemma 4
31B took 5 to 15 minutes per receipt and Aitta refused a scanned page as too large
(`docs/MODEL_REQUIREMENTS.md`).
Aitta defaults to `google/gemma-4-31b-it`, which passed the integration's text, schema,
extraction and vision checks. Cold starts can take several minutes.

A signed-out visitor sees **Sign in** in the nav instead of the model menu: every run
needs an account.

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
- API Docs: http://localhost:8000/docs (with `DEMO_API_DOCS=true` in `.env.local`, as in `.env.example`)

### Docker

```bash
docker compose up --build
```

### Pinned images and the API lock

The images build from pinned base images and Python packages, so a rebuild of
the same commit installs the same ones. The API image's system packages (ffmpeg,
tesseract, pandoc) still come from the Debian mirror at build time, and
`Dockerfile.pnpm` is not pinned.

- `Dockerfile` and `api/Dockerfile` name each base image by tag and digest
  (`oven/bun:1.4.4@sha256:…`). Dependabot proposes new ones once a month. To
  move one by hand, look up the digest of the new tag and replace both:

  ```bash
  docker buildx imagetools inspect oven/bun:1.4.4 | grep -m1 Digest
  ```

  Take the digest of the multi-platform index (the first `Digest:` line), not
  of one platform's image.
- The API image installs every Python package from `api/requirements.lock`,
  pinned with its hashes (`uv pip install --require-hashes`); a file whose hash
  is not in the lock fails the build. `api/requirements.txt` stays the list to
  edit, with the gaik pin. After changing it, write the lock again and commit
  both:

  ```bash
  scripts/lock_api_requirements.sh            # keeps the other pins as they are
  scripts/lock_api_requirements.sh --upgrade  # takes the newest allowed releases
  ```

  Nothing refreshes the lock on its own: run it with `--upgrade` now and then to
  take security releases. The lock is for the image: Python 3.12 on linux
  x86_64, with torch and torchvision as CPU builds from the PyTorch index. It
  records the sha256 of the `requirements.txt` it was made from, and
  `api/tests/test_api_image_pins.py` fails when that file has changed since, or
  when a base image has no digest.

## Project Structure

```
toolkit_demo_app/
├── app/                    # Next.js pages
│   ├── (home)/             # Landing page, privacy
│   ├── (auth)/             # sign-in, sign-up, access-pending
│   ├── (demos)/            # All demo pages
│   ├── (wizard)/           # Solution Wizard page (both wizards)
│   ├── api/                # Next route handlers
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
| `/extract` | Extract structured data; `/extract/trace` locates its quotes in the PDF |
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
| `/report-writer-v2` | Staged report writer (normalize, curate, synthesize) |
| `/source-normalizer` | Mixed files → Markdown |
| `/knowledge-curator` | Facts with verified quotes |
| `/knowledge-synthesis` | Report from curated facts |
| `/schema-generator` | Extraction schema from requirements |
| `/web-scraper` | Web page or site → Markdown |
| `/model-settings` | Server model list, Aitta warm-up and the own-key connection test |
| `/wizard` | First Solution Wizard sessions (per-user grant) |

API docs: <http://localhost:8000/docs> (Swagger UI), served only with `DEMO_API_DOCS=true`;
the deployed API leaves `/docs`, `/redoc` and `/openapi.json` off.

## Tech Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS v4, shadcn/ui
- **Backend:** FastAPI, Python 3.11+, GAIK toolkit (PyPI)
- **Package managers:** bun (frontend), uv (backend)
- **Auth:** Supabase
- **Deployment:** CSC Rahti 2 (OpenShift) — see `openshift/README.md`

## Optional GAIK Ops reporting

The demo API can report operational events to a GAIK Ops instance. Leave both
`OPS_URL` and `OPS_INGEST_KEY` unset to disable reporting completely. Neither the
`gaik` library nor a copied customer project requires this service.

When enabled, the demo reports successful POST/PUT/PATCH/DELETE operations and
HTTP server failures with a request trace, route template, status and duration.
The LLM Judge endpoints also report the model/provider and numeric usage records
returned by the judge. Other demos currently provide operation traces, not model
or token accounting. A matched route template is used instead of a request URL;
request bodies, documents, headers, user identifiers, exception messages and model
responses are not collected.

Delivery is best effort in daemon threads with a three-second HTTP timeout, no
retries, at most four concurrent sends and 60 attempts per minute per API process.
Excess events are dropped; process shutdown can also lose pending events. A slow,
misconfigured or unavailable monitor never changes the demo's response. These
limits apply to event delivery; critical email alert limits belong to GAIK Ops.

Tests: `api/tests/test_ops.py` covers missing settings, delivery failure, limits,
content filtering, exception handling and unchanged streaming responses.
