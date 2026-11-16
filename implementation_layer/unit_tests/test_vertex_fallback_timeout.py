"""The default Vertex AI path: only the EU request gets the implicit limit, a
location set on the config is used as given, and the release smoke test runs
that default path and reports which endpoint answered."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from gaik.software_components.llm import google_provider  # noqa: E402
from gaik.software_components.llm.config import get_llm_config  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
USER = [{"role": "user", "content": "hello"}]


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "release_smoke_vertex", ROOT / "scripts" / "release_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clients(monkeypatch):
    """The SDK client patched: each client's kwargs; the EU answers 503."""
    seen = []

    class Models:
        def __init__(self, location):
            self.location = location

        def generate_content(self, **kwargs):
            if self.location == "eu":
                raise genai_errors.ServerError(503, {"error": {"code": 503, "message": "x"}})
            return SimpleNamespace(text=f"from {self.location}", usage_metadata=None)

    def client(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(models=Models(kwargs["location"]))

    monkeypatch.setattr(google_provider.genai, "Client", client)
    monkeypatch.setattr(google_provider, "_NOT_SERVED", set())
    monkeypatch.setattr(google_provider, "_UNAVAILABLE_UNTIL", {})
    for name in ("GOOGLE_CLOUD_LOCATION", "GOOGLE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(name, raising=False)
    return seen


def _by_location(seen):
    return {kwargs["location"]: kwargs for kwargs in seen}


def test_the_fallback_client_gets_no_implicit_timeout(clients):
    config = get_llm_config("vertex", project_id="project", model="gemini-test")
    provider = google_provider.GoogleProvider(config)
    assert provider.chat(USER).text == "from global"
    by_location = _by_location(clients)
    assert by_location["eu"]["http_options"].timeout == 120_000
    # The global endpoint keeps the SDK's default: a long request can finish there.
    assert "http_options" not in by_location["global"]


def test_a_callers_timeout_applies_to_both_clients(clients):
    config = get_llm_config("vertex", project_id="project", model="gemini-test", timeout=300.0)
    google_provider.GoogleProvider(config).chat(USER)
    by_location = _by_location(clients)
    assert by_location["eu"]["http_options"].timeout == 300_000
    assert by_location["eu"]["http_options"].retry_options.attempts == 1
    assert by_location["global"]["http_options"].timeout == 300_000


@pytest.mark.parametrize("how", ["assigned", "merged"])
def test_a_location_set_on_the_returned_dict_does_not_fall_back(clients, how):
    config = get_llm_config("vertex", project_id="project", model="gemini-test")
    if how == "assigned":
        config["location"] = "europe-west4"
    else:
        config = {**config, "location": "europe-west4"}
    clients.clear()
    provider = google_provider.GoogleProvider(config)
    assert provider.chat(USER).text == "from europe-west4"
    assert [kwargs["location"] for kwargs in clients] == ["europe-west4"]
    assert provider._fallback_location is None
    assert "http_options" not in clients[0]


def test_a_regional_fallback_named_with_the_location_stays(clients):
    config = get_llm_config(
        "vertex",
        project_id="project",
        model="gemini-test",
        location="eu",
        location_fallback="europe-west1",
    )
    config["location"] = "europe-west4"
    provider = google_provider.GoogleProvider(config)
    assert provider._fallback_location == "europe-west1"


def test_release_smoke_runs_the_default_vertex_path(monkeypatch):
    smoke = _load_smoke()
    for name in ("GOOGLE_CLOUD_LOCATION", "GOOGLE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    config = smoke.smoke_config("vertex", "gemini-test", 180)
    assert config["location_fallback"] == "global"
    assert "timeout" not in config and "max_retries" not in config
    # A location from the environment, or the LiteLLM route, keeps the run's limits.
    assert smoke.smoke_config("vertex", "gemini-test", 180, "litellm")["max_retries"] == 0
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
    config = smoke.smoke_config("vertex", "gemini-test", 180)
    assert (config["timeout"], config["max_retries"]) == (180, 0)


def test_release_smoke_keeps_other_providers_bounded(monkeypatch):
    smoke = _load_smoke()
    monkeypatch.setenv("AZURE_API_KEY", "placeholder")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://example.invalid")
    config = smoke.smoke_config("azure", "release-model", 180)
    assert (config["timeout"], config["max_retries"]) == (180, 0)


def test_release_smoke_reports_which_endpoint_answered():
    smoke = _load_smoke()
    eu = SimpleNamespace(provider="vertex", location="eu")
    global_ = SimpleNamespace(provider="vertex", location="global")
    wrapped = SimpleNamespace(provider="vertex", location=None, _client=global_)
    other = SimpleNamespace(provider="azure")
    assert smoke.vertex_locations([wrapped, eu, global_, other]) == ["eu", "global"]


def test_a_global_fallback_named_with_a_regional_location_stays(clients):
    config = get_llm_config(
        "vertex",
        project_id="project",
        model="gemini-test",
        location="europe-west4",
        location_fallback="global",
    )
    provider = google_provider.GoogleProvider(config)
    assert provider._fallback_location == "global"
