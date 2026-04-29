"""High-level :class:`FinnishTextProcessor` used by RAG ingest and query paths."""

from __future__ import annotations

import logging
from typing import Literal

from .backends import (
    LemmatizationBackend,
    SimpleBackend,
    SpacyBackend,
    UralicNLPBackend,
    VoikkoBackend,
    discover_auto_backend,
)

logger = logging.getLogger(__name__)

BackendName = Literal["auto", "voikko", "spacy", "uralic", "simple"]


class FinnishTextProcessor:
    """Lemmatize Finnish text and (optionally) split compound words.

    The processor is typically wired into
    :class:`gaik.software_components.RAG.pg_vector_store.PgVectorStore` via its
    ``text_processor`` parameter so both ingestion and query lemmatize through
    the same pipeline. It can also be used standalone for ad-hoc preprocessing.

    Args:
        backend: One of ``"auto"`` (default), ``"voikko"``, ``"spacy"``,
            ``"uralic"``, ``"simple"``. ``"auto"`` tries voikko → spacy →
            uralic → simple in order and uses the first one that imports
            cleanly.
        spacy_model: spaCy model name when ``backend="spacy"``. Defaults to
            ``"fi_core_news_md"``.
        decompound: When the active backend supports compound splitting
            (currently only Voikko), split compound words into parts. No
            effect for backends that don't support it.

    Example::

        processor = FinnishTextProcessor(backend="auto")
        processor.lemmatize("kerrostalon kissoilla")
        # → ["kerros", "talo", "kissa"]   (Voikko)
        # → ["kerrostalo", "kissa"]       (spaCy / UralicNLP)

    The ``simple`` backend is a regex tokenizer + lowercase only, NOT a real
    lemmatizer — use it as a smoke-test fallback or for non-Finnish text.
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
        if backend == "spacy":
            return SpacyBackend(model=spacy_model)
        if backend == "uralic":
            return UralicNLPBackend()
        if backend == "simple":
            return SimpleBackend()
        raise ValueError(
            f"Unknown backend: {backend!r}. "
            "Expected one of auto/voikko/spacy/uralic/simple."
        )
