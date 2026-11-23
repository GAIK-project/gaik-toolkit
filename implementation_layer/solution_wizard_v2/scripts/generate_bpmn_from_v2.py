#!/usr/bin/env python3
"""Generate BPMN 2.0 XML from V2 simplified blueprint JSON on stdin."""

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
    session_id = sys.argv[1] if len(sys.argv) > 1 else "session"
    v2 = json.load(sys.stdin)
    v1 = v2_to_v1_dict(v2, session_id=session_id)
    blueprint = Blueprint.model_validate(v1)
    sys.stdout.write(generate_bpmn(blueprint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
