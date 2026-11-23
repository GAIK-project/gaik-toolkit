"""The spans the API sends to the WP5 collector (wizard_api.telemetry).

Each test reads what was recorded through an in-memory exporter: the span's
name, its numbers and statuses, and that nothing the user or the agent wrote
ended up in it.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from helpers import requires_postgres
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from wizard_api import telemetry
from wizard_api.services import agent_service

sdk = pytest.importorskip("claude_agent_sdk")

_EXPORTER = InMemorySpanExporter()


@pytest.fixture
def spans():
    """The spans recorded during the test, by name."""
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    # Another test module may have installed the provider first; join it once.
    if not getattr(provider, "_telemetry_test_exporter", False):
        provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
        provider._telemetry_test_exporter = True
    _EXPORTER.clear()

    def by_name(name: str) -> list:
        return [s for s in _EXPORTER.get_finished_spans() if s.name == name]

    yield by_name
    _EXPORTER.clear()


def _result(**overrides):
    fields = {
        "subtype": "success",
        "duration_ms": 1500,
        "duration_api_ms": 1200,
        "is_error": False,
        "num_turns": 3,
        "session_id": "s",
        "total_cost_usd": 0.042,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 340,
            "cache_read_input_tokens": 9000,
            "cache_creation_input_tokens": 500,
        },
        "result": "Tässä on vastaukseni.",
    }
    fields.update(overrides)
    return sdk.ResultMessage(**fields)


def _all_values(span) -> str:
    return " ".join(str(v) for v in span.attributes.values())


def test_without_an_endpoint_nothing_is_set_up(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_provider", None)
    telemetry.setup()
    assert telemetry._provider is None


@pytest.mark.parametrize(
    "variable", ["OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
)
def test_either_standard_endpoint_turns_the_spans_on(monkeypatch, variable):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert not telemetry.enabled()
    monkeypatch.setenv(variable, "http://127.0.0.1:4318")
    assert telemetry.enabled()


class _Exporter:
    """Stands in for OTLPSpanExporter and keeps the arguments it was made with."""

    made: list[dict] = []

    def __init__(self, **kwargs):
        _Exporter.made.append(kwargs)

    def export(self, spans):
        return None

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True


@pytest.mark.parametrize(
    ("timeout_env", "expected"), [(None, {"timeout": telemetry.EXPORT_TIMEOUT_S}), ("7", {})]
)
def test_the_traces_endpoint_alone_sets_up_an_exporter_with_a_short_timeout(
    monkeypatch, timeout_env, expected
):
    from opentelemetry.exporter.otlp.proto.http import trace_exporter

    for variable in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TIMEOUT",
        "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    if timeout_env:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", timeout_env)
    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", _Exporter)
    installed = []
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", installed.append)
    monkeypatch.setattr(telemetry, "_provider", None)
    _Exporter.made.clear()

    telemetry.setup()

    assert _Exporter.made == [expected]  # with the env timeout, the exporter reads it itself
    assert installed == [telemetry._provider]
    telemetry.shutdown()


def test_a_turns_model_usage_becomes_a_chat_span_under_the_turn(spans):
    turn = telemetry.tracer.start_span("wizard.turn")
    telemetry.record_turn_usage(turn, _result(), "claude-sonnet", cost=0.042)
    turn.end()

    (chat,) = spans("chat claude-sonnet")
    assert chat.parent.span_id == turn.get_span_context().span_id
    assert chat.attributes["gaik.event.class"] == "llm_call"
    assert chat.attributes["gen_ai.request.model"] == "claude-sonnet"
    # Every input token: 120 uncached + 9000 read from and 500 written to the cache.
    assert chat.attributes["gen_ai.usage.input_tokens"] == 9620
    assert chat.attributes["gen_ai.usage.output_tokens"] == 340
    assert chat.attributes["gen_ai.usage.cache_read.input_tokens"] == 9000
    assert chat.attributes["gaik.cost.usd"] == 0.042
    assert chat.attributes["gaik.agent.num_turns"] == 3
    assert (chat.end_time - chat.start_time) == 1500 * 1_000_000
    assert "vastaukseni" not in _all_values(chat)


def test_the_model_that_answered_is_read_from_the_result(spans):
    usage = {
        "claude-haiku": {"inputTokens": 50, "outputTokens": 10},
        "claude-sonnet-5-5": {"inputTokens": 900, "outputTokens": 300},
    }
    turn = telemetry.tracer.start_span("wizard.turn")
    telemetry.record_turn_usage(turn, _result(model_usage=usage), "sonnet-deployment")
    turn.end()
    (chat,) = spans("chat sonnet-deployment")
    assert chat.attributes["gen_ai.request.model"] == "sonnet-deployment"
    assert chat.attributes["gen_ai.response.model"] == "claude-sonnet-5-5"


def test_each_query_is_priced_on_its_own_not_with_the_queries_before_it():
    # The SDK's total_cost_usd grows over the client's life (seen live: setup
    # 0.183, then 0.205 after a message that cost 0.022).
    agent: dict = {}
    assert telemetry.query_cost(agent, _result(total_cost_usd=0.183)) == pytest.approx(0.183)
    assert telemetry.query_cost(agent, _result(total_cost_usd=0.205)) == pytest.approx(0.022)
    assert telemetry.query_cost(agent, _result(total_cost_usd=None)) is None
    assert telemetry.query_cost({}, _result(total_cost_usd=0.05)) == pytest.approx(0.05)


def test_usage_the_sdk_did_not_report_is_left_out(spans):
    turn = telemetry.tracer.start_span("wizard.turn")
    telemetry.record_turn_usage(turn, _result(usage=None, total_cost_usd=None), "m")
    turn.end()
    (chat,) = spans("chat m")
    assert "gen_ai.usage.input_tokens" not in chat.attributes
    assert "gaik.cost.usd" not in chat.attributes


async def _frames(*frames):
    for frame in frames:
        yield frame


def _turn(frames, agents, model="m"):
    """Run ``telemetry.traced_turn`` over ``frames`` and return what it passed on."""

    async def go():
        stream = telemetry.traced_turn(
            frames,
            {"gaik.session.id": "s-1"},
            lambda: agents,
            model,
            agent_service.frame_is_error,
        )
        return [frame async for frame in stream]

    return asyncio.run(go())


def test_a_turn_passes_its_frames_on_and_puts_its_queries_under_it(spans):
    agent = {"turn_results": [("setup", _result(total_cost_usd=0.01)), ("turn", _result())]}
    done = agent_service.sse({"done": True})

    assert _turn(_frames(done), [(agent, False)]) == [done]

    (turn,) = spans("wizard.turn")
    assert turn.status.is_ok
    setup, chat = spans("chat m")
    assert [setup.attributes["gaik.agent.purpose"], chat.attributes["gaik.agent.purpose"]] == [
        "setup",
        "turn",
    ]
    assert chat.attributes["gaik.cost.usd"] == pytest.approx(0.032)
    assert chat.parent.span_id == turn.context.span_id
    assert "turn_results" not in agent  # counted once


def test_a_turn_whose_reply_is_an_error_frame_is_an_error(spans):
    _turn(_frames(agent_service.sse({"error": True, "message": "x"})), [])
    (turn,) = spans("wizard.turn")
    assert not turn.status.is_ok


def test_stopping_at_the_turn_limit_is_not_an_error(spans):
    from wizard_api.routers.sessions import _turn_failed

    frame = agent_service.sse(agent_service.TURN_LIMIT_FRAME)
    assert agent_service.frame_is_error(frame)  # the UI shows it as a notice
    assert not _turn_failed(frame)
    assert _turn_failed(agent_service.sse({"error": True, "message": "x"}))


def test_a_turn_the_client_left_is_marked_aborted_and_ended(spans):
    agent = {"turn_results": [("setup", _result(total_cost_usd=0.01))]}

    async def go():
        stream = telemetry.traced_turn(
            _frames(agent_service.sse({"delta": "a"}), agent_service.sse({"delta": "b"})),
            {},
            lambda: [(agent, False)],
            "m",
            agent_service.frame_is_error,
        )
        await stream.__anext__()
        await stream.aclose()  # what Starlette does when the client disconnects

    asyncio.run(go())

    (turn,) = spans("wizard.turn")
    assert turn.attributes["gaik.turn.aborted"] is True
    assert len(spans("chat m")) == 1  # what had arrived is still counted, once


def test_a_failed_query_answered_by_a_retry_is_not_an_error(spans):
    old = {"turn_results": [("turn", _result(is_error=True, subtype="error_during_execution"))]}
    new = {"turn_results": [("setup", _result(total_cost_usd=0.01)), ("turn", _result())]}

    _turn(_frames(agent_service.sse({"done": True})), [(old, True), (new, False)])

    (turn,) = spans("wizard.turn")
    assert turn.status.is_ok
    replaced, setup, answered = spans("chat m")
    assert replaced.attributes["gaik.agent.replaced"] is True
    assert replaced.status.is_ok
    assert setup.status.is_ok and answered.status.is_ok


def test_a_turn_that_crashes_is_an_error_with_only_the_exception_type(spans):
    async def crashing():
        yield agent_service.sse({"delta": "a"})
        raise RuntimeError("database at 10.0.0.5 refused user someone@example.com")

    with pytest.raises(RuntimeError):
        _turn(crashing(), [])

    (turn,) = spans("wizard.turn")
    assert not turn.status.is_ok
    assert turn.attributes["error.type"] == "RuntimeError"
    assert "someone@example.com" not in _all_values(turn)
    assert not turn.events  # no exception event with the message in it


def _gate_session():
    return SimpleNamespace(id=uuid.uuid4(), gate_statuses={"gate_1": "pending"})


def _gate_update():
    from wizard_api.routers.sessions import SessionUpdate

    return SessionUpdate(gate_statuses={"gate_1": "approved"})


def test_a_gate_change_that_crashes_is_an_error(spans):
    from wizard_api.routers.sessions import _gate_span

    with pytest.raises(RuntimeError), _gate_span(_gate_session(), _gate_update()):
        raise RuntimeError("could not serialize access")

    (gate,) = spans("wizard.gate")
    assert not gate.status.is_ok
    assert gate.attributes["error.type"] == "RuntimeError"
    assert "gaik.gate.refused" not in gate.attributes


def test_a_refused_gate_change_is_an_answer_not_an_error(spans):
    from wizard_api.routers.sessions import _gate_span

    with pytest.raises(HTTPException), _gate_span(_gate_session(), _gate_update()):
        raise HTTPException(409, detail={"error": "gate_not_ready"})

    (gate,) = spans("wizard.gate")
    assert gate.status.is_unset
    assert gate.attributes["gaik.gate.refused"] == "gate_not_ready"


def test_a_gate_change_the_api_could_not_do_is_an_error(spans):
    from wizard_api.routers.sessions import _gate_span

    with pytest.raises(HTTPException), _gate_span(_gate_session(), _gate_update()):
        raise HTTPException(503, detail={"error": "sandbox_unavailable"})

    (gate,) = spans("wizard.gate")
    assert not gate.status.is_ok
    assert gate.attributes["error.type"] == "sandbox_unavailable"


def test_a_sandbox_start_the_api_could_not_do_is_an_error(spans):
    @telemetry.sandbox_start_span("run")
    def start(session_id):
        raise HTTPException(503, detail={"error": "sandbox_unavailable"})

    with pytest.raises(HTTPException):
        start(session_id="s-1")

    (span,) = spans("wizard.sandbox.start")
    assert not span.status.is_ok
    assert span.attributes["gaik.sandbox.refused"] == "sandbox_unavailable"


def test_a_sandbox_start_that_crashes_is_an_error(spans):
    @telemetry.sandbox_start_span("run")
    def start(session_id):
        raise RuntimeError("Kubernetes API unreachable")

    with pytest.raises(RuntimeError):
        start(session_id="s-1")

    (span,) = spans("wizard.sandbox.start")
    assert not span.status.is_ok
    assert span.attributes["error.type"] == "RuntimeError"


def test_a_refused_sandbox_start_is_an_answer_not_an_error(spans):
    @telemetry.sandbox_start_span("run")
    def start(session_id):
        raise HTTPException(409, detail={"error": "gate_not_approved"})

    with pytest.raises(HTTPException):
        start(session_id="s-1")

    (span,) = spans("wizard.sandbox.start")
    assert span.status.is_unset
    assert span.attributes["gaik.sandbox.refused"] == "gate_not_approved"


class _Client:
    """A ClaudeSDKClient that answers every query with one ResultMessage."""

    def __init__(self, *args, **kwargs):
        self.results = [_result(total_cost_usd=0.01), _result(total_cost_usd=0.02)]

    async def connect(self):
        pass

    async def query(self, text):
        pass

    async def receive_response(self):
        yield self.results.pop(0)


def test_the_agents_bootstrap_is_kept_for_the_first_turn(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text("skill")
    monkeypatch.setattr(agent_service, "resolve_wizard_dir", lambda: tmp_path)
    monkeypatch.setattr(agent_service, "_build_options", lambda *a, **k: None)
    monkeypatch.setattr(agent_service, "ClaudeSDKClient", _Client)
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {})

    agent = asyncio.run(
        agent_service._start_session("s-1", str(tmp_path / "out"), "fi", None, None, None)
    )

    assert [purpose for purpose, _ in agent["turn_results"]] == ["setup"]


def test_a_reply_language_change_is_kept_for_the_turn_that_asked_for_it(monkeypatch):
    agent = {"client": _Client(), "locale": "fi", "last_active": 0}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {"s-1": agent})

    asyncio.run(agent_service.get_or_create_session("s-1", "/tmp/unused", "en"))

    assert [purpose for purpose, _ in agent["turn_results"]] == ["language"]


def test_a_turns_query_is_kept_for_its_span():
    class _Turn:
        async def receive_response(self):
            yield sdk.AssistantMessage(content=[sdk.TextBlock(text="ok")], model="m")
            yield _result()

    agent = {"client": _Turn(), "id": "t", "last_active": 0}

    async def go():
        return [f async for f in agent_service._stream_turn(agent, [])]

    asyncio.run(go())

    assert [purpose for purpose, _ in agent["turn_results"]] == ["turn"]


@requires_postgres
def test_a_chat_message_is_one_turn_span_with_its_usage_and_no_text(client, monkeypatch, spans):
    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        # A new agent: its bootstrap query is counted with the first turn.
        return {"lock": asyncio.Lock(), "turn_results": [("setup", _result(total_cost_usd=0.01))]}

    async def fake_stream_turn_for(agent, message, parts):
        agent["turn_results"].append(("turn", _result()))
        parts.append("Tässä on vastaukseni.")
        yield agent_service.sse({"delta": "Tässä on vastaukseni."})
        yield agent_service.sse({"done": True})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)
    # The web UI sends the user's e-mail address as the user id.
    email = "matti.meikalainen@example.com"
    sid = client.post("/sessions", json={"user_id": email, "title": "T"}).json()["id"]

    client.post(
        f"/sessions/{sid}/chat",
        json={"message": "Salainen liiketoimintaongelma"},
        headers={"X-Wizard-User-Id": email},
    )

    (turn,) = spans("wizard.turn")
    assert turn.attributes["gaik.session.id"] == sid
    assert turn.attributes["gaik.step"] == 1
    assert "gate_1=pending" in turn.attributes["gaik.gate_statuses"]
    assert "enduser.id" not in turn.attributes
    assert turn.status.is_ok
    setup, chat = spans(f"chat {agent_service._model()}")
    assert setup.attributes["gaik.agent.purpose"] == "setup"
    assert setup.attributes["gaik.cost.usd"] == 0.01
    assert chat.attributes["gaik.agent.purpose"] == "turn"
    # The SDK's running total was 0.042 after the turn: the turn itself cost 0.032.
    assert chat.attributes["gaik.cost.usd"] == pytest.approx(0.032)
    for span in (setup, chat):
        assert span.parent.span_id == turn.context.span_id
    for span in (turn, setup, chat):
        assert "Salainen" not in _all_values(span)
        assert "vastaukseni" not in _all_values(span)
        assert email not in _all_values(span)


@requires_postgres
def test_usage_is_counted_once(client, monkeypatch, spans):
    agent = {"lock": asyncio.Lock()}

    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        return agent

    totals = iter([0.03, 0.05])  # the SDK's running total after each message

    async def fake_stream_turn_for(agent, message, parts):
        agent.setdefault("turn_results", []).append(("turn", _result(total_cost_usd=next(totals))))
        parts.append("ok")
        yield agent_service.sse({"done": True})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)
    sid = client.post("/sessions", json={"user_id": "u", "title": "T"}).json()["id"]

    client.post(f"/sessions/{sid}/chat", json={"message": "yksi"})
    client.post(f"/sessions/{sid}/chat", json={"message": "kaksi"})

    assert len(spans("wizard.turn")) == 2
    costs = [s.attributes["gaik.cost.usd"] for s in spans(f"chat {agent_service._model()}")]
    assert costs == [pytest.approx(0.03), pytest.approx(0.02)]


@requires_postgres
def test_a_refused_gate_approval_says_why(client, spans):
    sid = client.post("/sessions", json={"user_id": "g", "title": "G"}).json()["id"]

    response = client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_1": "approved"}})

    assert response.status_code == 409
    (gate,) = spans("wizard.gate")
    assert gate.attributes["gaik.gate"] == "gate_1"
    assert gate.attributes["gaik.gate.from"] == "pending"
    assert gate.attributes["gaik.gate.to"] == "approved"
    assert gate.attributes["gaik.gate.refused"] == "gate_not_ready"


@requires_postgres
def test_an_approved_gate_is_recorded(client, db_session, spans):
    from helpers import write_gate_artifacts
    from wizard_api.services import session_service

    created = client.post("/sessions", json={"user_id": "g", "title": "G"}).json()
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    write_gate_artifacts(session.output_dir, through="gate_1")

    response = client.patch(
        f"/sessions/{created['id']}", json={"gate_statuses": {"gate_1": "approved"}}
    )

    assert response.status_code == 200
    (gate,) = spans("wizard.gate")
    assert gate.attributes["gaik.gate.to"] == "approved"
    assert "gaik.gate.refused" not in gate.attributes


@requires_postgres
def test_a_request_that_changes_no_gate_makes_no_gate_span(client, spans):
    sid = client.post("/sessions", json={"user_id": "g", "title": "G"}).json()["id"]
    client.patch(f"/sessions/{sid}", json={"title": "Renamed"})
    assert spans("wizard.gate") == []


@requires_postgres
def test_a_sandbox_run_refused_before_gate_2_is_recorded(client, spans):
    sid = client.post("/sessions", json={"user_id": "s", "title": "S"}).json()["id"]

    assert client.post(f"/sessions/{sid}/runs").status_code == 409

    (start,) = spans("wizard.sandbox.start")
    assert start.attributes["gaik.sandbox.kind"] == "run"
    assert start.attributes["gaik.sandbox.refused"] == "gate_not_approved"
    assert "gaik.sandbox.run_id" not in start.attributes


class _Runner:
    """Stands in for SandboxRunner: a preflight that starts and fails."""

    def __init__(self, *args, **kwargs):
        pass

    def start_check(self, session_id, version, *, user_id=None):
        return {"run_id": "run-9-chk", "phase": "pending", "reused": False}

    def check_run_of_session(self, run_id, session_id):
        pass

    def stream_logs(self, run_id):
        yield "ModuleNotFoundError: no module named 'gaik'"

    def final_status(self, run_id, **_):
        from wizard_api.services.sandbox_runner import RunStatus

        return RunStatus(run_id, "failed", exit_code=1)

    def run_kind(self, run_id):
        return "check"


@requires_postgres
def test_a_sandbox_check_is_recorded_when_it_starts_and_when_it_settles(
    client, db_session, monkeypatch, spans
):
    from test_poc_endpoints import _write_poc
    from wizard_api.services import sandbox_runner, session_service

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _Runner)
    sid = client.post("/sessions", json={"user_id": "s", "title": "S"}).json()["id"]
    _write_poc(session_service.get_session(db_session, uuid.UUID(sid)).output_dir)

    assert client.post(f"/sessions/{sid}/poc/check").status_code == 201
    client.get(f"/sessions/{sid}/runs/run-9-chk/stream")

    (start,) = spans("wizard.sandbox.start")
    assert start.attributes["gaik.sandbox.kind"] == "check"
    assert start.attributes["gaik.sandbox.run_id"] == "run-9-chk"
    (result,) = spans("wizard.sandbox.result")
    assert result.attributes["gaik.sandbox.run_id"] == "run-9-chk"
    assert result.attributes["gaik.sandbox.phase"] == "failed"
    assert result.attributes["gaik.sandbox.exit_code"] == 1
    assert not result.status.is_ok
    assert "ModuleNotFoundError" not in _all_values(result)


@requires_postgres
def test_a_case_run_refused_before_gate_2_is_recorded(client, spans):
    sid = client.post("/sessions", json={"user_id": "c", "title": "C"}).json()["id"]

    response = client.post(f"/sessions/{sid}/cases/case-1/submit", json={})

    assert response.status_code in (404, 409)
    (start,) = spans("wizard.sandbox.start")
    assert start.attributes["gaik.sandbox.kind"] == "case"
    assert "gaik.sandbox.refused" in start.attributes
