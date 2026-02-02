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
#   4. Login to container registry:
#      oc registry login
#
# =============================================================================
set -e

REGISTRY="image-registry.apps.2.rahti.csc.fi"
PROJECT="gaik"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_usage() {
    echo "Usage: ./deploy.sh [api|frontend|all]"
    echo ""
    echo "Commands:"
    echo "  api       Build and deploy backend API"
    echo "  frontend  Build and deploy frontend"
    echo "  all       Deploy both api and frontend"
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

deploy_api() {
    echo -e "${YELLOW}Building API...${NC}"
    cd "$DEMO_DIR"
    docker build -t gaik-demo-api -f api/Dockerfile .

    echo -e "${YELLOW}Tagging and pushing API...${NC}"
    docker tag gaik-demo-api "$REGISTRY/$PROJECT/gaik-demo-api:latest"
    docker push "$REGISTRY/$PROJECT/gaik-demo-api:latest"

    echo -e "${GREEN}API deployed successfully${NC}"
}

deploy_frontend() {
    echo -e "${YELLOW}Building frontend...${NC}"
    cd "$DEMO_DIR"
    docker build -t gaik-demo .

    echo -e "${YELLOW}Tagging and pushing frontend...${NC}"
    docker tag gaik-demo "$REGISTRY/$PROJECT/gaik-demo:latest"
    docker push "$REGISTRY/$PROJECT/gaik-demo:latest"

    echo -e "${GREEN}Frontend deployed successfully${NC}"
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
    all)
        deploy_api
        deploy_frontend
        ;;
    *)
        print_usage
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
