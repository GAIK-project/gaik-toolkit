import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.utils import wizard_tracing as tracing


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("WIZARD_LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://langfuse.test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "private-test-credential")


def test_opt_out_does_not_initialize_exporter(enabled):
    with patch.object(tracing, "_client") as client:
        trace = tracing.WizardTrace("session", False, "private input")
        trace.observe(SimpleNamespace(event={"type": "message_start"}))
        trace.finish()
    client.assert_not_called()
    assert trace.trace_id is None


def test_disabled_configuration_does_not_use_cloud_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("WIZARD_LANGFUSE_ENABLED", "true")
    with patch.object(tracing, "_client") as client:
        tracing.WizardTrace("session", True, "input")
    client.assert_not_called()


def test_exporter_initialization_failure_is_optional(enabled):
    with patch.object(tracing, "_client", side_effect=RuntimeError("unreachable")):
        trace = tracing.WizardTrace("session", True, "input")
        trace.finish()
    assert trace.root is None


def test_redaction_preserves_usage_and_removes_credentials(enabled):
    value = tracing.redact(
        {
            "input_tokens": 20,
            "cache_read_input_tokens": 10,
            "api_key": "private-test-credential",
            "text": "private-test-credential sk-proj-abcdefghijklmnop",
        }
    )
    assert value["input_tokens"] == 20
    assert value["cache_read_input_tokens"] == 10
    assert "private-test-credential" not in str(value)
    assert "abcdefghijklmnop" not in str(value)


def test_per_generation_cache_buckets_and_turn_totals_are_not_double_counted(enabled):
    client = MagicMock()
    root = client.start_observation.return_value
    root.trace_id = "a" * 32
    generation = root.start_observation.return_value
    with patch.object(tracing, "_client", return_value=client):
        trace = tracing.WizardTrace("session", True, "input")
        for event in [
            {
                "type": "message_start",
                "message": {
                    "model": "test-model",
                    "usage": {
                        "input_tokens": 20,
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 5,
                    },
                },
            },
            {"type": "content_block_delta", "delta": {"text": "answer"}},
            {"type": "message_delta", "usage": {"output_tokens": 4}},
            {"type": "message_stop"},
        ]:
            trace.observe(SimpleNamespace(event=event))
        trace.observe(
            SimpleNamespace(usage={"input_tokens": 20}, is_error=False, total_cost_usd=0.01)
        )
        trace.finish()
    generation.update.assert_called_once_with(
        output="answer",
        usage_details={
            "input": 20,
            "output": 4,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
        },
    )
    assert not any("usage_details" in call.kwargs for call in root.update.call_args_list)
    generation.end.assert_called_once()
    root.end.assert_called_once()


def test_interrupted_generation_and_tools_close_without_content_leak(enabled):
    client = MagicMock()
    root = client.start_observation.return_value
    with patch.object(tracing, "_client", return_value=client):
        trace = tracing.WizardTrace("session", True, "input")
        trace.observe(SimpleNamespace(event={"type": "message_start", "message": {"usage": {}}}))
        trace.observe(
            SimpleNamespace(
                content=[SimpleNamespace(id="tool", name="Read", input={"file": "test"})]
            )
        )
        trace.error("CancelledError")
        trace.finish()
    assert not trace.generations and not trace.tools
    assert root.start_observation.return_value.end.call_count == 2


def test_negative_and_invalid_usage_is_not_fabricated():
    assert tracing._counts({"input_tokens": -1, "output_tokens": True}) == {}


def test_real_sdk_exports_readable_content_and_masks_credentials(enabled, monkeypatch):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:private-password@db/demo")
    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="test-sdk-mask-contract",
        secret_key="private-test-credential",
        base_url="http://localhost:9",
        mask=tracing.redact,
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
    )
    with patch.object(tracing, "_client", return_value=client):
        trace = tracing.WizardTrace("synthetic-sdk-session", True, "synthetic readable input")
        trace.observe(
            SimpleNamespace(
                event={
                    "type": "message_start",
                    "message": {"model": "test-model", "usage": {"input_tokens": 2}},
                }
            )
        )
        trace.observe(
            SimpleNamespace(
                event={
                    "type": "content_block_delta",
                    "delta": {
                        "text": "synthetic answer private-test-credential postgresql://user:private-password@db/demo"
                    },
                }
            )
        )
        trace.observe(
            SimpleNamespace(event={"type": "message_delta", "usage": {"output_tokens": 3}})
        )
        trace.finish()
    client.flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    generation = next(s for s in spans if s.name == "Claude model call")
    attributes = dict(generation.attributes)
    assert "synthetic answer" in attributes["langfuse.observation.output"]
    assert "private-password" not in str(attributes)
    assert "private-test-credential" not in str(attributes)
    assert attributes["langfuse.observation.model.name"] == "test-model"
    assert attributes["session.id"] == "synthetic-sdk-session"
    root = next(s for s in spans if s.name == "Solution Wizard turn")
    assert "synthetic readable input" in root.attributes["langfuse.observation.input"]
    assert generation.parent.span_id == root.context.span_id
    client.shutdown()


def test_session_recording_choice_is_fixed_on_first_message_and_turns_finish():
    from api.routers import solution_wizard as wizard

    async def stream(_session, **_kwargs):
        yield "event: done\ndata: {}\n\n"

    async def run():
        client = MagicMock()
        from unittest.mock import AsyncMock

        client.query = AsyncMock()
        session = {"lock": asyncio.Lock(), "client": client, "pending_bootstrap": "instructions"}
        with (
            patch.dict(wizard.WIZARD_SESSIONS, {"synthetic": session}, clear=True),
            patch.object(wizard, "tracing_available", return_value=True),
            patch.object(wizard, "WizardTrace") as trace,
            patch.object(wizard, "_stream_turn", stream),
        ):
            for choice in [False, True]:
                response = await wizard.send_message(
                    "synthetic", wizard.MessageRequest(text="test input", trace=choice)
                )
                async for _ in response.body_iterator:
                    pass
            assert session["tracing"] is False
            assert [c.args[1] for c in trace.call_args_list] == [False, False]
            assert trace.return_value.finish.call_count == 2

    asyncio.run(run())


def test_receiver_failure_terminates_instead_of_sending_heartbeats_forever():
    from api.routers.solution_wizard import _receive_with_heartbeat

    class Client:
        async def receive_response(self):
            raise RuntimeError("synthetic receiver failure")
            yield

    async def run():
        async for _ in _receive_with_heartbeat(Client()):
            pass

    with pytest.raises(RuntimeError, match="synthetic receiver failure"):
        asyncio.run(asyncio.wait_for(run(), timeout=1))
