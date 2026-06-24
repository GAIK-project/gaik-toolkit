# Wizard API (S1-1 + S1-3)

FastAPI service for Solution Wizard V2 session persistence.

**Issues:** [#5 S1-1 wizard_sessions](https://github.com/perttiy/gaik-toolkit-configuration-wizard-v2/issues/5) · [#7 S1-3 Session API](https://github.com/perttiy/gaik-toolkit-configuration-wizard-v2/issues/7)

## Setup

```bash
cd implementation_layer/wizard_api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Requires a running Postgres 15+ database. Docker Compose stack: task #8 (S1-12).

## Migrations

```bash
alembic upgrade head
```

## Run API

```bash
uvicorn wizard_api.main:app --reload --port 8100
curl http://localhost:8100/health
```

## Session API (S1-3)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create session (`user_id`, optional `output_dir`, `metadata`) |
| `GET` | `/sessions?user_id=` | List sessions for user (newest first) |
| `GET` | `/sessions/{id}` | Get session state |
| `PATCH` | `/sessions/{id}` | Update `step`, `gate_statuses`, `metadata` |

Example:

```bash
# Create
curl -s -X POST http://localhost:8100/sessions \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo","metadata":{"use_case":"PO PDFs"}}' | jq

# Resume / update (stub progress for Sprint 1 demo)
curl -s -X PATCH "http://localhost:8100/sessions/<id>" \
  -H 'Content-Type: application/json' \
  -d '{"step":3,"gate_statuses":{"gate_1":"approved"}}' | jq

# List
curl -s "http://localhost:8100/sessions?user_id=demo" | jq
```

If `output_dir` is omitted on create, the API sets  
`$WIZARD_SESSION_OUTPUT_ROOT/<user_id>/<session_id>` (see `.env.example`).

## Tests

```bash
pytest
```

Model tests run without Postgres. API persistence tests skip automatically if DB is unavailable.

## Model: `wizard_sessions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | string | indexed, per-user isolation |
| step | int | 1–12 |
| gate_statuses | JSONB | gate_1 … gate_4 |
| metadata | JSONB | session metadata |
| output_dir | string | session artefact path |
| created_at / updated_at | timestamptz | auto |

Blueprint versioning: task #6 (S1-2).
