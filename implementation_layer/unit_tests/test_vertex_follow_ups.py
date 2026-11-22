"""Vertex AI fallback follow-ups (#198): the record of what the EU did not answer is
kept per model and expires, the LLM judge shares it, and every client a provider
built is closed."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from gaik.software_components.llm import google_provider  # noqa: E402
from gaik.software_components.llm.config import get_llm_config  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402

USER = [{"role": "user", "content": "hello"}]


def _error(code: int) -> Exception:
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, {"error": {"code": code, "message": "synthetic"}})


@pytest.fixture
def world(monkeypatch):
    """The SDK client patched. ``failures`` maps (location, model) to an error;
    ``log`` lists (location, model) per request; ``clients`` every client built."""
    state = {"log": [], "failures": {}, "clients": []}

    class Models:
        def __init__(self, location):
            self.location = location

        def generate_content(self, *, model, **kwargs):
            state["log"].append((self.location, model))
            failure = state["failures"].get((self.location, model))
            if failure is not None:
                raise failure
            usage = SimpleNamespace(
                prompt_token_count=5, candidates_token_count=2, thoughts_token_count=None
            )
            return SimpleNamespace(text="{}", usage_metadata=usage, parsed=None)

    class Client:
        def __init__(self, **kwargs):
            self.kwargs, self.closed = kwargs, 0
            self.models = Models(kwargs.get("location"))
            state["clients"].append(self)

        def close(self):
            self.closed += 1

    monkeypatch.setattr(google_provider.genai, "Client", Client)
    monkeypatch.setattr(google_provider, "_NOT_SERVED", {})
    monkeypatch.setattr(google_provider, "_UNAVAILABLE_UNTIL", {})
    clock = [1000.0]
    monkeypatch.setattr(google_provider.time, "monotonic", lambda: clock[0])
    state["clock"] = clock
    for name in (
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_VERTEXAI_LOCATION",
    ):
        monkeypatch.delenv(name, raising=False)
    return state


def _provider(**overrides):
    config = get_llm_config("vertex", project_id="project", model="gemini-a", **overrides)
    return google_provider.GoogleProvider(config)


# ── The record is per model ──────────────────────────────────────────


@pytest.mark.parametrize("failure", [_error(504), _error(429), TimeoutError()])
def test_one_models_failure_leaves_the_other_models_in_the_eu(world, failure):
    world["failures"][("eu", "gemini-a")] = failure
    provider = _provider()
    provider.chat(USER)
    assert world["log"] == [("eu", "gemini-a"), ("global", "gemini-a")]

    world["log"].clear()
    provider.chat(USER, model="gemini-b")
    _provider().chat(USER, model="gemini-b")
    # The failing model stays on the global endpoint for the cool-down.
    _provider().chat(USER)
    assert world["log"] == [("eu", "gemini-b"), ("eu", "gemini-b"), ("global", "gemini-a")]


def test_a_model_the_eu_does_not_serve_is_asked_there_again_later(world, caplog):
    world["failures"][("eu", "gemini-a")] = _error(404)
    with caplog.at_level(logging.WARNING):
        _provider().chat(USER)
    assert "does not serve gemini-a; it is asked again in 60 minutes" in caplog.text

    world["clock"][0] += google_provider.NOT_SERVED_RETRY_SECONDS - 1
    _provider().chat(USER)
    assert world["log"][-1] == ("global", "gemini-a")

    # The EU now serves the model: after the lifetime it is asked and used.
    del world["failures"][("eu", "gemini-a")]
    world["clock"][0] += 2
    world["log"].clear()
    provider = _provider()
    provider.chat(USER)
    assert world["log"] == [("eu", "gemini-a")]
    assert provider.location == "eu"


def test_the_warning_says_what_happened(world, caplog):
    world["failures"][("eu", "gemini-a")] = _error(503)
    with caplog.at_level(logging.WARNING):
        _provider().chat(USER)
    assert "did not answer for gemini-a (ServerError 503)" in caplog.text
    assert "does not serve" not in caplog.text
    assert "Set GOOGLE_CLOUD_LOCATION" in caplog.text


# ── close() ──────────────────────────────────────────────────────────


def test_close_closes_the_client_of_every_location_used(world):
    world["failures"][("eu", "gemini-a")] = _error(404)
    provider = _provider()
    provider.chat(USER)
    assert {c.kwargs["location"] for c in world["clients"]} == {"eu", "global"}

    provider.close()
    assert [c.closed for c in world["clients"]] == [1, 1]
    # Closing twice does not close a client again.
    provider.close()
    assert [c.closed for c in world["clients"]] == [1, 1]


def test_close_closes_the_gemini_api_client(world):
    provider = google_provider.GoogleProvider(
        {"provider": "google", "api_key": "test-key", "model": "gemini-a"}
    )
    provider.close()
    assert [c.closed for c in world["clients"]] == [1]


class _ProviderWithClients:
    """A ProviderClient whose ``raw`` is one of the two clients it closes."""

    def __init__(self):
        self.closed = False
        self.raw = SimpleNamespace(closed=False)
        self.raw.close = lambda: setattr(self.raw, "closed", True)

    def close(self):
        self.closed = True

    def chat(self, messages, **kwargs):
        from gaik.software_components.llm.base import ChatResponse

        return ChatResponse(text="# Parsed", model="m", provider="vertex", usage={})

    def chat_parsed(self, messages, response_format, **kwargs):
        return response_format(name="Ada")


@pytest.mark.parametrize("component", ["parser", "extractor"])
def test_the_components_close_the_provider_not_only_its_last_client(
    monkeypatch, tmp_path, component
):
    import fitz
    from gaik.software_components import llm
    from gaik.software_components.parsers.multimodal_parser import MultimodalParser
    from gaik.software_components.vision_extractor import VisionExtractor
    from pydantic import BaseModel

    class Name(BaseModel):
        name: str

    path = tmp_path / "input.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((20, 20), "First page")
        document.save(path)
    client = _ProviderWithClients()
    monkeypatch.setattr(llm, "create_llm_client", lambda config: client)
    config = {"provider": "vertex", "model": "gemini-a", "project_id": "project"}
    if component == "parser":
        MultimodalParser(api_config=config).parse(path)
    else:
        VisionExtractor(api_config=config)._call_shared([path], "system", "user", Name)
    assert client.closed


# ── The judge's own Vertex path ─────────────────────────────────────


def _judge():
    from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge

    return LLMJudge(model_provider="google", model="gemini-a", max_tokens=64)


def test_the_judge_asks_the_eu_once_for_a_model_it_does_not_serve(world, monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    world["failures"][("eu", "gemini-a")] = _error(404)
    judge = _judge()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            judge._call_google([b"png"], "user", "system")
    assert world["log"] == [("eu", "gemini-a")] + [("global", "gemini-a")] * 3
    # One warning, which says what happened and names the judge's own variable.
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "does not serve gemini-a" in warnings[0]
    assert "Set GOOGLE_VERTEXAI_LOCATION" in warnings[0]
    # The judge keeps its provider: no client is built again per call.
    assert [c.kwargs["location"] for c in world["clients"]] == ["eu", "global"]
    # Another judge in the process does not ask the EU again either.
    world["log"].clear()
    _judge()._call_google([], "user", "system")
    assert world["log"] == [("global", "gemini-a")]


def test_the_judge_sends_its_pages_and_options_through_the_provider(world, monkeypatch):
    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    seen = {}
    original = google_provider.GoogleProvider.chat

    def chat(self, messages, **kwargs):
        seen.update(messages=messages, kwargs=kwargs)
        return original(self, messages, **kwargs)

    monkeypatch.setattr(google_provider.GoogleProvider, "chat", chat)
    text, prompt_tokens, completion_tokens = _judge()._call_google(
        [b"page-1", b"page-2"], "user prompt", "system prompt"
    )
    assert (text, prompt_tokens, completion_tokens) == ("{}", 5, 2)
    system, user = seen["messages"]
    assert system == {"role": "system", "content": "system prompt"}
    assert user["content"][0] == {"type": "text", "text": "user prompt"}
    assert [part["type"] for part in user["content"][1:]] == ["image_url", "image_url"]
    assert seen["kwargs"] == {
        "model": "gemini-a",
        "response_mime_type": "application/json",
        "max_output_tokens": 64,
    }


def test_the_judge_builds_a_new_provider_when_the_location_changes(world, monkeypatch):
    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    judge = _judge()
    judge._call_google([], "user", "system")
    monkeypatch.setenv("GOOGLE_VERTEXAI_LOCATION", "europe-north1")
    judge._call_google([], "user", "system")
    assert [c.kwargs["location"] for c in world["clients"]] == ["eu", "europe-north1"]
    # The replaced provider is not closed: another thread may still be using it.
    assert world["clients"][0].closed == 0


def test_threads_sharing_a_judge_get_one_provider(world, monkeypatch):
    import threading
    import time as real_time

    from gaik.software_components.validators.llm_judge import llm_judge as judge_module

    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    original = google_provider.GoogleProvider.__init__

    def slow_init(self, config):
        real_time.sleep(0.05)  # widen the window in which threads build at once
        original(self, config)

    monkeypatch.setattr(google_provider.GoogleProvider, "__init__", slow_init)
    judge = _judge()
    start = threading.Barrier(8)
    providers = []

    def build():
        start.wait()
        providers.append(judge_module._vertex_provider(judge))

    threads = [threading.Thread(target=build) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {id(provider) for provider in providers} == {id(judge._vertex_provider)}
    # A provider built by a thread that lost the race is closed; the one in use is not.
    published = judge._vertex_provider.raw
    assert published.closed == 0
    assert all(c.closed == 1 for c in world["clients"] if c is not published)


def test_building_a_provider_does_not_hold_up_another_judge(world, monkeypatch):
    import threading

    from gaik.software_components.validators.llm_judge import llm_judge as judge_module

    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    ready = _judge()
    ready_provider = judge_module._vertex_provider(ready)
    building, release = threading.Event(), threading.Event()
    original = google_provider.GoogleProvider.__init__

    def blocking_init(self, config):
        building.set()
        release.wait(5)
        original(self, config)

    monkeypatch.setattr(google_provider.GoogleProvider, "__init__", blocking_init)
    slow = threading.Thread(target=judge_module._vertex_provider, args=(_judge(),))
    slow.start()
    assert building.wait(5)
    found = []
    quick = threading.Thread(target=lambda: found.append(judge_module._vertex_provider(ready)))
    try:
        quick.start()
        quick.join(2)
        # Answered while the other judge's provider is still being built.
        assert found == [ready_provider]
    finally:
        release.set()
        slow.join(5)
        quick.join(5)


# ── The records stay small, and clients are built once ──────────────


@pytest.mark.parametrize(
    ("failure", "record", "lifetime"),
    [
        (_error(404), "_NOT_SERVED", "NOT_SERVED_RETRY_SECONDS"),
        (_error(503), "_UNAVAILABLE_UNTIL", "LOCATION_RETRY_SECONDS"),
    ],
)
def test_an_expired_entry_is_dropped_when_read(world, failure, record, lifetime):
    world["failures"][("eu", "gemini-a")] = failure
    _provider().chat(USER)
    assert ("project", "eu", "gemini-a") in getattr(google_provider, record)

    del world["failures"][("eu", "gemini-a")]
    world["clock"][0] += getattr(google_provider, lifetime) + 1
    _provider().chat(USER)
    assert getattr(google_provider, record) == {}


def test_threads_sharing_a_provider_build_each_client_once(world, monkeypatch):
    import threading
    import time as real_time

    world["failures"][("eu", "gemini-a")] = _error(404)
    provider = _provider()
    assert [c.kwargs["location"] for c in world["clients"]] == ["eu"]
    client_class = google_provider.genai.Client

    def slow_client(**kwargs):
        real_time.sleep(0.05)  # widen the window two unguarded threads would share
        return client_class(**kwargs)

    monkeypatch.setattr(google_provider.genai, "Client", slow_client)
    start = threading.Barrier(8)

    def ask():
        start.wait()
        provider.chat(USER)

    threads = [threading.Thread(target=ask) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [c.kwargs["location"] for c in world["clients"]] == ["eu", "global"]
