#!/usr/bin/env bash
# Install wizard_api Python deps into .venv
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
echo "wizard_api ready. Run: ./scripts/dev-api.sh"
