"""Traces reach MLflow through the collector, pseudonymised, without content, in the right experiment and session.

Sends one synthetic llm_call span to the collector's OTLP/HTTP endpoint and reads it back from MLflow.
Skipped when the stack (collector and MLflow) is not reachable.
"""

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

COLLECTOR = "http://127.0.0.1:4318"
MLFLOW = "http://127.0.0.1:5000"
PROM = "http://127.0.0.1:9090"
EXPERIMENT = os.environ.get("MLFLOW_TRACES_EXPERIMENT_ID", "0")


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.load(resp)


def _up() -> bool:
    try:
        urllib.request.urlopen(f"{MLFLOW}/health", timeout=3)
        urllib.request.urlopen(urllib.request.Request(f"{COLLECTOR}/v1/traces", data=b"{}",
                                                      headers={"Content-Type": "application/json"}), timeout=3)
    except Exception:  # noqa: BLE001
        return False
    return True


pytestmark = pytest.mark.skipif(not _up(), reason="collector or MLflow not running")


def _attr(key: str, value):
    kind = "intValue" if isinstance(value, int) else "stringValue"
    return {"key": key, "value": {kind: str(value) if kind == "intValue" else value}}


def _send_span(service: str, *extra: dict) -> str:
    """Send one span and return its MLflow trace id (MLflow keeps the OTel trace id)."""
    trace_id = secrets.token_hex(16)
    now = time.time_ns()
    span = {
        "traceId": trace_id,
        "spanId": secrets.token_hex(8),
        "name": "chat synthetic-model",
        "kind": 3,
        "startTimeUnixNano": str(now - 1_000_000_000),
        "endTimeUnixNano": str(now),
        "attributes": [
            _attr("gaik.event.class", "llm_call"),
            _attr("gen_ai.request.model", "synthetic-model"),
            _attr("gen_ai.usage.input_tokens", 2104),
            _attr("enduser.id", "someone@example.com"),
            _attr("client.address", "192.0.2.147"),
            _attr("gen_ai.input.messages", "prompt text that must not be stored"),
            _attr("gen_ai.output.messages", "response text that must not be stored"),
            *extra,
        ],
    }
    body = {"resourceSpans": [{
        "resource": {"attributes": [_attr("service.name", service)]},
        "scopeSpans": [{"scope": {"name": "test"}, "spans": [span]}],
    }]}
    req = urllib.request.Request(f"{COLLECTOR}/v1/traces", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
    return f"tr-{trace_id}"


def _find_trace(trace_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return _get(f"{MLFLOW}/api/3.0/mlflow/traces/get?trace_id={trace_id}")["trace"]
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(1)
    raise AssertionError(f"trace {trace_id} did not reach MLflow")


def _experiment_of(trace: dict) -> str:
    return trace["trace_info"]["trace_location"]["mlflow_experiment"]["experiment_id"]


def _experiment_id(name: str) -> str:
    query = urllib.parse.urlencode({"experiment_name": name})
    return _get(f"{MLFLOW}/api/2.0/mlflow/experiments/get-by-name?{query}")["experiment"]["experiment_id"]


@pytest.fixture(scope="module")
def stored_trace() -> dict:
    # An unlisted service: goes to the Default experiment.
    return _find_trace(_send_span(f"synthetic-{secrets.token_hex(4)}"))


@pytest.fixture(scope="module")
def stored_span(stored_trace) -> dict:
    [span] = stored_trace["spans"]
    return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}


def test_trace_reaches_mlflow_with_its_measures(stored_span):
    assert stored_span["gaik.event.class"] == "llm_call"
    assert stored_span["gen_ai.request.model"] == "synthetic-model"
    assert int(stored_span["gen_ai.usage.input_tokens"]) == 2104


def test_identity_is_replaced_by_a_pseudonym(stored_span):
    assert "enduser.id" not in stored_span
    assert len(stored_span["enduser.pseudo.id"]) == 64
    assert "someone@example.com" not in json.dumps(stored_span)


def test_client_address_is_masked(stored_span):
    assert stored_span["client.address"] == "192.0.2.0"


def test_prompt_and_response_content_is_dropped(stored_span):
    assert "gen_ai.input.messages" not in stored_span
    assert "gen_ai.output.messages" not in stored_span
    assert "must not be stored" not in json.dumps(stored_span)


def test_a_listed_application_gets_its_own_experiment():
    # example-producer is in the default MLFLOW_EXPERIMENTS list (deploy/compose/docker-compose.yml).
    trace = _find_trace(_send_span("example-producer"))
    assert _experiment_of(trace) == _experiment_id("example-producer")
    assert _experiment_of(trace) != EXPERIMENT


def test_an_unlisted_service_goes_to_the_default_experiment(stored_trace):
    assert _experiment_of(stored_trace) == EXPERIMENT


def _session_of(trace: dict) -> str | None:
    return trace["trace_info"].get("trace_metadata", {}).get("mlflow.trace.session")


def _attributes(trace: dict) -> dict:
    [span] = trace["spans"]
    return {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}


def test_a_wizard_session_becomes_one_mlflow_session_under_a_pseudonym():
    session = f"wizard-session-{secrets.token_hex(4)}"
    first = _find_trace(_send_span("synthetic-wizard", _attr("gaik.session.id", session)))
    second = _find_trace(_send_span("synthetic-wizard", _attr("gaik.session.id", session)))
    pseudonym = _session_of(first)
    assert pseudonym == _session_of(second)
    assert len(pseudonym) == 64 and pseudonym != session
    # The raw id, which leads to the session's owner, is stored nowhere.
    assert _attributes(first)["gaik.session.id"] == pseudonym
    assert session not in json.dumps(first)


def test_a_producers_own_session_id_wins_and_is_pseudonymised_too():
    own = f"producer-session-{secrets.token_hex(4)}"
    wizard = f"wizard-session-{secrets.token_hex(4)}"
    both = _find_trace(_send_span("synthetic-wizard", _attr("session.id", own), _attr("gaik.session.id", wizard)))
    own_only = _find_trace(_send_span("synthetic-wizard", _attr("session.id", own)))
    wizard_only = _find_trace(_send_span("synthetic-wizard", _attr("gaik.session.id", wizard)))
    # The producer's session.id names the session, as its pseudonym, not the wizard's id.
    assert _session_of(both) == _session_of(own_only) != _session_of(wizard_only)
    assert len(_session_of(both)) == 64
    assert own not in json.dumps(both) and wizard not in json.dumps(both)


def test_a_trace_without_a_session_gets_none(stored_trace):
    assert _session_of(stored_trace) is None


def _send_request_trace(service: str, name: str, route: str, function: str) -> str:
    """Send a server span and one FastAPI child span, as the wizard API's instrumentation does."""
    trace_id, root_id = secrets.token_hex(16), secrets.token_hex(8)
    now = time.time_ns()
    times = {"startTimeUnixNano": str(now - 3_000_000), "endTimeUnixNano": str(now)}
    spans = [
        {"traceId": trace_id, "spanId": root_id, "name": name, "kind": 2, **times,
         "attributes": [_attr("http.route", route)]},
        {"traceId": trace_id, "spanId": secrets.token_hex(8), "parentSpanId": root_id, "name": "fastapi.endpoint",
         "kind": 1, **times, "attributes": [_attr("code.function.name", function)]},
    ]
    body = {"resourceSpans": [{
        "resource": {"attributes": [_attr("service.name", service)]},
        "scopeSpans": [{"scope": {"name": "test"}, "spans": spans}],
    }]}
    req = urllib.request.Request(f"{COLLECTOR}/v1/traces", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
    return f"tr-{trace_id}"


def _requests_counted(service: str, span_name: str) -> float:
    expr = f'sum(traces_span_metrics_calls_total{{service_name="{service}", span_name="{span_name}"}})'
    result = _get(f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr}))["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0


def _assert_not_in_mlflow(trace_id: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as missing:
        _get(f"{MLFLOW}/api/3.0/mlflow/traces/get?trace_id={trace_id}")
    assert missing.value.code == 404


def _wait_until_counted(service: str, span_name: str, counted_before: float) -> None:
    deadline = time.monotonic() + 30
    while _requests_counted(service, span_name) <= counted_before:
        assert time.monotonic() < deadline, f"{span_name} was not counted in the span metrics"
        time.sleep(1)


def test_health_probes_stay_out_of_mlflow_and_in_the_span_metrics():
    health = ("GET /health", "/health", "wizard_api.main.health")
    counted_before = _requests_counted("wizard-v2-api", "GET /health")
    probe = _send_request_trace("wizard-v2-api", *health)
    # Sent after the probe through the same pipeline: once these are stored, the probe has passed too.
    kept = _find_trace(_send_span("wizard-v2-api"))
    assert _experiment_of(kept) == _experiment_id("wizard-v2-api")
    # The same spans from another application are stored: the filter is the wizard API's alone.
    _find_trace(_send_request_trace("example-producer", *health))
    time.sleep(3)
    _assert_not_in_mlflow(probe)
    # Prometheus still counts the probe: the span metrics are taken before the filter.
    _wait_until_counted("wizard-v2-api", "GET /health", counted_before)


def test_page_requests_without_a_session_stay_out_of_mlflow_and_in_the_span_metrics():
    counted_before = _requests_counted("wizard-v2-api", "GET /sessions/{session_id}")
    opened = _send_request_trace("wizard-v2-api", "GET /sessions/{session_id}", "/sessions/{session_id}",
                                 "wizard_api.routers.sessions.get_session")
    listed = _send_request_trace("wizard-v2-api", "GET /sessions", "/sessions",
                                 "wizard_api.routers.sessions.list_sessions")
    # A PATCH of the session has the same route as opening it, and is stored with both its spans.
    patched = _find_trace(_send_request_trace("wizard-v2-api", "PATCH /sessions/{session_id}",
                                              "/sessions/{session_id}", "wizard_api.routers.sessions.update_session"))
    assert len(patched["spans"]) == 2
    time.sleep(3)
    _assert_not_in_mlflow(opened)
    _assert_not_in_mlflow(listed)
    _wait_until_counted("wizard-v2-api", "GET /sessions/{session_id}", counted_before)
