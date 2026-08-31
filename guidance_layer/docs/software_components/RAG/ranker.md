# Ranker

Fuse, rerank and reorder retrieval results.

Every gaik vector store returns `list[tuple[Document, float]]`. `Ranker` consumes
and produces exactly that shape, so it composes with `PgVectorStore` and
`VectorStore` without adapters. It performs no IO of its own — no database, no
embedding API — which also makes it the one RAG component that is fully
testable without either.

Use it when you already hold one or more ranked lists and need to combine or
reorder them. Use `Retriever` instead when you want a query string turned into
documents in one call.

## Installation

```bash
pip install gaik[ranker]
```

Pure Python: nothing to download. Cross-encoder reranking is a separate extra,
so that fusing two lists does not pull in torch:

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

for doc, score in hits:
    print(f"{score:.6f}  {doc.page_content[:60]}")
```

Reorder by a business field rather than by relevance:

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

`score(d) = Σ weightᵢ / (k + rankᵢ(d))` over every list containing `d`, ranks
1-based, `k` defaulting to 60.

RRF fuses by **rank**, not by score. That is the whole point: cosine similarity
lives in `[0, 1]` while `ts_rank_cd` and cross-encoder logits are unbounded, so
adding them directly lets one arm dominate for reasons unrelated to relevance.
Give each arm its top candidates (20–100) rather than a whole result set.

Raising `rrf_k` flattens the difference between adjacent ranks; lowering it makes
the top of each list count for more.

### N-way fusion

Fusion is not limited to two search arms. Any ranked signal is another arm,
including non-search ones such as recency or popularity:

```python
ranker.fuse(semantic, keyword, recency, weights=(0.5, 0.3, 0.2))
```

Each signal stays independent and separately weightable, which is what makes the
result tunable without rewriting a scoring function.

### Provenance

```python
ranker.fuse(semantic, keyword, names=("semantic", "keyword"), expose_ranks=True)
```

Each returned document carries `metadata["rank_semantic"]`,
`metadata["rank_keyword"]` and `metadata["rrf_score"]`. A document an arm never
returned has **no** key for it, so `"rank_keyword" in doc.metadata` answers "did
the keyword arm find this at all". This turns a bad weighting from a mystery
into something you can read off the output.

### Ordering — `asc` / `desc`

```python
ranker.order_by(results, field="date", direction="asc", missing="last")
```

| Parameter | Meaning |
|---|---|
| `field` | Metadata key to sort on. `None` sorts on the relevance score. |
| `direction` | `"desc"` (default) or `"asc"`. Anything else raises `ValueError`. |
| `missing` | Rows lacking `field`: `"last"` (default), `"first"` or `"drop"`. |
| `top_k` | Truncate the reordered list. |

`None` values count as missing and never reach a comparison. Ties keep input
order. Ascending on the relevance score is legal and occasionally useful —
surfacing the weakest matches is a real evaluation and debugging move.

### Cross-encoder reranking

```python
ranker = Ranker(rerank_model="cross-encoder/ms-marco-MiniLM-L-12-v2")
best = ranker.rerank("tooth implant recovery", candidates, top_k=5)
```

The model is loaded once per `Ranker` instance and reused across calls.

Reranking is an enhancement, not a requirement. A runtime failure — model
download, HTTP error, malformed response — is logged at warning level and the
retrieval order is returned unchanged; a reranker outage must never break
search. A missing `sentence-transformers` install is a misconfiguration rather
than a runtime fault, so it raises.

Pass `on_error="raise"` to opt out of the fallback.

### Pluggable rerankers

```python
Ranker(model_loader=lambda name: MyHostedReranker(name))
```

Any object with `predict(pairs, batch_size=...)` returning a sequence of floats
works — numpy is not assumed. This is how you swap the local cross-encoder for a
hosted reranker (Cohere, Voyage, Jina).

### Flattening

```python
documents = Ranker.to_documents(hits)  # score in metadata["relevance_score"]
```

Builds new `Document` objects, so nothing upstream is mutated. No `Ranker`
method ever writes into a document your vector store handed back.

---

## Notes and limits

- **Rerankers and hybrid fusion can regress quality.** Double-digit Hit@5 losses
  have been measured on multilingual and heavily domain-specific corpora, and a
  badly weighted hybrid can score below either arm alone. Both are opt-in here
  by design. A/B on your own eval set before adopting either.
- **Reranked scores are not retrieval scores.** Cross-encoder logits are
  unbounded and frequently negative, so a `score_threshold` tuned against cosine
  similarity means nothing after reranking.
- **No timeout parameter.** A wall-clock deadline around a synchronous,
  CPU-bound `predict()` cannot be honoured in-process without threads or
  signals. Wrap the call instead:
  `asyncio.wait_for(asyncio.to_thread(ranker.rerank, ...), timeout=4)`.
- **Fusion identity.** Documents are matched across lists by `metadata["id"]`
  when present — `PgVectorStore` sets it from the table's primary key — falling
  back to the full page content. Override with
  `key=lambda d: d.metadata["chunk_uid"]` when neither fits.

---

## Related components

- **[pg_vector_store](../../../../implementation_layer/src/gaik/software_components/RAG/pg_vector_store/README.md)** —
  `search_semantic` and `search_keyword` produce the arms to fuse. Its
  `search_hybrid` already performs RRF *server-side* in a single query; reach for
  `Ranker` when you need to fuse across backends, weight more than two signals,
  or inspect the fusion.
- **[retriever](./retriever.md)** — query-in, documents-out. `Ranker` is the
  layer below it.
