"""Operational metrics for the WP5 alerting: capacity, refusals, sessions, disk.

Sent over OTLP/HTTP to the same collector as the spans (``telemetry``), from
where they reach Prometheus. Nothing is sent without an OTLP endpoint: the
instruments are then no-ops, as the spans are.

What the metrics carry: counts, sizes, ages and fixed codes. Never what a user
or the agent wrote, never an e-mail address. The one per-user label is the
owner id (``o_…``, a keyed pseudonym; see ``wizard_api.owner_id``) on session
creation, so a burst from one account can be told apart.

Gauges are read when the exporter collects (once a minute by default,
``OTEL_METRIC_EXPORT_INTERVAL``). The ones that need the database or a walk of
the sessions volume are cached for ``WIZARD_OPS_CHECK_SECONDS`` (600 unless set).

The ``wizard.*`` names are a draft until the WP5 event schema v1.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

logger = logging.getLogger(__name__)

meter = metrics.get_meter("wizard_api")

_provider: Any = None
_PROCESS_START = time.time()

#: The Secret sandbox runs read their model key from when nothing else is set.
SHARED_RUNNER_SECRET = "gaik-demo-api-keys"

# --------------------------------------------------------------------- counters

refusals = meter.create_counter(
    "wizard.refusals",
    description="Requests the API refused or failed, by error code and HTTP status",
)
ownership_denied = meter.create_counter(
    "wizard.ownership.denied",
    description="Requests for an existing session that belongs to another user",
)
sessions_created = meter.create_counter(
    "wizard.sessions.created", description="Sessions created, by owner id"
)
session_deletes = meter.create_counter(
    "wizard.session.deletes", description="Session deletions, by reason and outcome"
)
turns = meter.create_counter("wizard.turns", description="Chat turns that ended, by outcome")
agent_errors = meter.create_counter(
    "wizard.agent.errors", description="Chat turns that failed in the agent, by kind of cause"
)
sandbox_runs = meter.create_counter(
    "wizard.sandbox.runs", description="Sandbox runs that ended, by kind and phase"
)
gates = meter.create_counter(
    "wizard.gates", description="Gate changes that went through, by gate and new status"
)
components = meter.create_counter(
    "wizard.components.selected",
    description="GAIK components in a solution when its Gate 2 is approved",
)
uploads_scanned = meter.create_counter(
    "wizard.uploads.scanned",
    description="Uploaded files by malware check result: clean, refused, unavailable",
)
budget_stops = meter.create_counter(
    "wizard.agent.budget_stops",
    description="Chat turns the agent ended at its budget, by limit: agent "
    "(WIZARD_AGENT_MAX_BUDGET_USD) or usage_cap (what the usage caps left)",
)
usage_cost = meter.create_counter(
    "wizard.usage.cost_usd",
    description="Estimated USD the agent spent, added after each chat turn (usage caps)",
)
usage_unreported = meter.create_counter(
    "wizard.usage.unreported_queries",
    description="Agent queries that ended with no result, charged an estimate (usage caps)",
)
usage_warnings = meter.create_counter(
    "wizard.usage.warnings",
    description="Times a session, a user or the deployment passed the warning share of its cap",
)
tool_calls = meter.create_counter(
    "wizard.agent.tool_calls",
    description="Agent tool calls the tool guard decided, by kind, decision and reason code",
)
turn_duration = meter.create_histogram(
    "wizard.turn.duration", unit="s", description="Length of a chat turn, start to end"
)
turn_first_frame = meter.create_histogram(
    "wizard.turn.first_frame",
    unit="s",
    description="Time from the start of a turn to its first frame",
)

_COMPONENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def record_gate_changes(session: Any, changes: dict[str, tuple[str, str]]) -> None:
    """Count gate changes; on a Gate 2 approval, the components of the active solution.

    Component names come from the blueprint, which the agent writes, so only a
    plain identifier is kept as a label and anything else is ``other``.
    """
    for gate, (_old, new) in changes.items():
        gates.add(
            1,
            {
                "gate": gate if gate in ("gate_1", "gate_2", "gate_3", "gate_4") else "other",
                "to": new if _CODE.match(new or "") else "other",
            },
        )
    if changes.get("gate_2", ("", ""))[1] != "approved":
        return
    content = next(
        (
            v.content
            for v in getattr(session, "blueprint_versions", []) or []
            if v.version == session.active_version
        ),
        None,
    )
    seen: set[str] = set()
    for step in (content or {}).get("steps", [])[:50]:
        name = step.get("component") if isinstance(step, dict) else None
        if isinstance(name, str) and name:
            seen.add(name if _COMPONENT.match(name) else "other")
    for name in seen:
        components.add(1, {"component": name})


_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def refusal(code: str, status: int | str | None = None) -> None:
    """Count a refusal by its code; a code that is not one of ours is ``other``.

    ``status`` is accepted for the callers' sake and not kept: the code names the
    refusal, and one label set per code keeps the series primed at zero.
    """
    refusals.add(1, {"code": code if _CODE.match(code or "") else "other"})


# Label sets the alerts read, created at zero when export starts. A counter
# series that first appears at 1 shows no increase to Prometheus, so without
# this the first failed deletion or the first capacity refusal would not alert.
_PRIMED = {
    "refusals": [
        {"code": c}
        for c in (
            "agent_capacity",
            "agent_busy",
            "chat_rate_limited",
            "sandbox_busy",
            "busy",
            "input_too_large",
            "session_delete_failed",
            "not_found",
            "internal_error",
            "unavailable",
            "input_unsafe",
            "scanner_unavailable",
            "usage_cap",
            "session_limit",
        )
    ],
    "uploads_scanned": [{"result": r} for r in ("clean", "refused", "unavailable")],
    "session_deletes": [
        {"reason": r, "outcome": o}
        for r in ("owner", "data-subject-request", "owner-left", "retention", "other")
        for o in ("deleted", "failed")
    ],
    "turns": [{"outcome": o} for o in ("completed", "failed", "aborted")],
    "agent_errors": [
        {"kind": k} for k in ("rate_limited", "overloaded", "server_error", "timeout", "other")
    ],
    "sandbox_runs": [
        {"kind": k, "phase": p}
        for k in ("run", "check", "case")
        for p in ("succeeded", "failed", "timeout")
    ],
    "gates": [
        {"gate": g, "to": t}
        for g in ("gate_1", "gate_2", "gate_3", "gate_4")
        for t in ("approved", "rejected", "pending")
    ],
    "ownership_denied": [{}],
    "budget_stops": [{"limit": limit} for limit in ("agent", "usage_cap")],
    "usage_cost": [{}],
    "usage_unreported": [{}],
    "usage_warnings": [{"scope": s} for s in ("session", "user", "deployment")],
    # Metered calls refused at a limit (agent_tool_guard.METERED_KINDS).
    "tool_calls": [
        {"kind": k, "decision": "denied", "reason": r}
        for k in ("model_script", "web", "mcp")
        for r in ("turn_limit", "user_limit")
    ],
}


def prime() -> None:
    """Create the alerting label sets at zero."""
    for name, label_sets in _PRIMED.items():
        counter = globals()[name]
        for attrs in label_sets:
            counter.add(0, attrs)


def agent_error_kind(cause: object) -> str:
    """Sort an agent failure by what the provider said, without keeping its words."""
    text = str(cause).lower()
    if "429" in text or "rate limit" in text or "rate_limit" in text:
        return "rate_limited"
    if "529" in text or "overloaded" in text:
        return "overloaded"
    if re.search(r"\b5\d\d\b", text) or "server error" in text or "internal error" in text:
        return "server_error"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "other"


# ------------------------------------------------------------------------ gauges


def _cgroup_memory() -> tuple[int | None, int | None]:
    """Memory used and the limit of this container (cgroup v2, then v1)."""
    for current, limit in (
        ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
        (
            "/sys/fs/cgroup/memory/memory.usage_in_bytes",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        ),
    ):
        try:
            used = int(Path(current).read_text().strip())
        except (OSError, ValueError):
            continue
        try:
            raw = Path(limit).read_text().strip()
            cap = None if raw == "max" else int(raw)
        except (OSError, ValueError):
            cap = None
        # v1 reports "no limit" as a huge number.
        if cap is not None and cap >= 1 << 60:
            cap = None
        return used, cap
    return None, None


def _volume() -> tuple[int, int] | None:
    from wizard_api import config

    try:
        st = os.statvfs(config.get_session_output_root())
    except OSError:
        return None
    return (st.f_blocks - st.f_bfree) * st.f_frsize, st.f_blocks * st.f_frsize


def check_seconds() -> int:
    try:
        return max(30, int(os.getenv("WIZARD_OPS_CHECK_SECONDS", "600")))
    except ValueError:
        return 600


class _Cached:
    """A value computed at most once per ``check_seconds()``; the last good one stays."""

    def __init__(
        self, compute: Callable[[], dict[str, float]], seconds: Callable[[], int] = check_seconds
    ) -> None:
        self._compute = compute
        self._seconds = seconds
        self._value: dict[str, float] = {}
        self._at = 0.0
        self._lock = threading.Lock()

    def get(self) -> dict[str, float]:
        with self._lock:
            if time.monotonic() - self._at >= self._seconds() or not self._at:
                try:
                    self._value = self._compute()
                except Exception:  # noqa: BLE001 - a failed check keeps the last values
                    logger.warning("ops check failed", exc_info=True)
                self._at = time.monotonic()
            return self._value


def session_stats(db: Any, now: float | None = None) -> dict[str, float]:
    """Counts from the session table and the sessions volume.

    ``overdue``: unprotected sessions unchanged for longer than the retention
    period, which the removal should already have taken. ``active``: changed in
    the last 15 minutes. ``rows_without_folder`` and ``folders_without_row``:
    a removal that stopped half way, or a folder left behind.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from wizard_api import config
    from wizard_api.models import WizardSession
    from wizard_api.session_admin import due_for_removal, retention_days

    moment = datetime.fromtimestamp(now, UTC) if now else datetime.now(UTC)
    total = db.scalar(select(func.count()).select_from(WizardSession)) or 0
    active = (
        db.scalar(
            select(func.count())
            .select_from(WizardSession)
            .where(WizardSession.updated_at >= moment - timedelta(minutes=15))
        )
        or 0
    )
    overdue = len(due_for_removal(db, retention_days(), now=moment))
    rows = {
        str(s.id): s.output_dir
        for s in db.execute(select(WizardSession.id, WizardSession.output_dir))
    }
    root = config.get_session_output_root()
    folders: set[str] = set()
    try:
        for owner in root.iterdir():
            if owner.is_dir() and not owner.is_symlink() and not owner.name.startswith("."):
                folders.update(p.name for p in owner.iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        pass
    without_folder = sum(1 for path in rows.values() if not Path(path).is_dir())
    without_row = len(folders - set(rows)) if folders else 0
    size = None
    try:
        size = db.scalar(select(func.pg_database_size(func.current_database())))
    except Exception:  # noqa: BLE001 - not Postgres (tests) or no right to ask
        db.rollback()
    stats = {
        "total": float(total),
        "active": float(active),
        "overdue": float(overdue),
        "rows_without_folder": float(without_folder),
        "folders_without_row": float(without_row),
    }
    if size is not None:
        stats["db_bytes"] = float(size)
    return stats


def _session_stats() -> dict[str, float]:
    from wizard_api.db import SessionLocal

    with SessionLocal() as db:
        return session_stats(db)


_sessions = _Cached(_session_stats)


def _sandbox_active() -> dict[str, float]:
    from wizard_api.services import sandbox_runner

    if not sandbox_runner.kubernetes_available() or not sandbox_runner.runner_image():
        return {}
    return {"active": float(sandbox_runner.SandboxRunner().active_jobs())}


_sandbox = _Cached(_sandbox_active)


def _observe(values: Iterable[tuple[float | None, dict[str, str]]]) -> list[Observation]:
    return [Observation(v, attrs) for v, attrs in values if v is not None]


def _gauge(name: str, description: str, read: Callable[[], Iterable[tuple[float | None, dict]]]):
    def callback(_options: CallbackOptions) -> list[Observation]:
        try:
            return _observe(read())
        except Exception:  # noqa: BLE001 - a broken gauge must not stop the others
            logger.warning("gauge %s failed", name, exc_info=True)
            return []

    meter.create_observable_gauge(name, callbacks=[callback], description=description)


def _agents() -> Iterable[tuple[float | None, dict]]:
    from wizard_api.services import agent_service

    live = len(agent_service.AGENT_SESSIONS) + len(agent_service._STARTING)  # noqa: SLF001
    yield float(live), {}


def _agent_limit() -> Iterable[tuple[float | None, dict]]:
    from wizard_api import config

    yield float(config.max_live_agents()), {}


def _turns_running() -> Iterable[tuple[float | None, dict]]:
    from wizard_api.services import agent_service

    running = [t for t in agent_service.TURNS.values() if not t.finished]
    yield float(len(running)), {}


def _oldest_turn() -> Iterable[tuple[float | None, dict]]:
    from wizard_api.services import agent_service

    now = time.time()
    ages = [now - t.started_at for t in agent_service.TURNS.values() if not t.finished]
    yield (max(ages) if ages else 0.0), {}


def _runs_active() -> Iterable[tuple[float | None, dict]]:
    yield _sandbox.get().get("active"), {}


def _runs_limit() -> Iterable[tuple[float | None, dict]]:
    from wizard_api.services import sandbox_runner

    yield float(sandbox_runner.max_active_runs()), {}


def _volume_used() -> Iterable[tuple[float | None, dict]]:
    v = _volume()
    yield (float(v[0]) if v else None), {}


def _volume_capacity() -> Iterable[tuple[float | None, dict]]:
    v = _volume()
    yield (float(v[1]) if v else None), {}


def _memory_used() -> Iterable[tuple[float | None, dict]]:
    used, _ = _cgroup_memory()
    yield (float(used) if used is not None else None), {}


def _memory_limit() -> Iterable[tuple[float | None, dict]]:
    _, cap = _cgroup_memory()
    yield (float(cap) if cap is not None else None), {}


def _session_counts() -> Iterable[tuple[float | None, dict]]:
    stats = _sessions.get()
    for state in ("total", "active", "overdue"):
        if state in stats:
            yield stats[state], {"state": state}


def _session_mismatch() -> Iterable[tuple[float | None, dict]]:
    stats = _sessions.get()
    for kind in ("rows_without_folder", "folders_without_row"):
        if kind in stats:
            yield stats[kind], {"kind": kind}


def _db_size() -> Iterable[tuple[float | None, dict]]:
    yield _sessions.get().get("db_bytes"), {}


def _usage_stats() -> dict[str, float]:
    from wizard_api.db import SessionLocal
    from wizard_api.services import usage_caps

    with SessionLocal() as db:
        return usage_caps.usage_stats(db)


_usage = _Cached(_usage_stats)


def _usage_caps() -> Iterable[tuple[float | None, dict]]:
    from wizard_api import config

    yield config.session_max_cost_usd(), {"scope": "session"}
    yield config.user_max_cost_usd(), {"scope": "user"}
    yield config.deployment_max_cost_usd(), {"scope": "deployment"}


def _deployment_spent() -> Iterable[tuple[float | None, dict]]:
    yield _usage.get().get("deployment_spent"), {}


def _users_by_cap() -> Iterable[tuple[float | None, dict]]:
    stats = _usage.get()
    for state in ("near", "reached"):
        yield stats.get(f"users_{state}"), {"state": state}


def _shared_runner_key() -> Iterable[tuple[float | None, dict]]:
    secret = os.getenv("WIZARD_POC_RUNNER_SECRET", "").strip() or SHARED_RUNNER_SECRET
    yield (1.0 if secret == SHARED_RUNNER_SECRET else 0.0), {}


def _scanner_state() -> dict[str, float]:
    from wizard_api.services import malware_scan

    state = malware_scan.probe()
    if state is None:
        return {}
    values = {"up": 1.0 if state.up else 0.0}
    if state.signatures_time is not None:
        values["signatures_time"] = state.signatures_time
    return values


# Asked once a minute: a scanner that stops answering refuses every upload.
_scanner = _Cached(_scanner_state, seconds=lambda: 60)


def _malware_scan() -> Iterable[tuple[float | None, dict]]:
    from wizard_api.services import malware_scan

    yield (1.0 if malware_scan.enabled() else 0.0), {}


def _scanner_up() -> Iterable[tuple[float | None, dict]]:
    yield _scanner.get().get("up"), {}


def _signatures_age() -> Iterable[tuple[float | None, dict]]:
    published = _scanner.get().get("signatures_time")
    yield (None if published is None else max(0.0, time.time() - published)), {}


def _up() -> Iterable[tuple[float | None, dict]]:
    yield 1.0, {}


def _start_time() -> Iterable[tuple[float | None, dict]]:
    yield _PROCESS_START, {}


_GAUGES = [
    ("wizard.up", "1 while the API runs and exports", _up),
    ("wizard.process.start_time", "Unix time the API process started", _start_time),
    ("wizard.process.memory.used", "Memory the api container uses, bytes", _memory_used),
    ("wizard.process.memory.limit", "Memory limit of the api container, bytes", _memory_limit),
    ("wizard.agents.live", "Live and starting agents", _agents),
    ("wizard.agents.limit", "WIZARD_MAX_LIVE_AGENTS", _agent_limit),
    ("wizard.turns.running", "Chat turns in progress", _turns_running),
    (
        "wizard.turns.oldest_running",
        "Age of the oldest chat turn in progress, seconds",
        _oldest_turn,
    ),
    ("wizard.sandbox.runs.active", "Unfinished sandbox Jobs of this stack", _runs_active),
    ("wizard.sandbox.runs.limit", "WIZARD_MAX_ACTIVE_RUNS", _runs_limit),
    ("wizard.sessions.volume.used", "Bytes used on the sessions volume", _volume_used),
    ("wizard.sessions.volume.capacity", "Size of the sessions volume, bytes", _volume_capacity),
    ("wizard.sessions", "Sessions by state: total, active, overdue", _session_counts),
    ("wizard.sessions.mismatch", "Session rows and folders without each other", _session_mismatch),
    ("wizard.db.size", "Size of the wizard database, bytes", _db_size),
    (
        "wizard.usage.cap_usd",
        "The usage caps in USD, by scope; a cap that is off is absent",
        _usage_caps,
    ),
    (
        "wizard.usage.deployment_spent_usd",
        "Estimated USD the deployment spent this month",
        _deployment_spent,
    ),
    (
        "wizard.usage.users",
        "Users past the warning share (near) or at their cap (reached)",
        _users_by_cap,
    ),
    (
        "wizard.config.shared_runner_key",
        "1 while sandbox runs use the shared model key Secret",
        _shared_runner_key,
    ),
    ("wizard.config.malware_scan", "1 while uploads must pass the malware check", _malware_scan),
    ("wizard.malware_scanner.up", "1 while the malware scanner answers", _scanner_up),
    (
        "wizard.malware_scanner.signatures_age",
        "Age of the scanner's loaded signatures, seconds",
        _signatures_age,
    ),
]

for _name, _description, _read in _GAUGES:
    _gauge(_name, _description, _read)


# ------------------------------------------------------------------- export


def setup(resource: Any) -> None:
    """Export the metrics to the collector; ``telemetry.setup`` calls it. Idempotent."""
    global _provider
    if _provider is not None:
        return
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    timeout_set = os.getenv("OTEL_EXPORTER_OTLP_METRICS_TIMEOUT") or os.getenv(
        "OTEL_EXPORTER_OTLP_TIMEOUT"
    )
    exporter = OTLPMetricExporter() if timeout_set else OTLPMetricExporter(timeout=2)
    provider = MeterProvider(
        resource=resource, metric_readers=[PeriodicExportingMetricReader(exporter)]
    )
    metrics.set_meter_provider(provider)
    _provider = provider
    prime()


def shutdown() -> None:
    if _provider is not None:
        _provider.shutdown()
