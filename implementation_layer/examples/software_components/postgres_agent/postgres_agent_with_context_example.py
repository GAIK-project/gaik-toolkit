"""PostgresAgent with extra_instructions and answer_language.

Same setup as ``postgres_agent_example.py``, but demonstrates injecting a
domain glossary + example questions into the LLM prompt (``extra_instructions``)
and switching the answer language (``answer_language``).

This is the recommended pattern for adapting the generic PostgresAgent to a
specific dataset: keep the agent itself schema-agnostic, and put dataset-aware
context (glossary, naming conventions, canonical query patterns) in the
``extra_instructions`` string the wrapper assembles.

Prerequisites:
- Local PostgreSQL running with the demo schema from ``postgres_agent_example.py``.
- ``OPENAI_API_KEY`` set (or Azure equivalents).

Run:
    python postgres_agent_with_context_example.py
"""

from __future__ import annotations

import os

from gaik.software_components.postgres_agent import PostgresAgent

# Example: a tiny e-commerce dataset (customers, orders). The agent already
# introspects the schema — what we add here is *business* context that is not
# in the table/column names.
EXTRA_INSTRUCTIONS = """
Domain notes:
- A "loyal customer" is one whose total order amount is at least 500.
- A "recent order" is one placed in the last 30 days.
- Amounts are in EUR; assume the user means EUR unless they say otherwise.

Useful joins:
- orders.customer_id -> customers.id

Examples:

Q: Who are our loyal customers?
SQL: SELECT c.id, c.name, SUM(o.amount) AS total_eur
     FROM customers c JOIN orders o ON o.customer_id = c.id
     GROUP BY c.id, c.name
     HAVING SUM(o.amount) >= 500
     ORDER BY total_eur DESC;

Q: Which customers placed a recent order?
SQL: SELECT DISTINCT c.id, c.name
     FROM customers c JOIN orders o ON o.customer_id = c.id
     WHERE o.ordered_on >= current_date - 30
     ORDER BY c.id;
""".strip()


def main() -> None:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )

    # Build the agent with two new arguments:
    #   extra_instructions -> appended after the schema in the SQL prompt
    #   answer_language    -> answer is synthesized in the given language
    with PostgresAgent(
        dsn,
        schema_name="gaik_postgres_agent_demo",
        table_allowlist=["customers", "orders"],
        extra_instructions=EXTRA_INSTRUCTIONS,
        answer_language="en",  # try "fi" or "sv" to switch
    ) as agent:
        question = "Who are our loyal customers?"
        result = agent.ask(question)

        print(f"Q: {question}\n")
        print(f"SQL:\n{result.query_result.sql}\n")
        print(f"Rows: {result.query_result.row_count}\n")
        print(f"Answer:\n{result.answer}")


if __name__ == "__main__":
    main()
