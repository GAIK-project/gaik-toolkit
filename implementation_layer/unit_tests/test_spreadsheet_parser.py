"""Offline tests for SpreadsheetParser: row numbers, cell rendering and failures."""

from __future__ import annotations

from datetime import datetime

import pytest
from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser
from gaik.software_components.parsers.spreadsheet_parser.spreadsheet_parser import _cell
from openpyxl import Workbook


def _xlsx(path, sheets: dict[str, list[list]]):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    workbook.save(path)
    return path


def test_xlsx_keeps_source_row_numbers_and_renders_cells(tmp_path):
    path = _xlsx(
        tmp_path / "log.xlsx",
        {
            "Empty": [],
            "Log": [
                [],
                ["Date", "Item", "Cost"],
                [datetime(2016, 5, 12), "Gutter | east", 450],
                [None, None, None],
                [datetime(2019, 8, 30, 14, 15), "Roof\nrepair", 1200.5],
            ],
        },
    )

    assert SpreadsheetParser().parse_spreadsheet(path) == (
        "## Sheet: Log\n\n"
        "| Row | Date | Item | Cost |\n"
        "| --- | --- | --- | --- |\n"
        "| 3 | 2016-05-12 | Gutter \\| east | 450 |\n"
        "| 5 | 2019-08-30 14:15:00 | Roof repair | 1200.5 |"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (12.0, "12"),
        (12.5, "12.5"),
        (datetime(2016, 5, 12), "2016-05-12"),
        (datetime(2016, 5, 12, 8, 30), "2016-05-12 08:30:00"),
        ("a|b\r\nc", "a\\|b c"),
    ],
)
def test_cell_rendering(value, expected):
    assert _cell(value) == expected


def test_csv_is_one_table_without_sheet_heading(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("Item,Cost\n\nRoof,450\n", encoding="utf-8")

    result = SpreadsheetParser().parse_document(path)

    assert (
        result["text_content"] == "| Row | Item | Cost |\n| --- | --- | --- |\n| 3 | Roof | 450 |"
    )
    assert result["file_name"] == "log.csv"
    assert result["file_extension"] == ".csv"


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "old.xls"
    path.write_bytes(b"legacy")
    with pytest.raises(ValueError, match=r"old\.xls: unsupported spreadsheet type \.xls"):
        SpreadsheetParser().parse_spreadsheet(path)


def test_empty_workbook_and_csv_raise(tmp_path):
    workbook = _xlsx(tmp_path / "empty.xlsx", {"Sheet1": [[None, " "]], "Sheet2": []})
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("\n,\n", encoding="utf-8")
    for path in (workbook, csv_path):
        with pytest.raises(ValueError, match="no non-empty rows"):
            SpreadsheetParser().parse_spreadsheet(path)


def test_formulas_without_stored_results_raise(tmp_path):
    # openpyxl writes formulas without results, so data_only=True would read them as blank.
    path = _xlsx(tmp_path / "budget.xlsx", {"Budget": [["Total"], [1], ["=SUM(A2:A2)"]]})
    with pytest.raises(ValueError, match="budget.xlsx: its formulas have no stored results"):
        SpreadsheetParser().parse_spreadsheet(path)
