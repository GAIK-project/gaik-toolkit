"""Example: ask CSV and Excel files questions in natural language.

Demonstrates ``TabularAgent`` -- a read-only text-to-SQL query agent for files.
It loads spreadsheets into DuckDB, profiles every column, generates a validated
read-only SQL query, runs it, and answers in natural language. A lightweight
agentic loop retries on SQL errors.

Prerequisites:
    # Install dependencies
    pip install "gaik[tabular-agent]"

    # Generate the sample files used below
    python make_fixtures.py

    # Set environment variables (or use a .env file) -- Azure OpenAI shown:
    AZURE_API_KEY=your-key
    AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/

Workflow:
    files -> DuckDB tables -> column profiles -> SQL -> answer
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.tabular_agent import TabularAgent  # noqa: E402

INPUT_DIR = Path(__file__).parent / "input"


def ask_all(agent: TabularAgent, questions: list[str]) -> None:
    """Ask several questions, showing the SQL behind each answer."""
    for question in questions:
        result = agent.ask(question)
        print(f"\nQ: {question}")
        print(f"A: {result.answer}")
        if result.query_result.sql:
            sql = " ".join(result.query_result.sql.split())
            print(f"   SQL: {sql}")


def single_csv() -> None:
    """A tidy CSV export -- the simplest possible case."""
    print("=" * 70)
    print("1. Single CSV file")
    print("=" * 70)

    with TabularAgent(INPUT_DIR / "sales_clean.csv") as agent:
        print(f"Loaded tables: {agent.table_names}")
        print("\nWhat the model sees:")
        print(agent.get_schema().to_prompt_text())
        ask_all(
            agent,
            [
                "Which region had the highest total revenue?",
                "How many units of each product were sold in Q3?",
            ],
        )


def nordic_csv() -> None:
    """A semicolon-separated export with comma decimals and a UTF-8 BOM."""
    print("\n" + "=" * 70)
    print("2. Nordic CSV -- ';' separator, ',' decimals, answer in Finnish")
    print("=" * 70)

    with TabularAgent(INPUT_DIR / "sales_semicolon.csv", answer_language="fi") as agent:
        # revenue_eur arrives as text like "14400,00" and is converted to a
        # real number during load, so SUM() works.
        revenue = next(c for c in agent.get_schema().tables[0].columns if c.name == "revenue_eur")
        print(f"revenue_eur was typed as: {revenue.data_type}")
        ask_all(agent, ["Paljonko oli Widget-tuotteen kokonaisliikevaihto?"])


def joined_sheets() -> None:
    """One Excel workbook, two sheets, a question that needs both."""
    print("\n" + "=" * 70)
    print("3. Multi-sheet Excel -- each sheet becomes its own table")
    print("=" * 70)

    with TabularAgent(INPUT_DIR / "multi_sheet.xlsx") as agent:
        print(f"Loaded tables: {agent.table_names}")
        ask_all(agent, ["Which region has the highest revenue per employee?"])


def tool_style() -> None:
    """The low-level methods need no LLM credentials at all."""
    print("\n" + "=" * 70)
    print("4. Tool-style use -- schema and SQL without an LLM")
    print("=" * 70)

    with TabularAgent(INPUT_DIR / "sales_clean.csv", config={}) as agent:
        table = agent.get_schema().tables[0]
        print(f"{table.name}: {table.row_count} rows, {len(table.columns)} columns")
        rows = agent.run_sql(
            "SELECT region, sum(revenue_eur) AS total "
            "FROM sales_clean GROUP BY region ORDER BY total DESC"
        )
        for row in rows:
            print(f"  {row['region']:<6} {row['total']:>10,.0f}")


def main() -> None:
    """Run every example."""
    if not INPUT_DIR.exists():
        print("Sample files missing. Run: python make_fixtures.py")
        return
    single_csv()
    nordic_csv()
    joined_sheets()
    tool_style()


if __name__ == "__main__":
    main()
