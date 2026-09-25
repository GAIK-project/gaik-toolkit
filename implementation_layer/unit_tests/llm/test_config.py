"""Configuration overrides must work without provider credentials in the environment."""

import pytest
from gaik.software_components.llm.config import get_llm_config


@pytest.fixture(autouse=True)
def clear_provider_env(monkeypatch):
    import os

    for name in os.environ:
        if name.startswith(
            ("OPENAI_", "AZURE_", "ANTHROPIC_", "GOOGLE_", "GEMINI_", "AITTA_", "LITELLM_")
        ):
            monkeypatch.delenv(name)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


@pytest.mark.parametrize("provider", ["openai", "google", "anthropic", "aitta"])
def test_explicit_key_does_not_require_environment(provider):
    config = get_llm_config(provider, api_key="explicit-key", model="custom-model")
    assert config["api_key"] == "explicit-key"
    assert config["model"] == "custom-model"
    assert config["provider"] == provider
    assert config["use_azure"] is False


def test_azure_overrides_work_without_environment():
    config = get_llm_config(
        "azure", api_key="explicit-key", azure_endpoint="https://example.openai.azure.com/"
    )
    assert config["use_azure"] is True
    assert config["azure_endpoint"] == config["azure_audio_endpoint"]


def test_explicit_provider_wins_over_conflicting_legacy_flag():
    assert get_llm_config("openai", api_key="key", use_azure=True)["use_azure"] is False


def test_azure_accepts_base_url_without_endpoint_environment():
    config = get_llm_config(
        "azure", api_key="key", base_url="https://example.openai.azure.com/openai"
    )
    assert config["base_url"] == "https://example.openai.azure.com/openai"


def test_compatible_config_accepts_explicit_values():
    config = get_llm_config(
        "openai_compatible",
        api_key="local-key",
        base_url="https://local.example/v1",
        model="local-model",
        timeout=90,
        max_retries=0,
    )
    assert config["base_url"] == "https://local.example/v1"
    assert config["embedding_model"] == ""
    assert config["timeout"] == 90
    assert config["max_retries"] == 0


@pytest.mark.parametrize("missing", ["base_url", "model"])
def test_compatible_requires_explicit_endpoint_and_model(missing):
    overrides = {"api_key": "key", "base_url": "https://local.example/v1", "model": "model"}
    del overrides[missing]
    with pytest.raises(ValueError, match=missing):
        get_llm_config("openai_compatible", **overrides)


def test_compatible_reads_openai_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://local.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "local-model")
    config = get_llm_config("openai_compatible")
    assert config["model"] == "local-model"
    assert config["base_url"] == "https://local.example/v1"


@pytest.mark.parametrize("key_name", ["AITTA_API_KEY", "AITTA_API_TOKEN", "AITTA_TOKEN"])
def test_aitta_token_aliases_and_defaults(monkeypatch, key_name):
    monkeypatch.setenv(key_name, "  test-token  ")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    config = get_llm_config("aitta")
    assert config["api_key"] == "test-token"
    assert config["base_url"] == "https://aitta-api.csc.fi/openai/v1"
    assert config["model"] == "google/gemma-4-31b-it"
    assert config["embedding_model"] == ""
    assert config["timeout"] == 600.0


def test_aitta_environment_overrides(monkeypatch):
    monkeypatch.setenv("AITTA_API_TOKEN", "token")
    monkeypatch.setenv("AITTA_MODEL", "served-model")
    monkeypatch.setenv("AITTA_EMBEDDING_MODEL", "served-embedding-model")
    monkeypatch.setenv("AITTA_BASE_URL", "https://aitta.example/openai/v1")
    config = get_llm_config("aitta", timeout=120)
    assert config["model"] == "served-model"
    assert config["embedding_model"] == "served-embedding-model"
    assert config["base_url"] == "https://aitta.example/openai/v1"
    assert config["timeout"] == 120


def test_blank_credentials_are_rejected(monkeypatch):
    monkeypatch.setenv("AITTA_API_KEY", "   ")
    with pytest.raises(ValueError, match="AITTA_API_KEY"):
        get_llm_config("aitta")


def test_vertex_explicit_fields_do_not_require_environment():
    config = get_llm_config(
        "vertex",
        project_id="project",
        service_account_json="{}",
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
        generate_content_url="https://vertex.example/generateContent",
    )
    assert config["project_id"] == "project"


def test_foundry_explicit_fields_do_not_require_environment():
    config = get_llm_config("anthropic_foundry", api_key="key", resource="resource")
    assert config["resource"] == "resource"
