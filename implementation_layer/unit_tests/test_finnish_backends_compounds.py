"""spaCy keeps hyphenated tokens, and native Voikko splits inflected compounds."""

import sys
import types

import pytest
from gaik.software_components.RAG.finnish_text_processor import backends
from gaik.software_components.RAG.finnish_text_processor.backends import (
    SpacyBackend,
    VoikkoBackend,
)

# Voikko's STRUCTURE has one character per written character; "=" opens a part.
_ANALYSES = {
    "kerrostaloissa": {"BASEFORM": "kerrostalo", "STRUCTURE": "=pppppp=pppppppp"},
    "kerrostalo": {"BASEFORM": "kerrostalo", "STRUCTURE": "=pppppp=pppp"},
    "kissa": {"BASEFORM": "kissa", "STRUCTURE": "=ppppp"},
}


class _FakeVoikko:
    def __init__(self, language):
        pass

    def analyze(self, token):
        found = _ANALYSES.get(token.lower())
        return [dict(found)] if found else []


@pytest.fixture
def voikko(monkeypatch):
    module = types.ModuleType("libvoikko")
    module.Voikko = _FakeVoikko
    monkeypatch.setitem(sys.modules, "libvoikko", module)
    return VoikkoBackend()


def test_an_inflected_compound_splits_like_its_baseform(voikko):
    assert voikko.lemmatize("kerrostaloissa") == ["kerros", "talo"]
    assert voikko.lemmatize("kerrostalo") == ["kerros", "talo"]


def test_a_simple_word_keeps_its_baseform(voikko):
    assert voikko.lemmatize("kissa") == ["kissa"]


def test_a_structure_that_does_not_fit_the_written_word_is_not_split():
    assert backends._split_on_structure("kerrostalo", "=ppp=pp", "kerrostaloissa") == []


def test_spacy_keeps_hyphenated_and_mixed_tokens():
    spacy = pytest.importorskip("spacy")
    backend = SpacyBackend.__new__(SpacyBackend)
    backend._nlp = spacy.blank("fi")
    backend._stopwords = backends.DEFAULT_FINNISH_STOPWORDS

    lemmas = backend.lemmatize("Y-tunnus e-lasku 5G-verkossa COVID-19 kissa")

    assert lemmas == ["y-tunnus", "e-lasku", "5g-verkossa", "covid-19", "kissa"]
