#!/usr/bin/env python3
"""Generate the use-case documentation suite (spec §18) into <output_dir>/docs/.

Produces five documents from the validated blueprint: GenAI product canvas,
technical specification, user guide, developer guide, and evaluation plan. They
are deterministic skeletons pre-filled with blueprint facts; the wizard then
fills the `<!-- AGENT: ... -->` narrative markers.

Validates the blueprint first by default. Use --skip-validation for drafts.

Usage:
    python generate_docs.py --blueprint path/to/use_case.blueprint.json --output-dir path/to/output/
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.docs_generator import generate_docs
from solution_wizard.validator import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the use-case documentation suite.")
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json")
    parser.add_argument("--output-dir", required=True, help="Directory; docs are written to <output-dir>/docs/")
    parser.add_argument("--skip-validation", action="store_true", help="Render even if validation fails (drafts)")
    args = parser.parse_args()

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.exists():
        print(f"ERROR: Blueprint not found: {blueprint_path}", file=sys.stderr)
        return 1

    try:
        blueprint = Blueprint.from_file(blueprint_path)
    except Exception as exc:
        print(f"ERROR: Failed to load blueprint: {exc}", file=sys.stderr)
        return 1

    if not args.skip_validation:
        result = validate(blueprint)
        if not result.ok:
            print(result.summary(), file=sys.stderr)
            print("\nBlueprint has validation errors. Fix them first, or use --skip-validation.", file=sys.stderr)
            return 1
        for w in result.warnings:
            print(f"WARNING {w}")

    written = generate_docs(blueprint, args.output_dir)
    print("Documentation suite written:")
    for p in written:
        print(f"  - {p}")
    print("\nNext: fill the <!-- AGENT: ... --> narrative sections in each document.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
