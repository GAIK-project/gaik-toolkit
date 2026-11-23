#!/usr/bin/env bash
# Install solution_wizard_v2 npm deps + Python venv for UI-only BPMN scripts
set -euo pipefail
cd "$(dirname "$0")/.."

npm ci

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements-bpmn.txt
python -c "import pydantic; print(\"BPMN Python OK (pydantic\", pydantic.__version__ + \")\")"

echo ""
echo "UI ready."
echo "  cp .env.example .env.local   # if needed"
echo "  npm run dev"
echo ""
echo "BPMN without wizard_api: scripts use .venv/bin/python3 (pydantic installed)."
echo "With API: set WIZARD_API_URL=http://localhost:8100 in .env.local (BPMN via API)."
