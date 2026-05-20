"""Example: ask a PostgreSQL database questions in natural language.

Demonstrates ``PostgresAgent`` -- a read-only text-to-SQL query agent. It
introspects the schema, generates a validated read-only SQL query, runs it, and
answers in natural language. A lightweight agentic loop retries on SQL errors.

Prerequisites:
    # Start a local PostgreSQL
    docker run -d --name gaik-pg -p 5432:5432 \
        -e POSTGRES_PASSWORD=postgres postgres:17

    # Install dependencies
    pip install "gaik[postgres-agent]"

    # Set environment variables (or use a .env file) -- Azure OpenAI shown:
    AZURE_API_KEY=your-key
    AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
    # Optional: override the demo database
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.postgres_agent import PostgresAgent  # noqa: E402
from seed_demo_db import DEMO_SCHEMA, seed_demo_db  # noqa: E402

# Connection string (override with the DATABASE_URL environment variable)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)


def main() -> None:
    # 1. Seed an isolated demo schema (safe to re-run; localhost only)
    seed_demo_db(DATABASE_URL)
    print()

    # 2. Connect the agent (read-only) and restrict it to the demo tables
    with PostgresAgent(
        DATABASE_URL,
        schema_name=DEMO_SCHEMA,
        table_allowlist=["customers", "orders"],
    ) as agent:
        # 3. Inspect the schema the agent will reason over
        print("--- Schema ---")
        print(agent.get_schema().to_prompt_text())
        print()

        # 4. generate_sql() -- get SQL without running it (dry run / review)
        question = "Which customers are from Helsinki?"
        generated = agent.generate_sql(question)
        print(f'--- generate_sql: "{question}" ---')
        print(f"  SQL:       {generated.sql}")
        print(f"  Reasoning: {generated.reasoning}")
        print()

        # 5. query() -- the agentic loop: generate, validate, run, retry on error
        question = "How many orders did each customer place, and the total amount?"
        result = agent.query(question)
        print(f'--- query: "{question}" ---')
        print(f"  SQL:       {result.sql}")
        print(f"  Attempts:  {result.attempts}   Succeeded: {result.succeeded}")
        for row in result.rows:
            print(f"  {row}")
        print()

        # 6. ask() -- the one-liner: a natural-language answer
        question = "Who is the highest-spending customer and how much did they spend?"
        answer = agent.ask(question)
        print(f'--- ask: "{question}" ---')
        print(f"  {answer.answer}")
        print()


if __name__ == "__main__":
    main()
