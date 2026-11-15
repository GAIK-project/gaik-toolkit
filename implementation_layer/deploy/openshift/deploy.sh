#!/bin/bash
# =============================================================================
# GAIK Solution Wizard V2 — Rahti 2 (staging) deployment script
# =============================================================================
#
# Builds the wizard_api + solution_wizard_v2 images, pushes them to the CSC
# Rahti 2 registry, and rolls out the Deployments.
#
# USAGE:
#   cd implementation_layer/deploy/openshift
#   chmod +x deploy.sh
#   export PROJECT=<your-staging-project>          # required
#   export INSTANCE=                               # empty = the staging stack
#   export NEXT_PUBLIC_SUPABASE_URL=...            # web build (unless dev-auth)
#   export NEXT_PUBLIC_SUPABASE_ANON_KEY=...       # web build (unless dev-auth)
#   export NEXT_PUBLIC_DEV_AUTH=false              # or true for the dev login
#
#   ./deploy.sh secrets     # apply the untracked secrets.yaml for this instance
#   ./deploy.sh manifests   # apply db, PVCs, services, route, deployments
#   ./deploy.sh api         # build + push + roll out the backend
#   ./deploy.sh web         # build + push + roll out the frontend
#   ./deploy.sh poc-runner  # build + push the sandbox PoC run image
#   ./deploy.sh all         # manifests, then api, web and poc-runner
#   ./deploy.sh verify      # show route, env, recent api logs
#   ./deploy.sh render <f>  # print a manifest as it would be applied (no oc)
#
# INSTANCES:
#   Every resource is named after $NAME = wizard-v2[-$INSTANCE]: the
#   Deployments, Services, Route, PVCs, the db/token/web Secrets and the image
#   repositories. With INSTANCE empty the names are the historical ones
#   (wizard-v2-api, ...), so existing deployments are untouched. With
#   INSTANCE=s4 a second, independent stack (wizard-v2-s4-*) lives in the SAME
#   project, with its own database, session storage, images and public URL
#   (wizard-v2-s4-web-<project>.2.rahtiapp.fi). Only the project-wide
#   gaik-demo-api-keys Secret (model provider keys) is shared between instances.
#
# PREREQUISITES:
#   1. oc CLI + Docker with buildx.
#   2. oc login https://api.2.rahti.csc.fi:6443
#   3. oc project "$PROJECT"
#   4. Fill secrets: cp secrets.yaml.example secrets.yaml (edit) &&
#      ./deploy.sh secrets ; the file keeps NAME_PLACEHOLDER so the same copy
#      serves every instance.
# =============================================================================
set -euo pipefail

REGISTRY="image-registry.apps.2.rahti.csc.fi"
PROJECT="${PROJECT:-}"
INSTANCE="${INSTANCE:-}"
# Resource-name prefix. Kubernetes names are DNS labels, so the instance part
# is limited to lowercase letters, digits and dashes; the check is below.
NAME="wizard-v2${INSTANCE:+-$INSTANCE}"
API_DEPLOYMENT="$NAME-api"
WEB_DEPLOYMENT="$NAME-web"
# Not a Deployment: sandbox-job.yaml names this image per run (#89), so there is
# nothing to roll out -- pushing a new tag is the whole deploy.
POC_RUNNER_IMAGE="$NAME-poc-runner"
SCANNER_DEPLOYMENT="$NAME-scanner"
BUILDX_BUILDER="${BUILDX_BUILDER:-gaik-rahti}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMPL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"          # implementation_layer/
WEB_DIR="$IMPL_DIR/solution_wizard_v2"

# Baked into both images at build time so a running pod can report exactly
# what it's running (GET /health on the api, the login page footer on the
# web app) without needing GitHub or oc access. Prefers the nearest
# dev-YYYY-MM-DD-<sha> tag (see .github/workflows/solution-wizard-v2.yml);
# falls back to a bare short SHA if the checkout has no tags reachable.
APP_VERSION="$(cd "$IMPL_DIR/.." && git describe --tags --always --dirty 2>/dev/null || echo unknown)"
REPO_ROOT="$(cd "$IMPL_DIR/.." && pwd)"

