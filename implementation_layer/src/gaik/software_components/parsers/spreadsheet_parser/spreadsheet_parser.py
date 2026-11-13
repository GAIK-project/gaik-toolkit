"""Spreadsheet (.xlsx, .csv) to Markdown tables that keep the source row numbers."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

# Characters a number format shows as they are, without quotes.
_PLAIN_TEXT = frozenset("  -+()$€£¥")
_COLOURS = frozenset({"black", "blue", "cyan", "green", "magenta", "red", "white", "yellow"})


class _NumberLayout(NamedTuple):
    """How a number format shows a number."""

    before: str
    after: str
    integer_digits: int
    decimal_digits: int
    percent: bool


def _number_layout(number_format: str) -> _NumberLayout | None:
    """Read the first section of an Excel number format, the one for positive numbers.

    None for a format this parser does not render: scientific notation, fractions,
    conditions, digits scaled by a trailing comma or split by text (``000-000``).
    """
    before: list[str] = []
    after: list[str] = []
    digits = ""
    percent = False
    index = 0
    while index < len(number_format):
        char = number_format[index]
        index += 1
        if char == ";":
            break
        if char in "_*":
            # Room for the next character, or a fill with it: neither is text.
            index += 1
            continue
        if char in "0#?.," or number_format.startswith("General", index - 1):
            if after:
                return None
            if char == "G":
                char, index = "#", index + len("General") - 1
            digits += char
            continue
        if char == '"':
            end = number_format.find('"', index)
            if end < 0:
                return None
            text, index = number_format[index:end], end + 1
        elif char == "\\":
            text, index = number_format[index : index + 1], index + 1
        elif char == "[":
            end = number_format.find("]", index)
            if end < 0:
                return None
            inside, index = number_format[index:end], end + 1
            if inside.startswith("$"):
                text = inside[1:].split("-", 1)[0]  # [$€-40B] is €, [$-409] only a locale
            elif inside.lower() in _COLOURS or inside.lower().startswith("color"):
                text = ""
            else:
                return None
        elif char == "%":
            text, percent = "%", True
        elif char in _PLAIN_TEXT:
            text = char
        else:
            return None
        (after if digits else before).append(text)

    integer, _, decimals = digits.partition(".")
    grouped = integer.replace(",", "")
    if (
        not (grouped or decimals)
        or "." in decimals
        or "," in decimals
        or integer.startswith(",")
        or integer.endswith(",")
    ):
        return None
    return _NumberLayout(
        "".join(before), "".join(after), grouped.count("0"), decimals.count("0"), percent
    )


def _formatted_number(value: int | float, number_format: str) -> str | None:
    """The number as its format shows it, or None when the format is not rendered.

    Nothing of the stored value is lost: digits the format would round away are kept, and
    no thousands separator is added, since its character depends on the reader's locale.
    """
    layout = _number_layout(number_format)
    if layout is None or not math.isfinite(value):
        return None
    signs = set(layout.before + layout.after) & set("+-()")
    if value < 0 and signs:
        # The format's own sign is for a positive number.
        return None
    number = Decimal(repr(value)) * (100 if layout.percent else 1)
    whole, _, fraction = format(abs(number), "f").partition(".")
    fraction = fraction.rstrip("0").ljust(layout.decimal_digits, "0")
    text = whole.zfill(layout.integer_digits) + (f".{fraction}" if fraction else "")
    sign = "-" if number < 0 else ""
    return " ".join(f"{sign}{layout.before}{text}{layout.after}".split())


def _number(value: int | float, number_format: str | None) -> str:
    plain = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if not number_format or number_format in ("General", "@"):
        return plain
    shown = _formatted_number(value, number_format)
    if shown is None:
        return f"{plain} (number format: {number_format})"
    return shown


def _cell(value: Any, number_format: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        text = value.date().isoformat() if value.time() == time() else value.isoformat(sep=" ")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        text = _number(value, number_format)
    else:
        text = str(value)
    return " ".join(text.splitlines()).replace("|", "\\|")


def _table(
    rows: Iterable[Iterable[Any]],
    number_formats: Sequence[Sequence[str | None]] | None = None,
) -> str | None:
    """Render rows as a Markdown table with a leading ``Row`` column; None if all are empty."""
    kept = []
    source_rows = (
        zip(rows, number_formats) if number_formats is not None else ((row, None) for row in rows)
    )
    for number, (row, formats) in enumerate(source_rows, start=1):
        cells = [
            _cell(value, formats[index] if formats is not None and index < len(formats) else None)
            for index, value in enumerate(row)
        ]
        while cells and not cells[-1].strip():
            cells.pop()
        if cells:
            kept.append([str(number), *cells])
    if not kept:
        return None
    width = max(len(cells) for cells in kept)
    header, *body = [cells + [""] * (width - len(cells)) for cells in kept]
    lines = [["Row", *header[1:]], ["---"] * width, *body]
    return "\n".join("| " + " | ".join(line) + " |" for line in lines)


def _xlsx_blocks(path: Path) -> list[str]:
    """One ``## Sheet`` table per non-empty sheet, with the stored results of formulas."""
    from openpyxl import load_workbook

    values = load_workbook(path, read_only=True, data_only=True)
    formulas = load_workbook(path, read_only=True)
    try:
        blocks, results = [], []
        for sheet, formula_sheet in zip(values.worksheets, formulas.worksheets):
            rows, number_formats = [], []
            for row, formula_cells in zip(sheet.iter_rows(), formula_sheet.iter_rows()):
                rows.append([cell.value for cell in row])
                number_formats.append([cell.number_format for cell in row])
                results += [
                    cell.value
                    for cell, formula in zip(row, formula_cells)
                    if formula.data_type == "f"
                ]
            if table := _table(rows, number_formats):
                blocks.append(f"## Sheet: {sheet.title}\n\n{table}")
    finally:
        values.close()
        formulas.close()
    # A file written by a library such as openpyxl has formulas but no results, which
    # would read as blank cells. A single empty result can be a legitimate "".
    if results and all(v is None for v in results):
        raise ValueError(
            f"{path.name}: its formulas have no stored results; "
            "open and save it in Excel or LibreOffice to calculate them"
        )
    return blocks


class SpreadsheetParser:
    """Convert an .xlsx workbook or a .csv file to Markdown tables.

    The first non-empty row of each sheet is the header. A ``Row`` column holds the
    1-based sheet or CSV row number of each data row, so a citation can name the row.
    """

    def parse_spreadsheet(self, file_path: str | Path) -> str:
        """Return the spreadsheet as Markdown: one ``## Sheet: <name>`` table per sheet."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            blocks = _xlsx_blocks(path)
        elif suffix == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                blocks = [table] if (table := _table(csv.reader(handle))) else []
        else:
            raise ValueError(f"{path.name}: unsupported spreadsheet type {suffix}")
        if not blocks:
            raise ValueError(f"{path.name}: spreadsheet has no non-empty rows")
        return "\n\n".join(blocks)

    def parse_document(self, file_path: str | Path) -> dict[str, Any]:
        """Parse a spreadsheet and return its Markdown with file metadata."""
        path = Path(file_path)
        text_content = self.parse_spreadsheet(path)
        return {
            "file_path": str(path),
            "file_name": path.name,
            "file_extension": path.suffix.lower(),
            "text_content": text_content,
            "content_length": len(text_content),
            "word_count": len(text_content.split()),
            "parsing_method": "spreadsheet",
        }
