"""Simple demonstration of the spreadsheet parser for .xlsx and .csv files.

Each sheet becomes a Markdown table with a leading Row column that holds the source
row number. Runs locally without API keys.
Requires: pip install gaik[spreadsheet-parser]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

INPUT_DIR = Path(__file__).parent.parent / "tabular_agent" / "input"


def main() -> None:
    """Convert a two-sheet workbook and a CSV file to Markdown tables."""
    parser = SpreadsheetParser()

    print(parser.parse_spreadsheet(INPUT_DIR / "multi_sheet.xlsx"))

    result = parser.parse_document(INPUT_DIR / "sales_clean.csv")
    print("\n" + result["text_content"])
    print(f"\n{result['file_name']}: {result['content_length']} chars")


if __name__ == "__main__":
    main()
