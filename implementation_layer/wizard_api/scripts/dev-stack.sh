#!/usr/bin/env bash
# Start full Sprint 1 demo stack: Postgres + wizard_api + UI (Docker Compose).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export NEXT_SERVER_ACTIONS_ENCRYPTION_KEY="${NEXT_SERVER_ACTIONS_ENCRYPTION_KEY:-dev-compose-encryption-key-32chars!!}"

echo "==> Building and starting Postgres + wizard-api + wizard-ui"
docker compose up --build -d

echo "==> Waiting for Postgres"
docker compose up -d --wait postgres

echo "==> Waiting for API (http://localhost:8100/health)"
for i in $(seq 1 60); do
  if curl -sf http://localhost:8100/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -sf http://localhost:8100/health >/dev/null 2>&1; then
  echo "ERROR: wizard-api not healthy — try: docker compose logs wizard-api"
  exit 1
fi

echo "==> Waiting for UI (http://localhost:3000/login)"
for i in $(seq 1 90); do
  if curl -sf http://localhost:3000/login >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -sf http://localhost:3000/login >/dev/null 2>&1; then
  echo "ERROR: wizard-ui not ready — try: docker compose logs wizard-ui"
  exit 1
fi

echo ""
echo "Stack is up."
echo "  UI:  http://localhost:3000"
echo "  API: http://localhost:8100/health"
echo ""
echo "Dev login: dev@gaik.local / gaik  ·  dev2@gaik.local / gaik2"
echo ""
echo "Logs:  docker compose logs -f"
echo "Stop:  docker compose down"
