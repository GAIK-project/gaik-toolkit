# Wizard API (S1-1)

FastAPI service for Solution Wizard V2 session persistence.

**Issue:** [#5 S1-1 wizard_sessions](https://github.com/perttiy/gaik-toolkit-configuration-wizard-v2/issues/5)

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

## Run API (health only for now)

```bash
uvicorn wizard_api.main:app --reload --port 8100
curl http://localhost:8100/health
```

## Tests

```bash
pytest
```

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

Session REST API: task #7 (S1-3).
