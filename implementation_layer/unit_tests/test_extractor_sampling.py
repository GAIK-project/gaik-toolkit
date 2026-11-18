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

The schema generator's own calls also send ``reasoning_effort="none"`` on a model
that accepts it when no effort is set, so their ``temperature=0`` applies (#94).

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
        inst.config = {"model_family": "gpt-6-sol"}
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
        assert captured["config"] == inst.config

    def test_schema_generator_forwards_deployment_family(self, monkeypatch):
        from gaik.software_components.extractor import schema as schema_module

        client = _RecordingClient()
        monkeypatch.setattr(schema_module, "build_compat_client", lambda config: client)
        generator = schema_module.SchemaGenerator(
            {
                "provider": "azure",
                "model": "production",
                "model_family": "gpt-6-astra",
                "reasoning_effort": "high",
                "timeout": 120,
            }
        )
        generator.analyze_structure("Extract an answer")
        assert client.last["model"] == "production"
        assert client.last["reasoning_effort"] == "high"
        assert client.last["timeout"] == 120
        assert "temperature" not in client.last
        assert "top_p" not in client.last

    def test_nested_list_parser_passes_settings_to_item_parser(self, monkeypatch):
        from gaik.software_components.extractor import schema as schema_module

        captured: dict = {}
        analysis = schema_module.StructureAnalysis(
            structure_type="nested_list",
            parent_container_name="inventory_items",
            parent_description="Inventory items",
            item_description="One inventory item",
            reasoning="The document contains repeated structured items.",
        )

        monkeypatch.setattr(
            schema_module,
            "detect_structure_type",
            lambda *args, **kwargs: analysis,
        )

        def fake_parse_user_requirements(*args, **kwargs):
            captured.update(kwargs)
            return _flat_requirements()

        monkeypatch.setattr(
            schema_module,
            "parse_user_requirements",
            fake_parse_user_requirements,
        )

        schema_module.parse_nested_requirements(
            "For each inventory item, extract the answer.",
            client=object(),
            model="gpt-5.6-sol",
            temperature=None,
            reasoning_effort="low",
        )

        assert captured["temperature"] is None
        assert captured["reasoning_effort"] == "low"


class _RecordingProvider:
    """A ``ProviderClient`` that records the options ``chat_parsed`` receives."""

    raw = None

    def __init__(self, provider: str, model: str, config: dict | None = None) -> None:
        self.provider = provider
        self.model = model
        self._config = {"provider": provider, "model": model, **(config or {})}
        self.calls: list[dict] = []

    def chat_parsed(self, messages, response_format, **kwargs):
        from gaik.software_components.llm.parameters import normalize_chat_kwargs

        model = kwargs.pop("model", self.model)
        # What OpenAIProvider.chat_parsed would pass to the SDK.
        self.calls.append(normalize_chat_kwargs(model, kwargs, config=self._config))
        return _parsed_for(response_format)

    def chat(self, messages, **kwargs):
        raise AssertionError("Expected a structured call")

    def chat_stream(self, messages, **kwargs):
        raise AssertionError("Expected a structured call")

    def embed(self, texts, **kwargs):
        raise AssertionError("Expected a structured call")


def _parsed_for(response_format):
    from gaik.software_components.extractor.schema import (
        ExtractionRequirements,
        StructureAnalysis,
    )

    if response_format is ExtractionRequirements:
        return _flat_requirements()
    if response_format is StructureAnalysis:
        return StructureAnalysis(
            structure_type="flat",
            parent_container_name="record",
            parent_description="One record",
            item_description="One record",
            reasoning="Scalar fields only.",
        )
    return _Answer(answer="ok")


class _RecordingSchemaClient(_RecordingClient):
    """Raw-client fake whose parse answers in the requested response format."""

    def __init__(self) -> None:
        super().__init__()
        outer = self

        class _Completions:
            def parse(self, **kwargs):
                outer.calls.append(kwargs)
                message = type("M", (), {"parsed": _parsed_for(kwargs["response_format"])})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice], "usage": None})()

        self.beta = type(
            "Beta", (), {"chat": type("Chat", (), {"completions": _Completions()})()}
        )()


def _sent_by_parse_user_requirements(model: str, config: dict | None = None, **sampling) -> dict:
    """The kwargs the requirements parse sends to the SDK through a raw client."""
    from gaik.software_components.extractor.schema import parse_user_requirements

    client = _RecordingSchemaClient()
    parse_user_requirements(
        "Extract `po_number` and `order_date`.",
        client=client,
        model=model,
        config=config,
        **sampling,
    )
    return client.last


