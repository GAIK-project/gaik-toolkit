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
import threading
import time

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


# What the agent's role may do, read in one query. Outside the system schemas: role
# attributes; whether it can create in the database or in any schema; its memberships
# in other roles (SET ROLE, or rights inherited from them, such as the pg_* roles that
# read server files or run programs); the relations of any kind (tables, views,
# materialized views, foreign tables) it can write, also through a column grant; the
# relations outside the demo schema it can read, also through a column grant, and the
# sequences it can use; the SECURITY DEFINER functions it can call, which run with
# their owner's rights; and the built-in functions that read, list or copy server files,
# which PUBLIC cannot call unless someone grants them.
_NOT_SYSTEM = (
    "n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_%%'"
)
_SERVER_FILE_FUNCTIONS = (
    "pg_read_file", "pg_read_binary_file", "pg_stat_file", "pg_ls_dir", "pg_ls_logdir",
    "pg_ls_waldir", "pg_ls_tmpdir", "pg_ls_archive_statusdir", "pg_ls_logicalsnapdir",
    "pg_ls_logicalmapdir", "pg_ls_replslotdir", "lo_import", "lo_export",
)  # fmt: skip
_ROLE_FACTS_SQL = f"""
SELECT
    r.rolsuper,
    r.rolcreaterole,
    r.rolcreatedb,
    r.rolbypassrls,
    r.rolreplication,
    has_database_privilege(current_database(), 'CREATE'),
    EXISTS (SELECT 1 FROM pg_namespace n
             WHERE {_NOT_SYSTEM} AND has_schema_privilege(n.oid, 'CREATE')),
    (SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid),
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE {_NOT_SYSTEM} AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
         AND (has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
              OR has_any_column_privilege(c.oid, 'INSERT, UPDATE, REFERENCES')
              OR CASE WHEN current_setting('server_version_num')::int >= 170000
                      THEN has_table_privilege(c.oid, 'MAINTAIN') ELSE false END)),
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE {_NOT_SYSTEM}
         AND ((c.relkind IN ('r', 'p', 'v', 'm', 'f')
               AND NOT (n.nspname = %(schema)s AND c.relname = ANY(%(tables)s))
               AND has_any_column_privilege(c.oid, 'SELECT'))
              OR (c.relkind = 'S' AND has_sequence_privilege(c.oid, 'USAGE, SELECT, UPDATE')))),
    (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
       WHERE {_NOT_SYSTEM} AND p.prosecdef AND has_function_privilege(p.oid, 'EXECUTE')),
    (SELECT count(*) FROM pg_proc p
       WHERE p.pronamespace = 'pg_catalog'::regnamespace
         AND p.proname = ANY(%(server_file_functions)s)
         AND has_function_privilege(p.oid, 'EXECUTE')),
    current_user <> session_user,
    EXISTS (SELECT 1 FROM pg_largeobject_metadata m, aclexplode(m.lomacl) a
             WHERE a.grantee IN (0, r.oid) AND a.privilege_type = 'SELECT')
      OR current_setting('lo_compat_privileges')::bool,
    (SELECT count(*) FROM pg_extension
       WHERE extname IN ('dblink', 'postgres_fdw', 'file_fdw', 'adminpack')),
    EXISTS (SELECT 1 FROM pg_default_acl d, aclexplode(d.defaclacl) a
             WHERE a.grantee IN (0, r.oid))
FROM pg_roles r
WHERE r.rolname = session_user
"""


_ROLE_FACTS_PARAMS = {
    "schema": DEMO_SCHEMA,
    "tables": DEMO_TABLES,
    "server_file_functions": list(_SERVER_FILE_FUNCTIONS),
}


