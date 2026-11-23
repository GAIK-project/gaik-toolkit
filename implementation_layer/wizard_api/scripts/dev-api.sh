#!/usr/bin/env bash
# Start wizard_api with Postgres (docker) + uvicorn on :8100
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

docker compose up -d postgres
echo "Waiting for Postgres..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U wizard -d wizard >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -e ".[dev]"
fi
pip install -e "../solution_wizard"

export WIZARD_DATABASE_URL="${WIZARD_DATABASE_URL:-postgresql+psycopg://wizard:wizard@localhost:5432/wizard}"
export WIZARD_SESSION_OUTPUT_ROOT="${WIZARD_SESSION_OUTPUT_ROOT:-/tmp/wizard-sessions}"

alembic upgrade head
exec uvicorn wizard_api.main:app --reload --host 0.0.0.0 --port 8100
