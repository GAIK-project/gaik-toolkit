"""Offline tests for SpreadsheetParser: row numbers, cell rendering and failures."""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

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


def _copy_with_formula_result(source_path, target_path, cell_ref, value):
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", namespace)
    with ZipFile(source_path) as source, ZipFile(target_path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            contents = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(contents)
                cell = root.find(f".//{{{namespace}}}c[@r='{cell_ref}']")
                assert cell is not None
                cached_value = cell.find(f"{{{namespace}}}v")
                assert cached_value is not None
                cached_value.text = str(value)
                contents = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, contents)


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


def test_xlsx_preserves_values_and_number_formats(tmp_path):
    path = tmp_path / "formatted.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Percent", "Date", "Price", "Identifier"])
    sheet.append([0.25, datetime(2026, 8, 10), 1234.5, 7])
    sheet["A2"].number_format = "0%"
    sheet["B2"].number_format = "DD.MM.YYYY"
    sheet["C2"].number_format = '#,##0.00 "EUR"'
    sheet["D2"].number_format = "0000"
    workbook.save(path)

    result = SpreadsheetParser().parse_spreadsheet(path)

    assert (
        result == "## Sheet: Sheet\n\n"
        "| Row | Percent | Date | Price | Identifier |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2 | 25% | 2026-08-10 | 1234.50 EUR | 0007 |"
    )


# Excel's Accounting format for euros, as a Finnish workbook stores it.
ACCOUNTING_EUR = '_-* #,##0.00\\ "€"_-;\\-* #,##0.00\\ "€"_-;_-* "-"??\\ "€"_-;_-@_-'


@pytest.mark.parametrize(
    ("value", "number_format", "expected"),
    [
        # The format's text, decimals and leading zeros are shown with the value.
        (1234.5, ACCOUNTING_EUR, "1234.50 €"),
        (-1234.5, ACCOUNTING_EUR, "-1234.50 €"),
        (0, ACCOUNTING_EUR, "0.00 €"),
        (1234.5, '"$"#,##0.00_);[Red]("$"#,##0.00)', "$1234.50"),
        (-1234.5, '"$"#,##0.00_);[Red]("$"#,##0.00)', "-$1234.50"),
        (1234.5, "[$€-40B] #,##0.00", "€ 1234.50"),
        (1234.5, "#,##0.00 [$kr-41D]", "1234.50 kr"),
        (12, '0.0" kg"', "12.0 kg"),
        (12, 'General" pcs"', "12 pcs"),
        (7, "000000", "000007"),
        (0.07, "0%", "7%"),
        (0.5, "0.00%", "50.00%"),
        (1500000, "#,##0", "1500000"),
        # Digits the format would round away are kept.
        (0.256, "0%", "25.6%"),
        (1234.567, "0.00", "1234.567"),
        # Text formats and General add nothing, and a format applies to numbers only.
        (7, "@", "7"),
        (7, "General", "7"),
        ("A001", "0000", "A001"),
        (True, "0.00", "True"),
        (datetime(2026, 8, 10), "mm-dd-yy", "2026-08-10"),
        # A format the parser does not render stays next to the stored value.
        (12345.678, "0.00E+00", "12345.678 (number format: 0.00E+00)"),
        (0.5, "# ?/?", "0.5 (number format: # ?/?)"),
        (1500000, "#,##0,", "1500000 (number format: #,##0,)"),
        (358401234567, "000-000 0000", "358401234567 (number format: 000-000 0000)"),
        (-5, "+0;-0", "-5 (number format: +0;-0)"),
        (5, "[>100]0.0;0", "5 (number format: [>100]0.0;0)"),
    ],
)
def test_number_formats(value, number_format, expected):
    assert _cell(value, number_format) == expected


def test_a_formatted_sheet_stays_close_to_its_plain_size(tmp_path):
    path = tmp_path / "prices.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Code", "Date", "Price", "Share"])
    for row in range(2, 52):
        sheet.append([f"A{row:03d}", datetime(2026, 8, 1), 1234.5, 0.25])
        sheet[f"A{row}"].number_format = "@"
        sheet[f"B{row}"].number_format = "mm-dd-yy"
        sheet[f"C{row}"].number_format = ACCOUNTING_EUR
        sheet[f"D{row}"].number_format = "0%"
    workbook.save(path)

    result = SpreadsheetParser().parse_spreadsheet(path)

    assert "| 2 | A002 | 2026-08-01 | 1234.50 € | 25% |" in result
    assert "number format" not in result


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


def test_formulas_keep_stored_results_and_number_formats(tmp_path):
    source_path = tmp_path / "source.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Total"])
    sheet.append(["=SUM(1,1)"])
    sheet["A2"].number_format = "0.00"
    workbook.save(source_path)
    path = tmp_path / "budget.xlsx"
    _copy_with_formula_result(source_path, path, "A2", 2)

    result = SpreadsheetParser().parse_spreadsheet(path)

    assert "| 2 | 2.00 |" in result
