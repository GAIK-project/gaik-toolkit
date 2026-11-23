"""Spreadsheet (.xlsx, .csv) to Markdown tables that keep the source row numbers."""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple

from ...file_type import TEXT_TYPES, check_file_type
from ...input_limits import InputLimits, count_table_rows
from .._text import decode_text

# CSV delimiters, in the order a tie between them goes (see _csv_delimiter).
_CSV_DELIMITERS = ("\t", ";", "|", ",")
# How much of a CSV its delimiter is read from.
_CSV_SAMPLE_CHARS = 64 * 1024
# The share of rows that must have the header's field count for a delimiter to count.
_CSV_CONSISTENT_ROWS = 0.8

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


def _sections(number_format: str) -> list[str] | None:
    """The ``;``-separated sections of a number format: positive, negative, zero, text.

    None for a format with a condition (``[>100]``), which picks its sections by value
    rather than by sign, or with an unterminated quote or bracket.
    """
    sections: list[str] = []
    start = index = 0
    while index < len(number_format):
        char = number_format[index]
        if char in '"[':
            end = number_format.find('"' if char == '"' else "]", index + 1)
            if end < 0:
                return None
            if char == "[" and number_format[index + 1 : index + 2] in ("<", ">", "="):
                return None
            index = end + 1
            continue
        if char in "\\_*":
            # An escaped character, room for one or a fill with one: never a separator.
            index += 2
            continue
        if char == ";":
            sections.append(number_format[start:index])
            start = index + 1
        index += 1
    sections.append(number_format[start:])
    return sections


def _number_layout(number_format: str) -> _NumberLayout | None:
    """Read one section of an Excel number format (see :func:`_sections`).

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


def _section_text(layout: _NumberLayout) -> str:
    """The text a section shows around the digits, without spacing or a percent sign."""
    return " ".join(f"{layout.before} {layout.after}".replace("%", " ").split())


def _laid_out(value: int | float, layout: _NumberLayout, sign: str = "") -> str:
    """The absolute value laid out as ``layout`` says, after ``sign``."""
    number = abs(Decimal(repr(value))) * (100 if layout.percent else 1)
    whole, _, fraction = format(number, "f").partition(".")
    fraction = fraction.rstrip("0").ljust(layout.decimal_digits, "0")
    text = whole.zfill(layout.integer_digits) + (f".{fraction}" if fraction else "")
    return " ".join(f"{sign}{layout.before}{text}{layout.after}".split())


def _formatted_number(value: int | float, number_format: str) -> str | None:
    """The number as its format shows it, or None when the format is not rendered.

    Nothing of the stored value is lost: digits the format would round away are kept, and
    no thousands separator is added, since its character depends on the reader's locale.
    A negative number takes the format's second section when it has one, as Excel does
    (``-1200`` with ``0.00" Cr";0.00" Dr"`` is ``1200.00 Dr``). Excel adds no minus there,
    so a section whose own text shows no sign and does not differ from the positive
    section's (``0;0``, ``0.00;[Red]0.0``, where only a colour or the decimals differ) is
    not rendered: the plain value keeps the sign. Zero takes the first section, not the
    third: a zero section mostly shows a dash or nothing in place of the value.
    """
    sections = _sections(number_format)
    if sections is None or not math.isfinite(value):
        return None
    positive = _number_layout(sections[0])
    if positive is None:
        return None
    if value < 0 and len(sections) > 1:
        negative = _number_layout(sections[1])
        if negative is None:
            return None
        text = _section_text(negative)
        if not set(text) & set("-()") and text == _section_text(positive):
            return None
        return _laid_out(value, negative)
    if value < 0 and set(positive.before + positive.after) & set("+-()"):
        # The format's own sign is for a positive number.
        return None
    return _laid_out(value, positive, "-" if value < 0 else "")


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


def _xlsx_blocks(path: Path, limits: InputLimits) -> list[str]:
    """One ``## Sheet`` table per non-empty sheet, with the stored results of formulas."""
    from openpyxl import load_workbook

    values = load_workbook(path, read_only=True, data_only=True)
    formulas = load_workbook(path, read_only=True)
    try:
        blocks, results = [], []
        for sheet, formula_sheet in zip(values.worksheets, formulas.worksheets):
            # Read-only mode trusts the size a sheet states (<dimension ref>), which a
            # writer can leave stale ("A1" over six rows); read the rows themselves.
            sheet.reset_dimensions()
            formula_sheet.reset_dimensions()
            rows, number_formats = [], []
            sheet_rows = count_table_rows(sheet.iter_rows(), limits, f"{path.name} / {sheet.title}")
            for row, formula_cells in zip(sheet_rows, formula_sheet.iter_rows()):
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


