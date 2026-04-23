#!/bin/bash
# =============================================================================
# GAIK Toolkit API — Rahti 2 Deployment Script
# =============================================================================
#
# Builds the standalone API Docker image and pushes it to CSC Rahti 2,
# then applies the OpenShift manifests (Deployment, Service, Route).
#
# USAGE
#   cd implementation_layer/api/openshift
#   chmod +x deploy.sh
#
#   ./deploy.sh build     # build + push the image only
#   ./deploy.sh apply     # oc apply the manifests only
#   ./deploy.sh all       # build + push + apply + rollout restart
#   ./deploy.sh status    # show pods, routes, and recent logs
#
# PREREQUISITES
#   1. Install oc CLI: https://docs.rahti.csc.fi/
#   2. oc login https://api.2.rahti.csc.fi:6443
#   3. oc project gaik
#   4. oc registry login
#   5. Create the secret once:
#        cp secrets.yaml.example secrets.yaml
#        # fill in API_KEY + Azure creds
#        oc apply -f secrets.yaml -n gaik
# =============================================================================
set -e

REGISTRY="image-registry.apps.2.rahti.csc.fi"
PROJECT="gaik"
APP="gaik-toolkit-api"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_usage() {
    echo "Usage: ./deploy.sh [build|apply|all|status]"
    echo ""
    echo "Commands:"
    echo "  build   Build Docker image and push to Rahti registry"
    echo "  apply   oc apply deployment.yaml, service.yaml, route.yaml"
    echo "  all     build + apply + rollout restart"
    echo "  status  Show pods, routes, recent logs"
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

do_build() {
    check_docker
    echo -e "${YELLOW}Building $APP...${NC}"
    cd "$REPO_ROOT"
    docker build -t "$APP" -f implementation_layer/api/Dockerfile .

    echo -e "${YELLOW}Tagging and pushing $APP...${NC}"
    docker tag "$APP" "$REGISTRY/$PROJECT/$APP:latest"
    docker push "$REGISTRY/$PROJECT/$APP:latest"

    echo -e "${GREEN}Image pushed: $REGISTRY/$PROJECT/$APP:latest${NC}"
}

do_apply() {
    check_oc_login
    echo -e "${YELLOW}Applying manifests to namespace $PROJECT...${NC}"
    oc apply -f "$SCRIPT_DIR/deployment.yaml" -n "$PROJECT"
    oc apply -f "$SCRIPT_DIR/service.yaml" -n "$PROJECT"
    oc apply -f "$SCRIPT_DIR/route.yaml" -n "$PROJECT"
    echo -e "${GREEN}Manifests applied${NC}"
}

do_rollout() {
    check_oc_login
    echo -e "${YELLOW}Rolling out $APP...${NC}"
    oc rollout restart "deployment/$APP" -n "$PROJECT" || true
    oc rollout status "deployment/$APP" -n "$PROJECT" --timeout=3m
}

do_status() {
    check_oc_login
    echo -e "${YELLOW}Pods:${NC}"
    oc get pods -n "$PROJECT" -l "app=$APP"
    echo -e "${YELLOW}Routes:${NC}"
    oc get routes -n "$PROJECT" -l "app=$APP"
    echo -e "${YELLOW}Recent logs:${NC}"
    oc logs "deployment/$APP" -n "$PROJECT" --tail=50 || true
}

if [ $# -eq 0 ]; then
    print_usage
    exit 1
fi

case "$1" in
    build)
        do_build
        ;;
    apply)
        do_apply
        ;;
    all)
        do_build
        do_apply
        do_rollout
        do_status
        ;;
    status)
        do_status
        ;;
    *)
        print_usage
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
