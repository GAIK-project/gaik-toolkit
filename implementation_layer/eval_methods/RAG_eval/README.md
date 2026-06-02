# RAG Evaluation

Deterministic retrieval quality assessment for RAG pipelines. Evaluates how well a set of retrieved chunks covers a target text using token-level, rank-aware, and n-gram metrics — no LLM calls required.

---

## 1. Evaluation Metrics

### 1.1 List of Metrics

The evaluation computes 14 deterministic metrics grouped into three categories:

**Token Coverage (3 metrics):**
- Token Recall
- Retrieval Efficiency
- Token F1

**Coverage Structure (4 metrics):**
- Coverage Continuity
- Gap Count
- Mean Gap Size
- Chunk Redundancy

**Rank-Aware (4 metrics):**
- MRR (Mean Reciprocal Rank)
- Rank-Weighted Coverage
- Effective Chunk Ratio
- Min-K Full Coverage

**4-Gram Overlap (4 metrics):**
- 4-Gram Recall
- 4-Gram Precision
- 4-Gram F1
- 4-Gram IoU

### 1.2 Metric Descriptions

#### Token Recall

- Definition:
  - Fraction of target text tokens that are covered by at least one retrieved chunk.
- Formula:

```text
Token Recall = Unique Covered Tokens / Total Target Tokens
```

- Business interpretation:
  - High recall means the retrieved chunks collectively contain most of the relevant information.
  - A low recall means important parts of the source passage are missing from retrieval.

#### Retrieval Efficiency

- Definition:
  - How much new coverage is gained per retrieved token — penalizes redundant retrieval.
- Formula:

```text
Retrieval Efficiency = Unique Covered Tokens / Total Retrieved Tokens
```

- Business interpretation:
  - High efficiency means the retrieved chunks are dense in relevant content with little redundancy.
  - Low efficiency indicates the system is retrieving many tokens but most are repeated or irrelevant.

#### Token F1

- Definition:
  - Harmonic mean of Token Recall and Retrieval Efficiency.
- Formula:

```text
Token F1 = 2 · Recall · Efficiency / (Recall + Efficiency)
```

- Business interpretation:
  - The primary single-number summary of retrieval quality. Balances coverage and precision.

#### Coverage Continuity

- Definition:
  - Length of the longest contiguous span of covered target tokens, normalized by target length.
- Formula:

```text
Coverage Continuity = Max Contiguous Covered Run / Total Target Tokens
```

- Business interpretation:
  - High continuity means chunks cover the target passage in a coherent, unbroken span.
  - Low continuity with high recall means coverage is scattered — the answer may feel fragmented.

#### Gap Count

- Definition:
  - Number of internal uncovered gaps within the covered region of the target.
- Business interpretation:
  - Each gap represents a stretch of the target that no retrieved chunk covers.
  - Lower is better; zero gaps with high recall means complete contiguous coverage.

#### Mean Gap Size

- Definition:
  - Average size of internal gaps in tokens.
- Business interpretation:
  - Large mean gaps indicate that important stretches of the target passage are being skipped.

#### Chunk Redundancy

- Definition:
  - Fraction of matched tokens that overlap with tokens already covered by earlier chunks.
- Formula:

```text
Chunk Redundancy = (Total Matched Tokens − Unique Covered Tokens) / Total Matched Tokens
```

- Business interpretation:
  - High redundancy means many retrieved chunks repeat content already covered by earlier-ranked chunks.
  - Use to evaluate reranking effectiveness and chunk deduplication.

#### MRR (Mean Reciprocal Rank)

- Definition:
  - Reciprocal of the rank of the first chunk that matches the target.
- Formula:

```text
MRR = 1 / Rank of First Matching Chunk
```

- Business interpretation:
  - MRR = 1.0 if the best-ranked chunk already matches. Lower values mean relevant content appears deeper in the ranked list.

#### Rank-Weighted Coverage

