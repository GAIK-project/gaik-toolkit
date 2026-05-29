#!/bin/bash
# =============================================================================
# GAIK Demo - Rahti 2 Deployment Script
# =============================================================================
#
# Builds Docker images and pushes them to CSC Rahti 2 container registry.
#
# USAGE:
#   cd implementation_layer/toolkit_demo_app/openshift
#   chmod +x deploy.sh
#
#   ./deploy.sh api       # Deploy backend API only
#   ./deploy.sh frontend  # Deploy frontend only
#   ./deploy.sh all       # Deploy both
#
# PREREQUISITES:
#   1. Install oc CLI: https://docs.rahti.csc.fi/
#   2. Login to Rahti:
#      oc login https://api.2.rahti.csc.fi:6443
#   3. Select project:
#      oc project gaik
#   4. Login to container registry. The script will attempt this automatically
#      via `docker login` using `oc whoami -t`. Manual fallback:
#        Linux / WSL with podman or docker: `oc registry login`
#        Windows + Docker Desktop (auth file lives in ~/.docker/, not
#        ~/.config/containers/): pipe the oc token into docker directly:
#          oc whoami -t | docker login -u "$(oc whoami)" \
#            --password-stdin image-registry.apps.2.rahti.csc.fi
#
# =============================================================================
set -e

REGISTRY="image-registry.apps.2.rahti.csc.fi"
PROJECT="gaik"
API_DEPLOYMENT="gaik-demo-api"
FRONTEND_DEPLOYMENT="gaik-demo"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_usage() {
    echo "Usage: ./deploy.sh [api|frontend|all|db|seed|verify]"
    echo ""
    echo "Commands:"
    echo "  api       Build and deploy backend API"
    echo "  frontend  Build and deploy frontend"
    echo "  all       Deploy db, api, and frontend"
    echo "  db        Deploy PostgreSQL + pgvector database"
    echo "  seed      Run dental demo seed script"
    echo "  verify    Verify live video-search deployment, DB, and Allas"
    echo ""
    echo "Prerequisites:"
    echo "  oc login https://api.2.rahti.csc.fi:6443"
    echo "  oc project $PROJECT"
    echo "  oc registry login"
}

check_oc_login() {
    if ! oc whoami &> /dev/null; then
        echo -e "${RED}Error: Not logged in to OpenShift${NC}"
        echo "Run: oc login https://api.2.rahti.csc.fi:6443"
        exit 1
    fi
    echo -e "${GREEN}Logged in as: $(oc whoami)${NC}"
}

check_docker() {
    if ! docker info &> /dev/null; then
        echo -e "${RED}Error: Docker is not running${NC}"
        exit 1
    fi
}

ensure_registry_login() {
    # Docker on Windows/Mac (Docker Desktop) ignores `oc registry login` because
    # that writes to ~/.config/containers/auth.json (podman's path). We pipe the
    # OpenShift token straight into `docker login` so the credentials land in
    # ~/.docker/config.json regardless of platform.
    echo -e "${YELLOW}Authenticating Docker against $REGISTRY...${NC}"
    if ! oc whoami -t | docker login -u "$(oc whoami)" --password-stdin "$REGISTRY" &> /dev/null; then
        echo -e "${RED}Error: failed to log Docker into the Rahti registry${NC}"
        echo "Manual recovery:"
        echo "  oc whoami -t | docker login -u \"\$(oc whoami)\" --password-stdin $REGISTRY"
        exit 1
    fi
}

rollout_deployment() {
    local deployment="$1"
    # `:latest` images don't trigger a new rollout on their own — restart the
    # deployment explicitly so the new image is pulled, then wait until it's
    # actually healthy.
    echo -e "${YELLOW}Rolling out deployment/$deployment...${NC}"
    oc rollout restart "deployment/$deployment" -n "$PROJECT"
    oc rollout status "deployment/$deployment" -n "$PROJECT" --timeout=240s
}

