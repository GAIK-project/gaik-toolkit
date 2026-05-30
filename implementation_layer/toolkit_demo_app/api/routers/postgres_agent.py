"""PostgreSQL text-to-SQL agent router.

Exposes the gaik ``PostgresAgent`` against a fixed, server-side demo database.
The user only submits a natural-language question -- never a connection string
-- so there is no SSRF surface. The agent connects read-only and is restricted
to an isolated demo schema with a table allowlist.
"""

import asyncio
import decimal
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

DEMO_SCHEMA = "gaik_postgres_agent_demo"
DEMO_TABLES = ["customers", "orders"]

# The demo schema is created + populated once per process.
_seeded = False


def _get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def _llm_config() -> dict | None:
    """Return an Azure OpenAI config dict, or None when no API key is set."""
    from gaik.software_components.config import get_openai_config

    if os.getenv("AZURE_API_KEY"):
        return get_openai_config(use_azure=True)
    return None


def _seed_demo_schema(database_url: str) -> None:
    """Create and populate the isolated demo schema (idempotent, seed-once)."""
    global _seeded
    if _seeded:
        return

    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {DEMO_SCHEMA}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEMO_SCHEMA}.customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT,
                joined_on DATE
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEMO_SCHEMA}.orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES {DEMO_SCHEMA}.customers (id),
                product TEXT NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                ordered_on DATE
            )
            """
        )
        row = conn.execute(f"SELECT COUNT(*) FROM {DEMO_SCHEMA}.customers").fetchone()
        if not row or row[0] == 0:
            conn.execute(
                f"""
                INSERT INTO {DEMO_SCHEMA}.customers (id, name, city, joined_on) VALUES
                    (1, 'Aino Virtanen', 'Helsinki', '2024-01-15'),
                    (2, 'Bo Lindholm', 'Turku', '2024-03-02'),
                    (3, 'Carlos Mendez', 'Tampere', '2025-06-20'),
                    (4, 'Diana Korhonen', 'Helsinki', '2025-09-11')
                """
            )
            conn.execute(
                f"""
                INSERT INTO {DEMO_SCHEMA}.orders
                    (id, customer_id, product, amount, ordered_on) VALUES
                    (1, 1, 'Mechanical keyboard', 79.90, '2025-02-01'),
                    (2, 1, 'Monitor 27 inch', 249.00, '2025-02-15'),
                    (3, 2, 'Wireless mouse', 25.50, '2025-04-10'),
                    (4, 3, 'Laptop', 1299.00, '2025-07-01'),
                    (5, 3, 'Headphones', 149.00, '2025-07-03'),
                    (6, 4, 'Webcam HD', 89.00, '2025-10-05')
                """
            )

    _seeded = True
    logger.info("postgres_agent demo schema '%s' ready", DEMO_SCHEMA)


def _make_agent():
    """Build a fresh read-only PostgresAgent for the demo schema, or None."""
    db_url = _get_database_url()
    if not db_url:
        return None
    _seed_demo_schema(db_url)

    from gaik.software_components.postgres_agent import PostgresAgent

    return PostgresAgent(
        db_url,
        config=_llm_config(),
        schema_name=DEMO_SCHEMA,
        table_allowlist=DEMO_TABLES,
    )


def _jsonable(value):
    """Coerce a database value into a JSON-friendly primitive."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    return str(value)


# ---------- Models ----------


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    succeeded: bool
    sql: str | None = None
    reasoning: str | None = None
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    attempts: int = 0
    error: str | None = None


class SchemaColumn(BaseModel):
    name: str
    data_type: str
    is_primary_key: bool = False
    references: str | None = None


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn]


class SchemaResponse(BaseModel):
    schema_name: str
    schema_text: str
    tables: list[SchemaTable]


class StatusResponse(BaseModel):
    database_configured: bool
    llm_configured: bool
    demo_schema: str
    demo_tables: list[str]


# ---------- Endpoints ----------


@router.get("/status", response_model=StatusResponse)
async def postgres_agent_status():
    """Report whether the demo database and LLM are configured."""
    return StatusResponse(
        database_configured=_get_database_url() is not None,
        llm_configured=bool(os.getenv("AZURE_API_KEY")),
        demo_schema=DEMO_SCHEMA,
        demo_tables=DEMO_TABLES,
    )


@router.get("/schema", response_model=SchemaResponse)
async def get_demo_schema():
    """Return the introspected demo schema (tables, columns, sample rows)."""
    agent = _resolve_agent()
    try:
        return await asyncio.to_thread(_run_schema, agent)
    except Exception as e:
        logger.error("postgres_agent schema failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    """Answer a natural-language question against the demo database."""
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    agent = _resolve_agent()
    try:
        return await asyncio.to_thread(_run_ask, agent, question)
    except Exception as e:
        logger.error("postgres_agent ask failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------- Internal helpers ----------


def _resolve_agent():
    """Build the agent or raise a clean HTTPException."""
    try:
        agent = _make_agent()
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"postgres_agent component is not available in this build: {e}",
        ) from e
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail="Demo database not configured (DATABASE_URL is not set).",
        )
    return agent


def _run_schema(agent) -> SchemaResponse:
    try:
        schema = agent.get_schema(include_samples=True)
    finally:
        agent.close()
    return SchemaResponse(
        schema_name=schema.schema_name,
        schema_text=schema.to_prompt_text(),
        tables=[
            SchemaTable(
                name=t.name,
                columns=[
                    SchemaColumn(
                        name=c.name,
                        data_type=c.data_type,
                        is_primary_key=c.is_primary_key,
                        references=c.references,
                    )
                    for c in t.columns
                ],
            )
            for t in schema.tables
        ],
    )


def _run_ask(agent, question: str) -> AskResponse:
    try:
        result = agent.ask(question)
    finally:
        agent.close()
    qr = result.query_result
    return AskResponse(
        question=result.question,
        answer=result.answer,
        succeeded=qr.succeeded,
        sql=qr.sql,
        reasoning=qr.reasoning,
        rows=[{k: _jsonable(v) for k, v in row.items()} for row in qr.rows],
        row_count=qr.row_count,
        attempts=qr.attempts,
        error=qr.error,
    )