- Definition:
  - Average cumulative coverage across all ranks — rewards systems that surface relevant content early.
- Formula:

```text
Rank-Weighted Coverage = Σ(cumulative_coverage_at_rank_k) / N_chunks
```

- Business interpretation:
  - Higher values mean coverage builds up quickly with the first few chunks rather than slowly across many.

#### Effective Chunk Ratio

- Definition:
  - Fraction of retrieved chunks that contribute at least one new covered token.
- Formula:

```text
Effective Chunk Ratio = Chunks with New Coverage / Total Chunks
```

- Business interpretation:
  - Low ratio means many retrieved chunks are fully redundant.

#### Min-K Full Coverage

- Definition:
  - The minimum number of top-ranked chunks needed to reach the same total coverage as the full retrieved set.
- Business interpretation:
  - Lower values mean the retrieval is efficient — a small number of top chunks is enough.
  - If Min-K = total chunks, every chunk is necessary; if Min-K = 1, the top chunk alone covers everything.

#### 4-Gram Recall, Precision, F1, IoU

- Definition:
  - Set-based overlap metrics computed over 4-grams (sequences of 4 consecutive tokens) from target and retrieved texts.
- Formulas:

```text
4-Gram Recall    = |Target ∩ Retrieved| / |Target|
4-Gram Precision = |Target ∩ Retrieved| / |Retrieved|
4-Gram F1        = 2 · Recall · Precision / (Recall + Precision)
4-Gram IoU       = |Target ∩ Retrieved| / |Target ∪ Retrieved|
```

- Business interpretation:
  - N-gram metrics capture phrase-level overlap, not just individual token matches.
  - Useful for detecting whether the retrieval preserves multi-word expressions and domain terminology.

---

## 2. Evaluation Tools / Code

### 2.1 Python Scripts

- **`rag_eval.py`**
  - Contains `compute_retrieval_metrics(target_text, chunks)` — the standalone evaluation function.
  - Also contains the full GAIK benchmark pipeline (`run_benchmark()`) for evaluating a config grid (embedding model × chunking strategy × retriever) against a CSV test dataset.

- **`evaluate_standalone.py`**
  - Simple runner script that loads `data/target.txt` and all `.txt` files from `data/chunks/` in sorted order, runs `compute_retrieval_metrics()`, and prints a formatted report.
  - Contains `compute_retrieval_metrics()` inlined — no imports from `rag_eval.py` and no external dependencies. Runs with Python standard library only.
  - Intended as a starting point; modify the paths to point to your own data.

### 2.2 Python Dependencies

For `evaluate_standalone.py` (standalone use):
- No external packages required — pure Python standard library.

For `rag_eval.py` full benchmark mode:
- `pandas` — test dataset loading and results output
- `python-dotenv` — API key management
- GAIK RAG components (`src.rag_engine`, `src.data_processor`, `src.config`, `src.models`) — provided by the GAIK toolkit

### 2.3 Sample Data

The `data/` folder contains sample files for running the standalone evaluation immediately:

```
data/
├── target.txt              — gold/ground-truth passage (what the retriever should cover)
└── chunks/
    ├── chunk_1.txt         — highest-ranked retrieved chunk
    ├── chunk_2.txt         — second-ranked chunk
    └── chunk_3.txt         — third-ranked chunk
```

