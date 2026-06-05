"""Backend implementations for FinnishTextProcessor.

Each backend implements :class:`LemmatizationBackend` — a tiny ABC with one
method, ``lemmatize(text) -> list[str]``. The ``auto`` strategy in
:class:`gaik.software_components.RAG.finnish_text_processor.processor.FinnishTextProcessor`
tries them in order and uses the first one that imports cleanly.

Order chosen for accuracy vs. install cost:

1. ``VoikkoBackend`` — best Finnish morphology + compound splitting; requires
   ``libvoikko`` system library + ``voikko`` Python wheel.
2. ``SpacyBackend`` — good lemmatization via ``fi_core_news_md`` / ``lg``;
   ~100-700 MB model download but pure-pip otherwise.
3. ``UralicNLPBackend`` — pure-Python, no system deps; morphology smaller but
   handles inflection.
4. ``SimpleBackend`` — last-resort regex-tokenizer + lowercase. No real
   lemmatization; ensures the pipeline never crashes when nothing else is
   installed.
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
            if tok.is_space or tok.is_punct or tok.like_num is False and not tok.is_alpha:
                continue
            lemma = (tok.lemma_ or tok.text).lower()
            if lemma and lemma not in self._stopwords:
                out.append(lemma)
        return out


class VoikkoBackend(LemmatizationBackend):
    """Voikko-based lemmatizer with compound splitting.

    Requires ``libvoikko`` system library AND the ``voikko`` Python wheel.
    Returns base forms of compound parts when ``decompound=True``
    (e.g. "kerrostalon" → ["kerros", "talo"]).
    """

    name = "voikko"
    supports_compound_splitting = True

    def __init__(self, language: str = "fi", decompound: bool = True) -> None:
        try:
            import libvoikko  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import error path
            raise ImportError(
                "VoikkoBackend requires libvoikko (system library) and the "
                "voikko Python package. Install with: "
                "pip install gaik[finnish-rag-voikko] (and apt install "
                "libvoikko1 / brew install libvoikko)"
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
            base = analyses[0].get("BASEFORM", token).lower()
            if self._decompound and "+" in base:
                # libvoikko returns compound parts joined by "+".
                parts = [p.strip().lower() for p in base.split("+") if p.strip()]
                out.extend(p for p in parts if p and p not in self._stopwords)
            elif base not in self._stopwords:
                out.append(base)
        return out


def discover_auto_backend() -> LemmatizationBackend:
    """Try backends in best-to-worst order; return the first that imports cleanly."""
    candidates: list[type[LemmatizationBackend]] = [
        VoikkoBackend,
        SpacyBackend,
        UralicNLPBackend,
    ]
    for cls in candidates:
        try:
            backend = cls()
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
