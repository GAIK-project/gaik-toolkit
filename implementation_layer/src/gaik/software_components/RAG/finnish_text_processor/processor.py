"""High-level :class:`FinnishTextProcessor` used by RAG ingest and query paths."""

from __future__ import annotations

import logging
import re
from typing import Literal

from .backends import (
    LemmatizationBackend,
    PyVoikkoBackend,
    SimpleBackend,
    SpacyBackend,
    UralicNLPBackend,
    VoikkoBackend,
    discover_auto_backend,
)

logger = logging.getLogger(__name__)

BackendName = Literal["auto", "voikko", "pyvoikko", "spacy", "uralic", "simple"]

# Everything tsquery treats as syntax. A lemma is a word, so anything in this set
# arrived from user input and has no business reaching the parser.
_TSQUERY_UNSAFE = re.compile(r"[^\w\-]", flags=re.UNICODE)


class FinnishTextProcessor:
    """Lemmatize Finnish text and (optionally) split compound words.

    The processor is typically wired into
    :class:`gaik.software_components.RAG.pg_vector_store.PgVectorStore` via its
    ``text_processor`` parameter so both ingestion and query lemmatize through
    the same pipeline. It can also be used standalone for ad-hoc preprocessing.

    Args:
        backend: One of ``"auto"`` (default), ``"voikko"``, ``"pyvoikko"``,
            ``"spacy"``, ``"uralic"``, ``"simple"``. ``"auto"`` tries
            voikko → pyvoikko → spacy → uralic → simple in order and uses the
            first one that imports cleanly.
        spacy_model: spaCy model name when ``backend="spacy"``. Defaults to
            ``"fi_core_news_md"``.
        decompound: When the active backend supports compound splitting (the two
            Voikko backends), split compound words into parts. No effect for
            backends that don't support it.

    Example::

        processor = FinnishTextProcessor(backend="auto")
        processor.lemmatize("kerrostalon kissoilla")
        # → ["kerros", "talo", "kissa"]   (Voikko / PyVoikko)
        # → ["kerrostalo", "kissa"]       (spaCy / UralicNLP)

    **Lemmatize both sides or neither.** The gain comes from the index and the
    query agreeing on a form, not from either one alone. Postgres' ``finnish``
    snowball configuration is not that agreement: it stems ``tilinpäätös`` to
    ``tilinpäätös`` and ``tilinpäätöksen`` to ``tilinpäätöks``, two different
    lexemes, so a search for one misses a passage containing the other. Feeding
    lemmatized text to ``to_tsvector`` at ingest and lemmatized terms to
    ``to_tsquery`` at search time makes both sides ``tilinpäätös``. Lemmatizing
    only the query and matching it against stemmed content leaves the same
    mismatch in place.

    ``backend_name`` reports what actually loaded. Check it before relying on the
    processor: ``"simple"`` is a regex tokenizer + lowercase, NOT a lemmatizer,
    and content indexed through it is *less* searchable than snowball-stemmed
    content, not more.
    """

    def __init__(
        self,
        backend: BackendName = "auto",
        *,
        spacy_model: str = "fi_core_news_md",
        decompound: bool = True,
    ) -> None:
        self.requested_backend = backend
        self.decompound = decompound
        self._backend: LemmatizationBackend = self._resolve_backend(
            backend, spacy_model=spacy_model, decompound=decompound
        )

    @property
    def backend_name(self) -> str:
        """Name of the active backend (``"voikko"``, ``"spacy"``, ``"uralic"``, ``"simple"``)."""
        return self._backend.name

    @property
    def supports_compound_splitting(self) -> bool:
        """``True`` when the active backend can split compound words."""
        return self._backend.supports_compound_splitting

    # ── Public API ────────────────────────────────────────────────

    def lemmatize(self, text: str) -> list[str]:
        """Return a list of lemma tokens for *text*.

        Compound words are split when the active backend supports it (Voikko
        with ``decompound=True``).
        """
        if not text:
            return []
        return self._backend.lemmatize(text)

    def to_tsvector_text(self, text: str) -> str:
        """Render *text* as a space-separated string of lemmas, ready for ``to_tsvector``.

        Use this on the **document side** (ingest) so the FTS index stores
        lemmatized content.
        """
        return " ".join(self.lemmatize(text))

    def expand_query(self, query: str) -> str:
        """Render *query* as a space-separated string of lemmas, ready for ``websearch_to_tsquery``.

        Use this on the **query side** so the user's inflected search terms
        match the lemma-indexed content.
        """
        return " ".join(self.lemmatize(query))

    def to_tsquery(self, text: str, *, operator: str = "|", prefix: bool = False) -> str:
        """Render *text* as a ``tsquery`` expression built from its lemmas.

        Returns a string for ``to_tsquery()``, e.g.
        ``"tilinpäätös | korjata | yhtiökokous"``. Empty when *text* holds no
        usable lemma — which is **not** the same as empty input: a query made
        entirely of stopwords has content and still yields nothing. Callers must
        treat ``""`` as "no keyword arm", never pass it to ``to_tsquery()``.

        Args:
            operator: ``"|"`` (default) or ``"&"``. ``"|"`` is the right default
                for retrieval: conjoining every term means a nine-word question
                only matches a passage containing all nine, which on real prose
                is never, and the keyword arm silently contributes nothing.
                ``ts_rank_cd`` already scores by how many distinct terms matched
                and how close together they are, so it does the discriminating.
            prefix: append ``:*`` to each lemma. **Rarely what you want for
                Finnish.** Consonant gradation and stem alternation mean a lemma
                is frequently not a prefix of its own inflected forms —
                ``kolmikantakauppa`` against ``kolmikantakaupassa``,
                ``kirjanpitovelvollisuus`` against ``kirjanpitovelvollisuutta``.
                Prefix matching pays off for agglutinative *suffixing* on an
                unstemmed index; against lemma-indexed content it mostly adds
                false positives, since a short compound part like ``arvo:*``
                reaches ``arvopaperi`` and ``arvostus`` as readily as
                ``arvonlisävero``.

        Raises:
            ValueError: if *operator* is not ``"|"`` or ``"&"``.
        """
        if operator not in {"|", "&"}:
            raise ValueError(f"operator must be '|' or '&', got {operator!r}")
        terms: list[str] = []
        for lemma in self.lemmatize(text):
            safe = _TSQUERY_UNSAFE.sub("", lemma).strip("-")
            if safe:
                terms.append(f"{safe}:*" if prefix else safe)
        return f" {operator} ".join(terms)

    # ── Internal ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_backend(
        backend: BackendName,
        *,
        spacy_model: str,
        decompound: bool,
    ) -> LemmatizationBackend:
        if backend == "auto":
            return discover_auto_backend()
        if backend == "voikko":
            return VoikkoBackend(decompound=decompound)
        if backend == "pyvoikko":
            return PyVoikkoBackend(decompound=decompound)
        if backend == "spacy":
            return SpacyBackend(model=spacy_model)
        if backend == "uralic":
            return UralicNLPBackend()
        if backend == "simple":
            return SimpleBackend()
        raise ValueError(
            f"Unknown backend: {backend!r}. Expected one of auto/voikko/spacy/uralic/simple."
        )
