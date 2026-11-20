"""The reasoning effort picked in the model menu reaches GPT-6 models only."""

from __future__ import annotations

import json

import httpx
import pytest
from api.utils import model_settings as settings
from api.utils.config import get_model_options
from fastapi import FastAPI

EFFORT = settings.EFFORT_HEADER.decode()
OWN_KEY = settings.HEADER.decode()


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)

    def options(provider: str, model: str) -> dict:
        # An own key names its own model, as get_request_api_config does.
        own = settings.request_model_settings()
        if own is not None:
            provider, model = own.provider, own.model
        return get_model_options({"provider": provider, "model": model})

    # A route that takes a picked model, and one that does not.
    app.post("/extract")(options)
    app.post("/tabular-agent/ask")(options)
    return app


async def _effort(headers: dict | list, model: str, provider="azure", path="/extract"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            path, params={"provider": provider, "model": model}, headers=headers
        )
    assert response.status_code == 200
    return response.json()["reasoning_effort"]


@pytest.mark.parametrize("value", [b"low", b"medium", b"high"])
def test_the_header_names_one_of_three_efforts(value):
    assert settings.parse_reasoning_effort([value]) == value.decode()


@pytest.mark.parametrize(
    "values",
    [
        [],
        [b""],
        [b"none"],
        [b"minimal"],
        [b"xhigh"],
        [b"High"],
        [b"low,high"],
        [b"\xff"],
        [b"low", b"high"],
        [b"high", b"high"],
    ],
)
def test_any_other_header_means_auto(values):
    assert settings.parse_reasoning_effort(values) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra", "gpt-6.2-sol"])
@pytest.mark.parametrize("effort", ["low", "medium", "high"])
async def test_a_picked_effort_replaces_the_gpt6_default(model, effort):
    assert await _effort({EFFORT: effort}, model) == effort
    # The choice lasts for its own request only.
    assert settings.request_reasoning_effort() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,auto",
    [("gpt-6-sol", "none"), ("gpt-6-astra", "low"), ("gpt-6.2-sol", "medium")],
)
async def test_auto_and_an_invalid_value_keep_the_model_default(model, auto):
    assert await _effort({}, model) == auto
    for invalid in ("none", "minimal", "HIGH", "max", "low, high"):
        assert await _effort({EFFORT: invalid}, model) == auto
    # A repeated header is not a choice either.
    assert await _effort([(EFFORT, "high"), (EFFORT, "high")], model) == auto


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,model",
    [
        ("anthropic_foundry", "claude-sonnet-5-5"),
        ("vertex", "gemini-3.8-flash"),
        ("aitta", "openai/gpt-oss-120b"),
    ],
)
async def test_other_models_ignore_the_picked_effort(provider, model):
    assert await _effort({EFFORT: "high"}, model, provider) is None


@pytest.mark.asyncio
async def test_an_older_gpt_model_keeps_its_own_effort():
    assert await _effort({EFFORT: "high"}, "gpt-4o") == "medium"


@pytest.mark.asyncio
async def test_a_route_that_takes_no_picked_model_ignores_the_header():
    assert await _effort({EFFORT: "high"}, "gpt-6-sol", path="/tabular-agent/ask") == "none"


@pytest.mark.asyncio
async def test_the_picked_effort_applies_to_an_own_key_gpt6_model():
    def own_key(model: str) -> dict:
        return {
            OWN_KEY: json.dumps({"provider": "openai", "model": model, "apiKey": "test-key"}),
            EFFORT: "high",
        }

    assert await _effort(own_key("gpt-6-sol"), "ignored") == "high"
    assert await _effort(own_key("gpt-5.6-terra"), "ignored") is None