def _csv_delimiter(text: str) -> str:
    """The delimiter that splits the CSV's rows into the same number of fields, at least two.

    The header is the first non-empty row that the delimiter splits; rows above it with
    one field, such as an unpadded title ("Sales report"), are skipped. A delimiter
    counts only when the header has the most common field count of the rows from it on,
    and at least ``_CSV_CONSISTENT_ROWS`` of those rows have it. After skipped rows, two
    data rows must agree with the header, so a one-column file whose cells hold an odd
    ``;`` stays one column. Delimiters are then compared by how many rows have that
    count, then by the count. A tie goes to tab, then ``;``, ``|`` and ``,``: a
    semicolon CSV, which Excel writes in a locale with a decimal comma, often has commas
    in its cells, while a comma CSV seldom has semicolons. ``,`` when no delimiter counts.
    """
    sample = text[:_CSV_SAMPLE_CHARS]
    best, best_score = ",", None
    for preference, delimiter in enumerate(_CSV_DELIMITERS):
        rows = list(csv.reader(io.StringIO(sample, newline=""), delimiter=delimiter))
        if len(sample) < len(text) and rows:
            rows.pop()  # The sample may end inside this row.
        counts = [len(row) for row in rows if any(cell.strip() for cell in row)]
        header = next((n for n, count in enumerate(counts) if count >= 2), None)
        if header is None or (header and len(counts) - header < 3):
            continue
        counts = counts[header:]
        fields = Counter(counts).most_common(1)[0][0]
        consistency = counts.count(fields) / len(counts)
        if counts[0] != fields or consistency < _CSV_CONSISTENT_ROWS:
            continue
        score = (consistency, fields, -preference)
        if best_score is None or score > best_score:
            best, best_score = delimiter, score
    return best


class SpreadsheetParser:
    """Convert an .xlsx workbook or a .csv file to Markdown tables.

    The first non-empty row of each sheet is the header. A ``Row`` column holds the
    1-based sheet or CSV row number of each data row, so a citation can name the row.

    A CSV's delimiter (``,``, ``;``, tab or ``|``) is read from its rows, and its text
    from UTF-8, UTF-16 with a byte order mark or, failing those, Windows-1252, the
    "ANSI" code page Excel saves a plain CSV in on Western-European Windows.

    A file over its input limits (size, unpacked size, rows per sheet) is refused
    with ``InputLimitError``; the size is checked before the file is opened.
    """

    def __init__(
        self,
        *,
        limits: InputLimits | None = None,
        csv_delimiter: str | None = None,
        csv_encoding: str | None = None,
    ) -> None:
        """
        Args:
            limits: Size and row limits; defaults to
                :class:`~gaik.software_components.input_limits.InputLimits`.
            csv_delimiter: The CSV field delimiter, one character; ``None`` (default)
                reads it from the file's rows.
            csv_encoding: The CSV's text encoding, such as ``"utf-8"`` or ``"cp1252"``;
                ``None`` (default) reads it as the class docstring says.

        Raises:
            ValueError: If ``csv_delimiter`` is not one character, or is a quote or a
                line break.
        """
        if csv_delimiter is not None and (len(csv_delimiter) != 1 or csv_delimiter in '"\r\n'):
            raise ValueError(f"csv_delimiter must be one character, got {csv_delimiter!r}")
        self.limits = limits or InputLimits()
        self.csv_delimiter = csv_delimiter
        self.csv_encoding = csv_encoding

    def parse_spreadsheet(self, file_path: str | Path) -> str:
        """Return the spreadsheet as Markdown: one ``## Sheet: <name>`` table per sheet.

        Raises:
            ValueError: For an unsupported type, a spreadsheet without rows, or a
                CSV whose text cannot be decoded (the message names the fix).
            FileTypeMismatchError: If the content is not the type the file's
                extension says: an .xlsx that is no XLSX workbook, a .csv that is
                not text (a ``ValueError``).
            InputLimitError: If the file is over ``max_file_bytes``, an .xlsx unpacks
                to more than ten times that, or a sheet has more than ``max_table_rows``.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            self.limits.check_zip_container(path)
            check_file_type(path, {"xlsx"})
            blocks = _xlsx_blocks(path, self.limits)
        elif suffix == ".csv":
            self.limits.check_file_size(path)
            check_file_type(path, TEXT_TYPES)
            text = decode_text(
                path.read_bytes(),
                path,
                self.csv_encoding,
                advice="save it as UTF-8 (in Excel: CSV UTF-8) or pass csv_encoding",
            )
            delimiter = self.csv_delimiter or _csv_delimiter(text)
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
            rows = count_table_rows(reader, self.limits, path.name)
            blocks = [table] if (table := _table(rows)) else []
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
