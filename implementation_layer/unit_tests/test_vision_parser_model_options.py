"""Tests for model-specific VisionParser request options."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser
from gaik.software_components.parsers.visionPlus import VisionPlusParser


class _CapturingCompletions:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="parsed markdown"))]
        )


def _parser(
    monkeypatch,
    *,
    temperature: float | None,
    reasoning_effort: str | None,
) -> tuple[VisionParser, _CapturingCompletions]:
    completions = _CapturingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(VisionParser, "_initialize_client", lambda self: client)

    parser = VisionParser(
        OpenAIConfig(model="gpt-test", use_azure=False, api_key="test"),
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
    return parser, completions


def test_reasoning_model_omits_temperature(monkeypatch):
    parser, completions = _parser(
        monkeypatch,
        temperature=None,
        reasoning_effort="low",
    )

    assert parser._parse_image(b"image", page=1, previous_context=None) == "parsed markdown"
    assert completions.kwargs is not None
    assert "temperature" not in completions.kwargs
    assert completions.kwargs["reasoning_effort"] == "low"


def test_legacy_temperature_remains_supported(monkeypatch):
    parser, completions = _parser(
        monkeypatch,
        temperature=0.0,
        reasoning_effort=None,
    )

    parser._parse_image(b"image", page=1, previous_context=None)
    assert completions.kwargs is not None
    assert completions.kwargs["temperature"] == 0.0
    assert "reasoning_effort" not in completions.kwargs


def test_vision_plus_exposes_same_model_options():
    parameters = inspect.signature(VisionPlusParser).parameters

    assert parameters["temperature"].default == 0.0
    assert parameters["reasoning_effort"].default is None


@pytest.mark.parametrize("provider", ["openai", "openai_compatible", "aitta", " OPENAI "])
def test_explicit_non_azure_provider_uses_configured_endpoint(monkeypatch, provider):
    from gaik.software_components.parsers import vision

    captured = {}
    client = object()
    http_client = object()

    def build_client(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr(vision, "OpenAI", build_client)
    parser = VisionParser(
        {
            "provider": provider,
            "use_azure": True,
            "model": "vision-model",
            "api_key": "test",
            "base_url": "https://inference.example.test/v1",
            "timeout": 300.0,
            "max_retries": 0,
            "http_client": http_client,
        }
    )

    assert parser._client is client
    assert parser.config.use_azure is False
    assert captured == {
        "api_key": "test",
        "base_url": "https://inference.example.test/v1",
        "timeout": 300.0,
        "max_retries": 0,
        "http_client": http_client,
    }


def test_explicit_azure_provider_overrides_legacy_flag(monkeypatch):
    from gaik.software_components.parsers import vision

    captured = {}
    monkeypatch.setattr(vision, "AzureOpenAI", lambda **kwargs: captured.update(kwargs))

    parser = VisionParser(
        {
            "provider": "azure",
            "use_azure": False,
            "model": "vision-deployment",
            "api_key": "test",
            "azure_endpoint": "https://example.openai.azure.com/",
            "api_version": "2025-03-01-preview",
        }
    )

    assert parser.config.use_azure is True
    assert captured["azure_endpoint"] == "https://example.openai.azure.com/"
    assert captured["api_version"] == "2025-03-01-preview"


def test_vision_config_reads_openai_base_url(monkeypatch):
    from gaik.software_components.parsers import vision

    monkeypatch.setattr(vision, "_load_env", lambda: None)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example.test/v1")

    assert vision.get_openai_config(use_azure=False).base_url == (
        "https://inference.example.test/v1"
    )


def test_vision_azure_config_has_api_version_default(monkeypatch):
    from gaik.software_components.parsers import vision

    monkeypatch.setattr(vision, "_load_env", lambda: None)
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    assert vision.get_openai_config(use_azure=True).api_version == "2024-12-01-preview"


@pytest.mark.parametrize("provider", ["google", "anthropic", "vertex", "litellm"])
def test_native_provider_uses_shared_client_for_image_and_cleanup(monkeypatch, provider):
    from gaik.software_components.llm.base import ChatResponse
    from gaik.software_components.parsers import vision

    class Client:
        model = "vision-model"
        raw = None

        def __init__(self):
            self.provider = provider
            self.calls = []

        def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return ChatResponse(text="parsed", model=self.model, provider=self.provider)

        def chat_parsed(self, *args, **kwargs):
            raise AssertionError("Expected plain chat")

        def chat_stream(self, *args, **kwargs):
            raise AssertionError("Expected plain chat")

        def embed(self, *args, **kwargs):
            raise AssertionError("Expected plain chat")

    client = Client()
    configs = []
    monkeypatch.setattr(vision, "create_llm_client", lambda cfg: configs.append(cfg) or client)
    config = {"provider": provider, "model": "vision-model", "api_key": "provider-key"}
    parser = VisionParser(config)
    assert parser._parse_image(b"image", page=1, previous_context=None) == "parsed"
    assert parser._clean_markdown(["first", "second"]) == "parsed"
    assert configs == [config]
    assert client.calls[0][0][0]["content"][1]["type"] == "image_url"
    assert "first" in client.calls[1][0][0]["content"]
    assert client.calls[0][1]["max_tokens"] == 16000


def test_gpt6_raw_vision_omits_default_sampling(monkeypatch):
    completions = _CapturingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(VisionParser, "_initialize_client", lambda self: client)
    parser = VisionParser({"provider": "openai", "model": "gpt-6-sol", "api_key": "test"})
    parser._parse_image(b"image", page=1, previous_context=None)
    assert "temperature" not in completions.kwargs


def test_jpeg_image_uses_matching_media_type(monkeypatch, tmp_path):
    parser, completions = _parser(monkeypatch, temperature=None, reasoning_effort=None)
    path = tmp_path / "picture.jpg"
    path.write_bytes(b"synthetic-jpeg")
    assert parser.convert_image(path) == "parsed markdown"
    image = completions.kwargs["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/jpeg;base64,")


def test_aitta_vision_defaults_to_aitta_endpoint(monkeypatch):
    from gaik.software_components.parsers import vision

    captured = {}
    monkeypatch.setattr(vision, "OpenAI", lambda **kwargs: captured.update(kwargs))

    VisionParser({"provider": "aitta", "model": "vision-model", "api_key": "test"})

    assert captured["base_url"] == "https://aitta-api.csc.fi/openai/v1"
    assert captured["timeout"] == 600.0


@pytest.mark.parametrize("missing", ["base_url", "model"])
def test_openai_compatible_vision_requires_endpoint_and_model(missing):
    config = {
        "provider": "openai_compatible",
        "model": "vision-model",
        "api_key": "test",
        "base_url": "https://example.test/v1",
    }
    del config[missing]
    with pytest.raises(ValueError, match=f"requires an explicit '{missing}'"):
        VisionParser(config)


def test_azure_vision_accepts_explicit_base_url(monkeypatch):
    from gaik.software_components.parsers import vision

    captured = {}
    monkeypatch.setattr(vision, "AzureOpenAI", lambda **kwargs: captured.update(kwargs))

    VisionParser(
        {
            "provider": "azure",
            "model": "vision-model",
            "api_key": "test",
            "api_version": "2025-03-01-preview",
            "base_url": "https://example.openai.azure.com/openai",
        }
    )

    assert captured["base_url"] == "https://example.openai.azure.com/openai"
    assert "azure_endpoint" not in captured