The sample target and chunks describe a RAG pipeline to demonstrate the metrics. **Replace these files with your own data** to evaluate your RAG retrieval. See the [Customization Guide](#customization-guide) below.

---

## 3. Results

_N/A — to be completed._

---

## 4. Performance Issues

- **Low token recall** — the retrieved chunks are missing significant portions of the relevant passage. Common causes: chunk size too small, similarity top-k too low, or embedding model not suited to the domain.
- **High chunk redundancy** — multiple retrieved chunks repeat the same content. Common causes: dense overlapping chunks, insufficient reranking, or a document that is naturally repetitive.
- **High gap count** — coverage is scattered across the target passage. Common cause: the relevant content spans multiple non-adjacent sections that are split across different chunks.
- **Low MRR** — relevant content only appears in lower-ranked chunks. Common cause: the embedding model or retriever is not ranking the most relevant chunk first.
- **Low 4-gram metrics with reasonable token recall** — individual tokens are covered but key phrases are fragmented across different chunks. Common cause: chunk boundaries cutting through important multi-word expressions.

---

## 5. Improvement Strategies

### 5.1 Mapping Table: Issues → Improvement Strategies

| Performance issue | Improvement strategy |
|------------------|----------------------|
| Low token recall | Increase `similarity_top_k`; try a larger or domain-adapted embedding model; use hierarchical chunking |
| High chunk redundancy | Add a deduplication step after retrieval; reduce `chunk_overlap`; use reranking to select diverse chunks |
| High gap count | Use larger chunk sizes to keep related content together; try hierarchical chunking strategies |
| Low MRR | Tune the embedding model; add a reranker; use hybrid retrieval (dense + sparse) |
| Low 4-gram metrics | Reduce chunk size to avoid phrase fragmentation; use smaller overlap to reduce boundary artifacts |
| Low coverage continuity | Prefer `automerging` retriever for hierarchical chunks; increase `rerank_top_n` |

---

## Reproduction Notes (Usage Guide)

### Running the standalone evaluation

```bash
cd implementation_layer/eval_methods/RAG_eval
python evaluate_standalone.py
```

The script reads `data/target.txt` as the ground truth and all `.txt` files in `data/chunks/` in sorted filename order as the ranked retrieved chunks, then prints a full metrics report.

**Sample output:**

```
Target text : 97 words
Chunks loaded: 3 (from data/chunks/)
  Chunk 1: chunk_1.txt — 38 words
  Chunk 2: chunk_2.txt — 34 words
  Chunk 3: chunk_3.txt — 35 words

============================================================
RETRIEVAL EVALUATION RESULTS
============================================================

--- Token Coverage ---
  token_recall         : 0.9200   (fraction of target tokens covered)
  retrieval_efficiency : 0.8400   (coverage per retrieved token)
  token_f1             : 0.8780   (harmonic mean of recall and efficiency)

--- Coverage Structure ---
  coverage_continuity  : 0.7600   (longest contiguous covered span / target)
  gap_count            : 2        (internal uncovered gaps)
  mean_gap_size        : 3.5000   (average gap length in tokens)
  chunk_redundancy     : 0.2300   (fraction of matched tokens that are duplicates)

--- Rank-Aware ---
  mrr                  : 1.0000   (mean reciprocal rank of first hit)
  rank_weighted_cov    : 0.8900   (avg cumulative coverage over all ranks)
  effective_chunk_ratio: 1.0000   (fraction of chunks that add new coverage)
  min_k_full_coverage  : 3        (fewest top-k chunks for full coverage)

--- 4-Gram Overlap ---
  4gram_recall         : 0.8600
  4gram_precision      : 0.7900
  4gram_f1             : 0.8200
  4gram_iou            : 0.6900   (intersection over union)
============================================================
```

---

## Customization Guide

### Using your own target text and retrieved chunks

1. Replace `data/target.txt` with your gold/ground-truth passage — this is the text that a perfect retrieval should cover. In a RAG evaluation context, this is typically the reference answer's source passage or a manually annotated citation segment.

2. Place your retrieved chunks as individual `.txt` files in `data/chunks/`, named so they sort in ranked order:
   - `chunk_1.txt` — best-ranked chunk (highest similarity score)
   - `chunk_2.txt` — second-ranked
   - `chunk_3.txt` — third-ranked
   - ... and so on

3. Run `python evaluate_standalone.py`.

### Using `compute_retrieval_metrics()` directly in your own code

```python
from rag_eval import compute_retrieval_metrics

target_text = "The target passage text..."
chunks = [
    "First retrieved chunk text...",
    "Second retrieved chunk text...",
    "Third retrieved chunk text...",
]

# Chunks must be in ranked order — best ranked first
metrics = compute_retrieval_metrics(target_text, chunks)

print(f"Token Recall : {metrics['token_recall']:.4f}")
print(f"Token F1     : {metrics['token_f1']:.4f}")
print(f"MRR          : {metrics['mrr']:.4f}")
print(f"4-Gram IoU   : {metrics['4gram_iou']:.4f}")
```

**Parameters:**
- `target_text` (str) — the gold text the retrieval should cover
- `chunks` (list[str]) — retrieved chunks in ranked order (best first)
- `min_token_match` (int, default 4) — minimum consecutive token sequence to count as a match. Increase for stricter matching; decrease for short texts.
- `n_gram` (int, default 4) — n-gram size for set Jaccard metrics. Change to 3 for shorter texts.

### Running the full GAIK benchmark

The full benchmark (`run_benchmark()` in `rag_eval.py`) evaluates a config grid of embedding models, chunk sizes, and retriever strategies against a CSV test dataset. It requires:
- A test CSV with columns: `node`, `question`, `files`, `answer`, `citation`
- GAIK RAG infrastructure (`src.rag_engine`, `src.data_processor`, `src.config`)
- ChromaDB indices built for each config

Update the `CONFIGURATION` section at the top of `rag_eval.py` and run:

```bash
python rag_eval.py
```

Outputs are saved to `benchmark_results/results_detail.csv` (per-row scores) and `benchmark_results/results_summary.csv` (per-config means, ranked).

---

## Integration with GAIK Toolkit

### Evaluating GAIK RAG Retrieval

After retrieving chunks with GAIK's `RAGWorkflow` or `RAGEngine`, pass the results directly to `compute_retrieval_metrics()`:

```python
from rag_eval import compute_retrieval_metrics
from gaik.software_modules.rag_workflow import RAGWorkflow
from dotenv import load_dotenv

load_dotenv()

workflow = RAGWorkflow()
result = workflow.query("What is retrieval-augmented generation?")

# Use the gold citation as target_text
target_text = "Your manually annotated gold passage..."

# Retrieved chunks in ranked order
chunks = [node.get_content() for node in result.retrieved_nodes]

metrics = compute_retrieval_metrics(target_text, chunks)
print(f"Token F1: {metrics['token_f1']:.4f}")
print(f"MRR:      {metrics['mrr']:.4f}")
```

### Supported Use Cases

This evaluation applies to any GAIK RAG workflow:

- **Semantic video search** — evaluating whether retrieved transcript segments cover the queried topic
- **Document Q&A** — measuring whether the right passage is retrieved for each question
- **Knowledge base interrogation** — assessing retrieval coverage across organizational document corpora

---

## Installation & Setup

### 1. Install Dependencies (standalone mode)

No external packages required for `evaluate_standalone.py`. Run directly:

```bash
cd implementation_layer/eval_methods/RAG_eval
python evaluate_standalone.py
```

### 2. Install Dependencies (full benchmark mode)

```bash
pip install -r requirements.txt
```

Set your API key in `.env`:

```bash
AZURE_API_KEY=your-azure-api-key
```

---

## Related Resources

- **GAIK RAG Components**: [guidance_layer/docs/software_components/](../../../guidance_layer/docs/)
- **RAG Evaluation — Website**: [guidance_layer/website/content/docs/toolkit/evals/rag-eval.mdx](../../../guidance_layer/website/content/docs/toolkit/evals/rag-eval.mdx)
- **Extraction Evaluation**: [../extraction_eval/README.md](../extraction_eval/README.md)
- **Evaluation Methods Overview**: [../README.md](../README.md)
- **Project Website**: [gaik.ai](https://gaik.ai)
- **GitHub**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
