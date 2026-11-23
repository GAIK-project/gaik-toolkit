"""Write the packages the wizard API image installs next to wizard_api.

The API image (implementation_layer/wizard_api/Dockerfile) installs
solution_wizard and then `gaik[<extras>]==<version>` plus a few packages the
agent's PoCs import. This reads that pip line and its ARG defaults from the
Dockerfile, so the audit follows the image instead of a copy of it that can
drift. The output is a requirements.in for `uv pip compile`.

Usage: python api_image_requirements.py <Dockerfile> <out.in>
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path


def main(dockerfile: Path, out: Path) -> int:
    text = dockerfile.read_text(encoding="utf-8")
    args = dict(re.findall(r'^ARG\s+(\w+)="?([^"\n]*)"?\s*$', text, re.MULTILINE))
    line = next(
        (ln for ln in text.splitlines() if "pip install" in ln and "gaik[" in ln),
        None,
    )
    if line is None:
        print(f"no gaik pip install line in {dockerfile}", file=sys.stderr)
        return 1
    tokens = shlex.split(line.split("pip install", 1)[1])
    reqs = []
    for token in tokens:
        if token.startswith("-"):
            continue
        reqs.append(re.sub(r"\$\{(\w+)\}", lambda m: args[m.group(1)], token))
    out.write_text("\n".join(reqs) + "\n", encoding="utf-8")
    print("\n".join(reqs))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
