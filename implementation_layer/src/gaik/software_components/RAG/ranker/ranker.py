"""Ranking, fusion and reordering for retrieval results.

Operates on the ``list[tuple[Document, float]]`` shape that every gaik vector
store already returns, so it composes with ``PgVectorStore`` and ``VectorStore``
without adapters and without a database of its own.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable, Sequence
from typing import Any, Literal

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "Ranker requires 'langchain-core'. Install extras with 'pip install gaik[ranker]'"
    ) from exc

logger = logging.getLogger(__name__)

Result = tuple[Document, float]
Direction = Literal["asc", "desc"]
Missing = Literal["last", "first", "drop"]

DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"


def default_key(doc: Document) -> Hashable:
    """Stable identity used to match the same document across result lists.

    Prefers ``metadata["id"]`` (set by ``PgVectorStore``) and falls back to the
    full page content. The value is *tagged* so that a document with
    ``id == "x"`` can never collide with one whose content is ``"x"``.
    """
    doc_id = (doc.metadata or {}).get("id")
    if doc_id is not None:
        return ("id", doc_id)
    return ("content", doc.page_content)


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[Result]],
    *,
    weights: Sequence[float] | None = None,
    k: int = 60,
    key: Callable[[Document], Hashable] = default_key,
    names: Sequence[str] | None = None,
    expose_ranks: bool = False,
    top_k: int | None = None,
) -> list[Result]:
    """Fuse N ranked lists with weighted Reciprocal Rank Fusion.

    ``score(d) = sum(weight_i / (k + rank_i(d)))`` over every list that contains
    ``d``, where ``rank_i`` is 1-based.

    RRF fuses by *rank*, not by score, which is what makes it safe to combine
    lists whose scores live on incompatible scales -- cosine similarity in
    [0, 1] and an unbounded BM25 or cross-encoder score cannot be added
    directly. Feed it the top candidates from each list rather than whole
    result sets.

    Args:
        result_lists: Ranked lists, each already ordered best-first.
        weights: Per-list multipliers. Defaults to 1.0 for every list.
        k: RRF constant. Higher values flatten the difference between ranks.
        key: Identity function used to match a document across lists.
        names: Per-list labels used for the ``rank_<name>`` metadata keys.
            Defaults to the list index.
        expose_ranks: Write each arm's rank and the fused score into the
            returned documents' metadata. Input documents are never mutated.
        top_k: Truncate the fused list.

    Returns:
        ``list[tuple[Document, float]]`` ordered by fused score, best first.
        Ties keep first-seen order.
    """
    lists = [list(results) for results in result_lists]

    if weights is None:
        weights = [1.0] * len(lists)
    elif len(weights) != len(lists):
        raise ValueError(
            f"weights has {len(weights)} entries but {len(lists)} result lists were given"
        )
    if names is not None and len(names) != len(lists):
        raise ValueError(f"names has {len(names)} entries but {len(lists)} result lists were given")

    if not any(lists):
        return []

    scores: dict[Hashable, float] = {}
    docs: dict[Hashable, Document] = {}
    ranks: dict[Hashable, dict[str, int]] = {}
    positions: dict[Hashable, int] = {}

    for arm, (results, weight) in enumerate(zip(lists, weights)):
        arm_name = names[arm] if names is not None else str(arm)
        for rank, (doc, _score) in enumerate(results, start=1):
            doc_key = key(doc)
            if doc_key not in docs:
                docs[doc_key] = doc  # first list to surface it wins the Document
                scores[doc_key] = 0.0
                ranks[doc_key] = {}
                positions[doc_key] = len(positions)
            if arm_name in ranks[doc_key]:
                # A duplicate within one list contributes once, at its best rank.
                continue
            ranks[doc_key][arm_name] = rank
            scores[doc_key] += weight / (k + rank)

    ordered = sorted(positions, key=lambda dk: (-scores[dk], positions[dk]))
    if top_k is not None:
        ordered = ordered[:top_k]

    fused: list[Result] = []
    for doc_key in ordered:
        doc = docs[doc_key]
        if expose_ranks:
            metadata = dict(doc.metadata or {})
            for arm_name, rank in ranks[doc_key].items():
                metadata[f"rank_{arm_name}"] = rank
            metadata["rrf_score"] = scores[doc_key]
            doc = Document(page_content=doc.page_content, metadata=metadata)
        fused.append((doc, scores[doc_key]))

    return fused


class Ranker:
    """Fuse, rerank and reorder retrieval results.

    Stateless with respect to your data -- it never talks to a database or an
    embedding API. Feed it the lists your vector store already returned.

    Example:
        >>> ranker = Ranker()
        >>> semantic = store.search_semantic(query_embedding, top_k=50)
        >>> keyword = store.search_keyword(query_text, top_k=50)
        >>> hits = ranker.fuse(semantic, keyword, weights=(0.7, 0.3), top_k=10)

    Args:
        rrf_k: Default RRF constant for :meth:`fuse`.
        key: Identity function used to match a document across lists.
        top_k: Default truncation applied by every method.
        expose_ranks: Default for writing per-arm ranks into fused metadata.
        rerank_model: Cross-encoder model name for :meth:`rerank`.
        rerank_batch_size: Batch size passed to the cross-encoder.
        model_loader: Callable taking the model name and returning any object
            with a ``predict(pairs, batch_size=...)`` method. Use this to plug
            in a hosted reranker (Cohere, Voyage, Jina) instead of a local
            cross-encoder. Defaults to ``sentence_transformers.CrossEncoder``.
    """

    def __init__(
        self,
        *,
        rrf_k: int = 60,
        key: Callable[[Document], Hashable] | None = None,
        top_k: int | None = None,
        expose_ranks: bool = False,
        rerank_model: str = DEFAULT_RERANK_MODEL,
        rerank_batch_size: int = 32,
        model_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.rrf_k = rrf_k
        self.key = key or default_key
        self.top_k = top_k
        self.expose_ranks = expose_ranks
        self.rerank_model = rerank_model
        self.rerank_batch_size = rerank_batch_size
        self._model_loader = model_loader
        self._model: Any | None = None

    # ------------------------------------------------------------------
    # Fusion
    # ------------------------------------------------------------------

    def fuse(
        self,
        *result_lists: Sequence[Result],
        weights: Sequence[float] | None = None,
        names: Sequence[str] | None = None,
        top_k: int | None = None,
        expose_ranks: bool | None = None,
    ) -> list[Result]:
        """Combine N ranked lists with weighted RRF.

        Takes lists as positional arguments::

            ranker.fuse(semantic, keyword, recency, weights=(0.5, 0.3, 0.2))

        See :func:`reciprocal_rank_fusion` for the scoring detail.
        """
        return reciprocal_rank_fusion(
            result_lists,
            weights=weights,
            k=self.rrf_k,
            key=self.key,
            names=names,
            expose_ranks=self.expose_ranks if expose_ranks is None else expose_ranks,
            top_k=self._limit(top_k),
        )

    # ------------------------------------------------------------------
    # Cross-encoder reranking
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        results: Sequence[Result],
        *,
        top_k: int | None = None,
        on_error: Literal["fallback", "raise"] = "fallback",
    ) -> list[Result]:
        """Rescore candidates with a cross-encoder and reorder them.

        The model is loaded once per :class:`Ranker` instance and reused.

        Reranking is an enhancement, not a requirement: by default any runtime
        failure (model download, HTTP error, malformed response) is logged at
        warning level and the original order is returned unchanged. A missing
        ``sentence-transformers`` install is a misconfiguration rather than a
        runtime fault, so it always raises.

        Rerankers can *regress* retrieval quality on multilingual or heavily
        domain-specific corpora. Measure on your own eval set before adopting.

        There is no timeout parameter: a wall-clock deadline around a
        synchronous, CPU-bound ``predict()`` cannot be honoured in-process.
        Callers needing one should wrap the call, e.g.
        ``asyncio.wait_for(asyncio.to_thread(ranker.rerank, ...), timeout=4)``.

        Args:
            query: The search query the candidates were retrieved for.
            results: Candidates to rescore, typically 20-100 of them.
            top_k: Truncate the reranked list.
            on_error: ``"fallback"`` returns the input order on failure,
                ``"raise"`` propagates.

        Returns:
            ``list[tuple[Document, float]]`` carrying the cross-encoder scores,
            best first. Note these are not comparable to the retrieval scores
            they replace -- cross-encoder logits are unbounded and often
            negative, so a ``score_threshold`` tuned on cosine similarity is
            meaningless here.
        """
        candidates = list(results)
        limit = self._limit(top_k)
        if not candidates or not query:
            return candidates[:limit] if limit else candidates

        try:
            model = self._load_model()
            pairs = [(query, doc.page_content) for doc, _ in candidates]
            raw_scores = model.predict(pairs, batch_size=self.rerank_batch_size)
            scores = [float(score) for score in raw_scores]
            if len(scores) != len(candidates):
                raise ValueError(
                    f"reranker returned {len(scores)} scores for {len(candidates)} candidates"
                )
        except ImportError:
            raise  # a missing dependency is actionable; never swallow it
        except Exception as exc:
            if on_error == "raise":
                raise
            logger.warning(
                "Reranking failed (%s: %s); falling back to the retrieval order.",
                type(exc).__name__,
                exc,
            )
            return candidates[:limit] if limit else candidates

        reranked = sorted(
            zip(candidates, scores),
            key=lambda pair: -pair[1],
        )
        ordered = [(doc, score) for (doc, _old_score), score in reranked]
        return ordered[:limit] if limit else ordered

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_loader is not None:
            self._model = self._model_loader(self.rerank_model)
            return self._model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "Cross-encoder reranking requires 'sentence-transformers'. "
                "Install extras with 'pip install gaik[ranker-rerank]'"
            ) from exc
        self._model = CrossEncoder(self.rerank_model)
        return self._model

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def order_by(
        self,
        results: Sequence[Result],
        *,
        field: str | None = None,
        direction: Direction = "desc",
        missing: Missing = "last",
        top_k: int | None = None,
    ) -> list[Result]:
        """Reorder results by relevance score or by a metadata field.

        Args:
            results: Results to reorder.
            field: Metadata key to sort on. ``None`` sorts on the relevance
                score already attached to each result.
            direction: ``"desc"`` (default) or ``"asc"``. Ascending is the
                point for a metadata field such as a date or a price; on the
                relevance score it surfaces the weakest matches, which is
                useful for eval and debugging.
            missing: What to do with results lacking ``field`` --
                ``"last"`` (default), ``"first"`` or ``"drop"``.
            top_k: Truncate the reordered list.

        Returns:
            ``list[tuple[Document, float]]``. Scores are untouched; only the
            order changes. Ties keep input order.
        """
        if direction not in ("asc", "desc"):
            raise ValueError(f"direction must be 'asc' or 'desc', got {direction!r}")
        if missing not in ("last", "first", "drop"):
            raise ValueError(f"missing must be 'last', 'first' or 'drop', got {missing!r}")

        candidates = list(results)
        limit = self._limit(top_k)
        descending = direction == "desc"

        if field is None:
            ordered = sorted(candidates, key=lambda item: item[1], reverse=descending)
            return ordered[:limit] if limit else ordered

        present: list[Result] = []
        absent: list[Result] = []
        for doc, score in candidates:
            if (doc.metadata or {}).get(field) is None:
                absent.append((doc, score))
            else:
                present.append((doc, score))

        try:
            ordered_present = sorted(
                present,
                key=lambda item: item[0].metadata[field],
                reverse=descending,
            )
        except TypeError as exc:
            raise TypeError(
                f"metadata field {field!r} holds values that cannot be compared "
                f"to each other: {exc}"
            ) from exc

        if missing == "drop":
            ordered = ordered_present
        elif missing == "first":
            ordered = absent + ordered_present
        else:
            ordered = ordered_present + absent

        return ordered[:limit] if limit else ordered

    # ------------------------------------------------------------------
    # Facade + conversion
    # ------------------------------------------------------------------

    def rank(
        self,
        results: Sequence[Result],
        *,
        strategy: Literal["score", "rerank", "field"] = "score",
        query: str | None = None,
        field: str | None = None,
        direction: Direction = "desc",
        top_k: int | None = None,
    ) -> list[Result]:
        """Reorder a single list using the named strategy.

        ``"score"`` orders by the existing relevance score, ``"rerank"`` runs
        the cross-encoder (requires ``query``), ``"field"`` orders by a
        metadata field (requires ``field``).

        Use :meth:`fuse` instead when you have more than one ranked list.
        """
        if strategy == "score":
            return self.order_by(results, direction=direction, top_k=top_k)
        if strategy == "rerank":
            if not query:
                raise ValueError("strategy='rerank' requires a query")
            return self.rerank(query, results, top_k=top_k)
        if strategy == "field":
            if not field:
                raise ValueError("strategy='field' requires a field name")
            return self.order_by(results, field=field, direction=direction, top_k=top_k)
        raise ValueError(f"strategy must be 'score', 'rerank' or 'field', got {strategy!r}")

    @staticmethod
    def to_documents(
        results: Sequence[Result],
        *,
        include_scores: bool = True,
        score_key: str = "relevance_score",
    ) -> list[Document]:
        """Flatten results to plain documents, optionally carrying the score.

        Always builds new :class:`Document` objects, so the caller's -- and the
        vector store's -- documents are never mutated.
        """
        if not include_scores:
            return [doc for doc, _ in results]
        return [
            Document(
                page_content=doc.page_content,
                metadata={**(doc.metadata or {}), score_key: score},
            )
            for doc, score in results
        ]

    def _limit(self, top_k: int | None) -> int | None:
        return top_k if top_k is not None else self.top_k
