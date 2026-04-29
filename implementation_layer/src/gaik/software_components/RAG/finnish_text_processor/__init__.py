"""Finnish text processor for RAG pipelines.

Lemmatizes Finnish text and splits compound words ("kerrostalo" → kerros + talo)
so that hybrid full-text + vector search can match inflected forms ("kissan" →
"kissa") and compound parts. Plugs into ``PgVectorStore`` (in
``gaik.software_components.RAG.pg_vector_store``) via the ``text_processor``
parameter, but is also usable standalone.

Backends (auto-detected when ``backend="auto"``):

- ``voikko``: best morphological accuracy + compound splitting; requires the
  ``libvoikko`` system library and the ``voikko`` Python wheel.
- ``spacy``: solid lemmatization via ``fi_core_news_md`` / ``lg`` (download
  separately with ``python -m spacy download fi_core_news_md``).
- ``uralic``: pure-Python via ``uralicNLP``; lightweight, no system deps.
- ``simple``: regex-tokenizer + lowercase fallback (no real lemmatization);
  always available as last resort so the pipeline never crashes.

Example::

    from gaik.software_components.RAG.finnish_text_processor import (
        FinnishTextProcessor,
    )

    processor = FinnishTextProcessor(backend="auto")
    print(processor.lemmatize("kerrostalon kissoilla"))
    # → ["kerros", "talo", "kissa"]

    print(processor.to_tsvector_text("Kissoilla on neljä jalkaa"))
    # → "kissa olla neljä jalka"
"""

from .processor import (
    BackendName,
    FinnishTextProcessor,
    LemmatizationBackend,
)

__all__ = [
    "FinnishTextProcessor",
    "LemmatizationBackend",
    "BackendName",
]

__version__ = "0.1.0"