# The manifests deploy.sh applies, in dependency order. Every one of them goes
# through render_manifest, so a name that is not NAME_PLACEHOLDER-based would
# silently belong to every instance at once.
MANIFESTS=(rbac.yaml networkpolicy-sandbox.yaml postgres.yaml pvc-sessions.yaml services.yaml route.yaml deployment-scanner.yaml deployment-api.yaml deployment-web.yaml)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

print_usage() {
    echo "Usage: PROJECT=<project> [INSTANCE=<name>] ./deploy.sh [secrets|manifests|api|web|poc-runner|scanner|all|verify|render <file>]"
    echo ""
    echo "  secrets    Apply secrets.yaml (untracked) for this instance"
    echo "  manifests  Apply db + PVCs + services + route + deployments"
    echo "  api        Build, push and roll out $API_DEPLOYMENT"
    echo "  web        Build, push and roll out $WEB_DEPLOYMENT"
    echo "  poc-runner Build and push $POC_RUNNER_IMAGE (sandbox runs)"
    echo "  scanner    Build and push $SCANNER_DEPLOYMENT, apply and roll it out (upload malware check)"
    echo "  all        manifests, then api, web and poc-runner"
    echo "  verify     Show route, api env and recent api logs"
    echo "  render <f> Print manifest <f> with project and instance substituted"
    echo ""
    echo "  INSTANCE empty -> the staging stack (wizard-v2-*)."
    echo "  INSTANCE=s4    -> a second stack (wizard-v2-s4-*) in the same project."
}

require_project() {
    if [ -z "$PROJECT" ]; then
        echo -e "${RED}Error: PROJECT env var is required (export PROJECT=<staging-project>)${NC}"
        exit 1
    fi
}

