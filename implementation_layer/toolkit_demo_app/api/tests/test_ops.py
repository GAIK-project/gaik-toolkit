"""Telemetry is optional, bounded and content-free. No network or credentials."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from api.utils import ops
from fastapi import FastAPI, HTTPException
from starlette.responses import StreamingResponse


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("OPS_URL", "https://ops.invalid")
    monkeypatch.setenv("OPS_INGEST_KEY", "test-only")
    ops._attempts.clear()


def app():
    api = FastAPI()
    api.add_middleware(ops.OpsMiddleware)

    @api.post("/judge/{document_id}")
    async def judge(document_id: str):
        ops.record_llm(
            {
                "model": "test-model",
                "provider": "test",
                "input_tokens": 12,
                "output_tokens": 3,
                "duration_s": 0.2,
                "prompt": "PRIVATE",
            }
        )
        return {"answer": "PRIVATE"}

    @api.post("/broken")
    async def broken():
        raise RuntimeError("PRIVATE error with credential")

    @api.post("/handled")
    async def handled():
        raise HTTPException(503, "PRIVATE provider response")

    @api.post("/stream")
    async def stream():
        async def parts():
            yield b"data: first\n\n"
            await asyncio.sleep(0)
            yield b"data: second\n\n"

        return StreamingResponse(parts(), media_type="text/event-stream")

    @api.get("/health")
    async def health():
        return {"ok": True}

    return api


def request(api, path="/judge/PRIVATE-ID", method="POST"):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api, raise_app_exceptions=False),
            base_url="http://demo",
        ) as client:
            return await client.request(
                method, path, headers={"authorization": "PRIVATE"}, content="PRIVATE"
            )

    return asyncio.run(run())


@pytest.mark.parametrize("missing", ["OPS_URL", "OPS_INGEST_KEY"])
def test_disabled_without_either_setting(monkeypatch, missing):
    monkeypatch.delenv(missing)
    monkeypatch.setattr(ops, "report", lambda *args: pytest.fail("reporting must be disabled"))
    assert request(app()).json() == {"answer": "PRIVATE"}
    assert ops._trace.get() is None


def test_trace_and_actual_usage_are_allowlisted(monkeypatch):
    events = []
    monkeypatch.setattr(ops, "report", lambda *args: events.append(args))
    assert request(app()).status_code == 200
    assert [e[0] for e in events] == ["llm", "log"]
    llm, log = events
    assert llm[2]["input_tokens"] == 12
    assert llm[2]["model"] == "test-model"
    assert log[2]["route"] == "/judge/{document_id}"
    assert len(log[2]["trace"]) == 2
    assert llm[3] == log[3]
    assert "PRIVATE" not in json.dumps(events)
    assert ops._trace.get() is None


@pytest.mark.parametrize("path,status", [("/broken", 500), ("/handled", 503)])
def test_errors_report_status_without_messages(monkeypatch, path, status):
    events = []
    monkeypatch.setattr(ops, "report", lambda *args: events.append(args))
    assert request(app(), path).status_code == status
    assert len(events) == 1
    assert events[0][0] == "error"
    assert events[0][2]["status"] == status
    assert "PRIVATE" not in json.dumps(events)


def test_reporting_exception_cannot_change_success(monkeypatch):
    def fail(*args):
        raise RuntimeError("telemetry failed")

    monkeypatch.setattr(ops, "report", fail)
    assert request(app()).json() == {"answer": "PRIVATE"}


def test_streaming_bytes_unchanged(monkeypatch):
    events = []
    monkeypatch.setattr(ops, "report", lambda *args: events.append(args))
    response = request(app(), "/stream")
    assert response.content == b"data: first\n\ndata: second\n\n"
    assert len(events) == 1
    assert "data:" not in json.dumps(events)


def test_probes_and_unmatched_routes_are_not_reported(monkeypatch):
    events = []
    monkeypatch.setattr(ops, "report", lambda *args: events.append(args))
    request(app(), "/health", "GET")
    request(app(), "/does-not-exist/PRIVATE")
    assert events == []


def test_network_failure_is_swallowed_and_budget_is_bounded(monkeypatch):
    attempts = []

    def failed_post(*args, **kwargs):
        attempts.append(kwargs)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", failed_post)
    monkeypatch.setattr(
        ops.threading, "Thread", lambda *, target, **kw: SimpleNamespace(start=target)
    )
    for _ in range(100):
        ops.report("log", "operation", {}, "test")
    assert len(attempts) == 60
    assert attempts[0]["timeout"] == 3
    assert ops._slots.acquire(blocking=False)
    ops._slots.release()


def test_full_concurrency_and_thread_start_failure_never_block(monkeypatch):
    monkeypatch.setattr(
        ops.threading, "Thread", lambda **kw: (_ for _ in ()).throw(RuntimeError("cannot start"))
    )
    ops.report("log", "operation", {}, "test")
    for _ in range(4):
        assert ops._slots.acquire(blocking=False)
    try:
        ops.report("log", "operation", {}, "test")
        assert not ops._slots.acquire(blocking=False)
    finally:
        for _ in range(4):
            ops._slots.release()


def test_usage_outside_request_is_noop_and_bad_values_are_ignored():
    ops.record_llm({"prompt": "PRIVATE"})
    state = ops.RequestTrace()
    token = ops._trace.set(state)
    try:
        for _ in range(100):
            ops.record_llm(
                {"model": "PRIVATE with spaces", "input_tokens": float("nan"), "output_tokens": -1}
            )
        assert len(state.calls) == 63
        assert "model" not in state.calls[0]
        assert "input_tokens" not in state.calls[0]
    finally:
        ops._trace.reset(token)


def test_judge_adapter_records_real_usage_without_changing_response():
    from api.routers.llm_judge import _usage_dict
    from gaik.software_components.validators.llm_judge.schema import JudgeUsage

    usage = JudgeUsage(provider="azure", model="test-model", input_tokens=10, output_tokens=4)
    state = ops.RequestTrace()
    token = ops._trace.set(state)
    try:
        result = _usage_dict(usage)
        assert result["input_tokens"] == 10
        assert result["output_tokens"] == 4
        assert state.calls[0]["model"] == "test-model"
        assert state.calls[0]["input_tokens"] == 10
    finally:
        ops._trace.reset(token)
