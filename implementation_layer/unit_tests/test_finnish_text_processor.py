"""FinnishTextProcessor: tsquery rendering, compound splitting, backend honesty.

The compound tests are the ones worth keeping. Compound splitting was previously
implemented by splitting ``BASEFORM`` on ``"+"`` — a string Voikko never produces
— so the feature reported itself as available and then split nothing, on every
word, silently. A test that only asserted ``supports_compound_splitting is True``
would have passed throughout.
"""

from __future__ import annotations

import pytest
from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor
from gaik.software_components.RAG.finnish_text_processor.backends import (
    _split_on_structure,
)

pyvoikko = pytest.importorskip("pyvoikko", reason="needs gaik[finnish-rag]")


@pytest.fixture(scope="module")
def processor() -> FinnishTextProcessor:
    return FinnishTextProcessor(backend="pyvoikko", decompound=False)


@pytest.fixture(scope="module")
def splitter() -> FinnishTextProcessor:
    return FinnishTextProcessor(backend="pyvoikko", decompound=True)


class TestTsQuery:
    def test_lemmas_are_joined_with_or_by_default(self, processor):
        # OR, not AND: conjoining every term means a long question only matches a
        # passage containing all of them, which on real prose is never.
        assert processor.to_tsquery("tilinpäätöksen korjaaminen") == "tilinpäätös | korjata"

    def test_and_is_available_for_callers_that_want_it(self, processor):
        assert processor.to_tsquery("tilinpäätöksen korjaaminen", operator="&") == (
            "tilinpäätös & korjata"
        )

    def test_an_unsupported_operator_is_refused_rather_than_interpolated(self, processor):
        with pytest.raises(ValueError, match="operator must be"):
            processor.to_tsquery("tilinpäätös", operator="!")

    def test_tsquery_syntax_in_user_input_is_stripped(self, processor):
        """A query is user input, and `to_tsquery` raises on stray syntax.

        Anything that reaches the parser as an operator turns a search into a
        500, so the metacharacters go before the terms are joined.
        """
        rendered = processor.to_tsquery("alv & (foo | bar):* !baz 'x'")
        assert not set(rendered) & set("&()!*'")
        assert "alv" in rendered

    def test_prefix_mode_marks_every_term(self, processor):
        assert processor.to_tsquery("tilinpäätöksen", prefix=True) == "tilinpäätös:*"

    def test_a_query_of_only_stopwords_renders_empty(self, processor):
        """Not the same as empty input, and the caller has to tell them apart.

        `to_tsquery('')` raises in Postgres, so "" has to mean *no keyword arm*
        rather than being passed through.
        """
        assert processor.to_tsquery("ja tai kun") == ""
        assert processor.to_tsquery("") == ""


class TestCompoundSplitting:
    def test_compounds_split_into_words_a_searcher_would_use(self, splitter):
        assert splitter.lemmatize("vähennysoikeus") == ["vähennys", "oikeus"]
        assert splitter.lemmatize("kerrostalon") == ["kerros", "talo"]

    def test_splitting_does_not_fall_back_to_derivational_roots(self, splitter):
        """`WORDBASES` would give `vähetä` + `oikea` — a verb and an adjective.

        Those are morphologically correct and useless for retrieval, which is why
        the split comes from the compound structure instead.
        """
        parts = splitter.lemmatize("vähennysoikeus")
        assert "vähetä" not in parts and "oikea" not in parts

    def test_decompound_false_keeps_the_whole_baseform(self, processor):
        assert processor.lemmatize("vähennysoikeus") == ["vähennysoikeus"]

    def test_both_sides_agree_on_an_inflected_compound(self, processor):
        """The property the whole component exists for.

        Postgres' Finnish snowball stems `tilinpäätös` and `tilinpäätöksen` to two
        different lexemes, so one does not find the other. Lemmatizing both sides
        is what closes that gap.
        """
        indexed = processor.to_tsvector_text("Vahvistetun tilinpäätöksen korjaaminen")
        assert "tilinpäätös" in indexed.split()
        assert processor.to_tsquery("tilinpäätös") == "tilinpäätös"


class TestStructureSplitting:
    def test_a_non_compound_yields_no_parts(self):
        assert _split_on_structure("kissa", "=ppppp") == []

    def test_a_structure_that_does_not_cover_the_word_is_rejected(self):
        """A short structure would otherwise return a silently truncated word."""
        assert _split_on_structure("arvonlisäverotus", "=ppp=ppp") == []

    def test_missing_structure_is_not_an_error(self):
        assert _split_on_structure("kissa", None) == []


class TestBackendHonesty:
    def test_the_active_backend_is_reported_not_the_requested_one(self, processor):
        # A caller has to be able to refuse `simple`, which is a tokenizer rather
        # than a lemmatizer and makes content *less* searchable, not more.
        assert processor.backend_name == "pyvoikko"
        assert processor.requested_backend == "pyvoikko"

    def test_simple_backend_admits_it_cannot_split_compounds(self):
        simple = FinnishTextProcessor(backend="simple")
        assert simple.backend_name == "simple"
        assert simple.supports_compound_splitting is False

    def test_an_unknown_backend_name_is_refused(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            FinnishTextProcessor(backend="klingon")  # type: ignore[arg-type]
