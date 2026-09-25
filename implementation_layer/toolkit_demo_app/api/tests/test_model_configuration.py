"""Behavior checks for server defaults and per-model sampling options."""

import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.utils.config import get_api_config, get_model_options
from fastapi import HTTPException, UploadFile


@pytest.fixture(autouse=True)
def clear_provider_environment(monkeypatch):
    for name in (
        "DEMO_LLM_PROVIDER",
        "DEMO_LLM_MODEL",
        "LLM_PROVIDER",
        "AZURE_API_KEY",
        "OPENAI_API_KEY",
        "AITTA_API_KEY",
        "AITTA_API_TOKEN",
        "AITTA_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_preserves_provider_model_when_no_demo_override_is_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch(
        "gaik.software_components.llm.get_llm_config",
        return_value={"provider": "openai", "model": "account-specific-model"},
    ) as factory:
        config = get_api_config()
    assert config["model"] == "account-specific-model"
    factory.assert_called_once_with("openai")


def test_explicit_server_provider_and_model_win_over_azure_autodetection(monkeypatch):
    monkeypatch.setenv("AZURE_API_KEY", "test-azure")
    monkeypatch.setenv("DEMO_LLM_PROVIDER", "aitta")
    monkeypatch.setenv("DEMO_LLM_MODEL", "served-model")
    with patch("gaik.software_components.llm.get_llm_config", return_value={}) as factory:
        get_api_config()
    factory.assert_called_once_with("aitta", model="served-model")


def test_aitta_token_is_detected_without_azure_or_openai(monkeypatch):
    monkeypatch.setenv("AITTA_TOKEN", "test-token")
    with patch("gaik.software_components.llm.get_llm_config", return_value={}) as factory:
        get_api_config()
    factory.assert_called_once_with("aitta")


def test_unconfigured_server_has_actionable_error():
    with pytest.raises(HTTPException, match="Model settings") as error:
        get_api_config()
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "model,effort", [("gpt-6-luna", "none"), ("gpt-6-sol", "none"), ("gpt-6-astra", "low")]
)
def test_gpt6_sampling_is_valid_for_chat_and_schema(model, effort):
    for schema in (False, True):
        assert get_model_options({"provider": "azure", "model": model}, schema=schema) == {
            "temperature": None,
            "reasoning_effort": effort,
        }


def test_other_providers_do_not_receive_gpt_reasoning_settings():
    assert get_model_options({"provider": "aitta", "model": "served-model"}) == {
        "temperature": None,
        "reasoning_effort": None,
    }


@pytest.mark.parametrize("model,temperature", [("gpt-6-luna", None), ("gpt-4o", 0.0)])
def test_sql_agents_send_only_supported_temperatures(monkeypatch, tmp_path, model, temperature):
    from api.routers import postgres_agent, tabular_agent

    config = {"provider": "azure", "model": model}
    monkeypatch.setenv("DATABASE_URL", "postgresql://demo")
    monkeypatch.setattr(postgres_agent, "_seed_demo_schema", lambda url: None)
    for router in (postgres_agent, tabular_agent):
        monkeypatch.setattr(router, "_llm_config", lambda: config)
    with patch("gaik.software_components.postgres_agent.PostgresAgent") as sql_agent:
        postgres_agent._make_agent()
    with patch("gaik.software_components.tabular_agent.TabularAgent") as table_agent:
        table_agent.return_value.get_schema.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            tabular_agent._load_agent(tmp_path / "data.csv", "auto")
    assert sql_agent.call_args.kwargs["temperature"] == temperature
    assert table_agent.call_args.kwargs["temperature"] == temperature


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,model,effort", [("azure", "gpt-6-luna", "none"), ("aitta", "served-model", None)]
)
async def test_multimodal_parser_reads_reasoning_effort_from_its_config(
    monkeypatch, provider, model, effort
):
    import gaik.software_components.parsers as parsers
    from api.routers import parser as route

    captured = {}

    class FakeParser:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def parse(self, path):
            return SimpleNamespace(usage=None, clean_markdown="parsed")

    monkeypatch.delenv("AZURE_MULTIMODAL_DEPLOYMENT", raising=False)
    monkeypatch.setattr(parsers, "MultimodalParser", FakeParser)
    monkeypatch.setattr(route, "get_api_config", lambda: {"provider": provider, "model": model})
    result = await route.parse_document(
        file=UploadFile(filename="doc.pdf", file=io.BytesIO(b"%PDF-test")),
        parser_type="multimodal",
    )
    assert result["text_content"] == "parsed"
    assert "reasoning_effort" not in captured
    assert captured["api_config"].get("reasoning_effort") == effort
