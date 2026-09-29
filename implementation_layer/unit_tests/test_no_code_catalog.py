"""The demo app ships a generated copy of the no-code assets.

Its image is built from toolkit_demo_app/ alone, so the skills, prompts and zips it
serves are committed outputs of scripts/build_no_code_catalog.py. This test fails when
someone edits a skill or prompt under no-code-assets without regenerating them.
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT / "implementation_layer" / "toolkit_demo_app" / "scripts" / "build_no_code_catalog.py"
)
REGENERATE = "uv run python implementation_layer/toolkit_demo_app/scripts/build_no_code_catalog.py"


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location("build_no_code_catalog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_outputs_are_current(builder):
    catalog_text, zips = builder.build()

    committed = builder.CATALOG_OUT.read_text(encoding="utf-8")
    diff = difflib.unified_diff(
        committed.splitlines(), catalog_text.splitlines(), "committed", "built", n=0
    )
    assert committed == catalog_text, (
        f"catalog.generated.json is stale: run `{REGENERATE}`\n" + "\n".join(list(diff)[:20])
    )
    for name, payload in zips.items():
        assert (builder.ZIP_DIR / name).read_bytes() == payload, f"{name} is stale; regenerate"
    assert {p.name for p in builder.ZIP_DIR.glob("*.zip")} == set(zips), "orphaned zip; regenerate"


def test_every_zip_is_an_uploadable_skill(builder):
    catalog = json.loads(builder.CATALOG_OUT.read_text(encoding="utf-8"))

    for skill in catalog["skills"]:
        with zipfile.ZipFile(builder.ZIP_DIR / f"{skill['id']}.zip") as archive:
            names = archive.namelist()
        assert f"{skill['id']}/SKILL.md" in names
        assert all(n.startswith(f"{skill['id']}/") for n in names), (
            "skill folder must be the zip root"
        )


def test_prompts_are_not_empty(builder):
    catalog = json.loads(builder.CATALOG_OUT.read_text(encoding="utf-8"))

    for prompt in catalog["prompts"]:
        assert prompt["variants"]
        assert all(len(v["text"]) > 500 for v in prompt["variants"]), prompt["id"]
