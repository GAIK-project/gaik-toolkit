"""Tests for model-specific VisionParser request options."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

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
