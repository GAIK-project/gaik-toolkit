#!/usr/bin/env python3
"""Generate a Mermaid diagram from a blueprint and write workflow.mmd.

Validates the blueprint before rendering by default. Use --skip-validation
to render regardless (e.g. while iterating on a draft blueprint).

Usage:
    python generate_mermaid.py --blueprint path/to/blueprint.json --output-dir path/to/output/
    python generate_mermaid.py --blueprint path/to/blueprint.json --output-dir path/to/output/ --skip-validation
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.validator import validate
from solution_wizard.visualizer import write_mermaid


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Mermaid diagram from blueprint.")
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write workflow.mmd")
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

    mmd_path = write_mermaid(blueprint, args.output_dir)
    print(f"Mermaid diagram written to: {mmd_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
