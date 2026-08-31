# Ranker

Fuse, rerank and reorder retrieval results.

Every gaik vector store returns `list[tuple[Document, float]]`. `Ranker` consumes
and produces exactly that shape, so it drops in after `PgVectorStore` or
`VectorStore` without adapters. It never talks to a database or an embedding
API — feed it the lists your store already returned.

## Installation

```bash
pip install gaik[ranker]
```

Pure Python: no model download, no database. Cross-encoder reranking is a
separate extra so that fusing two lists does not pull in torch:

```bash
pip install gaik[ranker-rerank]
```

---

## Quick Start

```python
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from gaik.software_components.RAG.ranker import Ranker

ranker = Ranker(rrf_k=60)

with PgVectorStore(DATABASE_URL) as store:
    semantic = store.search_semantic(query_embedding, top_k=50)
    keyword = store.search_keyword(query_text, top_k=50)

    hits = ranker.fuse(semantic, keyword, weights=(0.7, 0.3), top_k=10)
```

Reorder by a business field instead of by relevance:

```python
newest_first = ranker.order_by(hits, field="published_at", direction="desc")
cheapest_first = ranker.order_by(hits, field="price", direction="asc")
```

---

## Features

### Weighted Reciprocal Rank Fusion

```python
ranker.fuse(semantic, keyword, weights=(0.7, 0.3), top_k=10)
```

`score(d) = Σ weightᵢ / (k + rankᵢ(d))`, ranks 1-based, `k` defaulting to 60.

RRF fuses by **rank**, not by score. This matters: cosine similarity lives in
[0, 1] while `ts_rank_cd` and cross-encoder logits are unbounded, so adding them
directly lets one arm dominate for reasons that have nothing to do with
relevance. Feed each arm its top candidates (20–100) rather than whole result
sets.

Fusion is not limited to two search arms — any ranked signal works, including
non-search ones:

```python
ranker.fuse(semantic, keyword, recency, weights=(0.5, 0.3, 0.2))
```

### Provenance

```python
ranker.fuse(semantic, keyword, names=("semantic", "keyword"), expose_ranks=True)
```

Each returned document carries `metadata["rank_semantic"]`,
`metadata["rank_keyword"]` and `metadata["rrf_score"]`. A document that an arm
never returned has **no** key for it, so `"rank_keyword" in doc.metadata`
answers "did the keyword arm find this at all". This is what makes a bad
weighting debuggable rather than mysteriously worse.

### Ordering — `asc` / `desc`

```python
ranker.order_by(results, field="date", direction="asc", missing="last")
```

`field=None` orders by the relevance score already attached to each result;
naming a field orders by that metadata value instead. `missing` controls rows
lacking the field: `"last"` (default), `"first"` or `"drop"`. `None` values
count as missing and never reach a comparison. Ties keep input order.

### Cross-encoder reranking

```python
ranker = Ranker(rerank_model="cross-encoder/ms-marco-MiniLM-L-12-v2")
best = ranker.rerank("tooth implant recovery", candidates, top_k=5)
```

The model is loaded **once** per `Ranker` instance and reused.

Reranking is an enhancement, not a requirement. A runtime failure (model
download, HTTP error, malformed response) is logged at warning level and the
retrieval order is returned unchanged — a reranker outage must never break
search. A missing `sentence-transformers` install is a misconfiguration rather
than a runtime fault, so it raises.

Use `model_loader` to plug in a hosted reranker instead of a local
cross-encoder:

```python
Ranker(model_loader=lambda name: MyCohereReranker(name))
```

Any object with `predict(pairs, batch_size=...)` returning a sequence of floats
works; numpy is not assumed.

---

## Notes and limits

- **Rerankers and hybrid search can regress quality.** Double-digit Hit@5 losses
  have been measured on multilingual and heavily domain-specific corpora, and a
  badly weighted hybrid can score below either arm alone. Both are opt-in here
  by design. A/B on your own eval set before adopting.
- **Reranked scores are not retrieval scores.** Cross-encoder logits are
  unbounded and frequently negative, so a `score_threshold` tuned against cosine
  similarity is meaningless after reranking.
- **No timeout parameter.** A wall-clock deadline around a synchronous,
  CPU-bound `predict()` cannot be honoured in-process without threads or
  signals. Wrap the call instead:
  `asyncio.wait_for(asyncio.to_thread(ranker.rerank, ...), timeout=4)`.
- **Fusion identity.** Documents are matched across lists by
  `metadata["id"]` when present (`PgVectorStore` sets it), falling back to the
  full page content. Override with `key=lambda d: d.metadata["chunk_uid"]`.
- **Nothing is mutated.** Every method builds new `Document` objects rather than
  writing into the ones your vector store handed back.

---

## Related components

- **PgVectorStore** — `search_semantic` / `search_keyword` produce the arms to
  fuse. Its `search_hybrid` already does RRF *server-side*; use `Ranker` when
  you need to fuse across backends, weight more than two signals, or inspect
  the fusion.
- **Retriever** — a query-in, documents-out convenience wrapper. Use `Ranker`
  when you already hold the ranked lists.
