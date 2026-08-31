"""Retriever for semantic and hybrid search."""

from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "Retriever requires 'langchain-core'. Install extras with 'pip install gaik[retriever]'"
    ) from exc

logger = logging.getLogger(__name__)


class Retriever:
    """Semantic and hybrid retriever for RAG pipelines."""

    def __init__(
        self,
        *,
        embedder,
        vector_store,
        hybrid_search: bool = False,
        re_rank: bool = False,
        rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        top_k: int = 5,
        score_threshold: float | None = None,
        candidate_multiplier: int = 4,
    ) -> None:
        """Initialise the retriever.

        Args:
            embedder: Object with ``embed_query(str) -> list[float]``.
            vector_store: Object with
                ``search(embedding, *, top_k, filters) -> list[(Document, float)]``.
            hybrid_search: Blend a BM25 score over the retrieved candidates into
                the vector score.
            re_rank: Rescore candidates with a cross-encoder. Rerankers can
                *regress* quality on multilingual or domain-specific corpora --
                measure before enabling.
            rerank_model: Cross-encoder model name. Loaded once and reused.
            top_k: Number of documents to return.
            score_threshold: Minimum score to keep. Note the score scale depends
                on which stages ran: cosine similarity in [0, 1] for plain
                semantic search, an unbounded BM25 blend when ``hybrid_search``
                is on, and unbounded cross-encoder logits (often negative) when
                ``re_rank`` is on. A threshold tuned for one is meaningless for
                the others.
            candidate_multiplier: How much wider than ``top_k`` to fetch when
                hybrid scoring or reranking is enabled, so those stages have
                something to reorder. Ignored for plain semantic search.
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.hybrid_search = hybrid_search
        self.re_rank = re_rank
        self.rerank_model = rerank_model
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.candidate_multiplier = candidate_multiplier
        self._cross_encoder: Any | None = None

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        score_threshold: float | None = None,
        filters: dict | None = None,
        include_scores: bool = False,
        hybrid_search: bool | None = None,
        re_rank: bool | None = None,
    ) -> list[Document]:
        """Search for relevant documents."""
        k = top_k if top_k is not None else self.top_k
        threshold = score_threshold if score_threshold is not None else self.score_threshold
        use_hybrid = hybrid_search if hybrid_search is not None else self.hybrid_search
        use_rerank = re_rank if re_rank is not None else self.re_rank

        # Hybrid scoring and reranking can only reorder what they are given, so
        # fetch a wider candidate pool when either is on. Plain semantic search
        # keeps its original behaviour exactly.
        candidate_k = k * self.candidate_multiplier if (use_hybrid or use_rerank) else k

        query_embedding = self.embedder.embed_query(query)
        results = self.vector_store.search(
            query_embedding,
            top_k=candidate_k,
            filters=filters,
        )

        scored = results
        if use_hybrid:
            scored = self._hybrid_score(query, results)

        if use_rerank:
            scored = self._rerank(query, scored)

        if use_hybrid or use_rerank:
            scored = sorted(scored, key=lambda item: item[1], reverse=True)

        if threshold is not None:
            scored = [(doc, score) for doc, score in scored if score >= threshold]

        documents: list[Document] = []
        for doc, score in scored[:k]:
            if include_scores:
                # Build a new Document: the vector store may have handed us the
                # object it stores, and writing the score into it would leak a
                # stale value into every later search.
                doc = Document(
                    page_content=doc.page_content,
                    metadata={**(doc.metadata or {}), "relevance_score": score},
                )
            documents.append(doc)

        return documents

    def _hybrid_score(
        self, query: str, results: list[tuple[Document, float]]
    ) -> list[tuple[Document, float]]:
        query_tokens = self._tokenize(query)
        doc_tokens = [self._tokenize(doc.page_content) for doc, _ in results]
        bm25_scores = self._bm25(query_tokens, doc_tokens)

        combined: list[tuple[Document, float]] = []
        for (doc, vec_score), bm25 in zip(results, bm25_scores):
            score = 0.7 * vec_score + 0.3 * bm25
            combined.append((doc, score))

        return combined

    def _load_cross_encoder(self) -> Any:
        """Load the cross-encoder once and reuse it across searches."""
        if self._cross_encoder is not None:
            return self._cross_encoder
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "Re-ranking requires 'sentence-transformers'. "
                "Install extras with 'pip install gaik[retriever]'"
            ) from exc

        self._cross_encoder = CrossEncoder(self.rerank_model)
        return self._cross_encoder

    def _rerank(
        self, query: str, results: list[tuple[Document, float]]
    ) -> list[tuple[Document, float]]:
        """Rescore candidates with a cross-encoder.

        Reranking is an enhancement, not a requirement: a runtime failure is
        logged and the retrieval scores are returned unchanged. A missing
        ``sentence-transformers`` install is a misconfiguration and still
        raises.
        """
        if not results:
            return results

        try:
            cross_encoder = self._load_cross_encoder()
            pairs = [(query, doc.page_content) for doc, _ in results]
            raw_scores = cross_encoder.predict(pairs)
            scores = [float(score) for score in raw_scores]
            if len(scores) != len(results):
                raise ValueError(f"reranker returned {len(scores)} scores for {len(results)} pairs")
        except ImportError:
            raise
        except Exception as exc:
            logger.warning(
                "Re-ranking failed (%s: %s); keeping the retrieval order.",
                type(exc).__name__,
                exc,
            )
            return results

        return [(doc, score) for (doc, _), score in zip(results, scores)]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.lower().split() if token]

    @staticmethod
    def _bm25(query_tokens: list[str], docs_tokens: list[list[str]]) -> list[float]:
        if not docs_tokens:
            return []

        doc_freq = Counter()
        for tokens in docs_tokens:
            doc_freq.update(set(tokens))

        avg_len = sum(len(tokens) for tokens in docs_tokens) / len(docs_tokens)
        k1 = 1.5
        b = 0.75
        scores: list[float] = []

        for tokens in docs_tokens:
            score = 0.0
            freqs = Counter(tokens)
            doc_len = len(tokens) or 1
            for term in query_tokens:
                if term not in freqs:
                    continue
                df = doc_freq.get(term, 0)
                idf = math.log(1 + (len(docs_tokens) - df + 0.5) / (df + 0.5))
                tf = freqs[term]
                denom = tf + k1 * (1 - b + b * (doc_len / avg_len))
                score += idf * ((tf * (k1 + 1)) / denom)
            scores.append(score)

        return scores