def _role_problems(facts: tuple | None) -> list[str]:
    """Why the agent's role is not read-only on the demo tables; empty when it is."""
    if facts is None:
        return ["the role was not found"]
    (
        superuser,
        createrole,
        createdb,
        bypassrls,
        replication,
        db_create,
        schema_create,
        memberships,
        writable,
        elsewhere,
        definer_functions,
        server_file_functions,
        switched,
        large_objects,
        reaching_extensions,
        default_grants,
    ) = facts
    problems = []
    if superuser:
        problems.append("it is a superuser")
    if createrole or createdb or bypassrls:
        problems.append("it can create roles or databases, or bypass row security")
    if replication:
        problems.append("it has the replication attribute")
    if db_create or schema_create:
        problems.append("it can create schemas or objects")
    if memberships:
        problems.append(f"it is a member of {memberships} other role(s)")
    if writable:
        problems.append(f"it can change or maintain {writable} table(s) or view(s)")
    if elsewhere:
        problems.append(
            f"it can read or use {elsewhere} relation(s) or sequence(s) besides the demo tables"
        )
    if definer_functions:
        problems.append(f"it can call {definer_functions} SECURITY DEFINER function(s)")
    if server_file_functions:
        problems.append(
            f"it can call {server_file_functions} function(s) that read or list server files"
        )
    if switched:
        problems.append("the connection switches to another role than the one it logs in as")
    if large_objects:
        problems.append("it can read large objects")
    if reaching_extensions:
        problems.append("an extension that reaches other hosts or files is installed")
    if default_grants:
        problems.append("default privileges grant future objects to it or to PUBLIC")
    return problems


_role_lock = threading.Lock()
_ROLE_RECHECK_SECONDS = 600
_role_checked_at = 0.0


def _check_agent_role(database_url: str) -> list[str]:
    """Check the agent's own role; the problems found.

    The result is kept for ten minutes, then checked again, so a grant made later on a
    shared database is seen without a restart.
    """
    global _role_checked, _role_checked_at
    with _role_lock:
        if _role_checked is None or time.monotonic() - _role_checked_at > _ROLE_RECHECK_SECONDS:
            import psycopg

            with psycopg.connect(database_url, connect_timeout=5) as conn:
                facts = conn.execute(_ROLE_FACTS_SQL, _ROLE_FACTS_PARAMS).fetchone()
            _role_checked = _role_problems(facts)
            _role_checked_at = time.monotonic()
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


_seed_lock = threading.Lock()


def _seed_demo_schema(database_url: str) -> None:
    """Create and populate the isolated demo schema (idempotent, seed-once).

    Requests build the agent in worker threads, so the first two can arrive together:
    the lock lets one seed while the other waits and then finds it done.
    """
    if _seeded:
        return
    with _seed_lock:
        _seed_demo_schema_once(database_url)


def _seed_demo_schema_once(database_url: str) -> None:
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


def _own_role_passes() -> bool:
    """True when the agent has its own connection and its role passed the last check.

    Only the kept result is read: /status is open to visitors, so it never opens a
    database connection of its own.
    """
    _, own = _agent_database_url()
    return bool(own) and _role_checked == []


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
    """The agent's SQL runs on its own role (POSTGRES_AGENT_DATABASE_URL), and that role
    passed the read-only check."""
    llm_configured: bool
    demo_schema: str
    demo_tables: list[str]


# ---------- Endpoints ----------


@router.get("/status", response_model=StatusResponse)
async def postgres_agent_status():
    """Report whether the demo database and LLM are configured."""
    return StatusResponse(
        database_configured=_agent_database_url()[0] is not None,
        own_read_only_role=_own_role_passes(),
        llm_configured=bool(os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")),
        demo_schema=DEMO_SCHEMA,
        demo_tables=DEMO_TABLES,
    )


@router.get("/schema", response_model=SchemaResponse)
async def get_demo_schema():
    """Return the introspected demo schema (tables, columns, sample rows)."""
    agent = await asyncio.to_thread(_resolve_agent)
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

    agent = await asyncio.to_thread(_resolve_agent)
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
