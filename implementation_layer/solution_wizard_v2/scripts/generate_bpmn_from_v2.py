#!/usr/bin/env python3
"""Generate BPMN 2.0 XML from V2 simplified blueprint JSON on stdin.

Usage: generate_bpmn_from_v2.py [session_id] [--no-data-objects]
``--no-data-objects`` draws the compact diagram without data objects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solution_wizard" / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.bpmn_generator import generate_bpmn  # noqa: E402
from solution_wizard.v2_adapter import v2_to_v1_dict  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    include_data_objects = "--no-data-objects" not in args
    positional = [a for a in args if not a.startswith("--")]
    session_id = positional[0] if positional else "session"
    v2 = json.load(sys.stdin)
    v1 = v2_to_v1_dict(v2, session_id=session_id)
    blueprint = Blueprint.model_validate(v1)
    sys.stdout.write(generate_bpmn(blueprint, include_data_objects=include_data_objects))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
