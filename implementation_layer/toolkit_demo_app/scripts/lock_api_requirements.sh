#!/usr/bin/env sh
# Writes api/requirements.lock: every package the API image installs, pinned
# with its hashes, for the image's Python (3.12) on linux x86_64, with torch
# and torchvision as CPU builds from the PyTorch index. Run it after changing
# api/requirements.txt (the gaik pin included) or to take newer releases
# (--upgrade), and commit both files. Run from anywhere; needs uv and python3.
#
# The lock records the sha256 of the requirements.txt it was made from, and
# api/tests/test_api_image_pins.py fails while the two differ.
set -eu
cd "$(dirname "$0")/../api"
uv pip compile requirements.txt \
  --output-file requirements.lock \
  --generate-hashes \
  --python-version 3.12 \
  --python-platform x86_64-manylinux_2_28 \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  --emit-index-url \
  --custom-compile-command "scripts/lock_api_requirements.sh" \
  "$@"
python3 - <<'PY'
import hashlib
from pathlib import Path

digest = hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest()
lock = Path("requirements.lock")
lines = [
    line
    for line in lock.read_text(encoding="utf-8").splitlines()
    if not line.startswith("# requirements.txt sha256: ")
]
lines.insert(2, f"# requirements.txt sha256: {digest}")
lock.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
