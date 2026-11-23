#!/usr/bin/env python3
"""Sync V2 blueprint JSON from edited BPMN XML. Args: session_id. stdin: {xml, blueprint}."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solution_wizard" / "src"))

from solution_wizard.bpmn_sync import sync_v2_blueprint_from_bpmn_xml  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    synced = sync_v2_blueprint_from_bpmn_xml(payload["blueprint"], payload["xml"])
    json.dump(synced, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
