"""Example: query a report-style Excel file that is not a clean data table.

``messy_report.xlsx`` is laid out for human readers, the way most real
spreadsheets are:

    row 0   ACME Nordics -- Quarterly Sales Report      <- title
    row 1   Generated for internal review               <- subtitle
    row 2                                               <- blank spacer
    row 3   Region | Quarter | Product | Units | Revenue <- the real header
    ...     six data rows per region
            North subtotal | | | 591 | 99000            <- subtotal
    ...
            Notes:                                      <- trailing note block
            Figures are unaudited.

A reader that assumes "headers are on row 1" produces nonsense from this. The
example prints the raw grid the loader starts from, then the table it ends up
with, so you can see exactly what the clean-up removed.

Note that most of the work here is deterministic and costs no tokens: the
header row is found by heuristics, and subtotal and note rows are dropped
structurally. ``layout_inference`` controls only the extra LLM call, which
earns its keep on sheets whose junk rows are as wide as the real data.

Prerequisites:
    pip install "gaik[tabular-agent]"
    python make_fixtures.py
    AZURE_API_KEY / AZURE_ENDPOINT (or OPENAI_API_KEY) in the environment
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.tabular_agent import TabularAgent  # noqa: E402
from gaik.software_components.tabular_agent import (  # noqa: E402
    read_sheet_grid,
    render_grid,
)

MESSY_FILE = Path(__file__).parent / "input" / "messy_report.xlsx"

# The loader logs what it inferred and what it dropped -- worth seeing here.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


def show_raw_sheet() -> None:
    """Print the cell grid exactly as the loader first sees it."""
    print("=" * 70)
    print("What is actually in the file")
    print("=" * 70)
    grid = read_sheet_grid(MESSY_FILE, "Sales Report")
    # Only the first rows and the tail -- enough to see the title block, a
    # subtotal line, and the trailing notes.
    lines = render_grid(grid).splitlines()
    print("\n".join(lines[:12]))
    print("   ...")
    print("\n".join(lines[-4:]))


def show_loaded_table() -> None:
    """Print the table the agent ends up querying."""
    print("\n" + "=" * 70)
    print("What the agent ends up with")
    print("=" * 70)
    with TabularAgent(MESSY_FILE) as agent:
        table = agent.get_schema().tables[0]
        regions = next(c for c in table.columns if c.name == "region")
        print(f"rows loaded  : {table.row_count}  (titles, subtotals and notes removed)")
        print(f"region values: {regions.top_values or regions.samples}")
        print()
        print(agent.get_schema().to_prompt_text())

        result = agent.ask("What was the total revenue, and which region led?")
        print(f"\nQ: {result.question}")
        print(f"A: {result.answer}")
        if result.query_result.sql:
            print(f"   SQL: {' '.join(result.query_result.sql.split())}")


def main() -> None:
    """Show the messy sheet, then the clean table the agent queries."""
    if not MESSY_FILE.exists():
        print("Sample file missing. Run: python make_fixtures.py")
        return
    show_raw_sheet()
    show_loaded_table()


if __name__ == "__main__":
    main()
