# Video Search Evaluation

Retrieval-quality evaluation for semantic video search — does the right moment in
the right lecture come back near the top when a user asks a natural-language
question? Measured repeatably in Finnish, English, and Swedish against an
LLM-built, human-triaged answer key.

> The full evaluation harness, dataset, and run history live in the separate
> **gaik-evals** repository under
> [`projects/qadental-video-search`](https://github.com/GAIK-project/gaik-evals/tree/main/projects/qadental-video-search).
> This page summarises the method and the current numbers; that repo is the
> source of truth and the place to reproduce them.

---

## 1. Evaluation Metrics

### 1.1 List of Metrics

The evaluation scores each query at the segment level using standard
information-retrieval metrics:

- Hit@K (K = 1, 5, 10)
- MRR (Mean Reciprocal Rank)
- NDCG@K (Normalized Discounted Cumulative Gain)
- Recall@K
- segment-NDCG@K (boundary-precision via Intersection-over-Union)

### 1.2 Metric Descriptions

#### Hit@K

- Definition:
  - Fraction of queries where at least one relevant segment appears in the top K results.
- Formula:

```text
Hit@K = (queries with ≥1 relevant hit in top K) / (total queries)
```

- Components:
  - A returned hit is "relevant" when `relevance ≥ 2` after matching (same video + time overlap).
- Business interpretation:
  - `Hit@1` = how often the very first result is already right.
  - `Hit@10` = how often the right moment is anywhere on the first page.
  - `Hit@10` ≥ `Hit@5` ≥ `Hit@1` always; a large `Hit@10`/`Hit@1` gap means the right lecture moment is found but not ranked first.
- Reference values: No universal thresholds; higher is better. Coverage (`Hit@10`) saturating near ~0.85 with a lower `Hit@1` points to a ranking-position problem, not a coverage problem.

#### MRR (Mean Reciprocal Rank)

- Definition:
  - Average of `1 / rank` of the first relevant hit per query (0 if none in the top K).
- Formula:

```text
MRR = mean( 1 / rank_of_first_relevant_hit )
```

- Business interpretation:
  - Rewards putting a relevant result early. `1.0` = always rank 1, `0.5` ≈ typically rank 2, `0.33` ≈ rank 3. Only cares about the first relevant hit.
- Reference values: No universal thresholds; higher is better.

#### NDCG@K

- Definition:
  - Quality-of-ordering metric — rewards placing more-relevant items higher, with a logarithmic position discount, normalized against the ideal ranking.
- Formula:

```text
DCG  = Σ  relᵢ / log₂(i + 2)         (i = 0-based rank)
IDCG = same sum for the ideal ordering
NDCG = DCG / IDCG
```

- Components:
  - Uses the graded relevance scale (`2` fully / `1` partially / `0` not relevant) directly.
- Business interpretation:
  - `1.0` = perfect ordering; lower = relevant items buried under irrelevant ones. The most complete single-number quality signal because it accounts for every hit's position.
- Reference values: No universal thresholds; higher is better.

#### Recall@K

- Definition:
  - Of all the relevant expected segments for a query, the fraction whose content was retrieved somewhere in the top K.
- Formula:

```text
Recall@K = found_relevant_segments / total_relevant_expected
```

- Business interpretation:
  - Completeness/coverage. High `Hit@K` but low `Recall@K` means "we find *a* good moment but miss the *other* good moments."
- Reference values: No universal thresholds; higher is better.

#### segment-NDCG@K

- Definition:
  - The strict temporal-precision metric. Grades each hit by the Intersection-over-Union (IoU) of its time window against the exact evidence window, then feeds that fraction into the NDCG formula.
- Formula:

```text
IoU = seconds_of_overlap / seconds_of_combined_span        (0.0 … 1.0)
segment_NDCG = NDCG computed with per-hit IoU as the gain
```

- Business interpretation:
  - Temporal precision of localization. A high `Hit@10` with a low `segment-NDCG@10` (~0.13 in the current baseline) means "we reliably surface the right region of the right lecture, but the returned clip's start/end don't tightly hug the exact evidence span." A stretch goal, not a pass/fail gate.
  - Note: unlike the others, this metric ignores the ±2 s tolerance — it measures raw boundary alignment.
- Reference values: No universal thresholds; higher is better.

---

## 2. Evaluation Tools / Code

### 2.1 Python Scripts

The runnable scripts live in the **gaik-evals** repo
([`projects/qadental-video-search/scripts/`](https://github.com/GAIK-project/gaik-evals/tree/main/projects/qadental-video-search/scripts)):

- **`run_search_eval.py`**
  - Search API client + scorer. Fans out over query × language, POSTs to the live `/api/search`, matches returned hits to the answer key, and computes Hit@K / MRR / NDCG@K / Recall@K / segment-NDCG.
  - Input: `ground-truth/queries.json` + live API → Output: `results/latest.md` + `results/_summary.json`.
- **`bench_embeddings.py`**
  - In-memory embedding-model comparator — scores candidate embedding models against the same answer key without reindexing the production database.
- **`generate_ground_truth.py`**
  - Builds the answer key: an LLM proposer reads each lecture's subtitles and proposes queries + evidence ranges; a separate LLM judge accepts / flags / discards each pair.
- **`translate_queries.py`**
  - Adds `en` and `sv` variants to each accepted Finnish query (natural search query, not a literal translation).
- **`download_srts.py`**
  - Stages Finnish SRT subtitle fixtures from the production DB + S3, recording a sha256 per file for idempotent regeneration.

### 2.2 Python Dependencies

The scoring runner needs only `requests` + `python-dotenv` (`uv sync` at the
gaik-evals repo root). Ground-truth regeneration/translation additionally needs
Azure OpenAI access via the OpenAI Agents SDK + LiteLLM.

### 2.3 Reproducibility Inputs

Committed in the gaik-evals project:
- `ground-truth/queries.json` — the golden set (237 annotated + 18 customer seed queries).
- `ground-truth/srt/` — committed SRT fixtures the labels are generated from.
- `results/latest.md` — the latest committed numbers (overwritten on every run).

---

## 3. Evaluations / Comparisons

### 3.1 Evaluation Setup / Context

Evaluation context:
- Domain: QAdental — transcribed Finnish dental-lecture videos (webinars, procedures, case discussions, vodcasts).
- Language: Finnish corpus; queries scored in Finnish, English, and Swedish.
- Content: 51 lecture videos, ~1,989 transcript segments; 237 annotated queries carrying 513 expected segments, every pair judged by `gpt-5.4`.
- Goal: measure whether the live hybrid search returns the right lecture moment near the top of the results.

Pipeline under test (the deployed app): non-FI → FI query translation → semantic
(pgvector HNSW, `halfvec(3072)`, `text-embedding-3-large`) + keyword (Postgres
FTS) → RRF fusion (`k = 60`) → trigram fallback.

### 3.2 Performance Comparison Table

Live API, `searchMode = hybrid`, `k = 10`, time tolerance ±2.0 s, mean latency
~1,434 ms. Best value per column in **bold**.

| Language | n | Hit@1 | Hit@5 | Hit@10 | MRR | NDCG@10 | Recall@10 | segment-NDCG@10 |
|----------|---|-------|-------|--------|-----|---------|-----------|-----------------|
| Finnish (fi) | 237 | 0.456 | 0.747 | 0.819 | 0.582 | 0.544 | 0.738 | 0.132 |
| English (en) | 236 | 0.466 | 0.729 | 0.805 | 0.577 | 0.517 | 0.694 | 0.129 |
| Swedish (sv) | 236 | **0.496** | **0.788** | **0.852** | **0.619** | **0.551** | **0.745** | **0.134** |

*Numbers from `results/latest.md`; that file is overwritten on every eval run, so
treat the gaik-evals repo as the live source.*

### 3.3 Key Findings / Observations

- **Coverage is saturated, ranking position is the gap.** `Hit@10` sits at ~0.81–0.85 while `Hit@1` is ~0.46–0.50 — the right moment is almost always on the first page, just not in slot #1.
- **Performance is remarkably uniform across languages.** Swedish edges ahead and English trails slightly; the embedding model is strongly multilingual on its own, so the translate-+-fusion path adds little for non-Finnish queries.
- **Boundary precision is the next frontier.** `segment-NDCG@10` ≈ 0.13 — the right region is found, but the clip boundaries are loose relative to the exact evidence span (the backend chunks video into coarser windows than the judge's cue ranges).
- **Cheap tuning levers are flat; a reranker regressed quality** (see §4).

---

## 4. Performance Issues (Errors)

### 4.1 List of Common Error Categories

#### Fundamental (need a bigger lever)

| Error Type | Description | Examples | Why / Fix Strategy |
|-----------|-------------|----------|--------------------|
| **Ranking-position miss** | Relevant moment is retrieved but not ranked #1 | `Hit@10` ≈ 0.85 but `Hit@1` ≈ 0.5 | Needs better multilingual embeddings or a proven reranker — not cheap tuning |
| **Loose clip boundaries** | Returned window overlaps the evidence but doesn't hug it | `segment-NDCG@10` ≈ 0.13 | Finer chunking / segmentation of the transcript |

#### Tunable but measured as non-wins on this corpus

| Error Type | Description | Examples | Why / Fix Strategy |
|-----------|-------------|----------|--------------------|
| **Keyword side barely fires** | AND-of-all-prefixes `tsquery` rarely matches a long auto-generated question | RRF weight sweeps produce identical numbers | Untested candidate: OR/quorum `tsquery` for long queries |
| **Recall knob has no effect** | At ~2k vectors the HNSW index already returns exact neighbours | `ef_search` 40 → 200 → exact: identical `Hit@10` | "Raise `ef_search` for recall" simply doesn't apply below ~10k vectors |

#### Regressions (do NOT adopt)

| Error Type | Description | Examples | Why / Fix Strategy |
|-----------|-------------|----------|--------------------|
| **Reranker hurts** | An LLM reranker over the semantic top-20 made every metric worse on Finnish (n=60) | `Hit@1` −0.017, MRR −0.049, `Hit@10` −0.033 | Do not add a reranker without A/B proof clearing +3 pp `Hit@5` on the Finnish corpus |

### 4.2 Side-by-Side Input-Output Examples

_N/A — to be completed._

---

## 5. Improvement Strategies

### 5.1 High-Level Improvement Strategies

Coverage@10 is saturated and ranking position is the gap, but the cheap levers
can't move either. The remaining levers are bigger and must each be A/B'd against
the ground truth before adoption (the `postgres-semantic-search` rule: adopt only
on ≥ +3 pp `Hit@5`, reject otherwise):

- **Better embeddings** — a Finnish-tuned / multilingual model (compared via `bench_embeddings.py`); a swap also needs a reseed of the embedding column.
- **Finer chunking / segmentation** — lifts both ranking and the low `segment-NDCG@10`.
- **Relax the keyword side for long queries** — OR/quorum `tsquery` instead of AND-of-all-prefixes, so the keyword signal actually contributes (untested).

### 5.2 Mapping Table: Performance Issues → Improvement Strategies

| Performance issue / error | Improvement strategy |
|--------------------------|----------------------|
| Ranking-position miss (low `Hit@1`) | A/B a better multilingual embedding model; A/B a dedicated multilingual cross-encoder reranker behind a flag |
| Loose clip boundaries (low `segment-NDCG`) | Finer transcript chunking / segmentation |
| Keyword side barely fires | OR/quorum `tsquery` for long queries |
| Per-language gaps (en/sv below fi) | Inspect the non-FI → FI translation + RRF fusion path |

---

## Reproduction Notes (Usage Guide)

All commands run from the **gaik-evals** repo root, with the relevant keys in
`.env`.

### Running the live benchmark

Scores the deployed API against the answer key and writes `results/latest.md`.

```bash
uv run python projects/qadental-video-search/scripts/run_search_eval.py
```

**Outputs:**
- `results/latest.md` — committed human-readable per-language table.
- `results/_summary.json` — full per-query detail (regenerated).

### Smoke run (no answer key needed)

```bash
uv run python projects/qadental-video-search/scripts/run_search_eval.py --smoke
```

### Comparing embedding models in-memory (no reindex)

```bash
uv run python projects/qadental-video-search/scripts/bench_embeddings.py
```

**Sample output:**

```text
- mode: hybrid, k: 10, time tolerance: ±2.0s
- runs total: 765 (annotated: 711, failed: 3)

| lang | n   | hit@1 | hit@5 | hit@10 | mrr   | ndcg@10 | recall@10 | segment_ndcg@10 |
|------|-----|-------|-------|--------|-------|---------|-----------|-----------------|
| fi   | 237 | 0.456 | 0.747 | 0.819  | 0.582 | 0.544   | 0.738     | 0.132           |
```

---

## Integration with GAIK Toolkit

### Evaluating a semantic-search deployment

This eval treats the search service as a black box behind its REST API, so the
same harness works for any deployment built on GAIK's pgvector / RAG retrieval
components. Point the runner at your endpoint:

```text
POST https://<your-search-host>/api/search
Headers:  Authorization: Bearer <SEARCH_API_KEY>
          Content-Type: application/json
Body:     { "query": "fluoride and xylitol", "k": 8, "searchMode": "hybrid" }
```

To assess retrieval *coverage* at the chunk level instead (no live API), pair this
with the deterministic [RAG Evaluation](../RAG_eval/README.md) suite.

### Supported Use Cases

- **Semantic video search** — natural-language search over transcribed lecture / webinar / meeting recordings.
- **Knowledge-base search** — measuring whether the right passage surfaces near the top for a user question.
- **Multilingual retrieval QA** — comparing per-language retrieval quality on a single-language corpus.

---

## Installation & Setup

### 1. Install Dependencies

```bash
git clone https://github.com/GAIK-project/gaik-evals
cd gaik-evals
uv sync
```

### 2. Configure API Access

Set `SEARCH_API_KEY` (Bearer token for the search API) in the repo-root `.env`;
optionally `SEARCH_BASE` to override the API URL. Ground-truth regeneration /
translation additionally needs `AZURE_API_KEY` + `AZURE_RESOURCE_NAME`. A missing
key skips that step rather than erroring.

---

## Related Resources

- **Evaluation harness & dataset (gaik-evals)**: [projects/qadental-video-search](https://github.com/GAIK-project/gaik-evals/tree/main/projects/qadental-video-search)
- **Use case — Semantic Video Search**: [/use-cases/semantic-video-search](https://gaik-project.github.io/gaik-toolkit/use-cases/semantic-video-search)
- **RAG Evaluation (chunk-level coverage)**: [../RAG_eval/README.md](../RAG_eval/README.md)
- **Evaluation Methods Overview**: [../README.md](../README.md)
- **Project Website**: [gaik.ai](https://gaik.ai)
- **Documentation**: [https://gaik-project.github.io/gaik-toolkit/](https://gaik-project.github.io/gaik-toolkit/)
