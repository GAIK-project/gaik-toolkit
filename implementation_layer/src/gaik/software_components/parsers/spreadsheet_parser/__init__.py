"""Spreadsheet Parser

Converts .xlsx workbooks and .csv files to Markdown tables. Each table has a leading
``Row`` column with the source row number, so a citation can name the sheet and row.

Main Classes:
    - SpreadsheetParser: Convert a spreadsheet to Markdown tables

Example:
    >>> from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser
    >>> markdown = SpreadsheetParser().parse_spreadsheet("budget.xlsx")
"""

from .spreadsheet_parser import SpreadsheetParser

__all__ = [
    "SpreadsheetParser",
]

__version__ = "0.1.0"
