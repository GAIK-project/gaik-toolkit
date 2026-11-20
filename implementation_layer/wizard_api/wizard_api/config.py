import math
import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Secrets the API needs but no child process may inherit
# ---------------------------------------------------------------------------
#
# The wizard agent (Claude Agent SDK, ``services/agent_service.py``) is spawned
# from this process and inherits its whole environment: the SDK merges
# ``ClaudeAgentOptions.env`` *over* ``os.environ`` instead of replacing it, so
# an allowlist handed to the SDK removes nothing. The agent has a Bash tool,
# which puts every variable one ``env`` away from a prompt injection — and with
# the service token in hand the agent could call this API as any user.
#
# So the API-internal secrets are read *once*, taken out of ``os.environ`` and
# kept only in this module. The agent, its Bash tool and the V1 scripts it runs
# never see them. Everything the agent legitimately needs (Foundry / Azure /
# OpenAI provider variables for ``generate_schema.py``) is left untouched.
#
# Known limit: a same-UID process can still read this process's *initial*
# environment through ``/proc/<pid>/environ``. Only running the agent in its
# own pod (or restricting its Bash tool) closes that. This is defence in depth,
# not isolation.

API_SECRET_ENV = ("WIZARD_API_TOKEN", "WIZARD_DATABASE_URL")

_consumed: dict[str, str] = {}


def _consume_secret(name: str) -> str | None:
    """Return ``name``'s value, removing it from ``os.environ`` on first read.

    Later reads return the cached value. If the variable is set again after
    that (tests, reconfiguration) the new value is consumed the same way.
    """
    if name in os.environ:
        _consumed[name] = os.environ.pop(name)
    return _consumed.get(name)


def consume_api_secrets() -> None:
    """Take every API-internal secret out of the environment. Idempotent.

    Runs at import so the guarantee does not depend on which getter happens
    to be called before the first agent is spawned.
    """
    for name in API_SECRET_ENV:
        _consume_secret(name)


def forget_consumed_secret(name: str) -> None:
    """Drop the cached value so the next read starts from the environment.

    Exists for the test suite, which toggles secrets per test via monkeypatch;
    production never calls it.
    """
    _consumed.pop(name, None)


consume_api_secrets()


def get_database_url() -> str:
    url = _consume_secret("WIZARD_DATABASE_URL")
    if url is not None:
        return url
    return "postgresql+psycopg://wizard:wizard@localhost:5432/wizard"


def get_service_token() -> str | None:
    """Shared secret the web app must present on every call (#132).

    Unset means service auth is OFF, so local dev, the docker stack and the
    test suite keep working untouched. `main.py` logs a loud warning in that
    case — a deployed environment is expected to set it. Read at call time,
    not import time, so tests can toggle it via monkeypatch. Each read consumes
    the variable from the environment (see above), so the wizard agent never
    inherits it.
    """
    token = (_consume_secret("WIZARD_API_TOKEN") or "").strip()
    return token or None


def service_auth_enabled() -> bool:
    return get_service_token() is not None


def user_header_required() -> bool:
    """When set, every call must name the user it acts for (X-Wizard-User-Id).

    Off by default: the sandbox Job's init container and the stack E2E helpers
    still call the API with the service token alone. Ownership is enforced
    whenever the header IS present regardless of this flag.
    """
    return os.getenv("WIZARD_REQUIRE_USER_HEADER", "").strip() == "1"


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


def max_chat_message_chars() -> int:
    """The longest chat message accepted, in characters (cost and memory bound)."""
    return _int_env("WIZARD_MAX_CHAT_MESSAGE_CHARS", 20_000)


def max_live_agents() -> int:
    """How many agent processes may run at once in this API process."""
    return _int_env("WIZARD_MAX_LIVE_AGENTS", 20)


def max_live_agents_per_user() -> int:
    """How many of those agent processes one user may hold at once.

    Without it one user opening sessions in several tabs could take every slot
    of ``WIZARD_MAX_LIVE_AGENTS``. Named like ``WIZARD_MAX_ACTIVE_RUNS_PER_USER``.
    """
    return _int_env("WIZARD_MAX_LIVE_AGENTS_PER_USER", 2)


def max_chat_turns_per_minute() -> int:
    """Chat messages one user may send per minute; 0 (the default) means no limit.

    Counted in this API process, so with several replicas each counts its own.
    """
    try:
        value = int(os.getenv("WIZARD_MAX_CHAT_TURNS_PER_MINUTE", "").strip() or 0)
    except ValueError:
        return 0
    return max(value, 0)


def agent_bridge_socket() -> str | None:
    """The agent container's socket, when the agent runs there (agent_bridge.py)."""
    return os.getenv("WIZARD_AGENT_BRIDGE_SOCKET", "").strip() or None


def agent_max_turns() -> int:
    """Model calls the agent may make for one query before it stops.

    A chat message is one query, plus up to two quiet "Please continue." nudges
    when the reply comes back empty, so one message stays under three times this.
    """
    return _int_env("WIZARD_AGENT_MAX_TURNS", 100)


