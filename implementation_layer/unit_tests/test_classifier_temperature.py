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
