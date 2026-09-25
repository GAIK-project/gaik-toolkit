"""Provider routing keeps label validation identical across SDKs."""

from types import SimpleNamespace

import pytest
from gaik.software_components.form_understander import FormUnderstander
from gaik.software_components.form_understander.understander import LabelMapping


class _Provider:
    provider = "google"
    model = "configured-model"
    raw = None

    def __init__(self):
        self.calls = []

    def chat_parsed(self, **kwargs):
        self.calls.append(kwargs)
        return LabelMapping.model_validate(
            {
                "entries": [
                    {"id": "known", "label": "  Etunimi  "},
                    {"id": "other", "label": "x" * 90},
                    {"id": "invented", "label": "Drop this"},
                    {"id": "empty", "label": "  "},
                ]
            }
        )

    def chat(self, *args, **kwargs):
        raise AssertionError("Expected structured output")

    def chat_stream(self, *args, **kwargs):
        raise AssertionError("Expected structured output")

    def embed(self, *args, **kwargs):
        raise AssertionError("Expected structured output")


@pytest.mark.parametrize("provider", ["google", "anthropic", "aitta", "openai_compatible"])
def test_form_routes_provider_and_preserves_label_contract(monkeypatch, provider):
    from gaik.software_components.llm import factory

    client = _Provider()
    client.provider = provider
    monkeypatch.setattr(factory, "create_llm_client", lambda config: client)
    form = FormUnderstander({"provider": provider, "model": "configured-model"})
    result = form.clean_labels(
        [{"id": key, "raw": "cryptic"} for key in ("known", "other", "empty")],
        language_hint="fi",
    )
    assert result == {"known": "Etunimi", "other": "x" * 60}
    assert client.calls[0]["model"] == "configured-model"
    assert client.calls[0]["response_format"] is LabelMapping
    assert "Output language hint: fi" in client.calls[0]["messages"][1]["content"]
    assert "timeout" not in client.calls[0]


def test_legacy_form_client_remains_supported(monkeypatch):
    from gaik.software_components.form_understander import understander

    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        mapping = LabelMapping.model_validate({"entries": [{"id": "a", "label": "Name"}]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=mapping))])

    raw = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )
    monkeypatch.setattr(understander, "build_compat_client", lambda config: raw)
    form = FormUnderstander({"use_azure": False, "model": "legacy"})
    assert form.clean_labels([{"id": "a", "raw": "Name:"}]) == {"a": "Name"}
    assert captured["timeout"] == 30


def test_empty_form_does_not_call_provider(monkeypatch):
    from gaik.software_components.llm import factory

    client = _Provider()
    monkeypatch.setattr(factory, "create_llm_client", lambda config: client)
    form = FormUnderstander({"provider": "google", "model": "configured-model"})
    assert form.clean_labels([]) == {}
    assert client.calls == []
