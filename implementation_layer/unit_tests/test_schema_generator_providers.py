"""Provider routing regressions for the public schema generator."""

from __future__ import annotations

import pytest
from gaik.software_components.extractor.schema import SchemaGenerator
from gaik.software_components.form_understander import FormUnderstander
from openai import OpenAI


@pytest.mark.parametrize("component", [SchemaGenerator, FormUnderstander])
def test_migrated_component_accepts_minimal_legacy_openai_config(monkeypatch, component):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    instance = component(config={"api_key": "test-key", "model": "legacy-model"})
    try:
        assert type(instance.client) is OpenAI
        assert instance.model == "legacy-model"
    finally:
        instance.client.close()


class _ProviderClient:
    provider = "google"
    model = "test-model"
    raw = None

    def __init__(self):
        self.calls = []

    def chat_parsed(self, messages, response_format, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return response_format.model_validate(
            {
                "structure_type": "flat",
                "parent_container_name": "invoice",
                "parent_description": "One invoice",
                "item_description": "One invoice",
                "reasoning": "One record with scalar fields.",
            }
        )

    def chat(self, messages, **kwargs):
        raise AssertionError("Expected a structured call")

    def chat_stream(self, messages, **kwargs):
        raise AssertionError("Expected a structured call")

    def embed(self, texts, **kwargs):
        raise AssertionError("Expected a structured call")


def test_schema_generator_uses_provider_adapter_for_structure_analysis(monkeypatch):
    from gaik.software_components.llm import factory

    client = _ProviderClient()
    configs = []

    def create_client(config):
        configs.append(config)
        return client

    monkeypatch.setattr(factory, "create_llm_client", create_client)
    monkeypatch.setattr(
        factory,
        "create_openai_client",
        lambda config: (_ for _ in ()).throw(AssertionError("Wrong provider factory")),
    )
    config = {"provider": "google", "api_key": "test", "model": "test-model"}

    generator = SchemaGenerator(config)
    result = generator.analyze_structure("Extract the invoice number.")

    assert generator.client is client
    assert configs == [config]
    assert result.structure_type == "flat"
    assert client.calls[0]["model"] == "test-model"
    assert client.calls[0]["temperature"] == 0.0
    assert "invoice number" in client.calls[0]["messages"][-1]["content"]


@pytest.mark.parametrize("provider", ["openai", "azure", "openai_compatible", "aitta"])
def test_provider_adapter_receives_reasoning_options(provider):
    from gaik.software_components.extractor.schema import StructureAnalysis, _parse_with

    client = _ProviderClient()
    client.provider = provider
    _parse_with(
        client=client,
        model="test-model",
        messages=[{"role": "user", "content": "Extract a number."}],
        response_format=StructureAnalysis,
        temperature=None,
        reasoning_effort="low",
    )

    assert client.calls[0]["reasoning_effort"] == "low"
    assert "temperature" not in client.calls[0]
    assert "timeout" not in client.calls[0]


@pytest.mark.parametrize("provider", ["google", "anthropic", "anthropic_foundry"])
def test_native_provider_receives_temperature_without_openai_reasoning_option(provider):
    from gaik.software_components.extractor.schema import StructureAnalysis, _parse_with

    client = _ProviderClient()
    client.provider = provider
    _parse_with(
        client=client,
        model="test-model",
        messages=[{"role": "user", "content": "Extract a number."}],
        response_format=StructureAnalysis,
        temperature=0.2,
        reasoning_effort="low",
    )

    assert client.calls[0]["temperature"] == 0.2
    assert "reasoning_effort" not in client.calls[0]