require_valid_instance() {
    # Empty is the staging stack. Anything else becomes part of DNS-1123 names
    # (Services, the Route host), so it must be a lowercase label fragment.
    if [ -n "$INSTANCE" ] && ! [[ "$INSTANCE" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
        echo -e "${RED}Error: INSTANCE='$INSTANCE' is not a valid name fragment (lowercase letters, digits, dashes; e.g. s4)${NC}"
        exit 1
    fi
}

check_oc_login() {
    if ! oc whoami &> /dev/null; then
        echo -e "${RED}Error: not logged in to OpenShift${NC}"
        echo "Run: oc login https://api.2.rahti.csc.fi:6443"
        exit 1
    fi
    echo -e "${GREEN}Logged in as: $(oc whoami) — project: $PROJECT — instance: $NAME${NC}"
}

# The deployed images carry APP_VERSION from `git describe`, and the login page
# shows it. That only means something if the commit exists somewhere other than
# the machine that built it: a customer test once reported build ce53774, which
# is in no branch of this repository, so nobody could tell what had been running.
# `--dirty` does not catch that case — the tree was clean, the commit was simply
# never pushed.
require_pushed_commit() {
    local head dirty remote_refs
    head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
    if [ -z "$head" ]; then
        echo -e "${RED}Error: not a git checkout — refusing to build an image nobody can trace${NC}"
        exit 1
    fi

    dirty="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)"
    if [ -n "$dirty" ]; then
        echo -e "${RED}Error: the working tree has uncommitted changes.${NC}"
        echo "  The image would be built from something that exists only here."
        echo "  Commit and push first, or stash."
        exit 1
    fi

    git -C "$REPO_ROOT" fetch --quiet origin 2>/dev/null || true
    remote_refs="$(git -C "$REPO_ROOT" branch -r --contains "$head" 2>/dev/null)"
    if [ -z "$remote_refs" ]; then
        echo -e "${RED}Error: HEAD ($(git -C "$REPO_ROOT" rev-parse --short HEAD)) is not on any remote branch.${NC}"
        echo "  The login page would report a version nobody else can resolve,"
        echo "  which is exactly what happened with ce53774."
        echo "  Push the branch first."
        exit 1
    fi

    echo -e "${GREEN}Building $APP_VERSION from a pushed commit${NC}"
}

check_docker() {
    if ! docker info &> /dev/null; then
        echo -e "${RED}Error: Docker is not running${NC}"; exit 1
    fi
}

ensure_registry_login() {
    echo -e "${YELLOW}Authenticating Docker against $REGISTRY...${NC}"
    if ! oc whoami -t | docker login -u "$(oc whoami)" --password-stdin "$REGISTRY" &> /dev/null; then
        echo -e "${RED}Error: failed to log Docker into the Rahti registry${NC}"
        echo "  oc whoami -t | docker login -u \"\$(oc whoami)\" --password-stdin $REGISTRY"
        exit 1
    fi
}

ensure_buildx_builder() {
    # Rahti's registry rejects Docker's default OCI manifest output. A
    # docker-container buildx builder lets us push Docker schema2 directly.
    if ! docker buildx inspect "$BUILDX_BUILDER" &> /dev/null; then
        echo -e "${YELLOW}Creating buildx builder $BUILDX_BUILDER...${NC}"
        docker buildx create --name "$BUILDX_BUILDER" --driver docker-container --use > /dev/null
    else
        docker buildx use "$BUILDX_BUILDER" > /dev/null
    fi
    docker buildx inspect --bootstrap > /dev/null
}

render_manifest() {
    # Substitute the image-registry project and the instance name prefix.
    # The same two placeholders appear in secrets.yaml(.example).
    sed -e "s/PROJECT_PLACEHOLDER/$PROJECT/g" -e "s/NAME_PLACEHOLDER/$NAME/g" "$1"
}

apply_manifest() {
    render_manifest "$SCRIPT_DIR/$1" | oc apply -n "$PROJECT" -f -
}

rollout() {
    local d="$1"
    echo -e "${YELLOW}Rolling out deployment/$d...${NC}"
    oc rollout restart "deployment/$d" -n "$PROJECT"
    oc rollout status "deployment/$d" -n "$PROJECT" --timeout=300s
}

deploy_secrets() {
    local f="$SCRIPT_DIR/secrets.yaml"
    if [ ! -f "$f" ]; then
        echo -e "${RED}Error: $f not found (cp secrets.yaml.example secrets.yaml and fill it in)${NC}"
        exit 1
    fi
    echo -e "${YELLOW}Applying secrets for $NAME to project $PROJECT...${NC}"
    apply_manifest secrets.yaml
    echo -e "${GREEN}Secrets applied.${NC}"
}

deploy_manifests() {
    echo -e "${YELLOW}Applying manifests for $NAME to project $PROJECT...${NC}"
    local m
    for m in "${MANIFESTS[@]}"; do
        apply_manifest "$m"
    done
    echo -e "${GREEN}Manifests applied. (Ensure ./deploy.sh secrets has run for this instance.)${NC}"
}

deploy_api() {
    ensure_registry_login
    ensure_buildx_builder
    # Build context is implementation_layer/ because the Dockerfile COPYs both
    # wizard_api/ and solution_wizard/ (BPMN generation).
    echo -e "${YELLOW}Building and pushing $API_DEPLOYMENT ($APP_VERSION)...${NC}"
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --target production \
        --output type=registry,oci-mediatypes=false \
        --build-arg "APP_VERSION=${APP_VERSION}" \
        -t "$REGISTRY/$PROJECT/$API_DEPLOYMENT:latest" \
        -t "$REGISTRY/$PROJECT/$API_DEPLOYMENT:$APP_VERSION" \
        -f "$IMPL_DIR/wizard_api/Dockerfile" \
        "$IMPL_DIR"
    rollout "$API_DEPLOYMENT"
    echo -e "${GREEN}$API_DEPLOYMENT deployed${NC}"
}

deploy_poc_runner() {
    ensure_registry_login
    ensure_buildx_builder
    # Build context is the poc-runner dir alone: the image installs gaik from
    # PyPI at a pinned version, so it needs no source from this repo.
    echo -e "${YELLOW}Building and pushing $POC_RUNNER_IMAGE ($APP_VERSION)...${NC}"
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=registry,oci-mediatypes=false \
        -t "$REGISTRY/$PROJECT/$POC_RUNNER_IMAGE:latest" \
        -t "$REGISTRY/$PROJECT/$POC_RUNNER_IMAGE:$APP_VERSION" \
        "$IMPL_DIR/deploy/poc-runner"
    echo -e "${GREEN}$POC_RUNNER_IMAGE pushed — submit a run with"
    echo -e "  ../openshift/scripts/submit-sandbox-job.sh <session-id> \\"
    echo -e "    $REGISTRY/$PROJECT/$POC_RUNNER_IMAGE:latest${NC}"
}

deploy_scanner() {
    ensure_registry_login
    ensure_buildx_builder
    # The build downloads the current ClamAV signatures into the image, so a
    # new pod scans before its first update; rebuild now and then to keep that
    # starting point fresh.
    echo -e "${YELLOW}Building and pushing $SCANNER_DEPLOYMENT ($APP_VERSION)...${NC}"
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=registry,oci-mediatypes=false \
        -t "$REGISTRY/$PROJECT/$SCANNER_DEPLOYMENT:latest" \
        -t "$REGISTRY/$PROJECT/$SCANNER_DEPLOYMENT:$APP_VERSION" \
        "$IMPL_DIR/deploy/scanner"
    # Its own manifest only: applying it touches no other deployment.
    apply_manifest deployment-scanner.yaml
    rollout "$SCANNER_DEPLOYMENT"
    echo -e "${GREEN}$SCANNER_DEPLOYMENT deployed. Point the api at it (once):"
    echo -e "  oc set env deployment/$API_DEPLOYMENT -c $API_DEPLOYMENT WIZARD_MALWARE_SCANNER=$SCANNER_DEPLOYMENT:3310${NC}"
}

deploy_web() {
    ensure_registry_login
    ensure_buildx_builder
    # NEXT_PUBLIC_* must be baked in at build time — pass them as build args.
    echo -e "${YELLOW}Building and pushing $WEB_DEPLOYMENT ($APP_VERSION)...${NC}"
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=registry,oci-mediatypes=false \
        --build-arg "NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL:-}" \
        --build-arg "NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY:-}" \
        --build-arg "NEXT_PUBLIC_DEV_AUTH=${NEXT_PUBLIC_DEV_AUTH:-false}" \
        --build-arg "NEXT_PUBLIC_APP_VERSION=${APP_VERSION}" \
        -t "$REGISTRY/$PROJECT/$WEB_DEPLOYMENT:latest" \
        -t "$REGISTRY/$PROJECT/$WEB_DEPLOYMENT:$APP_VERSION" \
        -f "$WEB_DIR/Dockerfile" \
        "$WEB_DIR"
    rollout "$WEB_DEPLOYMENT"
    echo -e "${GREEN}$WEB_DEPLOYMENT deployed${NC}"
}

verify() {
    echo -e "${YELLOW}Route:${NC}";    oc get route "$WEB_DEPLOYMENT" -n "$PROJECT"
    echo -e "${YELLOW}API env:${NC}";  oc set env deployment/$API_DEPLOYMENT --list -n "$PROJECT"
    echo -e "${YELLOW}API version (baked into the image, GET /health):${NC}"
    oc exec "deployment/$API_DEPLOYMENT" -n "$PROJECT" -- \
        python3 -c "import urllib.request,sys; sys.stdout.write(urllib.request.urlopen('http://localhost:8100/health').read().decode())" \
        2>/dev/null || echo "  (could not reach /health inside the pod)"
    echo -e "${YELLOW}API logs:${NC}"; oc logs deployment/$API_DEPLOYMENT -n "$PROJECT" --tail=40 || true
}

[ $# -eq 0 ] && { print_usage; exit 1; }
require_project
require_valid_instance

# `render` needs no cluster: it is what the manifest tests and a curious
# operator use to see exactly what `manifests` / `secrets` would apply.
if [ "$1" = "render" ]; then
    [ $# -eq 2 ] || { print_usage; exit 1; }
    render_manifest "$SCRIPT_DIR/$2"
    exit 0
fi

check_oc_login

case "$1" in
    secrets)    deploy_secrets ;;
    manifests)  deploy_manifests ;;
    api)        check_docker; require_pushed_commit; deploy_api ;;
    web)        check_docker; require_pushed_commit; deploy_web ;;
    poc-runner) check_docker; require_pushed_commit; deploy_poc_runner ;;
    scanner)    check_docker; require_pushed_commit; deploy_scanner ;;
    all)        check_docker; require_pushed_commit; deploy_scanner; deploy_manifests; deploy_api; deploy_web; deploy_poc_runner ;;
    verify)     verify ;;
    *)          print_usage; exit 1 ;;
esac

echo -e "${GREEN}Done!${NC}"
