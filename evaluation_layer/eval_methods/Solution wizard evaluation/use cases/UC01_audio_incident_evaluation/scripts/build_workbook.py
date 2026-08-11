#!/usr/bin/env python3
r"""Populate the UC01 Excel comparison template without external dependencies.

Place this file in the evaluation package's ``scripts`` directory and run it
from the package root:

    python .\scripts\build_workbook.py

Optional positional arguments:

    python .\scripts\build_workbook.py INPUT_JSON OUTPUT_XLSX
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": MAIN_NS, "r": DOC_REL_NS, "pr": PKG_REL_NS}
ET.register_namespace("x", MAIN_NS)
ET.register_namespace("r", DOC_REL_NS)

SHEET_GROUPS = {
    "EQ1 Requirements": "EQ1",
    "EQ1 Diagnostics": "EQ1_diagnostics",
    "EQ2 Configuration": "EQ2",
    "EQ3 Package": "EQ3",
    "EQ4 Execution": "EQ4",
}


def _excel_text(value: Any) -> str:
    """Return XML-safe text within Excel's 32,767-character cell limit."""

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    elif value is True:
        text = "Yes"
    elif value is False:
        text = "No"
    else:
        text = str(value)
    text = "".join(
        character
        for character in text
        if character in "\t\n\r" or ord(character) >= 32
    )
    if len(text) > 32767:
        text = f"{text[:32720]}\n[TRUNCATED FOR EXCEL CELL LIMIT]"
    return text


