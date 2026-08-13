"""Unit tests for how the extractor sends ``temperature`` and ``reasoning_effort``.

Every structured-output call in this component went through ``_parse_with``
with a hardcoded ``temperature=0``. That is the right default — the same
requirements should produce the same schema, and the same document the same
record — but it made the gpt-5.x reasoning deployments unusable:

    Unsupported value: 'temperature' does not support 0 with this model.
    Only the default (1) value is supported.

The two settings are coupled, which is why they are resolved as a pair rather
than independently: such a deployment accepts an explicit temperature *only*
while reasoning effort is ``"none"``. With an active effort the temperature has
to be omitted, and on the older non-reasoning models the effort has to be
omitted instead — they reject the parameter.

No network: a fake client records the kwargs ``_parse_with`` would have sent.
"""

from __future__ import annotations

import pytest
from gaik.software_components.extractor.schema import _parse_with, _sampling_kwargs
from pydantic import BaseModel


class _Answer(BaseModel):
    answer: str


class _RecordingClient:
    """Captures the kwargs of the one ``parse`` call ``_parse_with`` makes."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def parse(self, **kwargs):
                outer.calls.append(kwargs)
                parsed = _Answer(answer="ok")
                message = type("M", (), {"parsed": parsed})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice], "usage": None})()

        self.beta = type(
            "Beta", (), {"chat": type("Chat", (), {"completions": _Completions()})()}
        )()

    @property
    def last(self) -> dict:
        return self.calls[-1]


def _call(**sampling) -> dict:
    client = _RecordingClient()
    _parse_with(
        client=client,
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        response_format=_Answer,
        **sampling,
    )
    return client.last


class TestSamplingKwargs:
    def test_both_present(self):
        assert _sampling_kwargs(0.0, "none") == {"temperature": 0.0, "reasoning_effort": "none"}

    def test_temperature_only(self):
        assert _sampling_kwargs(0.0, None) == {"temperature": 0.0}

    def test_effort_only(self):
        assert _sampling_kwargs(None, "medium") == {"reasoning_effort": "medium"}

    def test_neither(self):
        assert _sampling_kwargs(None, None) == {}

    def test_none_is_omitted_not_sent_as_null(self):
        """The API rejects ``null``; the parameter has to be absent entirely."""
        assert "temperature" not in _sampling_kwargs(None, "low")
        assert "reasoning_effort" not in _sampling_kwargs(0.0, None)


class TestParseWithDefaults:
    def test_default_is_unchanged(self):
        """Deterministic and no effort — what the non-reasoning models require."""
        sent = _call()
        assert sent["temperature"] == 0.0
        assert sent["top_p"] == 1.0
        assert "reasoning_effort" not in sent

    def test_effort_none_keeps_determinism(self):
        sent = _call(temperature=0.0, reasoning_effort="none")
        assert sent["temperature"] == 0.0
        assert sent["reasoning_effort"] == "none"

    def test_active_effort_omits_temperature(self):
        sent = _call(temperature=None, reasoning_effort="high")
        assert "temperature" not in sent
        assert sent["reasoning_effort"] == "high"

    def test_top_p_and_timeout_always_sent(self):
        for sampling in ({}, {"temperature": None, "reasoning_effort": "low"}):
            sent = _call(**sampling)
            assert sent["top_p"] == 1.0
            assert sent["timeout"] == 30


class TestComponentsForwardTheirSettings:
    """The two public classes must pass their own settings down to the call."""

    def test_extractor_defaults_and_overrides(self):
        from gaik.software_components.extractor.extractor import DataExtractor

        assert _signature_default(DataExtractor, "temperature") == 0.0
        assert _signature_default(DataExtractor, "reasoning_effort") is None

    def test_schema_generator_defaults(self):
        from gaik.software_components.extractor.schema import SchemaGenerator

        assert _signature_default(SchemaGenerator, "temperature") == 0.0
        assert _signature_default(SchemaGenerator, "reasoning_effort") is None

    def test_extractor_passes_settings_through(self, monkeypatch):
        from gaik.software_components.extractor import extractor as extractor_module

        captured: dict = {}

        def fake_parse_with(**kwargs):
            captured.update(kwargs)
            parsed = type("P", (), {"model_dump": lambda self: {"answer": "ok"}})()
            message = type("M", (), {"parsed": parsed})()
            choice = type("C", (), {"message": message})()
            return type("R", (), {"choices": [choice], "usage": None})()

        monkeypatch.setattr(extractor_module, "_parse_with", fake_parse_with)

        inst = extractor_module.DataExtractor.__new__(extractor_module.DataExtractor)
        inst.client = object()
        inst.model = "test-model"
        inst.temperature = None
        inst.reasoning_effort = "medium"

        requirements = _flat_requirements()
        inst._extract_one(
            doc="doc",
            extraction_model=_Answer,
            requirements=requirements,
            user_requirements="extract the answer",
        )
        assert captured["temperature"] is None
        assert captured["reasoning_effort"] == "medium"


def _signature_default(cls, name: str):
    import inspect

    return inspect.signature(cls.__init__).parameters[name].default


def _flat_requirements():
    from gaik.software_components.extractor.schema import ExtractionRequirements, FieldSpec

    return ExtractionRequirements(
        use_case_name="answers",
        fields=[FieldSpec(field_name="answer", field_type="str", description="the answer")],
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
