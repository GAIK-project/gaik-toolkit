#!/usr/bin/env python3
"""Check requirement completeness against the Section-9 checklist (V3 Gate 1).

Run before component selection. Reports which of the 13 checklist points are
answered vs. still missing, so the wizard knows exactly what follow-up
questions to ask. Exit code 0 when complete, 1 when points are still missing.

Usage:
    python check_requirements.py --blueprint path/to/use_case.blueprint.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.requirements import check_completeness, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Section-9 requirement completeness for a (draft) blueprint."
    )
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json (draft is fine)")
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

    print(summary(blueprint))
    return 0 if not check_completeness(blueprint) else 1


if __name__ == "__main__":
    sys.exit(main())
