"""The demo's model calls stay in the region it names."""

from __future__ import annotations

import pytest
from api.utils import model_settings
from api.utils.model_settings import byok_openai_overrides, region_overrides


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_CLOUD_LOCATION_FALLBACK",
        "DEMO_BYOK_OPENAI_REGION",
    ):
        monkeypatch.delenv(name, raising=False)


def test_vertex_is_named_the_eu_so_gaik_never_falls_back_by_itself():
    from gaik.software_components.llm import get_llm_config

    overrides = region_overrides("vertex")
    config = get_llm_config("vertex", project_id="p", model="gemini-test", **overrides)

    assert overrides == {"location": "eu"}
    assert config["location"] == "eu"
    assert config.get("location_fallback") is None


def test_vertex_takes_its_location_and_a_named_fallback_from_the_environment(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-north1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION_FALLBACK", "europe-west4")
    assert region_overrides("vertex") == {
        "location": "europe-north1",
        "location_fallback": "europe-west4",
    }


@pytest.mark.parametrize("provider", ["azure", "openai", "aitta", "anthropic_foundry"])
def test_other_providers_get_nothing_added(provider):
    assert region_overrides(provider) == {}


def test_an_own_openai_key_goes_to_the_global_api_unless_the_eu_is_chosen(monkeypatch):
    from gaik.software_components.endpoints import check_endpoint

    assert byok_openai_overrides() == {"base_url": "https://api.openai.com/v1"}

    monkeypatch.setenv("DEMO_BYOK_OPENAI_REGION", "EU")
    eu = byok_openai_overrides()
    assert eu["base_url"] == "https://eu.api.openai.com/v1"
    assert check_endpoint(
        eu["base_url"], provider="openai", allowed_hosts=eu["allowed_endpoint_hosts"]
    )

    monkeypatch.setenv("DEMO_BYOK_OPENAI_REGION", "mars")
    assert byok_openai_overrides() == {"base_url": "https://api.openai.com/v1"}


def test_the_server_model_path_names_the_vertex_location(monkeypatch):
    seen = {}

    def fake_get_llm_config(provider, **overrides):
        seen.update(provider=provider, **overrides)
        return {"provider": provider, **overrides}

    import gaik.software_components.llm as llm

    monkeypatch.setattr(llm, "get_llm_config", fake_get_llm_config)
    chosen = type("Chosen", (), {"provider": "vertex", "model": "gemini-x"})()
    settings_token = model_settings._settings.set(None)
    server_token = model_settings._server_model.set(chosen)
    try:
        model_settings.get_request_api_config()
    finally:
        model_settings._server_model.reset(server_token)
        model_settings._settings.reset(settings_token)

    assert seen["location"] == "eu"
