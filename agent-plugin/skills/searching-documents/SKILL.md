---
name: searching-documents
description: >-
  Builds and debugs retrieval with the gaik toolkit — PgVectorStore, Ranker,
  FinnishTextProcessor, RelevanceGate — as hybrid search: pgvector similarity
  plus Postgres full-text, fused by rank, and the same design in plain SQL for a
  TypeScript app. Use whenever gaik is used for search or RAG retrieval,
  whenever Finnish text is indexed for full-text search, when adding semantic or
  hybrid search over document chunks, and when deciding whether a search found
  anything relevant at all. Also use when search misbehaves without an error: a
  sentence query gets no keyword hits, a word visibly in the text is not found,
  hybrid returns what vector-only returns, gibberish fills a page of results, or
  a similarity threshold never filters anything; and when measuring retrieval
  with Hit@K or MRR, or judging whether a reranker, synonyms, or query
  translation helped.
---

# Searching documents with gaik

```bash
pip install "gaik[pg-vector-store,embedder,ranker]"
pip install "gaik[finnish-rag]"   # Finnish lemmatization
```

Hybrid search runs two arms that fail differently. The vector arm finds passages that
answer in other words; the keyword arm finds exact tokens an embedding blurs — a section
number, a standard's code, a product name. Reciprocal Rank Fusion (RRF) combines them by
rank position, so a cosine similarity and a `ts_rank_cd` never have to share a scale.

Building that takes an afternoon. What costs weeks is that **either arm can stop working
without an error**, and the page still fills with plausible results because the other arm
keeps answering. Most of this skill is about making that failure visible.

## Keep vector-only as a mode and make hybrid earn its place

Do not assume hybrid wins. On one 92-question set, vector-only matched hybrid's recall from
top-10 upwards with a slightly better MRR at an eighth of the latency; hybrid won only at
top-5. That metric asks whether one chunk was found, so it cannot see the case hybrid
exists for — an exact code or section number — and on other corpora the keyword arm was
the only thing that found those at all.

So ship three modes behind one parameter — `hybrid`, `vector`, `keyword` — and judge hybrid
against vector-only on a query set that contains exact tokens. The modes double as the
cheapest health check there is (below).

## The gaik recipe

```python
from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.pg_vector_store import PgVectorStore
from gaik.software_components.RAG.ranker import Ranker

# model= is the deployment name on Azure; its output size must equal embedding_dim
embedder = Embedder(get_openai_config(use_azure=True), model="text-embedding-3-small")

store = PgVectorStore(
    "postgresql://postgres:postgres@localhost:5432/search",
    embedding_dim=1536,
    fts_language="finnish",    # "simple" when a text_processor supplies lemmas (below)
    tsquery_mode="or",         # a sentence query still matches; ts_rank_cd ranks
    hnsw_ef_search=100,
)
store.setup()                                  # table, HNSW + GIN indexes, SQL functions
embeddings, docs = embedder.embed(chunks)      # chunks: list[langchain Document]
store.add(docs, embeddings)

query_vec = embedder.embed_query(query)
semantic = store.search_semantic(query_vec, top_k=50, threshold=0.0)
keyword = store.search_keyword(query, top_k=50)
hits = Ranker(expose_ranks=True).fuse(
    semantic, keyword, names=("semantic", "keyword"), weights=(1.0, 1.0), top_k=10
)
```

Fuse the two lists yourself instead of calling `store.search_hybrid()`:

- the semantic list keeps its cosine similarities, which the relevance gate needs —
  `search_hybrid()` returns only RRF scores;
- `expose_ranks=True` writes `rank_semantic` and `rank_keyword` into every hit's metadata,
  so an arm that contributes nothing shows up per result;
- in gaik 0.7.2 `search_hybrid()` and `search_hybrid_weighted()` ignore `tsquery_mode` and
  always parse in `websearch` mode, which ANDs every term.

**Tune the weights and the RRF constant, do not assume them.** Where the keyword arm alone
reached 33.7% recall@15, equal weights at k=60 scored 8.7 points below vectors weighted 3×
at k=20 (`Ranker(rrf_k=...)` sets k).

**`embedding_dim` must equal the model's output, and at most 2,000.** `setup()` builds an
HNSW index on `vector(N)`, which pgvector refuses above 2,000 dimensions — and gaik's
`Embedder` defaults to `text-embedding-3-large` at 3,072. Pick a model (or a deployment)
that outputs 2,000 or fewer, or build the schema yourself with `halfvec`, which indexes up
to 4,000: `references/postgres-without-gaik.md`.

