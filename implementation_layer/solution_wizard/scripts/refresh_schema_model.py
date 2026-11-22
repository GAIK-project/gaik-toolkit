#!/usr/bin/env python3
"""Write output_schema_model.json again from a corrected output_schema.py.

With gaik 0.11 or later, the audio and document PoCs load their extraction model
with load_schema(), which rebuilds it from output_schema_model.json without
importing output_schema.py. After Step 4.5 in SKILL.md edits output_schema.py, run
this so the model file holds the same corrections; otherwise those PoCs run on the
schema from before them, unless they write the file again themselves (they do when
output_schema.py is newer). The custom and hybrid PoCs import output_schema.py.

The class is the one named "model_name" in output_schema_requirements.json. The
script imports output_schema.py: the file the wizard wrote and edited in this PoC
workspace, next to the run_poc.py the wizard runs. Do not point it at a schemas
folder from elsewhere. It refuses a model the saved format cannot describe, such as
a field constraint (exit code 1, nothing written). The one constraint kept is a
pattern on a text field written as the schema generator writes it,
Annotated[str, constr(pattern=r"...")], also inside Optional[...] or list[...];
Field(pattern=...), a bare constr(pattern=...) type and
Annotated[str, StringConstraints(pattern=...)] are refused. With a
gaik release that has no saved_schema module, load_schema() reads output_schema.py
itself, so the edit is in effect with that release: the script writes nothing and
exits 0, with a warning when an older output_schema_model.json is there, since a
later gaik would load that file. The file is kept rather than removed: without it,
gaik rebuilds the model from the requirements JSON, which drops a correction made
only in output_schema.py, and the PoCs no longer write it again from the .py.

Usage:
    python scripts/refresh_schema_model.py --schemas-dir poc/schemas
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def refresh(schemas_dir: Path) -> Path | None:
    """Write the model file again; ``None`` when the installed gaik does not use one."""
    try:
        from gaik.software_components.extractor.saved_schema import (
            SavedSchemaError,
            write_model_file,
        )
    except ImportError:  # older gaik: load_schema() reads output_schema.py
        return None

    py_path = schemas_dir / "output_schema.py"
    req_path = schemas_dir / "output_schema_requirements.json"
    model_path = schemas_dir / "output_schema_model.json"
    model_name = json.loads(req_path.read_text(encoding="utf-8"))["model_name"]

    spec = importlib.util.spec_from_file_location("_wizard_output_schema", py_path)
    if spec is None or spec.loader is None:
        raise SavedSchemaError(f"cannot read {py_path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = getattr(module, model_name, None)
    if model is None:
        raise SavedSchemaError(
            f"{py_path.name} has no class {model_name!r}, the name in {req_path.name}"
        )

    # Written next to the old file first, so a refused model leaves it as it was.
    # write_model_file() refuses a model whose description does not rebuild it.
    tmp_path = model_path.with_suffix(".json.tmp")
    try:
        write_model_file(model, tmp_path)
        tmp_path.replace(model_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return model_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schemas-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        path = refresh(args.schemas_dir)
    except Exception as exc:  # noqa: BLE001 - reported to the agent, exit 1
        print(f"Model file not refreshed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if path is None:
        stale = args.schemas_dir / "output_schema_model.json"
        if stale.is_file():
            print(
                f"WARNING: {stale} was not written again: the installed gaik has no "
                "saved_schema module. It still holds the schema from before this edit. "
                "This gaik's load_schema() reads output_schema.py, so the edit is in effect "
                "with it, but with gaik 0.11 or later the audio and document PoCs load the "
                "model file, and write it again from output_schema.py only while the .py "
                "is newer. Run this script with gaik 0.11 or later before such a run; do "
                "not delete the model file.",
                file=sys.stderr,
            )
            return 0
        print(
            "Model file not needed: the installed gaik has no saved_schema module, "
            "so load_schema() reads output_schema.py and the edit is in effect."
        )
        return 0
    print(f"Model written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
