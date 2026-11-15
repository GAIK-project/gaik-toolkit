"""The demo images build from pinned inputs.

Base images are pinned by digest, and the API image installs every Python
package from api/requirements.lock, pinned with its hashes. The lock is made
from api/requirements.txt by scripts/lock_api_requirements.sh; these tests fail
when the two drift apart, for example after a gaik bump without a new lock.
Dockerfile.pnpm, the alternative front-end build, is not covered.
"""

import hashlib
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[2]
DOCKERFILES = [DEMO / "Dockerfile", DEMO / "api" / "Dockerfile"]
REQUIREMENTS = DEMO / "api" / "requirements.txt"
LOCK = DEMO / "api" / "requirements.lock"

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _instructions(dockerfile: Path) -> list[list[str]]:
    """The words of each instruction line, comments left out."""
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    return [line.split() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _image_refs(dockerfile: Path) -> list[str]:
    """Every image a FROM or a COPY --from names, and the stages it defines."""
    refs, stages = [], set()
    for words in _instructions(dockerfile):
        if words[0].upper() == "FROM":
            args = [w for w in words[1:] if not w.startswith("--")]
            refs.append(args[0])
            if len(args) == 3 and args[1].upper() == "AS":
                stages.add(args[2])
        elif words[0].upper() == "COPY":
            refs += [w.removeprefix("--from=") for w in words if w.startswith("--from=")]
    return [ref for ref in refs if ref not in stages]


def _lock_entries() -> dict[str, tuple[str, list[str]]]:
    """name -> (version, hashes) for each package in the lock."""
    entries: dict[str, tuple[str, list[str]]] = {}
    current = None
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        pin = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", line)
        if pin:
            current = _norm(pin.group(1))
            entries[current] = (pin.group(2), [])
        elif current and line.strip().startswith("--hash=sha256:"):
            entries[current][1].append(line.strip().split(":", 1)[1].rstrip(" \\"))
    return entries


def _requirements() -> dict[str, str]:
    """name -> the requirement line, for each line of requirements.txt."""
    out = {}
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out[_norm(re.split(r"[\[<>=!~ ;]", line, maxsplit=1)[0])] = line
    return out


def test_every_base_image_is_pinned_by_digest():
    for dockerfile in DOCKERFILES:
        refs = _image_refs(dockerfile)
        assert refs, dockerfile
        for ref in refs:
            assert DIGEST.search(ref), f"{dockerfile.name}: {ref} has no digest"


def test_the_api_image_installs_from_the_lock_with_hashes():
    dockerfile = (DEMO / "api" / "Dockerfile").read_text(encoding="utf-8")
    runs = [
        " ".join(run.split())
        for run in re.findall(r"^RUN (.*?)(?<!\\)$", dockerfile, re.MULTILINE | re.DOTALL)
    ]
    installs = [run.split() for run in runs if "pip install" in run]
    assert len(installs) == 1, installs
    assert "--require-hashes" in installs[0]
    assert installs[0][-2:] == ["-r", "requirements.lock"]


def test_every_locked_package_carries_a_hash():
    entries = _lock_entries()
    assert len(entries) > 50
    missing = [name for name, (_, hashes) in entries.items() if not hashes]
    assert missing == []


def test_the_lock_was_made_from_this_requirements_txt():
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    recorded = re.search(r"^# requirements.txt sha256: ([0-9a-f]{64})$", LOCK.read_text(), re.M)
    assert recorded, "the lock records the requirements.txt it was made from"
    assert recorded.group(1) == digest, "run scripts/lock_api_requirements.sh"


def test_the_lock_holds_every_requirement_and_the_same_gaik_pin():
    entries = _lock_entries()
    requirements = _requirements()
    assert set(requirements) <= set(entries), set(requirements) - set(entries)

    gaik = re.search(r"==(\S+)$", requirements["gaik"])
    assert gaik, "requirements.txt pins gaik to one release"
    assert entries["gaik"][0] == gaik.group(1)
