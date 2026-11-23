"""The metrics and request spans the WP5 alerts read (wizard_api.ops_metrics).

Read through in-memory readers: names, numbers and fixed codes only, and no
e-mail address in any label.
"""

import json
import uuid

import pytest
from helpers import requires_postgres
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from wizard_api import ops_metrics, owner_id
from wizard_api.ownership import USER_HEADER

_READER = InMemoryMetricReader()
_SPANS = InMemorySpanExporter()
OWNER = owner_id.owner_id("alice@example.test", "k")
OTHER = owner_id.owner_id("bob@example.test", "k")


@pytest.fixture(scope="module", autouse=True)
def _providers():
    if not isinstance(metrics.get_meter_provider(), MeterProvider):
        metrics.set_meter_provider(MeterProvider(metric_readers=[_READER]))
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(_SPANS))
    yield


def _points(name: str) -> list[tuple[dict, float]]:
    data = _READER.get_metrics_data()
    out = []
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == name:
                    out += [(dict(p.attributes), p.value) for p in m.data.data_points]
    return out


def _value(name: str, **attrs) -> float:
    return sum(v for a, v in _points(name) if all(a.get(k) == w for k, w in attrs.items()))


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("WIZARD_AGENT_STATE_DIR", raising=False)
    return tmp_path


