"""Vertex AI runs in the EU multi-region, and on the global endpoint for a model
the EU does not serve or while the EU does not answer."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from gaik.software_components.llm import google_provider  # noqa: E402
from gaik.software_components.llm.config import get_llm_config  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def _error(code: int) -> Exception:
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, {"error": {"code": code, "message": "synthetic"}})


class _Models:
    """One Vertex location: it answers, or fails the way ``failures`` says."""

    def __init__(self, location: str, world: dict):
        self.location, self.world = location, world

    def _answer(self, kind: str):
        self.world["log"].append((self.location, kind))
        failure = self.world["failures"].get(self.location)
        if failure is not None:
            raise failure

    def generate_content(self, **kwargs):
        self._answer("chat")
        return SimpleNamespace(text=f"from {self.location}", usage_metadata=None, parsed=None)

    def generate_content_stream(self, **kwargs):
        def chunks():
            self._answer("stream")
            yield SimpleNamespace(text="a")
            yield SimpleNamespace(text="b")

        return chunks()

    def embed_content(self, **kwargs):
        self._answer("embed")
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.5])])


@pytest.fixture
def world(monkeypatch):
    """The SDK client patched: ``log`` of calls and ``failures`` per location."""
    state = {"log": [], "failures": {}}
    monkeypatch.setattr(
        google_provider.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(models=_Models(kwargs["location"], state)),
    )
    monkeypatch.setattr(google_provider, "_NOT_SERVED", set())
    monkeypatch.setattr(google_provider, "_UNAVAILABLE_UNTIL", {})
    for name in ("GOOGLE_CLOUD_LOCATION", "GOOGLE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(name, raising=False)
    return state


def _provider(**overrides):
    config = get_llm_config("vertex", project_id="project", model="gemini-test", **overrides)
    return google_provider.GoogleProvider(config)


USER = [{"role": "user", "content": "hello"}]


def test_the_default_location_is_the_eu(world):
    config = get_llm_config("vertex", project_id="project", model="gemini-test")
    assert (config["location"], config["location_fallback"]) == ("eu", "global")
    provider = google_provider.GoogleProvider(config)
    assert provider.chat(USER).text == "from eu"
    assert world["log"] == [("eu", "chat")]


def test_a_model_the_eu_does_not_serve_runs_on_the_global_endpoint(world, caplog):
    world["failures"]["eu"] = _error(404)
    provider = _provider()
    with caplog.at_level(logging.WARNING):
        assert provider.chat(USER).text == "from global"
    assert "does not serve gemini-test" in caplog.text
    assert "not tied to a region" in caplog.text
    assert provider.location == "global"
    # Known for the process: neither this provider nor a new one asks the EU again.
    assert provider.chat(USER).text == "from global"
    assert _provider().chat(USER).text == "from global"
    assert world["log"] == [("eu", "chat"), ("global", "chat"), ("global", "chat")] + [
        ("global", "chat")
    ]


def test_another_model_is_still_asked_from_the_eu(world):
    world["failures"]["eu"] = _error(404)
    provider = _provider()
    provider.chat(USER)
    world["failures"].clear()
    world["log"].clear()
    assert provider.chat(USER, model="gemini-other").text == "from eu"
    assert world["log"] == [("eu", "chat")]


@pytest.mark.parametrize("failure", [_error(504), _error(503), _error(429), TimeoutError()])
def test_while_the_eu_does_not_answer_the_global_endpoint_takes_the_requests(
    world, failure, monkeypatch, caplog
):
    clock = [1000.0]
    monkeypatch.setattr(google_provider.time, "monotonic", lambda: clock[0])
    world["failures"]["eu"] = failure
    with caplog.at_level(logging.WARNING):
        assert _provider().chat(USER).text == "from global"
    assert "did not answer" in caplog.text and "tried again in 10 minutes" in caplog.text
    # For ten minutes no request waits for the EU, in any provider.
    clock[0] += 300
    assert _provider().chat(USER).text == "from global"
    assert world["log"] == [("eu", "chat"), ("global", "chat"), ("global", "chat")]
    # Then the EU is tried again, and used when it answers.
    world["failures"].clear()
    world["log"].clear()
    clock[0] += 301
    provider = _provider()
    assert provider.chat(USER).text == "from eu"
    assert provider.location == "eu"
    assert world["log"] == [("eu", "chat")]


def test_streams_and_embeddings_fall_back_too(world):
    world["failures"]["eu"] = _error(404)
    assert "".join(_provider().chat_stream(USER)) == "ab"
    assert _provider().embed(["text"], model="embedding-test") == [[0.5]]
    assert world["log"] == [
        ("eu", "stream"),
        ("global", "stream"),
        ("eu", "embed"),
        ("global", "embed"),
    ]


def test_a_failure_of_the_global_endpoint_is_raised(world):
    world["failures"].update(eu=_error(503), **{"global": _error(500)})
    with pytest.raises(genai_errors.ServerError):
        _provider().chat(USER)
    assert world["log"] == [("eu", "chat"), ("global", "chat")]


def test_a_location_from_the_environment_is_used_as_given(world, monkeypatch):
    world["failures"]["europe-north1"] = _error(404)
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-north1")
    config = get_llm_config("vertex", project_id="project", model="gemini-test")
    assert (config["location"], config["location_fallback"]) == ("europe-north1", None)
    with pytest.raises(genai_errors.ClientError):
        google_provider.GoogleProvider(config).chat(USER)
    assert world["log"] == [("europe-north1", "chat")]


def test_a_location_from_the_caller_is_used_as_given(world):
    world["failures"]["eu"] = _error(503)
    with pytest.raises(genai_errors.ServerError):
        _provider(location="eu").chat(USER)
    assert world["log"] == [("eu", "chat")]


def test_a_refused_request_stays_where_it_is(world):
    world["failures"]["eu"] = _error(403)
    with pytest.raises(genai_errors.ClientError):
        _provider().chat(USER)
    assert world["log"] == [("eu", "chat")]


def test_a_config_without_a_location_gets_the_same_default(world):
    world["failures"]["eu"] = _error(404)
    provider = google_provider.GoogleProvider(
        {"provider": "vertex", "project_id": "project", "model": "gemini-test"}
    )
    assert provider.chat(USER).text == "from global"
    assert world["log"] == [("eu", "chat"), ("global", "chat")]


def test_a_default_location_gets_a_request_timeout(monkeypatch):
    """Without one a request that never returns would never reach the fallback."""
    seen = []
    monkeypatch.setattr(
        google_provider.genai, "Client", lambda **kwargs: seen.append(kwargs) or SimpleNamespace()
    )
    for name in ("GOOGLE_CLOUD_LOCATION", "GOOGLE_SERVICE_ACCOUNT_JSON"):
        monkeypatch.delenv(name, raising=False)
    _provider()
    assert seen[-1]["http_options"].timeout == 120_000
    # The fallback is the retry, so the EU is asked once, not with the SDK's retries.
    assert seen[-1]["http_options"].retry_options.attempts == 1
    # A caller's own timeout stands, and a chosen location gets the default limit.
    _provider(timeout=30.0)
    assert seen[-1]["http_options"].timeout == 30_000
    _provider(max_retries=2)
    assert seen[-1]["http_options"].retry_options.attempts == 3
    _provider(location="europe-west4")
    assert seen[-1]["http_options"].timeout == 600_000


def test_a_fallback_named_in_the_config_decides(world):
    """Also without a location: None means no fallback, another location is used."""
    world["failures"]["eu"] = _error(503)
    base = {"provider": "vertex", "project_id": "project", "model": "gemini-test"}
    with pytest.raises(genai_errors.ServerError):
        google_provider.GoogleProvider({**base, "location_fallback": None}).chat(USER)
    assert world["log"] == [("eu", "chat")]
    world["log"].clear()
    google_provider._UNAVAILABLE_UNTIL.clear()
    provider = google_provider.GoogleProvider({**base, "location_fallback": "us-central1"})
    assert provider.chat(USER).text == "from us-central1"
    assert world["log"] == [("eu", "chat"), ("us-central1", "chat")]


def test_the_judge_asks_the_eu_once_within_a_time_limit(monkeypatch):
    """Its EU request is bounded, so a stalled EU reaches the global endpoint."""
    from gaik.software_components.validators.llm_judge import llm_judge as judge_module
    from google import genai

    clients = []

    class Models:
        def __init__(self, location):
            self.location = location

        def generate_content(self, **kwargs):
            if self.location == "eu":
                raise _error(504)
            return SimpleNamespace(text="{}", usage_metadata=None)

    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(models=Models(kwargs["location"]))

    monkeypatch.setattr(genai, "Client", client)
    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    monkeypatch.delenv("GOOGLE_VERTEXAI_LOCATION", raising=False)
    judge = SimpleNamespace(use_vertexai=True, model="gemini-test", max_tokens=64)
    text, _, _ = judge_module.LLMJudge._call_google(judge, [], "user", "system")
    assert text == "{}"
    assert [c["location"] for c in clients] == ["eu", "global"]
    assert clients[0]["http_options"].timeout == 120_000
    assert clients[0]["http_options"].retry_options.attempts == 1
    # A location from the environment is used as given, with the default limit and
    # no fallback.
    clients.clear()
    monkeypatch.setenv("GOOGLE_VERTEXAI_LOCATION", "eu")
    with pytest.raises(genai_errors.ServerError):
        judge_module.LLMJudge._call_google(judge, [], "user", "system")
    assert len(clients) == 1 and clients[0]["http_options"].timeout == 600_000
    assert clients[1:] == []
