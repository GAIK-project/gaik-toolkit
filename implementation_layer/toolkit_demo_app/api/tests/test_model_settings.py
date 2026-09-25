"""BYOK security and request isolation; no network or real credentials."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import socket
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from api.utils import model_settings as settings
from api.utils.config import get_api_config, get_model_options
from fastapi import FastAPI, HTTPException, UploadFile
from starlette.responses import StreamingResponse


def header(provider="aitta", model="test-model", **kwargs):
    return json.dumps({"provider": provider, "model": model, "apiKey": "test-secret", **kwargs})


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://resource.openai.azure.com",
        "https://127.0.0.1",
        "https://localhost",
        "https://resource.openai.azure.com.attacker.example",
        "https://resource.privatelink.openai.azure.com",
        "https://user:password@resource.openai.azure.com",
        "https://resource.openai.azure.com:8443",
        "https://resource.openai.azure.com/path",
        "https://resource.openai.azure.com/?api-key=test-secret",
        "https://resource.openai.azure.com/#fragment",
    ],
)
def test_rejects_unsafe_azure_endpoints_without_echoing_inputs(endpoint):
    with pytest.raises(HTTPException) as exc:
        settings.parse_model_settings(header("azure", azureEndpoint=endpoint))
    assert exc.value.status_code == 400
    assert "test-secret" not in str(exc.value)
    assert endpoint not in str(exc.value)


@pytest.mark.parametrize("domain", ["openai.azure.com", "services.ai.azure.com"])
def test_normalizes_documented_public_azure_urls(domain):
    result = settings.parse_model_settings(
        header("azure", azureEndpoint=f"https://resource.{domain}/openai/v1/")
    )
    assert result.azure_endpoint == f"https://resource.{domain}"
    assert "test-secret" not in repr(result)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "192.168.1.5",
        "::1",
        "fe80::1",
        "::ffff:10.0.0.1",
    ],
)
def test_rejects_private_dns_answers(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(HTTPException, match="public Azure"):
        settings._validate_public_endpoint("https://resource.openai.azure.com")


def test_public_dns_is_allowed(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("20.10.20.30", 443))]
    )
    settings._validate_public_endpoint("https://resource.openai.azure.com")


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        header()[:-1],
        header(apiKey=""),
        header(apiKey="key\nheader"),
        header(base_url="http://localhost"),
        header(azureEndpoint="https://attacker.example"),
        header("other"),
        header(model=""),
        header(model="x" * 201),
        "x" * 8193,
    ],
)
def test_invalid_settings_fail_closed(payload):
    with pytest.raises(HTTPException):
        settings.parse_model_settings(payload)


@pytest.mark.asyncio
async def test_parallel_and_streaming_requests_keep_separate_credentials(monkeypatch):
    transports = []

    class Transport:
        def __init__(self, **kwargs):
            assert kwargs == {"follow_redirects": False, "trust_env": False}
            self.closed = False
            transports.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(settings.httpx, "Client", Transport)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://internal-server-should-not-be-used")
    monkeypatch.setenv("AITTA_BASE_URL", "http://also-not-used")
    monkeypatch.setenv("EMBEDDING_MODEL", "server-embedding")
    before = dict(__import__("os").environ)
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)
    observed = {}

    @app.post("/extract")
    async def extract():
        async def stream():
            config = await asyncio.to_thread(get_api_config)
            await asyncio.sleep(0.01)
            assert get_api_config()["api_key"] == config["api_key"]
            assert not config["http_client"].closed
            assert config["embedding_model"] == ""
            assert get_model_options(config) == {"temperature": None, "reasoning_effort": None}
            observed[config["model"]] = (config["api_key"], config["base_url"])
            yield "data: ok\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first, second = await asyncio.gather(
            client.post(
                "/extract",
                headers={settings.HEADER.decode(): header(model="first", apiKey="first-key")},
            ),
            client.post(
                "/extract",
                headers={settings.HEADER.decode(): header("openai", "second", apiKey="second-key")},
            ),
        )
    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert observed == {
        "first": ("first-key", "https://aitta-api.csc.fi/openai/v1"),
        "second": ("second-key", "https://api.openai.com/v1"),
    }
    assert all(t.closed for t in transports)
    assert settings.request_model_settings() is None
    assert dict(__import__("os").environ) == before


@pytest.mark.asyncio
async def test_keys_are_rejected_on_unsupported_routes_before_endpoint_runs():
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)
    called = []

    @app.post("/rag/index")
    async def endpoint():
        called.append(True)
        return {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/rag/index", headers={settings.HEADER.decode(): header()})
    assert response.status_code == 400
    assert not called
    assert "test-secret" not in response.text


def test_provider_errors_cannot_echo_the_submitted_secret():
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        assert "test-secret" not in settings.provider_error_detail(
            RuntimeError("test-secret rejected")
        )
    finally:
        settings._settings.reset(token)


@pytest.mark.asyncio
async def test_unexpected_provider_exception_is_sanitized_before_leaving_context():
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)

    @app.post("/extract")
    async def endpoint():
        raise RuntimeError("remote error includes test-secret")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/extract", headers={settings.HEADER.decode(): header()})
    assert response.status_code == 502
    assert "test-secret" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert settings.request_model_settings() is None


def test_provider_exception_log_arguments_are_not_serialized():
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            "test",
            1,
            "Call failed: %s",
            (RuntimeError("partially-masked-provider-key and test-secret"),),
            None,
        )
        settings._CredentialRedactionFilter().filter(record)
        assert record.getMessage() == "Call failed: RuntimeError"
    finally:
        settings._settings.reset(token)


def test_own_key_request_urls_are_not_logged():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        "httpx",
        1,
        "HTTP Request: %s %s",
        ("POST", "https://own-resource.openai.azure.com/openai/deployments/own-model"),
        None,
    )
    log_filter = settings._CredentialRedactionFilter()
    assert log_filter.filter(record)
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        assert not log_filter.filter(record)
    finally:
        settings._settings.reset(token)


@pytest.mark.asyncio
async def test_own_key_provider_calls_do_not_block_the_event_loop(monkeypatch):
    import threading

    import gaik.software_components.extractor as component
    from api.routers import extractor

    released = threading.Event()
    observed = {}

    class FakeExtractor:
        def __init__(self, config, **kwargs):
            pass

        def extract(self, **kwargs):
            # A cold Aitta model can take minutes; the loop must keep serving meanwhile.
            observed["api_key"] = get_api_config()["api_key"]
            observed["loop_ran"] = released.wait(timeout=2)
            return [{"extracted_data": "ok"}]

    monkeypatch.setattr(component, "DataExtractor", FakeExtractor)
    asyncio.get_running_loop().call_later(0.05, released.set)
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        result = await extractor.extract_data(
            extractor.ExtractRequest(documents=["Total 5 EUR"], user_requirements="Find the total")
        )
    finally:
        settings._settings.reset(token)
    assert observed == {"api_key": "test-secret", "loop_ran": True}
    assert result.document_count == 1


@pytest.mark.asyncio
async def test_classifier_result_error_does_not_bypass_sanitizer(monkeypatch):
    import gaik.software_components.doc_classifier as component
    from api.routers import classifier

    class FakeClassifier:
        def __init__(self, config):
            assert config["api_key"] == "test-secret"

        def classify(self, file_or_dir, **kwargs):
            return {
                Path(file_or_dir).name: {
                    "class": "unknown",
                    "confidence": 0,
                    "reasoning": "Classification error: test-secret rejected",
                }
            }

    monkeypatch.setattr(component, "DocumentClassifier", FakeClassifier)
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        result = await classifier.classify_document(
            file=UploadFile(filename="sample.pdf", file=io.BytesIO(b"%PDF-test")),
            classes="invoice,receipt",
            parser="auto",
        )
        assert "test-secret" not in result["reasoning"]
        assert "Model request failed" in result["reasoning"]
    finally:
        settings._settings.reset(token)


@pytest.mark.asyncio
async def test_judge_uses_own_config_and_sanitizes_remote_errors(monkeypatch):
    import gaik.software_components.validators as component
    from api.routers import llm_judge

    captured = {}

    class FakeJudge:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def judge_text_pair(self, **kwargs):
            raise RuntimeError("test-secret rejected")

    monkeypatch.setattr(component, "LLMJudge", FakeJudge)
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        with pytest.raises(HTTPException) as exc:
            await llm_judge.text_pair(
                llm_judge.TextPairRequest(
                    extracted_text="A", expected_text="B", provider="azure", model="server-model"
                )
            )
        assert captured["config"]["provider"] == "aitta"
        assert captured["model"] == "test-model"
        assert "test-secret" not in str(exc.value.detail)
    finally:
        settings._settings.reset(token)


@pytest.mark.asyncio
async def test_vision_extraction_uses_own_model_instead_of_server_allowlist(monkeypatch):
    import gaik.software_components.vision_extractor as component
    from api.routers import vision_extractor

    captured = {}

    class FakeExtractor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def extract(self, **kwargs):
            return SimpleNamespace(
                data={"ok": True},
                verification=None,
                model="test-model",
                documents_processed=1,
                duration_s=0.1,
                usage=None,
            )

    monkeypatch.setattr(component, "VisionExtractor", FakeExtractor)
    task, _, _ = vision_extractor._load_example_schema()
    token = settings._settings.set(settings.parse_model_settings(header()))
    try:
        result = await vision_extractor.extract_vision(
            files=[UploadFile(filename="sample.pdf", file=io.BytesIO(b"%PDF-test"))],
            user_requirements=task,
            schema_id=vision_extractor.EXAMPLE_SCHEMA_ID,
            model_provider="azure",
            model="not-allowed-server-model",
            reasoning_effort="high",
            merge_table=True,
            additional_instructions="",
            include_verification=False,
        )
        assert result.model == "test-model"
        assert captured["api_config"]["provider"] == "aitta"
        assert captured["model"] == "test-model"
        assert captured["reasoning_effort"] is None
    finally:
        settings._settings.reset(token)
