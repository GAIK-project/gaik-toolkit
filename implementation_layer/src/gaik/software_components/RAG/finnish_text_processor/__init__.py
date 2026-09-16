"""Finnish text processor for RAG pipelines.

Lemmatizes Finnish text and splits compound words ("kerrostalo" → kerros + talo)
so that hybrid full-text + vector search can match inflected forms ("kissan" →
"kissa") and compound parts. Plugs into ``PgVectorStore`` (in
``gaik.software_components.RAG.pg_vector_store``) via the ``text_processor``
parameter, but is also usable standalone.

Backends (auto-detected in this order when ``backend="auto"``):

- ``voikko``: native morphology + compound splitting; fastest. Requires the
  ``libvoikko`` system library and the ``libvoikko`` Python package.
- ``pyvoikko``: the same morphology as a pure-Python FST — no system library, no
  model download. The only real option on images where libvoikko is not
  packaged, which includes Red Hat UBI 9 and EPEL 9.
- ``spacy``: lemmatization via ``fi_core_news_md`` / ``lg`` (download separately
  with ``python -m spacy download fi_core_news_md``). Weaker on long compounds.
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

    print(processor.to_tsquery("vahvistetun tilinpäätöksen korjaaminen"))
    # → "vahvistettu | tilinpäätös | korjata"
"""

from .backends import (
    LemmatizationBackend,
    PyVoikkoBackend,
    SimpleBackend,
    SpacyBackend,
    UralicNLPBackend,
    VoikkoBackend,
)
from .processor import (
    BackendName,
    FinnishTextProcessor,
)

__all__ = [
    "FinnishTextProcessor",
    "LemmatizationBackend",
    "BackendName",
    "VoikkoBackend",
    "PyVoikkoBackend",
    "SpacyBackend",
    "UralicNLPBackend",
    "SimpleBackend",
]

__version__ = "0.1.0"
