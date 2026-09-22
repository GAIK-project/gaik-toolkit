"""Tell "the corpus answered this" apart from "here are the nearest neighbours".

A vector index returns results for every query, including ones it has nothing for,
so counting results cannot tell you whether a search succeeded. The distance to
the closest match can. :class:`RelevanceGate` applies that threshold and
:meth:`RelevanceGate.calibrate` measures it, since the right value is a property
of your embedding model and your corpus rather than a constant.

Pure Python — no database, no model, no dependencies. Works on any result shape
via a ``key`` function.

Example::

    from gaik.software_components.RAG.relevance_gate import RelevanceGate

    # PgVectorStore.search_semantic returns cosine similarity, higher is closer
    gate = RelevanceGate(floor=0.40, lower_is_better=False)
    hits = store.search_semantic(query_embedding, top_k=20, threshold=0.0)
    if not gate.is_answerable(hits, key=lambda hit: hit[1]):
        return "Nothing in the library covers this."
"""

from .gate import Calibration, RelevanceGate

__all__ = ["RelevanceGate", "Calibration"]
