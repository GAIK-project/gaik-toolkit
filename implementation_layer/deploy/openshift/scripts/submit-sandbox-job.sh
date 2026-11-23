#!/usr/bin/env bash
# Submit one sandbox PoC run (S5-1 / #89) and print the Job name.
#
#   WIZARD_USER_ID=<session owner> ./submit-sandbox-job.sh <session-id> [image]
#
# WIZARD_USER_ID is the session owner's user id: the package fetch sends it as
# X-Wizard-User-Id, which the api requires once WIZARD_REQUIRE_USER_HEADER=1.
#
# Renders sandbox-job.yaml's placeholders and applies it with `oc`. #91
# (SandboxRunner) will call this same path from wizard_api; keeping the
# rendering here means the manifest stays the single source of truth for the
# isolation settings.
#
# --dry-run renders to stdout without touching a cluster, which is also how the
# manifest test exercises it.
set -euo pipefail

TEMPLATE="$(cd "$(dirname "$0")/.." && pwd)/sandbox-job.yaml"
SESSION_ID="${1:-}"
DRY_RUN="${DRY_RUN:-}"
# Instance prefix, as deploy.sh names it: wizard-v2, or wizard-v2-<INSTANCE>.
NAME="wizard-v2${INSTANCE:+-$INSTANCE}"
IMAGE="${2:-image-registry.apps.2.rahti.csc.fi/PROJECT_PLACEHOLDER/${NAME}-poc-runner:latest}"

if [ -z "$SESSION_ID" ]; then
  echo "usage: $0 <session-id> [image]" >&2
  exit 2
fi

# The Secret the run reads its model settings from, as the api uses it
# (sandbox_runner.runner_secret): the shared one unless WIZARD_POC_RUNNER_SECRET names another.
RUNNER_SECRET="${WIZARD_POC_RUNNER_SECRET:-gaik-demo-api-keys}"
if ! printf '%s' "$RUNNER_SECRET" | grep -Eq '^[a-z0-9]([-a-z0-9]{0,251}[a-z0-9])?$'; then
  echo "WIZARD_POC_RUNNER_SECRET is not a Secret name" >&2
  exit 2
fi

# Job names must be DNS-1123 labels, so keep the run id lowercase alphanumeric.
RUN_ID="$(date +%Y%m%d%H%M%S)-$(printf '%s' "$SESSION_ID" | tr -dc 'a-z0-9' | tail -c 8)"

render() {
  sed \
    -e "s|SESSION_ID_PLACEHOLDER|${SESSION_ID}|g" \
    -e "s|RUN_ID_PLACEHOLDER|${RUN_ID}|g" \
    -e "s|IMAGE_PLACEHOLDER|${IMAGE}|g" \
    -e "s|NAME_PLACEHOLDER|${NAME}|g" \
    -e "s|name: gaik-demo-api-keys\$|name: ${RUNNER_SECRET}|" \
    "$TEMPLATE"
}

if [ -n "$DRY_RUN" ]; then
  render
  exit 0
fi

# The default image still carries the registry project placeholder the other
# manifests here use; submitting that would fail with an ImagePullBackOff after
# the Job is already created, so refuse up front.
case "$IMAGE" in
  *PROJECT_PLACEHOLDER*)
    echo "pass the runner image explicitly: $0 $SESSION_ID <image>" >&2
    exit 2
    ;;
esac

if [ -z "${WIZARD_USER_ID:-}" ]; then
  echo "set WIZARD_USER_ID to the session owner's user id" >&2
  exit 2
fi

if ! command -v oc >/dev/null 2>&1; then
  echo "oc not found — run with DRY_RUN=1 to render only" >&2
  exit 1
fi

# The owner goes in as an env value set by oc, not into the manifest text, the
# same way sandbox_runner._set_user sets it.
render \
  | oc set env --local -f - -c fetch-poc WIZARD_USER_ID="$WIZARD_USER_ID" -o yaml \
  | oc apply -f - >/dev/null
echo "wizard-v2-poc-run-${RUN_ID}"
