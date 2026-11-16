"""The API image runs the Python minor its hashed lock was made for.

scripts/lock_api_requirements.sh resolves api/requirements.lock for one
--python-version; an image on another minor (python:3.15-slim from a
Dependabot bump, say) installs wheels built for the wrong interpreter.
"""

import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[2]
DOCKERFILE = DEMO / "api" / "Dockerfile"
LOCK_SCRIPT = DEMO / "scripts" / "lock_api_requirements.sh"


def _dockerfile_minors() -> set[str]:
    minors = set()
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if words and words[0].upper() == "FROM":
            image = next(w for w in words[1:] if not w.startswith("--"))
            match = re.match(r"(?:docker\.io/)?(?:library/)?python:(\d+\.\d+)", image)
            if match:
                minors.add(match.group(1))
    return minors


def test_api_image_python_matches_lock_script():
    match = re.search(r"--python-version[ =](\d+\.\d+)", LOCK_SCRIPT.read_text(encoding="utf-8"))
    assert match, "lock script names no --python-version"
    minors = _dockerfile_minors()
    assert minors, "api/Dockerfile has no python:<minor> base image"
    assert minors == {match.group(1)}, (
        f"api/Dockerfile uses Python {sorted(minors)}, the lock is for {match.group(1)}; "
        "change both together and rerun the lock script"
    )
