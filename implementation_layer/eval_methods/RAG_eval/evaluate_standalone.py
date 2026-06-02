"""
Standalone RAG retrieval evaluation.

Loads a target text and a ranked list of retrieved chunks from plain .txt files,
computes retrieval metrics using compute_retrieval_metrics() from rag_eval.py,
and prints a formatted report.

Usage:
    python evaluate_standalone.py

Inputs (edit paths below or pass as arguments):
    data/target.txt              — the gold/ground-truth passage to retrieve
    data/chunks/chunk_1.txt ...  — retrieved chunks in ranked order (best first)

No external dependencies required — uses only Python standard library.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

# ---------------------------------------------------------------------------
# compute_retrieval_metrics — copied from rag_eval.py (stdlib only, no deps)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\w+(?:[.-]\w+)*", flags=re.UNICODE)


def compute_retrieval_metrics(
    target_text: str,
    chunks: list,
    min_token_match: int = 4,
    n_gram: int = 4,
) -> dict:
    zeros = {
        "token_recall": None, "retrieval_efficiency": None, "token_f1": None,
        "coverage_continuity": None, "gap_count": None, "mean_gap_size": None,
        "chunk_redundancy": None,
        f"{n_gram}gram_recall": None, f"{n_gram}gram_precision": None,
        f"{n_gram}gram_f1": None, f"{n_gram}gram_iou": None,
        "mrr": None, "rank_weighted_coverage": None,
        "effective_chunk_ratio": None, "min_k_full_coverage": None,
    }
    if not target_text or not chunks:
        return zeros
    target_tokens = _TOKEN_RE.findall(target_text.lower())
    n_target = len(target_tokens)
    if n_target == 0:
        return zeros
    effective_min = min(min_token_match, n_target)
    chunks_tokenized = [_TOKEN_RE.findall(c.lower()) for c in chunks]
    total_retrieved_tokens = sum(len(ct) for ct in chunks_tokenized)
    n_chunks = len(chunks)
    covered_target = [False] * n_target
    total_matched_tokens = 0
    first_hit_rank = None
    cumulative_coverages = []
    chunks_with_new = 0
    for k, chunk_tokens in enumerate(chunks_tokenized):
        matcher = SequenceMatcher(None, target_tokens, chunk_tokens, autojunk=False)
        chunk_new = 0
        chunk_had_match = False
        for m in matcher.get_matching_blocks():
            if m.size >= effective_min:
                chunk_had_match = True
                for i in range(m.a, m.a + m.size):
                    total_matched_tokens += 1
                    if not covered_target[i]:
                        chunk_new += 1
                    covered_target[i] = True
        if chunk_had_match and first_hit_rank is None:
            first_hit_rank = k + 1
        if chunk_new > 0:
            chunks_with_new += 1
        cumulative_coverages.append(sum(covered_target) / n_target)
    unique_covered = sum(covered_target)
    tok_rec = unique_covered / n_target
    tok_eff = unique_covered / total_retrieved_tokens if total_retrieved_tokens > 0 else 0.0
    tok_f1 = 2 * tok_rec * tok_eff / (tok_rec + tok_eff) if (tok_rec + tok_eff) > 0 else 0.0
    max_run = current_run = 0
    for c in covered_target:
        if c:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    coverage_continuity = max_run / n_target
    first_true = last_true = None
    for i, c in enumerate(covered_target):
        if c:
            if first_true is None:
                first_true = i
            last_true = i
    gap_count = 0
    gap_sizes = []
    if first_true is not None and last_true is not None:
        in_gap = False
        gs = 0
        for i in range(first_true, last_true + 1):
            if not covered_target[i]:
                in_gap, gs = True, gs + 1
            else:
                if in_gap:
                    gap_count += 1
                    gap_sizes.append(gs)
                    in_gap, gs = False, 0
        if in_gap:
            gap_count += 1
            gap_sizes.append(gs)
    mean_gap_size = sum(gap_sizes) / len(gap_sizes) if gap_sizes else 0.0
    chunk_redundancy = (
        (total_matched_tokens - unique_covered) / total_matched_tokens
        if total_matched_tokens > 0 else 0.0
    )
    mrr = 1.0 / first_hit_rank if first_hit_rank is not None else 0.0
    rank_weighted_coverage = sum(cumulative_coverages) / n_chunks
    effective_chunk_ratio = chunks_with_new / n_chunks
    final_coverage = cumulative_coverages[-1]
    min_k_full = n_chunks
    for i, c in enumerate(cumulative_coverages):
        if abs(c - final_coverage) < 1e-9:
            min_k_full = i + 1
            break

    def _ngrams(tokens, n):
        return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}

    target_ngrams = _ngrams(target_tokens, n_gram)
    result = {
        "token_recall": round(tok_rec, 4), "retrieval_efficiency": round(tok_eff, 4),
        "token_f1": round(tok_f1, 4), "coverage_continuity": round(coverage_continuity, 4),
        "gap_count": gap_count, "mean_gap_size": round(mean_gap_size, 4),
        "chunk_redundancy": round(chunk_redundancy, 4), "mrr": round(mrr, 4),
        "rank_weighted_coverage": round(rank_weighted_coverage, 4),
        "effective_chunk_ratio": round(effective_chunk_ratio, 4),
        "min_k_full_coverage": min_k_full,
    }
    if not target_ngrams:
        result.update({f"{n_gram}gram_recall": None, f"{n_gram}gram_precision": None,
                       f"{n_gram}gram_f1": None, f"{n_gram}gram_iou": None})
        return result
    retrieved_ngrams = set()
    for ct in chunks_tokenized:
        retrieved_ngrams.update(_ngrams(ct, n_gram))
    if not retrieved_ngrams:
        result.update({f"{n_gram}gram_recall": None, f"{n_gram}gram_precision": None,
                       f"{n_gram}gram_f1": None, f"{n_gram}gram_iou": None})
        return result
    intersection = target_ngrams & retrieved_ngrams
    union = target_ngrams | retrieved_ngrams
    len_i, len_t, len_r = len(intersection), len(target_ngrams), len(retrieved_ngrams)
    ng_rec = len_i / len_t
    ng_prec = len_i / len_r
    ng_f1 = 2 * ng_rec * ng_prec / (ng_rec + ng_prec) if (ng_rec + ng_prec) > 0 else 0.0
    ng_iou = len_i / len(union)
    result.update({
        f"{n_gram}gram_recall": round(ng_rec, 4), f"{n_gram}gram_precision": round(ng_prec, 4),
        f"{n_gram}gram_f1": round(ng_f1, 4), f"{n_gram}gram_iou": round(ng_iou, 4),
    })
    return result

# ---------------------------------------------------------------------------
# Configuration — edit these paths to point to your own data
# ---------------------------------------------------------------------------

TARGET_FILE = "data/target.txt"
CHUNKS_DIR  = "data/chunks"   # .txt files in this folder, loaded in sorted order

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

target_text = Path(TARGET_FILE).read_text(encoding="utf-8").strip()

chunk_files = sorted(Path(CHUNKS_DIR).glob("*.txt"))
assert chunk_files, f"No .txt files found in {CHUNKS_DIR}"

chunks = [f.read_text(encoding="utf-8").strip() for f in chunk_files]

print(f"Target text : {len(target_text.split())} words")
print(f"Chunks loaded: {len(chunks)} (from {CHUNKS_DIR}/)")
for i, (f, c) in enumerate(zip(chunk_files, chunks), 1):
    print(f"  Chunk {i}: {f.name} — {len(c.split())} words")

# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

metrics = compute_retrieval_metrics(target_text, chunks)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("RETRIEVAL EVALUATION RESULTS")
print("=" * 60)

print("\n--- Token Coverage ---")
print(f"  token_recall         : {metrics['token_recall']:.4f}   (fraction of target tokens covered)")
print(f"  retrieval_efficiency : {metrics['retrieval_efficiency']:.4f}   (coverage per retrieved token)")
print(f"  token_f1             : {metrics['token_f1']:.4f}   (harmonic mean of recall and efficiency)")

print("\n--- Coverage Structure ---")
print(f"  coverage_continuity  : {metrics['coverage_continuity']:.4f}   (longest contiguous covered span / target)")
print(f"  gap_count            : {metrics['gap_count']}          (internal uncovered gaps)")
print(f"  mean_gap_size        : {metrics['mean_gap_size']:.4f}   (average gap length in tokens)")
print(f"  chunk_redundancy     : {metrics['chunk_redundancy']:.4f}   (fraction of matched tokens that are duplicates)")

print("\n--- Rank-Aware ---")
print(f"  mrr                  : {metrics['mrr']:.4f}   (mean reciprocal rank of first hit)")
print(f"  rank_weighted_cov    : {metrics['rank_weighted_coverage']:.4f}   (avg cumulative coverage over all ranks)")
print(f"  effective_chunk_ratio: {metrics['effective_chunk_ratio']:.4f}   (fraction of chunks that add new coverage)")
print(f"  min_k_full_coverage  : {metrics['min_k_full_coverage']}          (fewest top-k chunks for full coverage)")

print("\n--- 4-Gram Overlap ---")
print(f"  4gram_recall         : {metrics['4gram_recall']:.4f}")
print(f"  4gram_precision      : {metrics['4gram_precision']:.4f}")
print(f"  4gram_f1             : {metrics['4gram_f1']:.4f}")
print(f"  4gram_iou            : {metrics['4gram_iou']:.4f}   (intersection over union)")

print("\n" + "=" * 60)