def _create(client, user: str) -> str:
    res = client.post(
        "/sessions", json={"user_id": user, "title": "t"}, headers={USER_HEADER: user}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_an_agent_failure_is_sorted_by_cause_without_its_words() -> None:
    kind = ops_metrics.agent_error_kind
    assert kind(RuntimeError("Error code: 429 - rate limit reached")) == "rate_limited"
    assert kind("overloaded_error 529") == "overloaded"
    assert kind(RuntimeError("upstream returned 503")) == "server_error"
    assert kind(TimeoutError("request timed out")) == "timeout"
    assert kind(ValueError("something else")) == "other"


def test_a_refusal_code_outside_ours_is_counted_as_other() -> None:
    before = _value("wizard.refusals", code="other")
    ops_metrics.refusal("Not A Code; DROP", 400)
    assert _value("wizard.refusals", code="other") == before + 1


def test_the_gauges_report_capacity_disk_memory_and_the_shared_key(root, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "55")
    monkeypatch.delenv("WIZARD_POC_RUNNER_SECRET", raising=False)
    assert _value("wizard.agents.limit") == 55
    assert _value("wizard.up") == 1
    assert _value("wizard.sessions.volume.capacity") > 0
    assert 0 < _value("wizard.sessions.volume.used") <= _value("wizard.sessions.volume.capacity")
    assert _value("wizard.config.shared_runner_key") == 1
    monkeypatch.setenv("WIZARD_POC_RUNNER_SECRET", "wizard-v2-poc-run-keys")
    assert _value("wizard.config.shared_runner_key") == 0
    assert _value("wizard.turns.oldest_running") >= 0


@requires_postgres
def test_refusals_ownership_creation_and_deletion_are_counted(client, db_session, root) -> None:
    created = _value("wizard.sessions.created", owner=OWNER)
    session_id = _create(client, OWNER)
    assert _value("wizard.sessions.created", owner=OWNER) == created + 1

    denied = _value("wizard.ownership.denied")
    not_found = _value("wizard.refusals", code="not_found")
    assert client.get(f"/sessions/{session_id}", headers={USER_HEADER: OTHER}).status_code == 404
    assert _value("wizard.ownership.denied") == denied + 1
    assert _value("wizard.refusals", code="not_found") == not_found + 1
    missing = str(uuid.uuid4())
    assert client.get(f"/sessions/{missing}", headers={USER_HEADER: OTHER}).status_code == 404
    assert _value("wizard.ownership.denied") == denied + 1  # a missing session is not a denial

    deleted = _value("wizard.session.deletes", reason="retention", outcome="deleted")
    res = client.delete(f"/sessions/{session_id}?reason=retention", headers={USER_HEADER: OWNER})
    assert res.status_code == 204
    assert _value("wizard.session.deletes", reason="retention", outcome="deleted") == deleted + 1

    for name in ("wizard.sessions.created", "wizard.refusals", "wizard.session.deletes"):
        assert "@" not in json.dumps([a for a, _ in _points(name)])


@requires_postgres
def test_session_stats_find_overdue_sessions_and_rows_and_folders_apart(
    client, db_session, root, monkeypatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from wizard_api.models import WizardSession

    old = _create(client, OWNER)
    _create(client, OWNER)
    row = db_session.get(WizardSession, uuid.UUID(old))
    row.updated_at = datetime.now(UTC) - timedelta(days=120)
    db_session.commit()
    (root / OWNER / str(uuid.uuid4())).mkdir(parents=True)  # a folder whose row is gone
    gone = _create(client, OWNER)
    import shutil

    shutil.rmtree(db_session.get(WizardSession, uuid.UUID(gone)).output_dir)

    stats = ops_metrics.session_stats(db_session)
    assert stats["total"] == 3
    assert stats["overdue"] == 1
    assert stats["rows_without_folder"] == 1
    assert stats["folders_without_row"] == 1
    assert stats["db_bytes"] > 0


@requires_postgres
def test_every_request_gets_a_server_span_named_by_its_route(client, db_session, root) -> None:
    """FastAPI makes these spans itself; the error-ratio and latency alerts read them."""
    _SPANS.clear()
    session_id = _create(client, OWNER)
    client.get(f"/sessions/{session_id}", headers={USER_HEADER: OWNER})
    server = [s for s in _SPANS.get_finished_spans() if s.kind == trace.SpanKind.SERVER]
    names = {s.name for s in server}
    assert {"POST /sessions", "GET /sessions/{session_id}"} <= names
    assert not any(session_id in s.name for s in server)
    got = next(s for s in server if s.name == "GET /sessions/{session_id}")
    assert got.attributes["http.response.status_code"] == 200
    assert got.attributes["http.route"] == "/sessions/{session_id}"


def test_gate_changes_are_counted_and_gate_2_counts_the_solutions_components() -> None:
    from types import SimpleNamespace

    version = SimpleNamespace(
        version=2,
        content={
            "steps": [
                {"component": "DocumentsToStructuredData"},
                {"component": "LLMJudge"},
                {"component": "LLMJudge"},
                {"component": "x; drop"},
                {"type": "io"},
            ]
        },
    )
    session = SimpleNamespace(active_version=2, blueprint_versions=[version])
    approved = _value("wizard.gates", gate="gate_2", to="approved")
    judge = _value("wizard.components.selected", component="LLMJudge")
    other = _value("wizard.components.selected", component="other")

    ops_metrics.record_gate_changes(session, {"gate_2": ("pending", "approved")})

    assert _value("wizard.gates", gate="gate_2", to="approved") == approved + 1
    assert _value("wizard.components.selected", component="LLMJudge") == judge + 1
    assert _value("wizard.components.selected", component="other") == other + 1
    ops_metrics.record_gate_changes(session, {"gate_1": ("pending", "approved")})
    assert _value("wizard.components.selected", component="LLMJudge") == judge + 1


def test_a_turn_records_its_outcome_and_how_long_it_took() -> None:
    import asyncio

    from wizard_api import telemetry

    async def frames():
        yield 'data: {"delta": "hei"}\n\n'

    async def run() -> None:
        async for _ in telemetry.traced_turn(frames(), {}, lambda: [], "m", lambda f: False):
            pass

    completed = _value("wizard.turns", outcome="completed")
    asyncio.run(run())
    assert _value("wizard.turns", outcome="completed") == completed + 1
    counts = [
        p.count
        for rm in _READER.get_metrics_data().resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "wizard.turn.duration"
        for p in m.data.data_points
    ]
    assert sum(counts) >= 1


def test_the_alerting_label_sets_start_at_zero() -> None:
    ops_metrics.prime()
    labels = [a for a, _ in _points("wizard.session.deletes")]
    assert {"reason": "retention", "outcome": "failed"} in labels
    assert {"code": "agent_capacity"} in [a for a, _ in _points("wizard.refusals")]
    assert _points("wizard.ownership.denied")


def test_a_log_record_leaves_the_pod_without_ids_addresses_or_traceback() -> None:
    import logging

    from wizard_api import telemetry

    sid = str(uuid.uuid4())
    try:
        raise ValueError(f"/app/secret/path {sid}")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "wizard_api",
            logging.WARNING,
            __file__,
            1,
            "session.delete session=%s by %s",
            (sid, "alice@example.test"),
            sys.exc_info(),
        )
    out = telemetry.exportable_record(record)
    assert out.getMessage() == "session.delete session=<id> by <address> (ValueError)"
    assert out.exc_info is None and out.exc_text is None
    # The pod's own log keeps the original record.
    assert sid in record.getMessage() and record.exc_info is not None
