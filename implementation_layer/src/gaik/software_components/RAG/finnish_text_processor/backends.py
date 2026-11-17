"""Backend implementations for FinnishTextProcessor.

Each backend implements :class:`LemmatizationBackend` — a tiny ABC with one
method, ``lemmatize(text) -> list[str]``. The ``auto`` strategy in
:class:`gaik.software_components.RAG.finnish_text_processor.processor.FinnishTextProcessor`
tries them in order and uses the first one that imports cleanly.

Order chosen for accuracy vs. install cost:

1. ``VoikkoBackend`` — Finnish morphology + compound splitting via the
   ``libvoikko`` system library and the ``libvoikko`` Python binding.
2. ``PyVoikkoBackend`` — the same morphology as a pure-Python FST, no system
   library at all. Measured identical to :class:`VoikkoBackend` on inflected
   domain compounds, so it sits second only because it is slower per token.
3. ``SpacyBackend`` — lemmatization via ``fi_core_news_md`` / ``lg``;
   ~100-700 MB model download but pure-pip otherwise. Weaker than either Voikko
   on long compounds: measured leaving ``kirjanpitovelvollisuutta`` and
   ``kolmikantakaupassa`` uninflected, and rendering ``kirjanpitolaissa`` as
   ``kirjanpitolati``.
4. ``UralicNLPBackend`` — pure-Python, no system deps; morphology smaller but
   handles inflection.
5. ``SimpleBackend`` — last-resort regex-tokenizer + lowercase. No real
   lemmatization; ensures the pipeline never crashes when nothing else is
   installed.

**Compound splitting comes from the analyser's compound structure, never from
``BASEFORM``.** Voikko does not join compound parts with ``+`` in ``BASEFORM`` —
it returns the whole baseform — so splitting that string finds nothing to split,
whatever the word. ``WORDBASES`` is not the answer either: its bases are
*derivational* roots, so ``vähennysoikeus`` comes back as ``vähetä`` + ``oikea``
and ``arvonlisäverotus`` as ``arvo`` + ``lisä`` + ``verottaa`` — verbs and
adjectives nobody searches for. ``STRUCTURE`` marks the real boundaries and
yields ``vähennys`` + ``oikeus``, which is what a searcher means.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .normalize import (
    DEFAULT_FINNISH_STOPWORDS,
    normalize_unicode,
    remove_stopwords,
    tokenize,
)

logger = logging.getLogger(__name__)


class LemmatizationBackend(ABC):
    """Single-method backend interface."""

    name: str = "unknown"
    supports_compound_splitting: bool = False

    @abstractmethod
    def lemmatize(self, text: str) -> list[str]:
        """Return a list of lemma tokens for *text*."""


class SimpleBackend(LemmatizationBackend):
    """Regex-tokenizer + lowercase + (optional) stopword removal.

    Always available — no extra deps. NOT a real lemmatizer; serves as a
    fallback so :class:`FinnishTextProcessor` never crashes.
    """

    name = "simple"
    supports_compound_splitting = False

    def __init__(self, stopwords: frozenset[str] | set[str] | None = None) -> None:
        self.stopwords = (
            frozenset(stopwords) if stopwords is not None else DEFAULT_FINNISH_STOPWORDS
        )

    def lemmatize(self, text: str) -> list[str]:
        tokens = [t.lower() for t in tokenize(normalize_unicode(text))]
        return remove_stopwords(tokens, self.stopwords)


class UralicNLPBackend(LemmatizationBackend):
    """Pure-Python lemmatizer via ``uralicNLP``.

    Auto-downloads the Finnish model on first use. Smaller morphology than
    Voikko but no system-library prerequisite.
    """

    name = "uralic"
    supports_compound_splitting = False

    def __init__(self, language: str = "fin") -> None:
        try:
            from uralicNLP import uralicApi  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import error path
            raise ImportError(
                "UralicNLPBackend requires uralicNLP. Install with: pip install gaik[finnish-rag]"
            ) from exc
        # Ensure the Finnish model is downloaded (no-op if already present).
        try:
            if not uralicApi.is_language_installed(language):
                uralicApi.download(language)
        except Exception:  # pragma: no cover - network/IO best-effort
            logger.debug("uralicNLP language download skipped or failed", exc_info=True)
        self._uralic = uralicApi
        self._language = language
        self._stopwords = DEFAULT_FINNISH_STOPWORDS

    def lemmatize(self, text: str) -> list[str]:
        tokens = tokenize(normalize_unicode(text))
        out: list[str] = []
        for token in tokens:
            lemmas = self._uralic.lemmatize(token, self._language)
            chosen = lemmas[0].lower() if lemmas else token.lower()
            if chosen not in self._stopwords:
                out.append(chosen)
        return out


class SpacyBackend(LemmatizationBackend):
    """spaCy-based lemmatizer using ``fi_core_news_*`` models.

    Requires the model to be installed separately:

    .. code-block:: shell

        python -m spacy download fi_core_news_md
    """

    name = "spacy"
    supports_compound_splitting = False

    def __init__(self, model: str = "fi_core_news_md") -> None:
        try:
            import spacy  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import error path
            raise ImportError(
                "SpacyBackend requires spacy. Install with: pip install gaik[finnish-rag]"
            ) from exc
        try:
            self._nlp = spacy.load(model, disable=["parser", "ner"])
        except OSError as exc:
            raise ImportError(
                f"spaCy model '{model}' is not installed. Run: python -m spacy download {model}"
            ) from exc
        self._stopwords = DEFAULT_FINNISH_STOPWORDS

    def lemmatize(self, text: str) -> list[str]:
        doc = self._nlp(normalize_unicode(text))
        out: list[str] = []
        for tok in doc:
            # Keep any token with a letter or digit: spaCy's Finnish tokenizer
            # keeps "Y-tunnus", "5G-verkossa" and "COVID-19" whole, and those are
            # neither alphabetic nor number-like.
            if tok.is_space or tok.is_punct or not any(ch.isalnum() for ch in tok.text):
                continue
            lemma = (tok.lemma_ or tok.text).lower()
            if lemma and lemma not in self._stopwords:
                out.append(lemma)
        return out


def _split_on_structure(
    baseform: str, structure: str | None, written: str | None = None
) -> list[str]:
    """Split a compound into parts on the ``=`` boundaries in *structure*.

    Voikko's ``STRUCTURE`` maps the characters of the word as written, where
    ``=`` opens each compound part: ``=pppppp=pppppppp`` over ``kerrostaloissa``
    marks ``kerros`` / ``taloissa``. When *written* is given, the written word is
    sliced and the last part is taken from *baseform* past the same prefix, so
    ``kerrostaloissa`` (baseform ``kerrostalo``) gives ``kerros`` / ``talo``, the
    same parts as the query ``kerrostalo``. Without *written*, *baseform* itself
    is sliced. Returns ``[]`` when the word is not a compound or the structure
    does not line up, so the caller can fall back to the baseform.
    """
    if not structure or structure.count("=") < 2:
        return []
    if written is not None:
        return _split_written(baseform, structure, written)
    parts: list[str] = []
    position = 0
    for segment in structure.split("=")[1:]:
        length = len(segment)
        piece = baseform[position : position + length]
        position += length
        if piece:
            parts.append(piece)
    # A structure that does not line up with the baseform (derived forms shift the
    # character count) would silently produce truncated nonsense.
    return parts if position == len(baseform) else []


def _split_written(baseform: str, structure: str, written: str) -> list[str]:
    segments = [len(segment) for segment in structure.split("=")[1:]]
    if sum(segments) != len(written):
        return []
    pieces: list[str] = []
    position = 0
    for length in segments:
        pieces.append(written[position : position + length])
        position += length
    head = [piece.strip("-") for piece in pieces[:-1] if piece.strip("-")]
    prefix = "".join(pieces[:-1])
    if not baseform.startswith(prefix):
        return []
    last = baseform[len(prefix) :].strip("-")
    if not head or not last:
        return []
    return [*head, last]


class VoikkoBackend(LemmatizationBackend):
    """Voikko-based lemmatizer with compound splitting.

    Requires the ``libvoikko`` system library AND the ``libvoikko`` Python
    binding. Note the binding is the PyPI package ``libvoikko``, not ``voikko``:
    the latter installs a ``voikko`` package exposing ``voikko.libvoikko``, so
    ``import libvoikko`` fails and this backend silently never loads.

    Returns base forms of compound parts when ``decompound=True``
    (e.g. "vähennysoikeus" → ["vähennys", "oikeus"]).
    """

    name = "voikko"
    supports_compound_splitting = True

    def __init__(self, language: str = "fi", decompound: bool = True) -> None:
        try:
            import libvoikko  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import error path
            raise ImportError(
                "VoikkoBackend requires libvoikko (system library) and the "
                "libvoikko Python package. Install with: "
                "pip install gaik[finnish-rag-voikko] (and apt install "
                "libvoikko1 voikko-fi / brew install libvoikko). For a "
                "pure-Python alternative with no system library, install "
                "gaik[finnish-rag] and use backend='pyvoikko'."
            ) from exc
        try:
            self._voikko = libvoikko.Voikko(language)
        except Exception as exc:
            raise ImportError(
                f"Failed to initialise libvoikko for language '{language}'. "
                "Is the suomi-malaga dictionary installed?"
            ) from exc
        self._decompound = decompound
        self._stopwords = DEFAULT_FINNISH_STOPWORDS

    def lemmatize(self, text: str) -> list[str]:
        tokens = tokenize(normalize_unicode(text))
        out: list[str] = []
        for token in tokens:
            analyses = self._voikko.analyze(token)
            if not analyses:
                lower = token.lower()
                if lower not in self._stopwords:
                    out.append(lower)
                continue
            analysis = analyses[0]
            base = analysis.get("BASEFORM", token).lower()
            parts = (
                _split_on_structure(base, analysis.get("STRUCTURE"), token.lower())
                if self._decompound
                else []
            )
            for word in parts or [base]:
                if word and word not in self._stopwords:
                    out.append(word)
        return out


class PyVoikkoBackend(LemmatizationBackend):
    """Voikko morphology as a pure-Python FST — no system library, no model download.

    ``pyvoikko`` ships the transducer in the wheel (~1 MB plus ``kfst``), so this
    is the only backend here that gives real Finnish morphology on an image where
    no package manager offers libvoikko. That is not hypothetical: libvoikko is in
    neither the Red Hat UBI 9 repositories nor EPEL 9.

    Measured against :class:`VoikkoBackend` on inflected domain compounds, the
    lemmas are identical. The cost is speed — roughly 2 ms per token against a
    native call's microseconds — so ``lemmatize`` memoises per token, which pays
    for itself immediately on prose, where vocabulary repeats.
    """

    name = "pyvoikko"
    supports_compound_splitting = True

    def __init__(self, decompound: bool = True) -> None:
        try:
            import pyvoikko  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import error path
            raise ImportError(
                "PyVoikkoBackend requires pyvoikko. Install with: pip install gaik[finnish-rag]"
            ) from exc
        self._pyvoikko = pyvoikko
        self._decompound = decompound
        self._stopwords = DEFAULT_FINNISH_STOPWORDS
        self._cache: dict[str, list[str]] = {}

    def _analyse_token(self, token: str) -> list[str]:
        cached = self._cache.get(token)
        if cached is not None:
            return cached
        try:
            analyses = self._pyvoikko.analyse(token)
        except Exception:  # pragma: no cover - tokenizer rejects odd input
            analyses = []
        if not analyses:
            words = [token]
        else:
            analysis = analyses[0]
            parts = analysis.COMPOUND_PARTS if self._decompound else None
            if parts:
                words = [(part.BASEFORM or part.FORM).lower() for part in parts]
            else:
                words = [(analysis.BASEFORM or token).lower()]
        self._cache[token] = words
        return words

    def lemmatize(self, text: str) -> list[str]:
        out: list[str] = []
        for token in tokenize(normalize_unicode(text)):
            for word in self._analyse_token(token.lower()):
                if word and word not in self._stopwords:
                    out.append(word)
        return out


def discover_auto_backend(decompound: bool = True) -> LemmatizationBackend:
    """Try backends in best-to-worst order; return the first that imports cleanly.

    ``decompound`` reaches the backends that can split compounds. It used to be
    dropped here, so ``FinnishTextProcessor(backend="auto", decompound=False)``
    split compounds all the same.
    """
    candidates: list[type[LemmatizationBackend]] = [
        VoikkoBackend,
        PyVoikkoBackend,
        SpacyBackend,
        UralicNLPBackend,
    ]
    for cls in candidates:
        try:
            backend = cls(decompound=decompound) if cls.supports_compound_splitting else cls()
        except ImportError as exc:
            logger.debug("FinnishTextProcessor: backend %s not available (%s)", cls.name, exc)
            continue
        logger.info("FinnishTextProcessor: using backend '%s'", backend.name)
        return backend
    logger.warning(
        "FinnishTextProcessor: no morphological backend available; "
        "falling back to SimpleBackend (regex + lowercase, no lemmatization). "
        "Install gaik[finnish-rag] for better recall."
    )
    return SimpleBackend()
