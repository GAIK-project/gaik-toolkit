"""Behavior checks for server defaults and per-model sampling options."""

from unittest.mock import patch

import pytest
from api.utils.config import get_api_config, get_model_options
from fastapi import HTTPException


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
