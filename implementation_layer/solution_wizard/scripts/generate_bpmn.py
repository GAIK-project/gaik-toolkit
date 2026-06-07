#!/usr/bin/env python3
"""Generate a BPMN 2.0 diagram from a blueprint and write workflow.bpmn.

The BPMN is the *visual blueprint*: a standards-based, Level-2 business-process
model derived from the blueprint JSON. It is linked-by-derivation -- every
element id maps back to a blueprint object (the map is written to
visualizations.bpmn_mapping). Keep it in sync by editing the JSON and
regenerating; never hand-edit the diagram.

Validates the blueprint before rendering by default. Use --skip-validation to
render regardless (e.g. while iterating on a draft blueprint).

Usage:
    python generate_bpmn.py --blueprint path/to/blueprint.json --output-dir path/to/output/
    python generate_bpmn.py --blueprint path/to/blueprint.json --output-dir path/to/output/ --skip-validation
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import write_bpmn
from solution_wizard.validator import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BPMN 2.0 diagram from blueprint.")
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write workflow.bpmn")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip blueprint validation and render anyway (useful for draft blueprints)",
    )
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
            print(
                "\nBlueprint has validation errors. Fix them first, or use "
                "--skip-validation to render anyway.",
                file=sys.stderr,
            )
            return 1
        for w in result.warnings:
            print(f"WARNING {w}")

    bpmn_path = write_bpmn(blueprint, args.output_dir)
    print(f"BPMN diagram written to: {bpmn_path}")

    # Persist the updated blueprint so visualizations.bpmn_mapping is saved.
    # write_bpmn() populates the mapping in-memory; without this the map is lost
    # when the process exits (run_wizard.py writes the blueprint, but the
    # standalone CLI must do it too to stay consistent with the documentation).
    out_blueprint = Path(args.output_dir) / "use_case.blueprint.json"
    blueprint.to_file(out_blueprint)
    print(f"Blueprint (with bpmn_mapping) saved to: {out_blueprint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
