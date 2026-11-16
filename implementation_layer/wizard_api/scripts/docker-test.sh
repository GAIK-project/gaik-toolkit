#!/usr/bin/env bash
# Run wizard_api + solution_wizard_v2 tests entirely in Docker.
# Progress is streamed to stdout with timestamps — safe to run in a local terminal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test)
COMPOSE_STACK=(docker compose -f docker-compose.yml -f docker-compose.test.yml --profile stack-e2e)
export COMPOSE_PROGRESS_NO_TRUNC=1
export BUILDKIT_PROGRESS=plain
export PYTHONUNBUFFERED=1

STEP_START=0

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

step() {
  STEP_START=$SECONDS
  echo ""
  log ">>> $*"
}

finish_step() {
  log "finished in $((SECONDS - STEP_START))s"
}

wait_for_healthy() {
  local service="$1"
  local timeout="${2:-300}"
  local elapsed=0
  local interval=5
  local -a DC=( "${COMPOSE[@]}" )
  if [[ "$service" == wizard-api-e2e || "$service" == wizard-ui-stack-e2e ]]; then
    DC=( "${COMPOSE_STACK[@]}" )
  fi

  while [ "$elapsed" -lt "$timeout" ]; do
    local cid
    cid="$("${DC[@]}" ps -q "$service" 2>/dev/null || true)"
    if [ -z "$cid" ]; then
      log "$service: container not created yet (${elapsed}s)"
    else
      local health
      health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)"
      log "$service: $health (${elapsed}s)"
      if [ "$health" = "healthy" ]; then
        return 0
      fi
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done

  log "ERROR: $service did not become healthy within ${timeout}s"
  "${DC[@]}" logs --tail=80 "$service" || true
  return 1
}

run_step() {
  local name="$1"
  shift
  step "$name"
  "$@"
  finish_step
}

ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --step)
      ONLY="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/docker-test.sh [--step api|ui|e2e|stack-e2e]

Runs the full Docker test pipeline with timestamped progress on stdout.
First run builds images (npm ci + Playwright) — can take several minutes.

  --step api        pytest only
  --step ui         vitest + lint + build only
  --step e2e        Playwright E2E (mock UI)
  --step stack-e2e  Playwright E2E (Postgres + wizard_api + UI)

Tip: run in your own terminal for live output:
  cd implementation_layer/wizard_api && ./scripts/docker-test.sh
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

should_run() {
  [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]
}

build_services() {
  local services=()
  if should_run api; then services+=(test-api); fi
  if should_run ui; then services+=(test-ui); fi
  if should_run e2e; then services+=(wizard-ui-e2e test-e2e); fi
  if should_run stack-e2e; then services+=(wizard-api-e2e wizard-ui-stack-e2e test-e2e-stack); fi
  if [ ${#services[@]} -eq 0 ]; then
    services=(test-api test-ui wizard-ui-e2e test-e2e wizard-api-e2e wizard-ui-stack-e2e test-e2e-stack)
  fi
  step "Building images: ${services[*]} (first run ~5–10 min, then cached)"
  docker compose --progress plain -f docker-compose.yml -f docker-compose.test.yml --profile test --profile stack-e2e build "${services[@]}"
  finish_step
}

log "Docker test pipeline starting (cwd: $ROOT)"
if [ -n "$ONLY" ]; then
  log "Running only step: $ONLY"
fi

if should_run api || should_run ui || should_run e2e || should_run stack-e2e; then
  run_step "Postgres up" docker compose up -d --wait postgres
fi

if should_run api || should_run ui || should_run e2e || should_run stack-e2e; then
  build_services
fi

if should_run api; then
  run_step "Backend tests (pytest)" \
    "${COMPOSE[@]}" run --rm --no-deps test-api
fi

if should_run ui; then
  run_step "Frontend unit + lint + build" \
    "${COMPOSE[@]}" run --rm --no-deps test-ui
fi

if should_run e2e; then
  step "E2E — starting mock UI (next dev)"
  "${COMPOSE[@]}" up -d --no-deps wizard-ui-e2e
  wait_for_healthy wizard-ui-e2e 300
  finish_step

  step "E2E — Playwright"
  "${COMPOSE[@]}" run --rm --no-deps test-e2e
  E2E_EXIT=$?
  finish_step

  step "Stopping mock UI"
  "${COMPOSE[@]}" stop wizard-ui-e2e
  finish_step

  if [ "${E2E_EXIT:-0}" -ne 0 ]; then
    exit "$E2E_EXIT"
  fi
fi

if should_run stack-e2e; then
  step "Stack E2E — wizard_api + Postgres + UI"
  "${COMPOSE_STACK[@]}" up -d --no-deps wizard-api-e2e
  wait_for_healthy wizard-api-e2e 300
  "${COMPOSE_STACK[@]}" up -d --no-deps wizard-ui-stack-e2e
  wait_for_healthy wizard-ui-stack-e2e 300
  finish_step

  step "Stack E2E — Playwright (every *-stack spec)"
  # The container writes its JUnit and HTML reports here (docker-compose.test.yml);
  # created up front and writable for the container's user.
  report_dir="${STACK_E2E_REPORT_DIR:-./.stack-e2e-report}"
  mkdir -p "$report_dir" && chmod a+rwx "$report_dir"
  "${COMPOSE_STACK[@]}" run --rm --no-deps test-e2e-stack
  STACK_E2E_EXIT=$?
  finish_step

  step "Stopping stack E2E services"
  "${COMPOSE_STACK[@]}" stop wizard-ui-stack-e2e wizard-api-e2e
  finish_step

  if [ "${STACK_E2E_EXIT:-0}" -ne 0 ]; then
    exit "$STACK_E2E_EXIT"
  fi
fi

echo ""
log "All requested Docker tests passed."
