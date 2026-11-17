"""PostgreSQL text-to-SQL agent router.

Exposes the gaik ``PostgresAgent`` against a fixed, server-side demo database.
The user only submits a natural-language question -- never a connection string
-- so there is no SSRF surface. The agent connects read-only and is restricted
to an isolated demo schema with a table allowlist.

The model writes the SQL, so the agent's connection is its own: set
``POSTGRES_AGENT_DATABASE_URL`` to a role that can only read the demo tables
(``api/scripts/postgres_agent_role.sql`` creates one). The agent checks that role
before it runs a question and refuses one that can write, create, or read a table
outside the demo schema. ``DATABASE_URL`` (the demo's own connection, which also
holds the video-search index) only seeds the demo schema. Without the agent's
variable the agent falls back to ``DATABASE_URL`` and says so in the log and in
``/status``.
"""

import asyncio
import decimal
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from utils.errors import error_detail
except ImportError:
    from api.utils.errors import error_detail

logger = logging.getLogger(__name__)


try:
    from utils.model_settings import provider_error_detail
except ImportError:
    from api.utils.model_settings import provider_error_detail

try:
    from utils.config import get_model_options
    from utils.model_settings import get_request_api_config
except ImportError:
    from api.utils.config import get_model_options
    from api.utils.model_settings import get_request_api_config

router = APIRouter()

DEMO_SCHEMA = "gaik_postgres_agent_demo"
DEMO_TABLES = ["customers", "orders"]
AGENT_DATABASE_ENV = "POSTGRES_AGENT_DATABASE_URL"

# The demo schema is created + populated once per process.
_seeded = False
# The agent role is checked once per process; the problems found, if any.
_role_checked: list[str] | None = None
_warned_fallback = False


def _agent_database_url() -> tuple[str | None, bool]:
    """The connection the agent's SQL runs on, and whether it is the agent's own."""
    own = os.getenv(AGENT_DATABASE_ENV)
    if own:
        return own, True
    global _warned_fallback
    if not _warned_fallback and os.getenv("DATABASE_URL"):
        _warned_fallback = True
        logger.warning(
            "postgres_agent: %s is not set, so model-written SQL runs on DATABASE_URL; "
            "create a read-only role with api/scripts/postgres_agent_role.sql",
            AGENT_DATABASE_ENV,
        )
    return os.getenv("DATABASE_URL"), False


# What the agent's role may do, read in one query: role attributes, whether it can
# create in the database or in any schema, the demo tables it can change, and the
# tables outside the demo schema and the system schemas that it can read.
_ROLE_FACTS_SQL = """
SELECT
    r.rolsuper,
    r.rolcreaterole,
    r.rolcreatedb,
    r.rolbypassrls,
    has_database_privilege(current_database(), 'CREATE'),
    EXISTS (SELECT 1 FROM pg_namespace n
             WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND n.nspname NOT LIKE 'pg\\_%%'
               AND has_schema_privilege(n.oid, 'CREATE')),
    (SELECT count(*) FROM pg_tables t
       WHERE t.schemaname = %(schema)s
         AND has_table_privilege(
               format('%%I.%%I', t.schemaname, t.tablename),
               'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')),
    (SELECT count(*) FROM pg_tables t
       WHERE t.schemaname NOT IN (%(schema)s, 'pg_catalog', 'information_schema')
         AND has_table_privilege(format('%%I.%%I', t.schemaname, t.tablename), 'SELECT'))
FROM pg_roles r
WHERE r.rolname = current_user
"""


def _role_problems(facts: tuple | None) -> list[str]:
    """Why the agent's role is not read-only on the demo schema; empty when it is."""
    if facts is None:
        return ["the role was not found"]
    (superuser, createrole, createdb, bypassrls, db_create, schema_create, writable, elsewhere) = (
        facts
    )
    problems = []
    if superuser:
        problems.append("it is a superuser")
    if createrole or createdb or bypassrls:
        problems.append("it can create roles or databases, or bypass row security")
    if db_create or schema_create:
        problems.append("it can create schemas or objects")
    if writable:
        problems.append(f"it can change {writable} demo table(s)")
    if elsewhere:
        problems.append(f"it can read {elsewhere} table(s) outside the demo schema")
    return problems


def _check_agent_role(database_url: str) -> list[str]:
    """Check the agent's own role once per process; the problems found."""
    global _role_checked
    if _role_checked is None:
        import psycopg

        with psycopg.connect(database_url) as conn:
            facts = conn.execute(_ROLE_FACTS_SQL, {"schema": DEMO_SCHEMA}).fetchone()
        _role_checked = _role_problems(facts)
        if _role_checked:
            logger.error(
                "postgres_agent: %s is not read-only: %s",
                AGENT_DATABASE_ENV,
                "; ".join(_role_checked),
            )
    return _role_checked


def _llm_config() -> dict | None:
    """Return an OpenAI/Azure config dict, or None when no API key is set.

    Auto-detects the provider: Azure OpenAI when ``AZURE_API_KEY`` is set,
    otherwise standard OpenAI when ``OPENAI_API_KEY`` is set. This lets the
    demo run on either an Azure or a plain-OpenAI deployment without code
    changes.
    """
    from gaik.software_components.config import get_openai_config

    request_config = get_request_api_config()
    if request_config is not None:
        return request_config
    if os.getenv("AZURE_API_KEY"):
        return get_openai_config(use_azure=True)
    if os.getenv("OPENAI_API_KEY"):
        return get_openai_config(use_azure=False)
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


class AgentRoleError(RuntimeError):
    """The agent's own database role can do more than read the demo tables."""


def _make_agent():
    """Build a fresh read-only PostgresAgent for the demo schema, or None."""
    admin_url = os.getenv("DATABASE_URL")
    agent_url, own = _agent_database_url()
    if not agent_url:
        return None
    if admin_url:
        _seed_demo_schema(admin_url)
    if own and _check_agent_role(agent_url):
        raise AgentRoleError(AGENT_DATABASE_ENV)

    from gaik.software_components.postgres_agent import PostgresAgent

    config = _llm_config()
    return PostgresAgent(
        agent_url,
        config=config,
        schema_name=DEMO_SCHEMA,
        table_allowlist=DEMO_TABLES,
        # The agent sends temperature 0.0 by default, which GPT-6 models reject.
        temperature=get_model_options(config, schema=True)["temperature"] if config else None,
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
    own_read_only_role: bool = False
    """The agent's SQL runs on its own role (POSTGRES_AGENT_DATABASE_URL), not DATABASE_URL."""
    llm_configured: bool
    demo_schema: str
    demo_tables: list[str]


# ---------- Endpoints ----------


@router.get("/status", response_model=StatusResponse)
async def postgres_agent_status():
    """Report whether the demo database and LLM are configured."""
    return StatusResponse(
        database_configured=_agent_database_url()[0] is not None,
        own_read_only_role=bool(os.getenv(AGENT_DATABASE_ENV)),
        llm_configured=bool(os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")),
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
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e


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
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e


# ---------- Internal helpers ----------


def _resolve_agent():
    """Build the agent or raise a clean HTTPException."""
    try:
        agent = _make_agent()
    except AgentRoleError as e:
        # The reasons are in the log; the page only learns that the demo is off.
        raise HTTPException(
            status_code=503,
            detail="The demo database is not set up for the agent. An administrator "
            "needs to give it a read-only role.",
        ) from e
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=error_detail(e, "Loading the postgres_agent component"),
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
