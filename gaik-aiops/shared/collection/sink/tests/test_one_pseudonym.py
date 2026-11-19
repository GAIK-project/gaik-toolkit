"""One pseudonym per user across destinations, and the two collector configs kept in step.

The collector pseudonymises once, before branching, so an audit row in Postgres and a trace in MLflow
carry the same pseudonym for the same identity. The stack test is skipped when the stack is
not running; the config test always runs.
"""

import json
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
import pytest

OTLP = "http://127.0.0.1:4318"
MLFLOW = "http://127.0.0.1:5000"
READER = "host=127.0.0.1 port=55432 dbname=observability user=collection_reader password=reader-local-only"
COMPOSE = Path(__file__).resolve().parents[4] / "deploy" / "compose"


def _privacy_statements(path: Path, key_source: str) -> list[str]:
    text = path.read_text()
    block = text[text.index("  transform/privacy:"):]
    block = block[: re.search(r"\n  [a-z][\w/]*:\n", block[1:]).start() + 1]
    lines = [line.strip() for line in block.splitlines() if line.strip().startswith(("- set", "- delete", "- replace"))]
    return [line.replace(key_source, "<key>") for line in lines]


def test_the_openbao_overlay_differs_from_the_base_only_in_the_key_source():
    base = _privacy_statements(COMPOSE / "otel-collector.yaml", "${env:PSEUDONYM_KEY}")
    vault = _privacy_statements(COMPOSE / "openbao" / "otel-collector.openbao.yaml", "${file:/run/bao/pseudonym_key}")
    assert base and base == vault


def test_the_session_id_is_pseudonymised_before_it_names_the_mlflow_session():
    base = (COMPOSE / "otel-collector.yaml").read_text()
    statements = _privacy_statements(COMPOSE / "otel-collector.yaml", "${env:PSEUDONYM_KEY}")
    # Every name MLflow reads a session from, on spans and on logs.
    for context in ("span", "log"):
        for name in ("gaik.session.id", "session.id", "gen_ai.conversation.id"):
            hashed = f'set({context}.attributes["{name}"], SHA256(Concat(["<key>", "session:"'
            assert any(hashed in s for s in statements), (context, name)
    # The copy to session.id runs after the privacy processor, so it copies the pseudonym.
    assert "processors: [memory_limiter, filter/health, transform/privacy, transform/session, batch]" in base
    # The overlay overrides transform/privacy only; the session rule lives in the base config.
    assert "transform/session" not in (COMPOSE / "openbao" / "otel-collector.openbao.yaml").read_text()


def _post(path: str, body: dict) -> None:
    req = urllib.request.Request(f"{OTLP}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


def _s(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


def _up() -> bool:
    try:
        with psycopg.connect(READER, connect_timeout=2):
            pass
        urllib.request.urlopen(f"{MLFLOW}/health", timeout=2)
    except Exception:  # noqa: BLE001
        return False
    return True


@pytest.mark.skipif(not _up(), reason="compose stack not running")
def test_an_audit_row_and_a_trace_share_the_pseudonym():
    identity = f"user-{secrets.token_hex(6)}@example.com"
    trace_id = secrets.token_hex(16)
    resource = {"attributes": [_s("service.name", "pseudonym-test")]}
    _post("/v1/logs", {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": [{
        "traceId": trace_id,
        "attributes": [_s("gaik.event.class", "audit"), _s("event.name", "auth.login"),
                       _s("gaik.audit.outcome", "success"), _s("enduser.id", identity)],
    }]}]}]})
    now = time.time_ns()
    _post("/v1/traces", {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": [{
        "traceId": trace_id, "spanId": secrets.token_hex(8), "name": "chat", "kind": 3,
        "startTimeUnixNano": str(now - 1_000_000), "endTimeUnixNano": str(now),
        "attributes": [_s("gaik.event.class", "llm_call"), _s("enduser.id", identity)],
    }]}]}]})

    deadline = time.monotonic() + 30
    audit = span = None
    while time.monotonic() < deadline and not (audit and span):
        with psycopg.connect(READER) as conn:
            row = conn.execute("SELECT actor_pseudo_id FROM collection.audit_events WHERE trace_id = %s",
                               (trace_id,)).fetchone()
        audit = row[0] if row else None
        try:
            trace = json.load(urllib.request.urlopen(f"{MLFLOW}/api/3.0/mlflow/traces/get?trace_id=tr-{trace_id}",
                                                     timeout=5))["trace"]
            attrs = {a["key"]: next(iter(a["value"].values())) for a in trace["spans"][0]["attributes"]}
            span = attrs.get("enduser.pseudo.id")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(1)

    assert audit and span, f"audit={audit!r} span={span!r}"
    assert audit == span
    assert identity not in audit


def _routes_module():
    """deploy/compose/mlflow/setup_experiments.py, without the mlflow package it imports."""
    import importlib.util
    import sys
    import types

    sys.modules.setdefault("mlflow", types.SimpleNamespace(MlflowClient=object))
    spec = importlib.util.spec_from_file_location("setup_experiments", COMPOSE / "mlflow" / "setup_experiments.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_mlflow_routes_keep_the_base_traces_processors():
    # The routes fragment is merged over the base config and the collector replaces lists:
    # naming receivers or processors there would drop transform/session (or a later rule).
    traces = _routes_module().routes({"wizard-v2-api": "1"})["service"]["pipelines"]["traces"]
    assert traces == {"exporters": ["spanmetrics", "routing/mlflow"]}


def test_health_probe_spans_are_dropped_from_traces_only():
    # The wizard API's probe spans (GET /health and FastAPI's child spans) are dropped first in the
    # traces pipeline, after the memory limiter; logs and metrics keep their processors.
    base = (COMPOSE / "otel-collector.yaml").read_text()
    conditions = [
        line.strip()
        for line in base.split("  filter/health:\n")[1].split("  # Prometheus")[0].splitlines()
        if line.strip().startswith("- ")
    ]
    wizard = 'resource.attributes["service.name"] == "wizard-v2-api" and '
    assert conditions == [
        f'- {wizard}attributes["http.route"] == "/health"',
        f'- {wizard}attributes["code.function.name"] == "wizard_api.main.health"',
    ]
    assert "processors: [memory_limiter, filter/health, transform/privacy, transform/session, batch]" in base
    assert base.count("filter/health") == 2
    # The files merged over the base config name no processors (lists are replaced), so the filter stays.
    rahti_ingress = COMPOSE.parent / "k8s" / "stack" / "overlays" / "rahti" / "otlp-ingress-collector.yaml"
    for overlay in (COMPOSE / "openbao" / "otel-collector.openbao.yaml", rahti_ingress):
        text = overlay.read_text()
        assert "filter/health" not in text
        assert "transform/session" not in text