def agent_max_budget_usd() -> float | None:
    """Estimated USD one agent may spend from its start or resume; None means no limit.

    The agent SDK's ``max_budget_usd``. Its CLI counts the spend of the whole
    agent process, across messages, from its own price table, so this is not a
    limit per message and not a bill (README, "Agent and chat limits"). Unset,
    0, a negative, an unreadable or an infinite value is off, the default.
    """
    try:
        value = float(os.getenv("WIZARD_AGENT_MAX_BUDGET_USD", "").strip() or 0)
    except ValueError:
        return None
    return value if 0 < value < math.inf else None


def _usd_cap_env(name: str, default: float) -> float | None:
    """A spend cap in estimated USD. Unset is ``default``; ``0`` turns the cap off.

    A negative, unreadable or infinite value is the default, so a typo does not
    lift the cap.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value == 0:
        return None
    return value if 0 < value < math.inf else default


def session_max_cost_usd() -> float | None:
    """Estimated USD one session may spend in all, across agent restarts; None is off.

    Counted from the agent's own cost estimate after each chat message and kept
    in the session (services/usage_caps.py). The default is about 5 euros.
    """
    return _usd_cap_env("WIZARD_SESSION_MAX_COST_USD", 5.4)


def user_max_cost_usd() -> float | None:
    """Estimated USD one user may spend across all their sessions; None is off.

    Deleting a session does not give its spend back. The default is about 10 euros.
    """
    return _usd_cap_env("WIZARD_USER_MAX_COST_USD", 10.8)


def deployment_max_cost_usd() -> float | None:
    """Estimated USD the whole deployment may spend in one calendar month (UTC); None is off.

    Below the model provider's own monthly cap, which stays the hard limit: this
    one is the API's estimate, not the bill.
    """
    return _usd_cap_env("WIZARD_DEPLOYMENT_MAX_COST_USD", 2000.0)


def max_sessions_per_user() -> int | None:
    """Sessions one user may have at a time; None (``0``) means no limit.

    A removed session gives its place back. A negative or unreadable value is
    the default, 3.
    """
    raw = os.getenv("WIZARD_MAX_SESSIONS_PER_USER", "").strip()
    if not raw:
        return 3
    try:
        value = int(raw)
    except ValueError:
        return 3
    if value == 0:
        return None
    return value if value > 0 else 3


def cost_warn_ratio() -> float:
    """The share of a session's or user's cap after which the chat says so once.

    Between 0 and 1, both left out; anything else is the default, 0.8.
    """
    try:
        value = float(os.getenv("WIZARD_COST_WARN_RATIO", "").strip() or 0.8)
    except ValueError:
        return 0.8
    return value if 0 < value < 1 else 0.8


def agent_fallback_model() -> str | None:
    """The model the agent switches to when its own fails or is unavailable; None is off."""
    return os.getenv("WIZARD_AGENT_FALLBACK_MODEL", "").strip() or None


def max_metered_calls_per_turn() -> int:
    """Metered tool calls the agent may make for one chat message.

    Metered are the calls that reach a model or the web other than the agent's
    own model calls, which ``WIZARD_AGENT_MAX_TURNS`` counts: a wizard script
    that calls a model, web search and fetch, and the tools of an MCP server
    other than the wizard's own (``agent_tool_guard``). A cap like
    ``WIZARD_AGENT_MAX_TURNS``: 0, a negative or an unreadable value is the default.
    """
    return _int_env("WIZARD_MAX_METERED_CALLS_PER_TURN", 10)


def max_metered_calls_per_user_per_hour() -> int:
    """Metered tool calls one user's agents may make in a sliding hour; 0 means no limit.

    Counted across all of the user's sessions, in this API process, like
    ``WIZARD_MAX_CHAT_TURNS_PER_MINUTE``. A negative or unreadable value is the
    default, so a typo does not lift the limit.
    """
    try:
        value = int(os.getenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "").strip() or 60)
    except ValueError:
        return 60
    return value if value >= 0 else 60


def turn_timeout_seconds() -> int:
    """How long one chat turn may take before it is ended.

    A turn runs as its own task, so nothing the user does ends one that hangs
    (a reload used to). Generating a package takes minutes, so the limit is
    generous: it is for a turn that will never finish, not a slow one.
    """
    return _int_env("WIZARD_TURN_TIMEOUT_SECONDS", 45 * 60)


def get_session_output_root() -> Path:
    return Path(os.getenv("WIZARD_SESSION_OUTPUT_ROOT", "/tmp/wizard-sessions"))


def build_session_output_dir(user_id: str, session_id: UUID) -> str:
    """Per-session artefact path (S1-5 convention stub)."""
    safe_user = user_id.replace("/", "_")
    return str(get_session_output_root() / safe_user / str(session_id))
