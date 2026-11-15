# Spreadsheet Parser

Converts `.xlsx` workbooks and `.csv` files to Markdown tables. Each table has a leading
`Row` column with the source row number, so a citation can say "sheet Log, row 7".

## Installation

```bash
pip install "gaik[spreadsheet-parser]"
```

Runs locally; no API access is needed.

---

## Quick Start

```python
from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

parser = SpreadsheetParser()
markdown = parser.parse_spreadsheet("maintenance_log.xlsx")
print(markdown)

# The same text with file metadata (file_name, file_extension, text_content, ...)
result = parser.parse_document("maintenance_log.xlsx")
```

---

## Output Format

An `.xlsx` file gives one `## Sheet: <name>` block per sheet. A `.csv` file gives a
single table with no sheet heading.

```markdown
## Sheet: Log

| Row | Date | Item | Cost |
| --- | --- | --- | --- |
| 2 | 2016-05-12 | Roof inspection | 450 |
| 4 | 2019-08-30 14:15:00 | Gutter repair \| east side | 1200.5 |
```

- The first non-empty row is the header.
- The `Row` column holds the 1-based sheet or CSV row number of each data row. Empty rows
  are dropped; the numbers of the rows kept stay those of the source (row 3 above was
  empty).
- `|` in a cell is escaped as `\|`, and newlines in a cell become spaces. An empty cell
  stays empty.
- A date at midnight renders as an ISO date and other date-times as
  `YYYY-MM-DD HH:MM:SS`. A whole-number float such as `12.0` renders as `12`.
- A number is shown with what its Excel number format adds: `0.25` with `0%` is `25%`,
  `1234.5` with `#,##0.00 "EUR"` is `1234.50 EUR`, `7` with `0000` is `0007`. Nothing of
  the stored value is dropped: digits the format would round away stay (`0.256` with
  `0%` is `25.6%`), and no thousands separator is added, because its character depends
  on the reader's locale. A date keeps the ISO form above whatever its format, and text
  cells are not changed.
- A format the parser does not render (scientific notation, fractions, conditions, digits
  split by text) stays next to the stored value: `0.5 (number format: # ?/?)`.
- Formula cells show the result stored in the file. A workbook whose formulas have no
  stored results (one written by a library such as openpyxl and never opened in Excel)
  raises `ValueError`; open and save it in Excel or LibreOffice first.
- An empty sheet is omitted. A file with no non-empty rows raises `ValueError`.
- Only `.xlsx` and `.csv` are supported; other types, including `.xls`, raise
  `ValueError`.

See the [example](../../../../../examples/software_components/parsers/demo_spreadsheet_parser.py)
for a complete working script.

## License

MIT - see [LICENSE](../../../../../../LICENSE)