def _display_value(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return ""
    return str(value)


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


def _cell(sheet: ET.Element, coordinate: str) -> ET.Element:
    found = sheet.find(f".//x:c[@r='{coordinate}']", NS)
    if found is not None:
        return found

    match = re.fullmatch(r"([A-Z]+)([0-9]+)", coordinate)
    if not match:
        raise ValueError(f"Invalid Excel coordinate: {coordinate}")
    row_number = match.group(2)
    sheet_data = sheet.find("x:sheetData", NS)
    if sheet_data is None:
        sheet_data = ET.SubElement(sheet, f"{{{MAIN_NS}}}sheetData")
    row = sheet_data.find(f"x:row[@r='{row_number}']", NS)
    if row is None:
        row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": row_number})
    return ET.SubElement(row, f"{{{MAIN_NS}}}c", {"r": coordinate})


def _set_text(sheet: ET.Element, coordinate: str, value: Any) -> None:
    cell = _cell(sheet, coordinate)
    style = cell.attrib.get("s")
    cell.clear()
    cell.attrib["r"] = coordinate
    if style is not None:
        cell.attrib["s"] = style
    text = _excel_text(value)
    cell.attrib["t"] = "str"
    if text:
        ET.SubElement(cell, f"{{{MAIN_NS}}}v").text = text


def _read_text(cell: ET.Element | None, shared_strings: list[str]) -> str:
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


def _shared_strings(entries: dict[str, bytes]) -> list[str]:
    data = entries.get("xl/sharedStrings.xml")
    if not data:
        return []
    root = ET.fromstring(data)
    return [
        "".join(node.text or "" for node in item.findall(".//x:t", NS))
        for item in root.findall("x:si", NS)
    ]


def _row_for_check(
    sheet: ET.Element, check_id: str, shared_strings: list[str]
) -> int:
    for cell in sheet.findall(".//x:c", NS):
        coordinate = cell.attrib.get("r", "")
        if not coordinate.startswith("B"):
            continue
        if _read_text(cell, shared_strings) == check_id:
            return int(coordinate[1:])
    raise KeyError(f"Check {check_id!r} is not present in the workbook template.")


def _run_results(comparison: dict[str, Any], run_name: str, group: str) -> dict[str, dict[str, Any]]:
    rows = (
        comparison.get("runs", {})
        .get(run_name, {})
        .get("results", {})
        .get(group, [])
    )
    return {
        str(row.get("check_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("check_id")
    }


def _populate_evaluation_sheet(
    sheet: ET.Element,
    group: str,
    comparison: dict[str, Any],
    shared_strings: list[str],
) -> None:
    run_01 = _run_results(comparison, "run_01", group)
    run_02 = _run_results(comparison, "run_02", group)
    check_ids = sorted(set(run_01) | set(run_02))
    for check_id in check_ids:
        row_number = _row_for_check(sheet, check_id, shared_strings)
        first = run_01.get(check_id, {})
        second = run_02.get(check_id, {})
        values = {
            f"F{row_number}": first.get("generated_value", ""),
            f"G{row_number}": first.get("evidence", ""),
            f"H{row_number}": first.get("automatic_result", ""),
            f"I{row_number}": first.get("human_verdict", ""),
            f"J{row_number}": second.get("generated_value", ""),
            f"K{row_number}": second.get("evidence", ""),
            f"L{row_number}": second.get("automatic_result", ""),
            f"M{row_number}": second.get("human_verdict", ""),
            f"N{row_number}": " | ".join(
                str(note)
                for note in (
                    first.get("evaluator_notes", ""),
                    second.get("evaluator_notes", ""),
                )
                if note
            ),
        }
        for coordinate, value in values.items():
            _set_text(sheet, coordinate, value)


def _populate_recovery(sheet: ET.Element, comparison: dict[str, Any]) -> None:
    run_01 = (
        comparison.get("runs", {}).get("run_01", {}).get("recovery_diagnostic", {})
    )
    run_02 = (
        comparison.get("runs", {}).get("run_02", {}).get("recovery_diagnostic", {})
    )
    rows = (
        (4, "initial_execution_successful"),
        (5, "refinement_attempts_to_success"),
        (6, "final_execution_successful"),
        (7, "status"),
    )
    for row_number, key in rows:
        _set_text(sheet, f"B{row_number}", _display_value(run_01.get(key)))
        _set_text(sheet, f"C{row_number}", run_01.get("evidence", ""))
        _set_text(sheet, f"D{row_number}", _display_value(run_02.get(key)))
        _set_text(sheet, f"E{row_number}", run_02.get("evidence", ""))


def _force_recalculation(entries: dict[str, bytes]) -> None:
    workbook = ET.fromstring(entries["xl/workbook.xml"])
    calculation = workbook.find("x:calcPr", NS)
    if calculation is None:
        calculation = ET.SubElement(workbook, f"{{{MAIN_NS}}}calcPr")
    calculation.attrib.update(
        {"calcId": "0", "fullCalcOnLoad": "1", "forceFullCalc": "1"}
    )
    entries["xl/workbook.xml"] = ET.tostring(
        workbook, encoding="utf-8", xml_declaration=True
    )


def build_workbook(
    comparison_path: Path, output_path: Path, template_path: Path
) -> None:
    if not comparison_path.is_file():
        raise FileNotFoundError(
            f"Comparison data not found: {comparison_path}. "
            "Run collect_evidence.py --run all first."
        )
    if not template_path.is_file():
        raise FileNotFoundError(f"Workbook template not found: {template_path}")

    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(template_path, "r") as source:
        infos = source.infolist()
        entries = {info.filename: source.read(info.filename) for info in infos}

    paths = _sheet_paths(entries)
    shared_strings = _shared_strings(entries)
    for sheet_name, group in SHEET_GROUPS.items():
        sheet = ET.fromstring(entries[paths[sheet_name]])
        _populate_evaluation_sheet(sheet, group, comparison, shared_strings)
        entries[paths[sheet_name]] = ET.tostring(
            sheet, encoding="utf-8", xml_declaration=True
        )

    recovery = ET.fromstring(entries[paths["PoC Recovery"]])
    _populate_recovery(recovery, comparison)
    entries[paths["PoC Recovery"]] = ET.tostring(
        recovery, encoding="utf-8", xml_declaration=True
    )
    _force_recalculation(entries)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=f"{output_path.stem}.",
        suffix=".xlsx",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as destination:
            for info in infos:
                destination.writestr(info, entries[info.filename])
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    script_directory = Path(__file__).resolve().parent
    package_root = script_directory.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "comparison",
        nargs="?",
        type=Path,
        default=package_root / "results" / "comparison_data.json",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=package_root / "results" / "UC01_comparison.xlsx",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=package_root / "templates" / "UC01_comparison_template.xlsx",
    )
    arguments = parser.parse_args()
    build_workbook(
        arguments.comparison.resolve(),
        arguments.output.resolve(),
        arguments.template.resolve(),
    )
    print(f"Wrote {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
