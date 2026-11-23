#!/usr/bin/env bash
# Full Sprint 1 dev stack: Postgres + wizard_api + Next.js UI
set -euo pipefail
WIZARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_ROOT="$WIZARD_ROOT/wizard_api"
UI_ROOT="$WIZARD_ROOT/solution_wizard_v2"

export NEXT_PUBLIC_DEV_AUTH=true
export WIZARD_API_URL="${WIZARD_API_URL:-http://localhost:8100}"
export NEXT_SERVER_ACTIONS_ENCRYPTION_KEY="${NEXT_SERVER_ACTIONS_ENCRYPTION_KEY:-dev-local-encryption-key-32chars!!}"

echo "==> Starting Postgres + wizard_api (background)"
"$API_ROOT/scripts/dev-api.sh" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

echo "==> Waiting for API health"
for i in $(seq 1 60); do
  if curl -sf http://localhost:8100/health >/dev/null; then
    break
  fi
  sleep 1
done

cd "$UI_ROOT"
if [ ! -d node_modules ]; then
  npm ci
fi
echo "==> Starting UI on http://localhost:3000"
exec npm run dev
