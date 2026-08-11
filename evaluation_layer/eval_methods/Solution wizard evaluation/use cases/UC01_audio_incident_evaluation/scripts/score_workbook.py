#!/usr/bin/env python3
r"""Calculate UC01 scores from the evaluator-completed Excel workbook.

Place this file in the evaluation package's ``scripts`` directory and run it
from the package root:

    python .\scripts\score_workbook.py

Optional positional arguments:

    python .\scripts\score_workbook.py INPUT_XLSX OUTPUT_JSON
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": MAIN_NS, "r": DOC_REL_NS, "pr": PKG_REL_NS}

CONFIGURATIONS = (
    ("EQ1", "EQ1 Requirements", False),
    ("EQ2", "EQ2 Configuration", False),
    ("EQ3", "EQ3 Package", True),
    ("EQ4", "EQ4 Execution", True),
)


def _sheet_paths(entries: dict[str, bytes]) -> dict[str, str]:
    workbook = ET.fromstring(entries["xl/workbook.xml"])
    relationships = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"].lstrip("/")
        for relationship in relationships.findall("pr:Relationship", NS)
    }
    result: dict[str, str] = {}
    for sheet in workbook.findall("x:sheets/x:sheet", NS):
        relationship_id = sheet.attrib[f"{{{DOC_REL_NS}}}id"]
        target = targets[relationship_id]
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        result[sheet.attrib["name"]] = target
    return result


def _shared_strings(entries: dict[str, bytes]) -> list[str]:
    data = entries.get("xl/sharedStrings.xml")
    if not data:
        return []
    root = ET.fromstring(data)
    return [
        "".join(node.text or "" for node in item.findall(".//x:t", NS))
        for item in root.findall("x:si", NS)
    ]


def _cell_text(
    sheet: ET.Element, coordinate: str, shared_strings: list[str]
) -> str:
    cell = sheet.find(f".//x:c[@r='{coordinate}']", NS)
    if cell is None:
        return ""
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(".//x:is//x:t", NS)
        )
    value = cell.find("x:v", NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def _normalized(value: str) -> str:
    return value.strip().lower()


def _rows(
    sheet: ET.Element, shared_strings: list[str]
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    sheet_data = sheet.find("x:sheetData", NS)
    if sheet_data is None:
        return result
    for row in sheet_data.findall("x:row", NS):
        row_number = int(row.attrib.get("r", "0"))
        if row_number < 4:
            continue
        scored = _normalized(
            _cell_text(sheet, f"A{row_number}", shared_strings)
        )
        check_id = _cell_text(sheet, f"B{row_number}", shared_strings).strip()
        if scored != "yes" or not check_id:
            continue
        result.append(
            {
                "check_id": check_id,
                "run_01": _normalized(
                    _cell_text(sheet, f"I{row_number}", shared_strings)
                ),
                "run_02": _normalized(
                    _cell_text(sheet, f"M{row_number}", shared_strings)
                ),
            }
        )
    return result


def score_workbook(workbook_path: Path, output_path: Path) -> dict[str, Any]:
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")
    with zipfile.ZipFile(workbook_path, "r") as workbook_file:
        entries = {
            info.filename: workbook_file.read(info.filename)
            for info in workbook_file.infolist()
        }

    paths = _sheet_paths(entries)
    shared_strings = _shared_strings(entries)
    results: dict[str, Any] = {
        "schema_version": "1.0.0",
        "scenario_id": "UC01",
        "source_workbook": str(workbook_path),
        "complete": True,
        "metrics": {},
        "diagnostics": {},
    }

    for eq, sheet_name, binary in CONFIGURATIONS:
        sheet = ET.fromstring(entries[paths[sheet_name]])
        rows = _rows(sheet, shared_strings)
        missing = [
            f"{row['check_id']}:{run_name}"
            for row in rows
            for run_name in ("run_01", "run_02")
            if row[run_name] not in {"yes", "no"}
        ]
        if missing:
            results["complete"] = False
            results["metrics"][eq] = {
                "complete": False,
                "missing_verdicts": missing,
            }
            continue

        if not rows:
            results["complete"] = False
            results["metrics"][eq] = {
                "complete": False,
                "missing_verdicts": ["No scored rows found."],
            }
            continue

        run_scores: dict[str, float | int] = {}
        for run_name in ("run_01", "run_02"):
            yes_count = sum(row[run_name] == "yes" for row in rows)
            run_scores[run_name] = (
                int(yes_count == len(rows)) if binary else yes_count / len(rows)
            )
        if binary:
            combined = (run_scores["run_01"] + run_scores["run_02"]) / 2
        else:
            combined = (
                sum(
                    int(row["run_01"] == "yes")
                    + int(row["run_02"] == "yes")
                    for row in rows
                )
                / (len(rows) * 2)
            )
        results["metrics"][eq] = {
            "complete": True,
            "scored_checks_per_run": len(rows),
            "run_01": run_scores["run_01"],
            "run_02": run_scores["run_02"],
            "combined": combined,
        }

    recovery = ET.fromstring(entries[paths["PoC Recovery"]])
    results["diagnostics"]["poc_recovery"] = {
        "scored_under_EQ4": False,
        "maximum_refinement_attempts": 3,
        "run_01": {
            "initial_execution_successful": _cell_text(
                recovery, "B4", shared_strings
            ),
            "refinement_attempts_to_success": _cell_text(
                recovery, "B5", shared_strings
            ),
            "final_execution_successful": _cell_text(
                recovery, "B6", shared_strings
            ),
            "status": _cell_text(recovery, "B7", shared_strings),
        },
        "run_02": {
            "initial_execution_successful": _cell_text(
                recovery, "D4", shared_strings
            ),
            "refinement_attempts_to_success": _cell_text(
                recovery, "D5", shared_strings
            ),
            "final_execution_successful": _cell_text(
                recovery, "D6", shared_strings
            ),
            "status": _cell_text(recovery, "D7", shared_strings),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(results, indent=2, ensure_ascii=False)}\n",
        encoding="utf-8",
    )
    return results


def main() -> int:
    script_directory = Path(__file__).resolve().parent
    package_root = script_directory.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=package_root / "results" / "UC01_comparison.xlsx",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=package_root / "results" / "UC01_scores.json",
    )
    arguments = parser.parse_args()
    results = score_workbook(
        arguments.workbook.resolve(), arguments.output.resolve()
    )
    print(f"Wrote {arguments.output.resolve()}")
    if not results["complete"]:
        print("Scoring is incomplete because one or more human verdicts are blank.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