deploy_api() {
    echo -e "${YELLOW}Building API...${NC}"
    cd "$DEMO_DIR"
    docker build -t gaik-demo-api -f api/Dockerfile .

    ensure_registry_login

    echo -e "${YELLOW}Tagging and pushing API...${NC}"
    docker tag gaik-demo-api "$REGISTRY/$PROJECT/$API_DEPLOYMENT:latest"
    docker push "$REGISTRY/$PROJECT/$API_DEPLOYMENT:latest"

    rollout_deployment "$API_DEPLOYMENT"

    echo -e "${GREEN}API deployed successfully${NC}"
}

deploy_frontend() {
    echo -e "${YELLOW}Building frontend...${NC}"
    cd "$DEMO_DIR"
    docker build -t gaik-demo .

    ensure_registry_login

    echo -e "${YELLOW}Tagging and pushing frontend...${NC}"
    docker tag gaik-demo "$REGISTRY/$PROJECT/$FRONTEND_DEPLOYMENT:latest"
    docker push "$REGISTRY/$PROJECT/$FRONTEND_DEPLOYMENT:latest"

    rollout_deployment "$FRONTEND_DEPLOYMENT"

    echo -e "${GREEN}Frontend deployed successfully${NC}"
}

deploy_db() {
    echo -e "${YELLOW}Deploying PostgreSQL + pgvector...${NC}"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    if [ -z "${POSTGRESQL_PASSWORD:-}" ]; then
        echo -e "${RED}Error: POSTGRESQL_PASSWORD env var required${NC}"
        echo "Run: export POSTGRESQL_PASSWORD=your_secure_password"
        exit 1
    fi

    # Apply manifest with password substitution
    envsubst < "$SCRIPT_DIR/pgvector.yaml" | oc apply -f - -n "$PROJECT"

    # Set DATABASE_URL on API deployment
    echo -e "${YELLOW}Setting DATABASE_URL on API deployment...${NC}"
    oc set env deployment/gaik-demo-api \
        "DATABASE_URL=postgresql://postgres:${POSTGRESQL_PASSWORD}@pgvector-demo:5432/gaik_demo" \
        -n "$PROJECT"

    echo -e "${GREEN}pgvector deployed and DATABASE_URL configured${NC}"
}

run_seed() {
    echo -e "${YELLOW}Running dental demo seed script...${NC}"
    cd "$DEMO_DIR"
    uv run python api/scripts/seed_dental_demo.py
    echo -e "${GREEN}Seed complete${NC}"
}

verify_video_search() {
    echo -e "${YELLOW}Verifying Rahti routes and gaik-demo-api env...${NC}"
    oc get routes -n "$PROJECT"
    oc set env deployment/gaik-demo-api --list -n "$PROJECT"
    oc logs deployment/gaik-demo-api -n "$PROJECT" --tail=40

    echo -e "${YELLOW}Running live video-search verification...${NC}"
    cd "$DEMO_DIR"
    uv run python api/scripts/verify_video_search_deployment.py
    echo -e "${GREEN}Verification complete${NC}"
}

# Main
if [ $# -eq 0 ]; then
    print_usage
    exit 1
fi

check_docker
check_oc_login

case "$1" in
    api)
        deploy_api
        ;;
    frontend)
        deploy_frontend
        ;;
    db)
        deploy_db
        ;;
    seed)
        run_seed
        ;;
    verify)
        verify_video_search
        ;;
    all)
        # `all` is the common refresh path. Run db only when the password is
        # provided AND the cluster doesn't already have pgvector-demo — DB is
        # long-lived state, not part of every release.
        if [ -n "${POSTGRESQL_PASSWORD:-}" ] && \
           ! oc get deployment pgvector-demo -n "$PROJECT" &> /dev/null; then
            deploy_db
        else
            echo -e "${YELLOW}Skipping db (already deployed or POSTGRESQL_PASSWORD unset).${NC}"
            echo "  Run \`./deploy.sh db\` explicitly when you need to re-provision."
        fi
        deploy_api
        deploy_frontend
        ;;
    *)
        print_usage
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
