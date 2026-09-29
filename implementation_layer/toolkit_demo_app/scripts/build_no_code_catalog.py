"""Build the demo app's no-code assets data from implementation_layer/no-code-assets.

The demo app image is built from toolkit_demo_app/ alone, so it cannot read the
skills and prompts that live beside it. This script packs them into two committed
outputs:

    lib/no-code/catalog.generated.json   metadata, prompt text, file lists
    public/downloads/skills/<id>.zip     one uploadable skill per zip

Run it after any change under implementation_layer/no-code-assets:

    uv run python implementation_layer/toolkit_demo_app/scripts/build_no_code_catalog.py

`--check` exits non-zero when the committed outputs are stale; a unit test runs it.
The zips are byte-for-byte reproducible (stored uncompressed, since deflate output varies
with the zlib version; sorted entries, fixed timestamps, LF line
endings), so a stale zip shows up as a diff instead of a checkout artefact.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import yaml

APP_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = APP_DIR.parent / "no-code-assets"
CATALOG_OUT = APP_DIR / "lib" / "no-code" / "catalog.generated.json"
ZIP_DIR = APP_DIR / "public" / "downloads" / "skills"

REPO_TREE = (
    "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets"
)
ZIP_DATE = (2026, 1, 1, 0, 0, 0)
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".yaml", ".yml", ".toml", ".bat"}
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}


def _read_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return data


def _files(skill_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in skill_dir.rglob("*")
        if p.is_file() and not (SKIP_NAMES & set(p.relative_to(skill_dir).parts))
    )


def _frontmatter(skill_dir: Path) -> dict:
    text = _read_bytes(skill_dir / "SKILL.md").decode("utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise SystemExit(f"{skill_dir}: SKILL.md has no frontmatter")
    return yaml.safe_load(match.group(1))


def _zip_skill(skill_dir: Path, name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for path in _files(skill_dir):
            info = zipfile.ZipInfo(f"{name}/{path.relative_to(skill_dir).as_posix()}", ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, _read_bytes(path))
    return buffer.getvalue()


def _tree_url(relative: str) -> str:
    return f"{REPO_TREE}/{relative}".replace(" ", "%20")


def build() -> tuple[str, dict[str, bytes]]:
    """Return the catalog JSON text and the zip bytes keyed by file name."""
    source = json.loads((ASSETS_DIR / "catalog.json").read_text(encoding="utf-8"))
    zips: dict[str, bytes] = {}

    skills = []
    for entry in source["skills"]:
        skill_dir = ASSETS_DIR / entry["path"]
        meta = _frontmatter(skill_dir)
        if meta["name"] != skill_dir.name or meta["name"] != entry["id"]:
            raise SystemExit(f"{entry['id']}: name, directory and catalog id must match")
        payload = _zip_skill(skill_dir, meta["name"])
        zips[f"{entry['id']}.zip"] = payload
        skills.append(
            {
                "id": entry["id"],
                "group": entry["group"],
                "title": entry["title"],
                "tagline": entry["tagline"],
                "description": " ".join(str(meta["description"]).split()),
                "input": entry["input"],
                "output": entry["output"],
                "needs": entry["needs"],
                "tryPrompt": entry["tryPrompt"],
                "files": [p.relative_to(skill_dir).as_posix() for p in _files(skill_dir)],
                "zip": f"/downloads/skills/{entry['id']}.zip",
                "zipBytes": len(payload),
                "githubUrl": _tree_url(entry["path"]),
                "guideUrl": _tree_url(entry["guide"]) if "guide" in entry else None,
            }
        )

    prompts = []
    for entry in source["prompts"]:
        variants = []
        for variant in entry["variants"]:
            text = _read_bytes(ASSETS_DIR / entry["path"] / variant["file"]).decode("utf-8")
            variants.append(
                {"label": variant["label"], "file": variant["file"], "text": text.strip()}
            )
        prompts.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "tagline": entry["tagline"],
                "input": entry["input"],
                "output": entry["output"],
                "then": entry["then"],
                "variants": variants,
                "githubUrl": _tree_url(entry["path"]),
            }
        )

    plugin = json.loads((ASSETS_DIR / "agent-plugin" / "plugin.json").read_text(encoding="utf-8"))
    catalog = {
        "plugin": {
            "name": plugin["name"],
            "version": plugin["version"],
            "marketplace": "GAIK-project/gaik-toolkit",
            "githubUrl": _tree_url("agent-plugin"),
        },
        "skills": skills,
        "prompts": prompts,
    }
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", zips


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if committed outputs are stale")
    args = parser.parse_args()

    catalog_text, zips = build()
    stale = []
    if not CATALOG_OUT.exists() or CATALOG_OUT.read_bytes() != catalog_text.encode("utf-8"):
        stale.append(CATALOG_OUT)
    for name, payload in zips.items():
        target = ZIP_DIR / name
        if not target.exists() or target.read_bytes() != payload:
            stale.append(target)
    extra = [p for p in ZIP_DIR.glob("*.zip") if p.name not in zips] if ZIP_DIR.exists() else []

    if args.check:
        for path in stale + extra:
            print(f"stale: {path.relative_to(APP_DIR)}", file=sys.stderr)
        return 1 if stale or extra else 0

    CATALOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_OUT.write_bytes(catalog_text.encode("utf-8"))
    for name, payload in zips.items():
        (ZIP_DIR / name).write_bytes(payload)
    for path in extra:
        path.unlink()
    print(f"wrote {CATALOG_OUT.relative_to(APP_DIR)} and {len(zips)} zips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
