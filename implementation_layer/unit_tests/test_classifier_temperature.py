"""DocumentClassifier's temperature can be left out for a model that refuses one (#146 item 12)."""

from types import SimpleNamespace

import pytest
from gaik.software_components.doc_classifier import classifier as module


def _classifier(monkeypatch, **options):
    calls = []

    class Completions:
        def parse(self, **kwargs):
            calls.append(kwargs)
            parsed = kwargs["response_format"](
                document_class="invoice", confidence=0.9, reasoning="ok"
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
            )

    client = SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(module, "build_compat_client", lambda config: client)
    classifier = module.DocumentClassifier({"model": "gpt-4.1"}, **options)
    return classifier, calls


def _classify(classifier):
    return classifier._classify_with_llm("Invoice 12", ["invoice", "receipt", "unknown"])


def test_the_default_temperature_is_zero(monkeypatch):
    classifier, calls = _classifier(monkeypatch)
    assert _classify(classifier)["class"] == "invoice"
    assert calls[0]["temperature"] == 0


def test_none_leaves_the_temperature_out(monkeypatch):
    classifier, calls = _classifier(monkeypatch, temperature=None)
    assert _classify(classifier)["class"] == "invoice"
    assert "temperature" not in calls[0]


@pytest.mark.parametrize("temperature", [0.3, 1.0])
def test_a_temperature_is_sent_as_given(monkeypatch, temperature):
    classifier, calls = _classifier(monkeypatch, temperature=temperature)
    _classify(classifier)
    assert calls[0]["temperature"] == temperature


def test_the_solution_wizard_knows_every_constructor_option():
    """The registry and the card list each keyword, so the wizard can set temperature=None."""
    import inspect
    import json
    from pathlib import Path

    registries = Path(__file__).resolve().parents[1] / "solution_wizard" / "registries"
    registry = json.loads((registries / "gaik_component_registry.json").read_text("utf-8"))
    cards = json.loads((registries / "component_reference_cards.json").read_text("utf-8"))
    entry = next(c for c in registry if c["name"] == "DocumentClassifier")
    card_options = {o["name"]: o for o in cards["DocumentClassifier"]["options"]}

    keywords = set(inspect.signature(module.DocumentClassifier.__init__).parameters)
    keywords -= {"self"}
    assert keywords <= set(entry["optional_parameters"]) | {"config"}
    assert keywords <= set(card_options)
    assert card_options["temperature"]["default"] == 0.0
