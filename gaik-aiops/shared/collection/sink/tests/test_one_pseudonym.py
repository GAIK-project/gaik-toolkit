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
import yaml

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
    assert "processors: [memory_limiter, transform/privacy, transform/session, batch]" in base
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


def _wizard_filter() -> tuple[dict, list[str]]:
    """The routes fragment for two applications, and the wizard API's filter conditions in it."""
    fragment = _routes_module().routes({"wizard-v2-api": "1", "gaik-poc": "2"})
    [(name, mlflow_filter)] = fragment["processors"].items()
    assert name == "filter/mlflow-wizard-v2-api" and mlflow_filter["error_mode"] == "ignore"
    return fragment, mlflow_filter["traces"]["span"]


UNLESS_FAILED = " and status.code != STATUS_CODE_ERROR"


def test_the_wizard_apis_filter_is_on_its_own_pipeline_to_mlflow_only():
    fragment, _ = _wizard_filter()
    pipelines = fragment["service"]["pipelines"]
    assert pipelines["traces/mlflow-wizard-v2-api"] == {
        "receivers": ["routing/mlflow"],
        "processors": ["filter/mlflow-wizard-v2-api"],
        "exporters": ["otlphttp/mlflow-wizard-v2-api"],
    }
    # Other applications and the Default experiment get every span.
    assert "processors" not in pipelines["traces/mlflow-gaik-poc"]
    assert "processors" not in pipelines["traces/mlflow-default"]
    assert "processors" not in _routes_module().routes({"gaik-poc": "2"})


def test_health_probe_spans_are_left_out_of_mlflow_also_when_the_probe_fails():
    # The GET /health server span, and FastAPI's child spans under it by the endpoint function.
    _, conditions = _wizard_filter()
    assert 'attributes["http.route"] == "/health"' in conditions
    assert 'attributes["code.function.name"] == "wizard_api.main.health"' in conditions


PAGE_REQUESTS = (
    ("GET /sessions", "sessions.list_sessions"),
    ("GET /sessions/{session_id}", "sessions.get_session"),
    ("POST /sessions", "sessions.create_session"),
    ("POST /owners/claim", "owners.claim_legacy_sessions"),
)


def test_page_requests_without_a_session_are_left_out_of_mlflow():
    _, conditions = _wizard_filter()
    for span_name, function in PAGE_REQUESTS:
        assert f'name == "{span_name}"{UNLESS_FAILED}' in conditions
        assert f'attributes["code.function.name"] == "wizard_api.routers.{function}"' in conditions
    # A PATCH of the session is a step of it and is not named, and no condition goes by the route
    # that the PATCH shares with opening a session.
    assert not [c for c in conditions if "PATCH" in c or "update_session" in c]
    assert not [c for c in conditions if '"/sessions' in c]


# What the web app reads in the background while a session is open. Each passes the ownership check,
# so it carries the session and would be a row inside it.
BACKGROUND_READS = (
    ("GET /sessions/{session_id}/poc", "sessions.download_poc"),
    ("GET /sessions/{session_id}/poc/files", "sessions.list_poc_files"),
    ("GET /sessions/{session_id}/poc/file", "sessions.read_poc_file"),
    ("GET /sessions/{session_id}/poc/input", "sessions.list_poc_inputs"),
    ("GET /sessions/{session_id}/chat/stream", "sessions.chat_stream"),
)


def test_a_sessions_background_reads_are_left_out_of_mlflow_and_what_the_user_does_is_not():
    _, conditions = _wizard_filter()
    for span_name, function in BACKGROUND_READS:
        assert f'name == "{span_name}"{UNLESS_FAILED}' in conditions
        assert f'attributes["code.function.name"] == "wizard_api.routers.{function}"' in conditions
    # Only reads are named: the chat turn, an upload, a check, a run and a saved file are stored.
    named = [c for c in conditions if c.startswith("name == ")]
    assert not [c for c in named if not c.startswith(('name == "GET ', 'name == "POST /sessions"', 'name == "POST /owners/claim"'))]
    # Of the chat routes only the rejoined stream is named, not the turn.
    assert [c for c in conditions if "chat" in c] == [
        f'name == "GET /sessions/{{session_id}}/chat/stream"{UNLESS_FAILED}',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.chat_stream"',
    ]


def test_only_the_server_span_of_a_failed_request_is_kept():
    # Kept: the server span with an error status (a 5xx). Its child spans go whatever their status,
    # so a refused request, where only a child span is marked as an error, leaves nothing root-less.
    _, conditions = _wizard_filter()
    kept_when_failed = [c for c in conditions if "status.code" in c]
    assert kept_when_failed == [
        f'name == "{span_name}"{UNLESS_FAILED}' for span_name, _ in PAGE_REQUESTS + BACKGROUND_READS
    ]


def test_no_config_filters_spans_before_the_span_metrics():
    # The span metrics branch off the traces pipeline. Its processors are the base config's, and no
    # file merged over it (the collector replaces lists) names others, so Prometheus counts every span.
    base = yaml.safe_load((COMPOSE / "otel-collector.yaml").read_text())
    processors = base["service"]["pipelines"]["traces"]["processors"]
    assert processors and not [name for name in processors if name.startswith("filter")]
    rahti_ingress = COMPOSE.parent / "k8s" / "stack" / "overlays" / "rahti" / "otlp-ingress-collector.yaml"
    for overlay in (COMPOSE / "openbao" / "otel-collector.openbao.yaml", rahti_ingress):
        traces = yaml.safe_load(overlay.read_text())["service"]["pipelines"].get("traces", {})
        assert "processors" not in traces and "exporters" not in traces, overlay.name
    assert "processors" not in _wizard_filter()[0]["service"]["pipelines"]["traces"]


def test_a_filtered_application_that_is_not_listed_is_named():
    # Without a pipeline of its own the application has no filter: setup_experiments.py warns about it.
    module = _routes_module()
    assert module.unfiltered(["wizard-v2-api", "gaik-poc"]) == []
    assert module.unfiltered(["gaik-poc"]) == ["wizard-v2-api"]
    assert module.unfiltered([]) == ["wizard-v2-api"]