## Three ways the keyword arm returns nothing, silently

1. **The tsquery ANDs a sentence.** `websearch_to_tsquery` and `plainto_tsquery` conjoin
   every term, so a nine-word question only matches a passage containing all nine stems —
   on real prose, none. Rewrite `&` to `|` and let `ts_rank_cd` rank by how many terms
   matched and how close together. In gaik that is `tsquery_mode="or"`.
2. **The index column is empty.** On one production system the tsvector column existed as a
   plain nullable column instead of the `GENERATED ALWAYS AS (…) STORED` column the
   migration declared. Every row was NULL for about six months, the GIN index indexed
   nothing, and "hybrid" was vector search the whole time. Users noticed first.
3. **The query is in another language than the index.** Postgres full-text cannot cross
   languages: an English question against a `finnish` index took the keyword arm's
   recall@15 from 33.7% to 5.4%, and hybrid became vector-only. Translate the query into the
   corpus language **as a question, not a keyword list** — a keyword list helped the keyword
   arm but wrecked the vector arm and ended 14 points below not translating at all.

A fourth, rarer: zero-width characters (U+200B) pasted in from a CMS glue onto words.
Postgres does not treat them as whitespace, so the word stays unstemmed and never matches.
Strip them at ingest and at query time.

**Check the arms are alive, against the live database.** A unit test cannot see a column
the migration declared correctly and the database never got. Run these from a health
endpoint or a startup check:

- rows with a NULL tsvector: 0, or exactly the rows deliberately left unindexed;
- a word copied out of a random stored chunk, searched in keyword mode, returns that chunk;
- one query in `hybrid` and in `vector` mode: identical result lists mean the keyword arm is
  contributing nothing.

## Finnish and other inflected languages

Postgres' `finnish` snowball stemmer is inconsistent across a word family —
`tilinpäätös` stems to `tilinpäätös`, `tilinpäätöksen` to `tilinpäätöks` — so a search for
one form misses a passage containing the other, and nothing reports the miss. Lemmatize
**both sides** with the same analyser. Measured on sentences queried in a different
inflection than the document used: snowball matched 1 of 4, every prefix strategy 0–1 of
4, lemmas on both sides 4 of 4.

```python
from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

processor = FinnishTextProcessor(backend="pyvoikko", decompound=False)
if processor.backend_name == "simple":  # a tokenizer, not a lemmatizer
    raise RuntimeError("No Finnish morphology installed: pip install 'gaik[finnish-rag]'")

store = PgVectorStore(dsn, embedding_dim=1536, fts_language="simple",
                      text_processor=processor, tsquery_mode="or")
```

Read `references/finnish.md` before indexing Finnish. The rules that each cost a debugging
session:

- **Pin the backend.** `backend="auto"` picks native libvoikko where it is installed and
  something else where it is not, so a laptop indexes different lemmas than the container
  queries with, and the arm silently stops matching. `pyvoikko` is pure Python and runs
  everywhere, including images where libvoikko is not packaged.
- **Start with `decompound=False`** — gaik defaults to `True`. With both sides lemmatized,
  whole compounds already match, and splitting adds noise: `arvonlisävero` yields `arvo`,
  which reaches `arvopaperi`. Index and query must agree; changing it means re-indexing.
- **Long questions flood the lemma arm.** A 25-word question became ~20 OR-ed lemmas that
  matched 78–79% of one corpus, and Hit@1 fell from 3/5 to 2/5 while short-term queries
  improved sharply. Split long questions into short topic queries before searching.
- **No `unaccent`.** In Finnish, ä/a and ö/o are different letters: `tähti`/`tahti`,
  `sää`/`saa`.

## A result count is not evidence

The vector arm answers every query with its nearest neighbours: on one corpus, a gibberish
string returned 24 results and a real question 12. What separates them is the distance to
the **closest** chunk — 17 answerable queries scored 0.26–0.56 cosine distance, 16
unanswerable ones 0.64–0.87 — so a floor at 0.60 split them cleanly. That number belongs to
one embedding model and one corpus; take your own reading.

```python
from gaik.software_components.RAG.relevance_gate import RelevanceGate

# answerable_best / unanswerable_best: the top similarity of search_semantic(...) per query
reading = RelevanceGate.calibrate(answerable_best, unanswerable_best, lower_is_better=False)
print(reading)                   # says so plainly when the two populations overlap
gate = RelevanceGate(reading.floor, lower_is_better=False) if reading.separated else None

if gate and not gate.is_answerable(semantic, key=lambda hit: hit[1]):
    ...                          # "nothing in the library covers this"
```

