#!/usr/bin/env python3
"""Validate a blueprint JSON against all V1 rules.

Usage:
    python validate_blueprint.py --blueprint path/to/use_case.blueprint.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.validator import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a GAIK use-case blueprint.")
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json")
    args = parser.parse_args()

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.exists():
        print(f"ERROR: Blueprint file not found: {blueprint_path}", file=sys.stderr)
        return 1

    try:
        blueprint = Blueprint.from_file(blueprint_path)
    except Exception as exc:
        print(f"ERROR: Failed to load blueprint: {exc}", file=sys.stderr)
        return 1

    result = validate(blueprint)
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
