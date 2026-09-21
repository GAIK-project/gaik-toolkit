# Evaluating retrieval

Read this before reporting a retrieval number, comparing two configurations, or adopting a
reranker, synonym list, query translation, or new embedding model.

## Contents
- Two query sets, because they disagree
- Metrics at the level the reader sees
- Baselines on every run
- Noise before signal
- End to end, not in isolation
- What a retrieval metric cannot see
- Traps that produce a confident wrong number
- Measured not to help

## Two query sets, because they disagree

Build both:

- **short** — one to three domain terms, the shape people actually type;
- **long** — full natural-language questions.

On one corpus, dropping common words from the keyword text helped the short set and hurt the
long one, while a reranker helped the long set and hurt the short one. A change accepted on
one set alone was measured on the wrong population, and one failure survived for months
because only the long set was being run.

Add two more kinds of query: **exact tokens** (codes, section numbers, product names) — the
keyword arm's reason to exist — and **unanswerable** ones, including well-formed questions
about a subject the corpus does not cover, for calibrating the relevance floor.

## Metrics at the level the reader sees

Report chunk-level metrics (hit@k, MRR, recall@k, nDCG@k — is the right passage near the
top) and document-level ones (hit@k and MRR over documents — is the right document near the
front). Reordering documents moves their chunks as a block, so one change can improve one
level and regress the other.

gaik has no rank-metric helper; they are a few lines each. For the answer side,
`RAGEvaluator(judge)` from `gaik.software_components.evaluators` grades faithfulness, answer
relevance and context precision with an `LLMJudge`, plus context recall when a ground-truth
answer is given.

## Baselines on every run

Run `vector`, `keyword` and `hybrid` on the same set each time. The per-arm numbers are what
explain a change in the fused one — and a hybrid result identical to vector-only is the
signature of a dead keyword arm.

## Noise before signal

Run the unchanged configuration twice before comparing anything. On a 70-query set, metrics
swung by about ±3 points between identical runs, so the adoption bar there was **at least +3
points** on the metric that matters, with latency inside its budget. LLM steps in the path —
translation, query expansion, reranking — make runs non-deterministic; repeat them.

## End to end, not in isolation

An arm feeds the fusion, so making it more selective changes what the fusion produces.
Measured on the keyword arm alone, dropping one-character parts of hyphenated tokens looked
like a win (hit@5 0.800 → 0.829); end to end it was a loss (0.790 → 0.768 across four runs)
and was reverted. The dropped fragment had been the only lexical bridge to a correct passage
whose other words did not prefix-match.

## What a retrieval metric cannot see

"Was the chunk found" is not "was the question answered":

- A needle-in-haystack metric cannot show the keyword arm rescuing exact terms and section
  numbers. Measure answer quality before dropping an arm on a recall number.
- More context is not a better answer. Raising top-k from 15 to 30 lifted recall to 80.4%
  while the judged share of covered claims fell from 82.1% to 78.8%.

## Traps that produce a confident wrong number

- **Ground truth pointing at documents no longer in the corpus.** Every metric read 0.000
  after a re-ingest, because each expected id resolved to nothing.
- **Ground truth resolved by filename.** Deduplication retired the file the fixtures named
  in favour of a fuller copy under another name; 8 of 92 answerable questions scored as
  misses, about 5 points of under-reporting. Resolve by a stable id or title, and count how
  many expected ids still resolve after every re-ingest.
- **An id type mismatch.** bigint ids arriving as strings made a strict comparison fail
  everywhere: 0% recall, from a bug rather than the retriever.
- **A baseline measured while an arm was dead.** Every number recorded while the keyword
  arm silently returned nothing describes a different system — including findings such as
  "fusion weights have no effect", which is trivially true when one side is always empty.

## Measured not to help

On at least one corpus each — re-measure on yours before relying on it:

- **HyDE.** Question plus a generated answer found one more question out of 92, ranked
  worse, cost an LLM call per search, and turned the keyword query into an 80-word paragraph
  at six times the latency.
- **Translating into a keyword list** instead of a question (see `finnish.md`).
- **Ordering documents by hit count** instead of fusing best-chunk rank with density.
- **Raising `hnsw.ef_search` on a corpus of a few thousand rows** — the index already
  returns exact neighbours.
- **BM25 via a Postgres extension on a small corpus.** `ts_rank_cd` lacks IDF and
  term-frequency saturation, and both showed on a ~2,000-chunk corpus, but a deterministic
  fix already covered the visible symptom and the extension would have changed the database
  requirement for an unmeasured gain. Revisit when the corpus grows by an order of
  magnitude — the way to test it is to swap only the keyword arm's scoring and re-run the
  same sets.