class TestSchemaGenerationIsDeterministicWhereTheModelAllows:
    """Issue #94: with reasoning and free sampling, gpt-6-luna kept only the first field.

    The schema generator asks for ``temperature=0`` by default, but on GPT-6 and GPT-5.6
    the compatibility layer drops the temperature unless ``reasoning_effort="none"``, so
    the default sent neither and the deployment reasoned.
    """

    @pytest.mark.parametrize(
        "model",
        ["gpt-6-luna", "gpt-6-sol", "gpt-6-luna-2026-09-22", "gpt-5.6-sol", "azure/gpt-6-luna"],
    )
    def test_default_sends_effort_none_and_temperature_zero(self, model):
        sent = _sent_by_parse_user_requirements(model)
        assert sent["reasoning_effort"] == "none"
        assert sent["temperature"] == 0.0
        assert sent["top_p"] == 1.0

    def test_deployment_alias_with_model_family(self):
        sent = _sent_by_parse_user_requirements(
            "production", config={"provider": "azure", "model_family": "gpt-6-luna"}
        )
        assert sent["model"] == "production"
        assert (sent["reasoning_effort"], sent["temperature"]) == ("none", 0.0)

    @pytest.mark.parametrize(
        "model", ["gpt-6-astra", "gpt-6.1-sol", "gpt-6.2-sol", "gpt-6-rosalind"]
    )
    def test_model_that_rejects_none_gets_no_effort(self, model):
        # "none" would be refused; these reason, so the temperature is dropped as
        # before. gpt-6-rosalind is a GPT-6 name outside the allowlist.
        sent = _sent_by_parse_user_requirements(model)
        assert "reasoning_effort" not in sent
        assert "temperature" not in sent
        assert "top_p" not in sent

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-5.4", "my-deployment", "o3"])
    def test_other_models_unchanged(self, model):
        # A deployment alias without model_family is not recognised either.
        sent = _sent_by_parse_user_requirements(model)
        assert "reasoning_effort" not in sent
        assert sent["temperature"] == 0.0

    @pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
    def test_caller_effort_wins(self, effort):
        sent = _sent_by_parse_user_requirements(
            "gpt-6-luna", temperature=None, reasoning_effort=effort
        )
        assert sent["reasoning_effort"] == effort
        assert "temperature" not in sent

    def test_caller_effort_wins_even_with_a_temperature(self):
        # The compatibility layer still drops the temperature an active effort cannot take.
        sent = _sent_by_parse_user_requirements("gpt-6-luna", reasoning_effort="low")
        assert sent["reasoning_effort"] == "low"
        assert "temperature" not in sent

    def test_config_effort_wins(self):
        sent = _sent_by_parse_user_requirements(
            "gpt-6-luna", config={"provider": "azure", "reasoning_effort": "medium"}
        )
        assert sent["reasoning_effort"] == "medium"
        assert "temperature" not in sent

    def test_caller_temperature_wins(self):
        sent = _sent_by_parse_user_requirements("gpt-6-luna", temperature=0.3)
        assert (sent["reasoning_effort"], sent["temperature"]) == ("none", 0.3)

    def test_temperature_none_leaves_the_model_default(self):
        sent = _sent_by_parse_user_requirements("gpt-6-luna", temperature=None)
        assert "reasoning_effort" not in sent
        assert "temperature" not in sent

    def test_explicit_none_effort_is_kept(self):
        sent = _sent_by_parse_user_requirements("gpt-6-luna", reasoning_effort="none")
        assert (sent["reasoning_effort"], sent["temperature"]) == ("none", 0.0)

    def test_every_requirements_parse_gets_it_but_structure_detection_does_not(self, monkeypatch):
        """The parent and child parses from the class; detection keeps the model default.

        At effort "none" the structure detector often ignored the list name a task gave,
        so it is left as it was.
        """
        from gaik.software_components.extractor import schema as schema_module

        client = _RecordingSchemaClient()
        monkeypatch.setattr(schema_module, "build_compat_client", lambda config: client)
        analysis = schema_module.StructureAnalysis(
            structure_type="parent_with_nested_list",
            parent_container_name="purchase_order",
            parent_description="One purchase order",
            item_description="One order line",
            reasoning="A header with repeated lines.",
            child_containers=[
                schema_module.ChildContainerSpec(
                    container_name="line_items", container_description="Order lines"
                )
            ],
        )
        real_parse = client.beta.chat.completions.parse

        def parse(**kwargs):
            if kwargs["response_format"] is schema_module.StructureAnalysis:
                client.calls.append(kwargs)
                message = type("M", (), {"parsed": analysis})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice], "usage": None})()
            return real_parse(**kwargs)

        client.beta.chat.completions.parse = parse
        generator = schema_module.SchemaGenerator(
            {"provider": "azure", "api_key": "test", "model": "gpt-6-luna"}
        )
        generator.generate_schema_with_usage("Extract `po_number`; for each line `sku`.")

        formats = [call["response_format"].__name__ for call in client.calls]
        assert formats == ["StructureAnalysis", "ExtractionRequirements", "ExtractionRequirements"]
        detection, *parses = client.calls
        assert "reasoning_effort" not in detection
        assert "temperature" not in detection
        for call in parses:
            assert (call["reasoning_effort"], call["temperature"]) == ("none", 0.0)

    def test_structure_detection_still_takes_a_caller_effort(self):
        from gaik.software_components.extractor.schema import detect_structure_type

        client = _RecordingSchemaClient()
        detect_structure_type(
            "Extract `po_number`.", client=client, model="gpt-6-luna", reasoning_effort="none"
        )
        assert (client.last["reasoning_effort"], client.last["temperature"]) == ("none", 0.0)

    @pytest.mark.parametrize("provider", ["openai_compatible", "aitta", "litellm"])
    def test_provider_adapter_gets_it_for_a_gpt6_model(self, provider):
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider(provider, "gpt-6-luna")
        parse_user_requirements("Extract `po_number`.", client=client, model="gpt-6-luna")
        assert client.calls[0] == {"temperature": 0.0, "reasoning_effort": "none"}

    @pytest.mark.parametrize(
        ("model", "config"),
        [
            ("azure/gpt-6-luna-prod", {"model_family": "gpt-6-luna"}),
            ("openai/gpt-6-rosalind", None),
            ("azure/gpt-6-luna", {"model_family": "gpt-6-astra"}),
        ],
    )
    def test_litellm_gets_no_none_unless_route_and_family_accept_it(self, model, config):
        # LiteLLM checks "none" against the routed name and gaik against model_family;
        # either refusal stops the request, so the parse sends no effort, as before.
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider("litellm", model, config)
        parse_user_requirements("Extract `po_number`.", client=client, model=model)
        assert "reasoning_effort" not in client.calls[0]

    def test_litellm_gets_none_when_route_and_family_accept_it(self):
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider("litellm", "azure/gpt-6-luna", {"model_family": "gpt-6-luna"})
        parse_user_requirements("Extract `po_number`.", client=client, model="azure/gpt-6-luna")
        assert client.calls[0] == {"temperature": 0.0, "reasoning_effort": "none"}

    def test_adapter_effort_wins_over_a_passed_config_without_one(self):
        # The adapter sends with its own config, so its effort is the one that counts.
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider("aitta", "gpt-6-luna", {"reasoning_effort": "high"})
        parse_user_requirements(
            "Extract `po_number`.",
            client=client,
            model="gpt-6-luna",
            config={"provider": "aitta", "reasoning_effort": None},
        )
        assert client.calls[0] == {"reasoning_effort": "high"}

    def test_provider_adapter_config_effort_wins(self):
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider("aitta", "gpt-6-luna", {"reasoning_effort": "high"})
        parse_user_requirements("Extract `po_number`.", client=client, model="gpt-6-luna")
        assert client.calls[0] == {"reasoning_effort": "high"}

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("aitta", "google/gemma-4-31b-it"),
            ("anthropic", "claude-sonnet-5-5"),
            ("google", "gemini-2.5-flash"),
        ],
    )
    def test_other_providers_unchanged(self, provider, model):
        from gaik.software_components.extractor.schema import parse_user_requirements

        client = _RecordingProvider(provider, model)
        parse_user_requirements("Extract `po_number`.", client=client, model=model)
        assert client.calls[0] == {"temperature": 0.0}

    def test_data_extractor_is_unchanged(self, monkeypatch):
        """The change is the schema generator's: DataExtractor still sends no effort."""
        from gaik.software_components.extractor import extractor as extractor_module

        client = _RecordingSchemaClient()
        monkeypatch.setattr(extractor_module, "build_compat_client", lambda config: client)
        extractor = extractor_module.DataExtractor(
            {"provider": "azure", "api_key": "test", "model": "gpt-6-luna"}
        )
        extractor._extract_one(
            doc="doc",
            extraction_model=_Answer,
            requirements=_flat_requirements(),
            user_requirements="extract the answer",
        )
        assert "reasoning_effort" not in client.last
        assert "temperature" not in client.last


@pytest.mark.parametrize(
    ("returned", "field"),
    [
        ("", "records"),
        ("Upcoming events!", "upcoming_events"),
        ("2026 events", "records_2026_events"),
    ],
)
def test_nested_list_container_name_is_a_usable_field_name(monkeypatch, returned, field):
    # The structure detector's container name is free text from the model. An empty
    # one used to become a field called "", whose records no caller could address.
    from gaik.software_components.extractor import schema as schema_module

    analysis = schema_module.StructureAnalysis(
        structure_type="nested_list",
        parent_container_name=returned,
        parent_description="Events on the pages",
        item_description="One event",
        reasoning="Repeated events.",
    )
    monkeypatch.setattr(schema_module, "detect_structure_type", lambda *a, **k: analysis)
    monkeypatch.setattr(
        schema_module, "parse_user_requirements", lambda *a, **k: _flat_requirements()
    )

    model, _, returned_analysis = schema_module.parse_nested_requirements(
        "List the events.", client=object(), model="gpt-6-luna"
    )

    assert list(model.model_fields) == [field]
    assert returned_analysis.parent_container_name == field
    assert model.model_validate({field: [{"answer": "x"}]})


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
