"""The price list preview of the Purchase Order demo must match the spreadsheet."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_example_price_list.py"


def _script():
    spec = importlib.util.spec_from_file_location("build_example_price_list", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_json_preview_matches_the_example_spreadsheet():
    module = _script()

    # Fails when the price list changed without running scripts/build_example_price_list.py.
    current = module.TARGET.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == module.render()


def test_the_preview_keeps_the_rows_the_example_order_uses():
    module = _script()
    rows = json.loads(module.TARGET.read_text(encoding="utf-8"))["rows"]
    by_item = {row[0]: row for row in rows if row}

    # Item No., type designation, ..., unit price, ..., cutting, testing and cert fees.
    assert by_item["MAT-2401"][1] == "Aluminum Angle - L Profile"
    assert by_item["MAT-2401"][4] == 28.5
    assert by_item["MAT-4829"][4] == 67.2