- `search_semantic()` returns cosine **similarity**, higher is better, so pass
  `lower_is_better=False`. Getting the direction backwards inverts the gate with no error.
- Put ordinary questions about the wrong subject into the unanswerable set, not only
  gibberish. Gibberish separates easily; a sensible off-topic question is what users type.
- Never gate on the RRF score. It is built from rank positions, so the top hit for gibberish
  scores exactly what the top hit for a real question does, and fused scores are compressed
  — rank 1 is 1/61 and rank 20 is 1/80, a ratio of 0.76 — so a relative floor such as "30%
  of the top score" can never fire.
- Judge each result, not the page. A literal keyword match is evidence whatever its cosine;
  a vector-only hit has to clear the floor. Gating on the top hit alone lets one good
  result promote a page of unrelated ones.
- Re-take the reading whenever the embedding model or the corpus changes.

## From chunks to documents

Search ranks chunks; the reader usually sees documents. Over-fetch chunks — about four
times the documents wanted — collapse them onto their parent, and keep the **closest**
distance per document: rows arrive in fused order, so a document's first chunk is its
best-ranked, not necessarily its nearest.

Do not order documents by hit count. On one set that dropped document-level hit@1 from
0.79 to 0.63, because a long document that keeps mentioning a topic outranks the short one
that is about it. Fusing the best-chunk rank with a length-normalised hit density raised it
to 0.83 — and only for short topical queries; on long questions it moved nothing and pushed
correct chunks down.

## Measuring

Read `references/evaluating-retrieval.md` before reporting a number or adopting a change.
The rules that matter most:

- Build two query sets, short domain terms and full questions. They disagree: dropping
  common words and adding a reranker each helped one set and hurt the other.
- Measure end to end. An improvement to the keyword arm measured in isolation (hit@5 0.800
  → 0.829) was an end-to-end loss (0.790 → 0.768) once fused.
- Treat a recall of 0 as a bug until proven otherwise. One benchmark read 0% because the
  database returned bigint ids as strings and the comparison was strict.

## Rerankers

A cross-encoder reorders only the pool it is handed. On one set it raised hit@1 from 0.757
to 0.843 on full questions, did nothing for short domain terms, and made some of them worse. `Ranker().rerank(query, hits,
on_error="fallback")` returns the input order when the model fails, but has no timeout —
wrap it: `asyncio.wait_for(asyncio.to_thread(ranker.rerank, query, hits), timeout=4)`.
Hosted rerankers often ship with tight rate limits; check the quota before designing
around one.

## Gotchas

- `Retriever(hybrid_search=True)` is not a keyword arm. It BM25-rescores the vector
  candidates (0.7 × vector + 0.3 × BM25), so a document the embedding missed cannot come
  back. `PgVectorStore.search_keyword()` is the real one.
- `search_semantic()` defaults to `threshold=0.7`. Pass `threshold=0.0` when fusing or
  gating, or the list arrives pre-cut and the gate never sees the weak cases.
- `hnsw.ef_search` defaults to 40. Raising it to 100 measured recall@20 against an exact
  scan at 96.2% → 99.2% for +0.7 ms on one 1,500-dimension corpus. On a few thousand rows
  it changes nothing — the index already returns exact neighbours.
- A filtered vector query returns fewer rows than asked unless iterative scans are on
  (pgvector 0.8+): `SET hnsw.iterative_scan = relaxed_order`, per connection or as a
  database default.
- The HNSW operator class must match the query operator. An index built with `*_l2_ops` and
  queried with `<=>` is ignored, and every search scans the table.
- `ts_rank_cd` has no IDF: in a two-word query where one word is common, that word decides
  the ranking. Dropping very common words from a short query's keyword text helps — check
  it on both query sets.
- `store.setup()` creates the `vector`, `pg_trgm` and `unaccent` extensions. On a managed
  database without that privilege, have them installed and call
  `setup(create_extensions=False)`.
- Changing the embedding model or its dimension means re-embedding everything; the column is
  `vector(N)`.
- Chunk size is a token limit, not a character one. Finnish runs about 2.5 characters per
  token, so an English-based estimate is twice too generous and an oversized chunk fails
  the whole document at the embedding endpoint.
