"""
Retrieval benchmark for TES nodes.

Evaluates chunking strategies, embedding models, and retrieval parameters
against a gold dataset of 90 samples. Bypasses the Planner — test data
specifies which node to retrieve from directly.

Pipeline per config × sample:
  1. Retrieve chunks from subset index
  2. Fuzzy-match retrieved chunks against gold citation segments
  3. Synthesize answer from retrieved chunks
  4. LLM judge: compare synthesized answer vs gold answer

Output:
  benchmark_results/results_detail.csv  — per-row scores
  benchmark_results/results_summary.csv — per-config means, ranked
"""

import asyncio
import gc
import json
import os
import pickle
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def _ws_norm(t: str) -> str:
    """Collapse all whitespace to single spaces — mirrors LlamaIndex parser whitespace handling."""
    return " ".join(t.split())


def _strip_hws_heading_prefix(node) -> str:
    """Return the node's content with any HWS-injected heading prefix removed.

    Mirrors `_extract_heading_prefix` from rag_engine (header_path OR first
    non-empty line fallback) so both branches of the chunk-time injection are
    reversed. Must be kept in lock-step with rag_engine._parse_nodes mutations.
    """
    from src.rag_engine import _extract_heading_prefix

    content = node.get_content()
    heading = _extract_heading_prefix(node)
    if heading:
        prefix = f"{heading}\n\n"
        if content.startswith(prefix):
            return content[len(prefix) :]
    return content


# Cache of whitespace-normalized file contents keyed by absolute path.
# Files are read once per run; the same node appears in hundreds of configs.
_SOURCE_CONTENT_CACHE: dict[str, str] = {}

import pandas as pd
from dotenv import load_dotenv

from src.config import Settings
from src.data_processor import DataProcessor
from src.models import DocumentStrategy
from src.rag_engine import RAGEngine

# Load .env so os.getenv() sees AZURE_API_KEY (pydantic Settings does not populate os.environ).
load_dotenv()

# ==============================================================================
# CONFIGURATION — edit this section freely
# ==============================================================================

TEST_CSV = "data/RAG_test_dataset_merged_2026-04-15_refined.csv"
OUTPUT_DIR = "benchmark_results"

# Set True to rebuild all test indices from scratch
FORCE_REBUILD_INDICES = False

# Embedding API endpoints
# SnowflakeV2 uses local LM Studio (default in Settings)
# OpenAITextEmbedding3Large uses Azure OpenAI
AZURE_EMBEDDING_API_BASE = "https://haagahelia-poc-gaik.openai.azure.com/"
AZURE_EMBEDDING_API_KEY = os.getenv("AZURE_API_KEY", "")  # from .env — never commit real keys
AZURE_EMBEDDING_API_VERSION = "2023-05-15"

_EMBEDDING_API_OVERRIDES = {
    "OpenAITextEmbedding3Large": dict(
        embedding_api_base=AZURE_EMBEDDING_API_BASE,
        embedding_api_key=AZURE_EMBEDDING_API_KEY,
        embedding_azure_api_version=AZURE_EMBEDDING_API_VERSION,
    ),
    # SnowflakeV2, Gemma300m: use LM Studio defaults — no override needed
    # VoyageNano, FinParaphrase: ST backend — loaded directly via SentenceTransformer, no override needed
}

# Config grid — all combinations are generated automatically below.
_EMBEDDINGS = [
    "FinParaphrase",
    "VoyageNano",
    "Gemma300m",
    "SnowflakeV2",
]  # "OpenAITextEmbedding3Large"
_CHUNK_SIZES = [2000, 300, 500, 700, 800, 900, 1500]
_RERANK_TOP_N = [8]
_USE_RERANKER = [True, False]
_RETRIEVERS = ["hybrid"]
_HWS_RETRIEVERS = ["hybrid", "automerging"]  # automerging only valid for hierarchical chunkings
_HWS_CHUNK_SIZES = [600, 800, 1000, 1400]
_SIMILARITY_TOP_KS = [15]
CONFIGS = [
    dict(
        embedding=emb,
        chunking="simple",
        chunk_size=cs,
        chunk_overlap=50,
        retriever=ret,
        rerank_top_n=rtn,
        use_reranker=rnk,
        similarity_top_k=stk,
    )
    for emb in _EMBEDDINGS
    for cs in _CHUNK_SIZES
    for rtn in _RERANK_TOP_N
    for rnk in _USE_RERANKER
    for ret in _RETRIEVERS
    for stk in _SIMILARITY_TOP_KS
] + [
    dict(
        embedding=emb,
        chunking="hierarchical_with_structure",
        hws_chunk_size=hcs,
        retriever=ret,
        rerank_top_n=rtn,
        use_reranker=rnk,
        similarity_top_k=stk,
    )
    for emb in _EMBEDDINGS
    for hcs in _HWS_CHUNK_SIZES
    for rtn in _RERANK_TOP_N
    for rnk in _USE_RERANKER
    for ret in _HWS_RETRIEVERS
    for stk in _SIMILARITY_TOP_KS
]


def _validate_config(cfg: dict) -> None:
    """Crash immediately if a config is missing required keys."""
    assert "embedding" in cfg, f"Config missing 'embedding': {cfg}"
    assert "chunking" in cfg, f"Config missing 'chunking': {cfg}"
    assert "retriever" in cfg, f"Config missing 'retriever': {cfg}"
    assert "rerank_top_n" in cfg, f"Config missing 'rerank_top_n': {cfg}"
    assert "use_reranker" in cfg, f"Config missing 'use_reranker': {cfg}"
    assert isinstance(cfg["use_reranker"], bool), f"Config 'use_reranker' must be bool: {cfg}"
    assert "similarity_top_k" in cfg, f"Config missing 'similarity_top_k': {cfg}"
    if cfg["chunking"] == "simple":
        assert "chunk_size" in cfg, f"Config with chunking='simple' missing 'chunk_size': {cfg}"
        assert "chunk_overlap" in cfg, (
            f"Config with chunking='simple' missing 'chunk_overlap': {cfg}"
        )
    if cfg["chunking"] == "hierarchical_with_structure":
        assert "hws_chunk_size" in cfg, (
            f"Config with chunking='hierarchical_with_structure' missing 'hws_chunk_size': {cfg}"
        )
    assert cfg["retriever"] != "automerging" or cfg["chunking"] in (
        "hierarchical",
        "hierarchical_with_structure",
    ), f"retriever='automerging' requires hierarchical chunking: {cfg}"
    if cfg["chunking"] == "lightrag":
        assert cfg["retriever"] == "lightrag", (
            f"chunking='lightrag' requires retriever='lightrag': {cfg}"
        )
    if cfg["retriever"] == "lightrag":
        assert cfg["chunking"] == "lightrag", (
            f"retriever='lightrag' requires chunking='lightrag': {cfg}"
        )


def _config_name(cfg: dict) -> str:
    """Auto-generate a unique, human-readable config name from its parameters."""
    parts = [cfg["embedding"], cfg["chunking"]]
    if cfg["chunking"] == "simple":
        parts.append(f"cs{cfg['chunk_size']}_co{cfg['chunk_overlap']}")
    elif cfg["chunking"] == "hierarchical_with_structure":
        parts.append(f"hcs{cfg['hws_chunk_size']}")
    parts.append(cfg["retriever"])
    if cfg.get("use_reranker", True):
        parts.append(f"top{cfg['rerank_top_n']}")
    else:
        parts.append("norerank")
    parts.append(f"stk{cfg['similarity_top_k']}")
    return "_".join(parts)


# ==============================================================================
# CITATION PARSING
# ==============================================================================

_CITATION_RE = re.compile(
    r"---\s*START:\s*(.*?)\s*---\n(.*?)\n---\s*END\s*---",
    re.DOTALL,
)


def parse_citations(citations_str: str) -> list[tuple[str, str]]:
    """Parse citation string into list of (source_file, text) tuples.

    Expected format:
        --- START: path/to/file.md ---
        <text segment>
        --- END ---
    """
    if not isinstance(citations_str, str) or not citations_str.strip():
        return []
    return [(m.group(1).strip(), m.group(2).strip()) for m in _CITATION_RE.finditer(citations_str)]


# ==============================================================================
# SANITY CHECK
# ==============================================================================

_PARSED_REFINED_DIR = "data/parsed_refined_v2"

# Cache: (node_dir_basename, filename) → absolute path inside parsed_refined_v2.
# Keyed by node directory name because filenames like "Sopimus_suomeksi_PDF.md"
# are shared across many nodes.
_REFINED_FILE_INDEX: dict[tuple[str, str], str] = {}


def _build_refined_index(base: Path) -> None:
    """Walk parsed_refined_v2 once and map (node_dir, filename) to absolute path."""
    root = base / _PARSED_REFINED_DIR
    assert root.is_dir(), f"Refined data directory not found: {root}"
    for dirpath, _, filenames in os.walk(root):
        node_dir = os.path.basename(dirpath)
        for fname in filenames:
            _REFINED_FILE_INDEX[(node_dir, fname)] = os.path.join(dirpath, fname)


def _testdata(csv_path: str = TEST_CSV) -> None:
    """Verify test dataset integrity before any processing starts.

    For every row in the test CSV:
    - The source file (looked up by filename in parsed_refined_v2) must exist.
    - Each citation segment (split on standalone '---' lines) must be found
      verbatim (whitespace-normalised) inside that source file.

    Crashes hard with all violations reported at once.
    """
    base = Path(__file__).parent

    print(f"\n[Sanity] Verifying test data integrity: {csv_path}")
    assert os.path.exists(csv_path), f"Test CSV not found: {csv_path}"
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig")

    required = {"node", "files", "citation"}
    missing = required - set(df.columns)
    assert not missing, f"Test CSV missing columns required for sanity check: {missing}"

    if not _REFINED_FILE_INDEX:
        _build_refined_index(base)

    errors: list[str] = []
    for idx, row in df.iterrows():
        node = str(row["node"])
        fname = str(row["files"]) if pd.notna(row["files"]) else ""
        assert fname, f"Row {idx} (node={node}): 'files' column is empty"

        key = (node, fname)
        if key not in _REFINED_FILE_INDEX:
            errors.append(
                f"Row {idx} (node={node}): '{fname}' not found under {_PARSED_REFINED_DIR}/{node}/"
            )
            continue

        source_path = _REFINED_FILE_INDEX[key]
        citation_raw = str(row["citation"]) if pd.notna(row["citation"]) else ""
        if not citation_raw.strip():
            errors.append(f"Row {idx} (node={node}): citation is empty")
            continue

        content = _ws_norm(Path(source_path).read_text(encoding="utf-8", errors="ignore"))

        # Split on standalone '---' lines (segments from different parts of the doc)
        segments = re.split(r"(?m)^---\s*$", citation_raw)
        segments = [s.strip() for s in segments if s.strip()]

        for seg_idx, seg in enumerate(segments):
            norm_seg = _ws_norm(seg)
            if not norm_seg:
                continue
            if norm_seg not in content:
                errors.append(
                    f"Row {idx} (node={node}): citation segment {seg_idx + 1}/{len(segments)} "
                    f"not found in {source_path}.\n"
                    f"  Segment (full): {norm_seg}"
                )

    assert not errors, f"[Sanity] {len(errors)} test data error(s):\n" + "\n".join(errors)
    print(f"[Sanity] OK — {len(df)} rows checked, all files found and all citations verified.")


def verify_chunks_in_source(
    node_meta,
    retrieved_chunks: list[str],
    retrieved_node_ids: list[str],
    chunking: str = "unknown",
) -> None:
    """Assert every retrieved chunk is a substring of its source file.

    Reads source files from disk (cached) and checks each chunk against the file it
    claims to come from. Only whitespace is normalized — no unicode transforms — to
    match LlamaIndex's own whitespace handling without altering characters.
    Crashes immediately on mismatch — indicates encoding/chunking bug.

    HWS exception: `_merge_tiny_sections` in rag_engine.py concatenates (and may
    reorder) non-adjacent tiny sections into their sibling, so the merged chunk
    text is not a contiguous substring of source. For HWS, if the full-chunk
    check fails, fall back to per-heading-segment verification.
    """
    data_path = node_meta.data_path

    def _load(fpath: str) -> str:
        if fpath not in _SOURCE_CONTENT_CACHE:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                _SOURCE_CONTENT_CACHE[fpath] = _ws_norm(f.read())
        return _SOURCE_CONTENT_CACHE[fpath]

    # Build map: filename → normalized content (cached reads)
    file_contents: dict[str, str] = {}
    if os.path.isfile(data_path):
        file_contents[os.path.basename(data_path)] = _load(data_path)
    elif os.path.isdir(data_path):
        for root, _, files in os.walk(data_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                file_contents[fname] = _load(fpath)

    for i, (chunk, fname) in enumerate(zip(retrieved_chunks, retrieved_node_ids)):
        assert fname in file_contents, (
            f"Chunk #{i} claims source file '{fname}' but it was not found under {data_path}"
        )
        content = file_contents[fname]
        norm_chunk = _ws_norm(chunk)
        if norm_chunk in content:
            continue

        if chunking == "hierarchical_with_structure":
            # Tiny sections get merged (possibly reordered) into siblings. Split
            # the chunk on markdown heading boundaries and verify each segment.
            segments = re.split(r"(?m)(?=^#{1,6}\s)", chunk)
            missing = []
            for seg in segments:
                norm_seg = _ws_norm(seg)
                if norm_seg and norm_seg not in content:
                    missing.append(norm_seg[:200])
            if not missing:
                continue
            assert False, (
                f"Chunk #{i} HWS segment(s) not in source file '{fname}'.\n"
                f"  Node data_path: {data_path}\n"
                f"  Missing segments: {missing}"
            )

        assert False, (
            f"Chunk #{i} NOT found in source file '{fname}'.\n"
            f"  Node data_path: {data_path}\n"
            f"  Chunk (full):\n{norm_chunk}"
        )


# ==============================================================================
# RETRIEVAL METRICS
# ==============================================================================
_TOKEN_RE = re.compile(r"\w+(?:[.-]\w+)*", flags=re.UNICODE)


def compute_retrieval_metrics(
    target_text: str,
    chunks: list[str],
    min_token_match: int = 4,
    n_gram: int = 4,
) -> dict:
    """
    Comprehensive deterministic evaluation for RAG retrieval.

    Computes token-level coverage, coverage structure, chunk redundancy,
    rank-aware metrics, and N-gram set Jaccard. Chunks must be in ranked
    order (best-ranked first) for MRR and rank-weighted coverage to be valid.

    Returns None for each metric when target or chunks are empty/invalid.
    """

    zeros = {
        "token_recall": None,
        "retrieval_efficiency": None,
        "token_f1": None,
        "coverage_continuity": None,
        "gap_count": None,
        "mean_gap_size": None,
        "chunk_redundancy": None,
        f"{n_gram}gram_recall": None,
        f"{n_gram}gram_precision": None,
        f"{n_gram}gram_f1": None,
        f"{n_gram}gram_iou": None,
        "mrr": None,
        "rank_weighted_coverage": None,
        "effective_chunk_ratio": None,
        "min_k_full_coverage": None,
    }

    if not target_text or not chunks:
        return zeros

    target_tokens = _TOKEN_RE.findall(target_text.lower())
    n_target = len(target_tokens)

    if n_target == 0:
        return zeros

    # Clamp min_token_match so short targets are still evaluable
    effective_min = min(min_token_match, n_target)

    # Pre-tokenize all chunks once
    chunks_tokenized = [_TOKEN_RE.findall(c.lower()) for c in chunks]
    total_retrieved_tokens = sum(len(ct) for ct in chunks_tokenized)
    n_chunks = len(chunks)

    # ══════════════════════════════════════════════════════════════
    # 1. Token Coverage + Rank-Aware + Redundancy
    # ══════════════════════════════════════════════════════════════
    covered_target = [False] * n_target
    total_matched_tokens = 0
    first_hit_rank = None
    cumulative_coverages: list[float] = []
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

    # Coverage continuity: longest contiguous True run
    max_run = current_run = 0
    for c in covered_target:
        if c:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    coverage_continuity = max_run / n_target

    # Gap analysis (internal gaps only)
    first_true = last_true = None
    for i, c in enumerate(covered_target):
        if c:
            if first_true is None:
                first_true = i
            last_true = i

    gap_count = 0
    gap_sizes: list[int] = []
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

    # Chunk redundancy
    chunk_redundancy = (
        (total_matched_tokens - unique_covered) / total_matched_tokens
        if total_matched_tokens > 0
        else 0.0
    )

    # MRR
    mrr = 1.0 / first_hit_rank if first_hit_rank is not None else 0.0

    # Rank-weighted coverage
    rank_weighted_coverage = sum(cumulative_coverages) / n_chunks

    # Effective chunk ratio
    effective_chunk_ratio = chunks_with_new / n_chunks

    # Min K for full coverage
    final_coverage = cumulative_coverages[-1]
    min_k_full = n_chunks
    for i, c in enumerate(cumulative_coverages):
        if abs(c - final_coverage) < 1e-9:
            min_k_full = i + 1
            break

    # ══════════════════════════════════════════════════════════════
    # 2. N-Gram Set Jaccard
    # ══════════════════════════════════════════════════════════════
    def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
        return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}

    target_ngrams = _ngrams(target_tokens, n_gram)

    result: dict = {
        "token_recall": round(tok_rec, 4),
        "retrieval_efficiency": round(tok_eff, 4),
        "token_f1": round(tok_f1, 4),
        "coverage_continuity": round(coverage_continuity, 4),
        "gap_count": gap_count,
        "mean_gap_size": round(mean_gap_size, 4),
        "chunk_redundancy": round(chunk_redundancy, 4),
        "mrr": round(mrr, 4),
        "rank_weighted_coverage": round(rank_weighted_coverage, 4),
        "effective_chunk_ratio": round(effective_chunk_ratio, 4),
        "min_k_full_coverage": min_k_full,
    }

    if not target_ngrams:
        result.update(
            {
                f"{n_gram}gram_recall": None,
                f"{n_gram}gram_precision": None,
                f"{n_gram}gram_f1": None,
                f"{n_gram}gram_iou": None,
            }
        )
        return result

    retrieved_ngrams: set[tuple[str, ...]] = set()
    for ct in chunks_tokenized:
        retrieved_ngrams.update(_ngrams(ct, n_gram))

    if not retrieved_ngrams:
        result.update(
            {
                f"{n_gram}gram_recall": None,
                f"{n_gram}gram_precision": None,
                f"{n_gram}gram_f1": None,
                f"{n_gram}gram_iou": None,
            }
        )
        return result

    intersection = target_ngrams & retrieved_ngrams
    union = target_ngrams | retrieved_ngrams
    len_i = len(intersection)
    len_t = len(target_ngrams)
    len_r = len(retrieved_ngrams)

    ng_rec = len_i / len_t
    ng_prec = len_i / len_r
    ng_f1 = 2 * ng_rec * ng_prec / (ng_rec + ng_prec) if (ng_rec + ng_prec) > 0 else 0.0
    ng_iou = len_i / len(union)

    result.update(
        {
            f"{n_gram}gram_recall": round(ng_rec, 4),
            f"{n_gram}gram_precision": round(ng_prec, 4),
            f"{n_gram}gram_f1": round(ng_f1, 4),
            f"{n_gram}gram_iou": round(ng_iou, 4),
        }
    )
    return result


# ==============================================================================
# INDEX MANAGEMENT
# ==============================================================================

# Index cache: (embedding, chunking, chunk_size, chunk_overlap, chunk_sizes_str) → (RAGEngine, DataProcessor, Settings)
_INDEX_CACHE: dict[tuple, tuple[RAGEngine, DataProcessor, Settings]] = {}

# Query embedding cache: (embedding_config_name, question) → embedding vector
# Pre-computed once per embedding model before Phase 3 to avoid redundant API calls.
_QUERY_EMBEDDING_CACHE: dict[tuple[str, str], list[float]] = {}


def _index_cache_key(cfg: dict) -> tuple:
    return (
        cfg["embedding"],
        cfg["chunking"],
        cfg.get("chunk_size"),
        cfg.get("chunk_overlap"),
        cfg.get("hws_chunk_size"),
    )


def _storage_path_for(cfg: dict) -> str:
    parts = [cfg["embedding"], cfg["chunking"]]
    if cfg["chunking"] == "simple":
        parts.append(f"cs{cfg['chunk_size']}_co{cfg['chunk_overlap']}")
    elif cfg["chunking"] == "hierarchical_with_structure":
        parts.append(f"hcs{cfg['hws_chunk_size']}")
    return os.path.join("test_indices", "_".join(parts))


def _index_exists_on_disk(cfg: dict, test_node_ids: set[str] | None = None) -> bool:
    """Check if the index for this config has already been built on disk.

    For Chroma variants: checks for chroma.sqlite3 inside the variant subdirectory.
    For LightRAG: checks that every tested node has kv_store_full_docs.json under
    the variant root. A missing or incomplete per-node directory triggers a rebuild.
    """
    variant_path = os.path.join(_storage_path_for(cfg), f"{cfg['chunking']}_plain")
    if cfg["chunking"] == "lightrag":
        if not os.path.isdir(variant_path):
            return False
        nodes_to_check = test_node_ids or set()
        return all(
            os.path.isfile(os.path.join(variant_path, node_id, "kv_store_full_docs.json"))
            for node_id in nodes_to_check
        )
    return os.path.isfile(os.path.join(variant_path, "chroma.sqlite3"))


def _resolve_node_id(raw_node: str, all_node_ids: set[str]) -> str:
    """Resolve a test CSV node value to the internal node ID.

    Test CSV may contain 'TES3' (short form) or 'A30_TES3' (full form).
    Returns the matching internal node ID.
    """
    if raw_node in all_node_ids:
        return raw_node
    full = f"A30_{raw_node}"
    if full in all_node_ids:
        return full
    raise ValueError(
        f"Node '{raw_node}' not found in data processor nodes.\n"
        f"Tried: '{raw_node}', '{full}'\n"
        f"Check the 'node' column in your test CSV."
    )


def build_or_load_index(
    cfg: dict,
    test_node_ids: set[str],
) -> tuple["RAGEngine", "DataProcessor", Settings]:
    """Return cached or freshly built (RAGEngine, DataProcessor, Settings) for cfg."""
    key = _index_cache_key(cfg)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]

    print(f"\n{'=' * 70}")
    print(f"[Index] Building/loading: {_config_name(cfg)}")
    print(f"{'=' * 70}")

    storage_path = _storage_path_for(cfg)

    # Build settings
    settings_kwargs: dict = dict(embedding_config=cfg["embedding"], use_reranker=True)
    if cfg["chunking"] == "simple":
        settings_kwargs["simple_chunk_size"] = cfg["chunk_size"]
        settings_kwargs["simple_chunk_overlap"] = cfg["chunk_overlap"]
    elif cfg["chunking"] == "hierarchical_with_structure":
        settings_kwargs["hws_chunk_size"] = cfg["hws_chunk_size"]

    settings_kwargs["similarity_top_k"] = cfg["similarity_top_k"]
    settings_kwargs["rerank_top_n"] = cfg["rerank_top_n"]
    settings_kwargs.update(_EMBEDDING_API_OVERRIDES.get(cfg["embedding"], {}))

    settings = Settings(**settings_kwargs)
    # Bypass production storage: point to isolated test index folder
    settings.chroma_storage_path = storage_path
    hcs_suffix = (
        f"_hcs{cfg['hws_chunk_size']}" if cfg["chunking"] == "hierarchical_with_structure" else ""
    )
    settings.chroma_collection_name = f"test_{cfg['embedding']}_{cfg['chunking']}{hcs_suffix}"

    # Load only the nodes needed for this benchmark run
    expanded_ids = {nid for raw in test_node_ids for nid in (raw, f"A30_{raw}")}
    data_processor = DataProcessor(settings)
    data_processor.load_and_classify(node_id_filter=expanded_ids)

    # Resolve test node IDs against loaded node registry
    resolved_node_ids: set[str] = set()
    for raw_node in test_node_ids:
        resolved = _resolve_node_id(raw_node, set(data_processor.nodes.keys()))
        resolved_node_ids.add(resolved)

    # Validate: all test nodes must be non-excluded
    for nid in resolved_node_ids:
        meta = data_processor.nodes[nid]
        assert meta.strategy != DocumentStrategy.EXCLUDED, (
            f"Test node '{nid}' is EXCLUDED: {meta.exclude_reason}"
        )

    # Build file list for test nodes only
    file_list = [
        {
            "file_id": nid,
            "filepath": data_processor.nodes[nid].data_path,
            "title": data_processor.nodes[nid].level3_label
            or data_processor.nodes[nid].level2_label,
        }
        for nid in resolved_node_ids
    ]

    node_registry = {nid: data_processor.nodes[nid] for nid in resolved_node_ids}

    rag_engine = RAGEngine(settings)
    rag_engine.setup_embedding()

    rag_engine.build_indices(
        file_list=file_list,
        chunking_modes=[cfg["chunking"]],
        force_rebuild=FORCE_REBUILD_INDICES,
        node_registry=node_registry,
    )

    rag_engine.setup_reranker()

    rag_engine.preload_indices(
        chunking_modes=[cfg["chunking"]],
        node_registry=node_registry,
    )

    _INDEX_CACHE[key] = (rag_engine, data_processor, settings)
    print(f"[Index] Ready: {_config_name(cfg)}")
    return rag_engine, data_processor, settings


# ==============================================================================
# RESULT FILES
# ==============================================================================

DETAIL_CSV = os.path.join(OUTPUT_DIR, "results_detail.csv")
DETAIL_PICKLE = os.path.join(OUTPUT_DIR, "results_detail.pkl")
EMBEDDING_CACHE_PKL = os.path.join(OUTPUT_DIR, "query_embedding_cache.pkl")


def load_embedding_cache() -> None:
    """Load persisted query embeddings into _QUERY_EMBEDDING_CACHE (if file exists)."""
    if not os.path.exists(EMBEDDING_CACHE_PKL):
        return
    with open(EMBEDDING_CACHE_PKL, "rb") as f:
        cached = pickle.load(f)
    assert isinstance(cached, dict), f"Embedding cache pickle is not a dict: {type(cached)}"
    _QUERY_EMBEDDING_CACHE.update(cached)
    print(f"[EmbedCache] Loaded {len(cached)} cached query embeddings from {EMBEDDING_CACHE_PKL}")


def save_embedding_cache() -> None:
    """Persist _QUERY_EMBEDDING_CACHE to disk."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(EMBEDDING_CACHE_PKL, "wb") as f:
        pickle.dump(_QUERY_EMBEDDING_CACHE, f)


_RETRIEVAL_COLS = [
    "token_recall",
    "retrieval_efficiency",
    "token_f1",
    "coverage_continuity",
    "gap_count",
    "mean_gap_size",
    "chunk_redundancy",
    "mrr",
    "rank_weighted_coverage",
    "effective_chunk_ratio",
    "min_k_full_coverage",
    "4gram_recall",
    "4gram_precision",
    "4gram_f1",
    "4gram_iou",
    "num_chunks_retrieved",
    "retrieval_ms",
]
_TOP1_RETRIEVAL_COLS = [
    "top1_" + col for col in _RETRIEVAL_COLS if col not in ("num_chunks_retrieved", "retrieval_ms")
]

_LAST_SAVE_TIME: float = 0.0
_SAVE_INTERVAL_SECS: float = 300.0  # 5 minutes


def load_existing_detail() -> pd.DataFrame | None:
    if os.path.exists(DETAIL_CSV):
        try:
            df = pd.read_csv(DETAIL_CSV)
            print(f"[Resume] Loaded CSV: {DETAIL_CSV} ({len(df)} rows)")
            return df
        except Exception as e:
            print(f"[Resume] CSV load failed ({e}), trying pickle...")
    if os.path.exists(DETAIL_PICKLE):
        df = pd.read_pickle(DETAIL_PICKLE)
        print(f"[Resume] Loaded pickle backup: {DETAIL_PICKLE} ({len(df)} rows)")
        return df
    return None


def save_detail(df: pd.DataFrame, force: bool = False) -> None:
    global _LAST_SAVE_TIME
    now = time.time()
    if not force and (now - _LAST_SAVE_TIME) < _SAVE_INTERVAL_SECS:
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(DETAIL_CSV, index=False)
    df.to_pickle(DETAIL_PICKLE)
    _LAST_SAVE_TIME = now


# Plotting moved to test_retrieval_benchmark_part1_plots.py — run that script
# separately after the benchmark completes to generate all charts and the
# results_summary.csv ranking.


# ==============================================================================
# EVALUATION LOOP
# ==============================================================================


def run_benchmark() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    load_embedding_cache()

    _testdata()

    # Validate all configs up front — crash before touching any data
    for cfg in CONFIGS:
        _validate_config(cfg)
    print(f"[OK] {len(CONFIGS)} configs validated")

    # ── Phase 1: Load test data ────────────────────────────────────────────────
    print(f"\nLoading test data from {TEST_CSV}...")
    assert os.path.exists(TEST_CSV), f"Test CSV not found: {TEST_CSV}"
    test_df = pd.read_csv(TEST_CSV, sep=";", encoding="utf-8-sig")

    required_cols = {"node", "question", "files", "answer"}
    missing_cols = required_cols - set(test_df.columns)
    assert not missing_cols, (
        f"Test CSV missing columns: {missing_cols}. Found: {list(test_df.columns)}"
    )
    assert "citations" in test_df.columns or "citation" in test_df.columns, (
        f"Test CSV must have 'citations' or 'citation' column. Found: {list(test_df.columns)}"
    )

    # Parse citations for all rows up front.
    # Supports two formats:
    #   'citations' — formatted with --- START: file --- / --- END --- markers
    #   'citation'  — raw text (paired with 'files' column for the source filename)
    if "citations" in test_df.columns:
        test_df["_parsed_citations"] = test_df["citations"].apply(parse_citations)
    else:
        test_df["_parsed_citations"] = [
            [(str(row["files"]), str(row["citation"]))] for _, row in test_df.iterrows()
        ]

    test_node_ids: set[str] = set(test_df["node"].astype(str).unique())
    print(f"  {len(test_df)} samples, {len(test_node_ids)} unique nodes: {sorted(test_node_ids)}")

    n_configs = len(CONFIGS)
    n_samples = len(test_df)
    print(f"  {n_configs} configs × {n_samples} samples = {n_configs * n_samples} total runs")

    # ── Load or init detail DataFrame ─────────────────────────────────────────
    existing_detail = load_existing_detail()

    all_rows: list[dict] = []
    for cfg in CONFIGS:
        for _, sample in test_df.iterrows():
            all_rows.append(
                {
                    "config": _config_name(cfg),
                    "embedding": cfg["embedding"],
                    "chunking": cfg["chunking"],
                    "retriever": cfg["retriever"],
                    "chunk_size": cfg.get("chunk_size", ""),
                    "chunk_overlap": cfg.get("chunk_overlap", ""),
                    "hws_chunk_size": cfg.get("hws_chunk_size", ""),
                    "rerank_top_n": cfg.get("rerank_top_n", 8),
                    "use_reranker": cfg.get("use_reranker", True),
                    "similarity_top_k": cfg["similarity_top_k"],
                    "node_raw": str(sample["node"]),
                    "question": str(sample["question"]),
                    "gold_answer": str(sample["answer"]),
                    "_parsed_citations": sample["_parsed_citations"],
                    # Results (filled in during phases below)
                    "token_recall": None,
                    "retrieval_efficiency": None,
                    "token_f1": None,
                    "coverage_continuity": None,
                    "gap_count": None,
                    "mean_gap_size": None,
                    "chunk_redundancy": None,
                    "mrr": None,
                    "rank_weighted_coverage": None,
                    "effective_chunk_ratio": None,
                    "min_k_full_coverage": None,
                    "4gram_recall": None,
                    "4gram_precision": None,
                    "4gram_f1": None,
                    "4gram_iou": None,
                    **{col: None for col in _TOP1_RETRIEVAL_COLS},
                    "raw_chunks": "",  # JSON list of all retrieved chunks (Phase 3a)
                    "reranked_chunks": "",  # JSON list of reranked chunks; "" if no reranker (Phase 3a)
                    "chunk_file_names": "",  # JSON list of filenames (Phase 3a)
                    "num_chunks_retrieved": float("nan"),
                    "retrieval_ms": float("nan"),
                    "synthesized_answer": "",
                    "synthesis_ms": float("nan"),
                    "semantic_similarity": float("nan"),
                    "coverage": pd.NA,
                    "contradiction": pd.NA,
                    "relevance": pd.NA,
                    "precision": pd.NA,
                    "overall": pd.NA,
                    "reason": "",
                }
            )

    # Build detail_df: start from existing or fresh
    if existing_detail is not None:
        detail_df = existing_detail
        # Migrate from old single-column schema to raw_chunks + reranked_chunks
        if "raw_chunks" not in detail_df.columns:
            detail_df["raw_chunks"] = None  # forces full Phase 3 re-run
        if "reranked_chunks" not in detail_df.columns:
            detail_df["reranked_chunks"] = ""
        if "retrieved_chunks" in detail_df.columns:
            detail_df = detail_df.drop(columns=["retrieved_chunks"])
        if "hws_chunk_size" not in detail_df.columns:
            detail_df["hws_chunk_size"] = (
                detail_df["config"].str.extract(r"hcs(\d+)", expand=False).fillna("")
            )
        if "use_reranker" not in detail_df.columns:
            detail_df["use_reranker"] = ~detail_df["config"].str.contains("norerank")
        # Ensure all expected rows exist (add new configs/samples)
        existing_keys = set(zip(detail_df["config"], detail_df["question"]))
        new_rows = [r for r in all_rows if (r["config"], r["question"]) not in existing_keys]
        if new_rows:
            print(f"  [Resume] Adding {len(new_rows)} new rows not in existing results")
            new_df = pd.DataFrame(new_rows).drop(columns=["_parsed_citations"])
            detail_df = pd.concat([detail_df, new_df], ignore_index=True)
    else:
        detail_df = pd.DataFrame(all_rows).drop(columns=["_parsed_citations"])

    save_detail(detail_df, force=True)

    # Pre-compute which configs still need retrieval — used to skip index loading below
    _retrieved_filled = detail_df["raw_chunks"].apply(
        lambda v: pd.notna(v) and bool(str(v).strip()) and str(v).strip() != "nan"
    )
    configs_needing_retrieval: set[str] = set(detail_df.loc[~_retrieved_filled, "config"].unique())
    print(f"  {len(configs_needing_retrieval)}/{n_configs} configs have rows needing retrieval")

    # ── Phase 1.5: Preflight index audit (read-only, no changes) ─────────────
    # Report every index status BEFORE touching anything.
    # Uses sqlite3 directly — no ChromaDB client, no file lock risk.
    print(f"\n{'=' * 70}")
    print(
        f"[Preflight] Auditing {len(set(_index_cache_key(c) for c in CONFIGS))} unique indices..."
    )
    print(f"{'=' * 70}")
    _audit_ok, _audit_stale, _audit_missing = [], [], []
    _seen_audit: set[tuple] = set()
    for cfg in CONFIGS:
        key = _index_cache_key(cfg)
        if key in _seen_audit:
            continue
        _seen_audit.add(key)
        variant_path = os.path.join(_storage_path_for(cfg), f"{cfg['chunking']}_plain")
        label = os.path.relpath(variant_path, "test_indices")
        if cfg["chunking"] == "lightrag":
            # LightRAG stores one working_dir per RAG_INDEX node. Count
            # subdirectories with kv_store_full_docs.json as "ready".
            if not os.path.isdir(variant_path):
                print(f"  [MISSING ] {label}")
                _audit_missing.append(label)
            else:
                node_dirs = [
                    d
                    for d in os.listdir(variant_path)
                    if os.path.isdir(os.path.join(variant_path, d))
                ]
                ready = sum(
                    os.path.isfile(os.path.join(variant_path, d, "kv_store_full_docs.json"))
                    for d in node_dirs
                )
                if ready == 0:
                    print(f"  [STALE   ] {label}  ← no per-node kv_store_full_docs.json found")
                    _audit_stale.append(label)
                else:
                    print(f"  [OK {ready:>7} nodes] {label}")
                    _audit_ok.append(label)
            continue
        db_path = os.path.join(variant_path, "chroma.sqlite3")
        if not os.path.exists(variant_path):
            print(f"  [MISSING ] {label}")
            _audit_missing.append(label)
        elif not os.path.isfile(db_path):
            print(f"  [STALE   ] {label}  ← directory exists but no chroma.sqlite3")
            _audit_stale.append(label)
        else:
            import sqlite3 as _sq3

            try:
                _conn = _sq3.connect(f"file:{db_path}?mode=ro", uri=True)
                _count = _conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
                _conn.close()
                if _count > 0:
                    print(f"  [OK {_count:>7}] {label}")
                    _audit_ok.append(label)
                else:
                    print(f"  [STALE   ] {label}  ← sqlite exists but 0 embeddings")
                    _audit_stale.append(label)
            except Exception as _e:
                print(f"  [ERROR   ] {label}  ← {_e}")
                _audit_stale.append(label)
    print(
        f"\n  {len(_audit_ok)} OK  |  {len(_audit_stale)} stale/broken  |  {len(_audit_missing)} missing"
    )
    if _audit_stale:
        print(
            f"  WARNING: {len(_audit_stale)} stale director{'y' if len(_audit_stale) == 1 else 'ies'} will be DELETED and rebuilt:"
        )
        for p in _audit_stale:
            print(f"    - {p}")
    print(f"{'=' * 70}")

    # ── Phase 2: Build missing indices on disk ────────────────────────────────
    if not FORCE_REBUILD_INDICES and not configs_needing_retrieval:
        print(f"\n[Phase 2] Skipped — all chunks already in table.")
    else:
        print(f"\n{'=' * 70}")
        print(f"[Phase 2] Checking/building indices ({n_configs} configs)...")
        print(f"{'=' * 70}")
        seen_index_keys: set[tuple] = set()
        for cfg in CONFIGS:
            key = _index_cache_key(cfg)
            if key in seen_index_keys:
                continue
            seen_index_keys.add(key)
            if not FORCE_REBUILD_INDICES and _index_exists_on_disk(cfg, test_node_ids):
                print(f"  [Skip] Already on disk: {_storage_path_for(cfg)}")
                continue
            engine, _, _ = build_or_load_index(cfg, test_node_ids)
            engine.teardown()
            del _INDEX_CACHE[key]
            gc.collect()
        print(f"[Phase 2] All indices ready on disk.")

    # ── Phase 3: Retrieval + metrics (no LLM) ─────────────────────────────────
    # Process one index at a time: load → precompute embeddings → run all its
    # configs → teardown → next. Never holds more than one index in memory.
    print(f"\n{'=' * 70}")
    print(f"[Phase 3] Running retrieval + metrics for all configs...")
    print(f"{'=' * 70}")

    all_questions = list(test_df["question"].astype(str).unique())
    precomputed_embedding_models: set[str] = set()

    # Group configs by shared index key so each index is loaded exactly once
    index_groups: dict[tuple, list[dict]] = defaultdict(list)
    for cfg in CONFIGS:
        index_groups[_index_cache_key(cfg)].append(cfg)

    for group_cfgs in index_groups.values():
        first_cfg = group_cfgs[0]
        emb_name = first_cfg["embedding"]

        # Skip index loading if no config in this group needs retrieval
        group_config_names = {_config_name(cfg) for cfg in group_cfgs}
        if not FORCE_REBUILD_INDICES and not (group_config_names & configs_needing_retrieval):
            print(f"\n  [Skip] Index group {emb_name}/{first_cfg['chunking']} — all chunks present")
            continue

        # Load this index (one at a time)
        rag_engine, data_processor, _ = build_or_load_index(first_cfg, test_node_ids)
        all_node_ids = set(data_processor.nodes.keys())

        # Pre-compute query embeddings for this embedding model (once per model)
        if emb_name not in precomputed_embedding_models:
            missing = [q for q in all_questions if (emb_name, q) not in _QUERY_EMBEDDING_CACHE]
            if missing:
                print(
                    f"\n  [{emb_name}] Embedding {len(missing)}/{len(all_questions)} new questions (rest cached)..."
                )
                embeddings = rag_engine.embed_queries_batch(missing)
                for q, emb in zip(missing, embeddings):
                    _QUERY_EMBEDDING_CACHE[(emb_name, q)] = emb
                save_embedding_cache()
                print(
                    f"  [{emb_name}] Cache updated ({len(_QUERY_EMBEDDING_CACHE)} total entries)."
                )
            else:
                print(f"\n  [{emb_name}] All {len(all_questions)} query embeddings already cached.")
            precomputed_embedding_models.add(emb_name)

        for cfg in group_cfgs:
            config_name = _config_name(cfg)
            chunking = cfg["chunking"]
            retriever_type = cfg["retriever"]
            rerank_top_n = cfg["rerank_top_n"]
            use_reranker = cfg.get("use_reranker", True)

            print(f"\n{'─' * 70}")
            print(f"[Config] {config_name}")
            print(f"{'─' * 70}")

            _ok = detail_df["raw_chunks"].apply(
                lambda v: pd.notna(v) and bool(str(v).strip()) and str(v).strip() != "nan"
            )
            needs_retrieval = detail_df[(detail_df["config"] == config_name) & ~_ok].to_dict(
                "records"
            )

            if not needs_retrieval:
                print(f"  [Skip] All {n_samples} samples already retrieved")
                continue

            print(f"  Retrieving {len(needs_retrieval)} sample(s)...")
            for i, row in enumerate(needs_retrieval, 1):
                question = row["question"]
                raw_node = row["node_raw"]

                node_id = _resolve_node_id(raw_node, all_node_ids)
                node_meta = data_processor.nodes[node_id]
                print(
                    f"  [{i}/{len(needs_retrieval)}] node={node_id} | {question[:60]}...", end=" "
                )

                t0 = time.time()
                # Temporarily null out reranker for no-reranker configs so
                # _apply_reranking falls through to plain truncation.
                _saved_reranker = rag_engine._reranker
                if not use_reranker:
                    rag_engine._reranker = None
                try:
                    if node_meta.strategy == DocumentStrategy.DIRECT_READ:
                        full_content, file_names = data_processor.read_direct(node_id)
                        raw_chunks = [full_content]
                        reranked_chunks = []
                        print(f"[DIRECT_READ]", end=" ")
                    elif chunking == "lightrag":
                        # LightRAG uses its own async retrieval (owns chunking +
                        # embedding + reranking inside the per-node graph).
                        result = asyncio.run(
                            rag_engine.aretrieve_filtered(
                                question=question,
                                node_ids=[node_id],
                                chunking=chunking,
                                retriever_type=retriever_type,
                                rerank_top_n=rerank_top_n,
                            )
                        )
                        raw_chunks = [n.node.get_content() for n in result.raw]
                        reranked_chunks = (
                            [n.node.get_content() for n in result.reranked]
                            if result.reranked is not None
                            else []
                        )
                        file_names = [n.node.metadata.get("file_name", "") for n in result.raw]
                        # LightRAG's tiktoken chunker may shift whitespace at chunk
                        # boundaries vs. the raw source file — skip the substring check.
                    else:
                        result = rag_engine.retrieve_filtered(
                            question=question,
                            node_ids=[node_id],
                            chunking=chunking,
                            retriever_type=retriever_type,
                            rerank_top_n=rerank_top_n,
                            query_embedding=_QUERY_EMBEDDING_CACHE.get((emb_name, question)),
                        )
                        if chunking == "hierarchical_with_structure":
                            raw_chunks = [_strip_hws_heading_prefix(n.node) for n in result.raw]
                            reranked_chunks = (
                                [_strip_hws_heading_prefix(n.node) for n in result.reranked]
                                if result.reranked is not None
                                else []
                            )
                        else:
                            raw_chunks = [n.node.get_content() for n in result.raw]
                            reranked_chunks = (
                                [n.node.get_content() for n in result.reranked]
                                if result.reranked is not None
                                else []
                            )
                        file_names = [n.node.metadata.get("file_name", "") for n in result.raw]
                        verify_chunks_in_source(
                            node_meta, raw_chunks, file_names, chunking=chunking
                        )
                finally:
                    rag_engine._reranker = _saved_reranker

                retrieval_ms = int((time.time() - t0) * 1000)
                print(f"raw={len(raw_chunks)} reranked={len(reranked_chunks)} ({retrieval_ms}ms)")

                mask = (detail_df["config"] == config_name) & (detail_df["question"] == question)
                assert mask.sum() == 1
                idx = detail_df.index[mask][0]
                detail_df.at[idx, "raw_chunks"] = json.dumps(raw_chunks)
                detail_df.at[idx, "reranked_chunks"] = json.dumps(reranked_chunks)
                detail_df.at[idx, "chunk_file_names"] = json.dumps(file_names)
                detail_df.at[idx, "num_chunks_retrieved"] = len(raw_chunks)
                detail_df.at[idx, "retrieval_ms"] = retrieval_ms
                save_detail(detail_df)  # throttled — writes at most every 5 minutes

        # Teardown this index before loading the next
        rag_engine.teardown()
        del _INDEX_CACHE[_index_cache_key(first_cfg)]
        gc.collect()

    save_detail(detail_df, force=True)

    # ── Phase 3b: Compute metrics from saved chunks (no LLM, no index) ────────
    print(f"\n{'=' * 70}")
    print(f"[Phase 3b] Computing retrieval metrics from saved chunks...")
    print(f"{'=' * 70}")

    # Build lookup: (config, question) → citation_segments
    citation_lookup: dict[tuple[str, str], list] = {
        (row["config"], row["question"]): row["_parsed_citations"] for row in all_rows
    }

    if "coverage_continuity" not in detail_df.columns:
        detail_df["coverage_continuity"] = None
    if "top1_token_recall" not in detail_df.columns:
        detail_df["top1_token_recall"] = None

    needs_full = set(detail_df[pd.isna(detail_df["coverage_continuity"])].index)
    needs_top1 = set(detail_df[pd.isna(detail_df["top1_token_recall"])].index)
    needs_metrics = sorted(needs_full | needs_top1)
    print(
        f"  {len(needs_metrics)} rows need metric computation ({len(needs_full)} full, {len(needs_top1)} top1)."
    )
    for i, idx in enumerate(needs_metrics, 1):
        row = detail_df.loc[idx]
        raw_str = row.get("raw_chunks", "")
        assert pd.notna(raw_str) and str(raw_str).strip(), (
            f"Row {idx} has no saved raw_chunks — Phase 3a must complete first"
        )
        raw_chunks = json.loads(str(raw_str))
        assert isinstance(raw_chunks, list) and len(raw_chunks) > 0, (
            f"Row {idx}: raw_chunks is empty — retrieval must have returned nothing"
        )
        expected_n = int(row["num_chunks_retrieved"])
        assert len(raw_chunks) == expected_n, (
            f"Row {idx}: chunk count mismatch: {len(raw_chunks)} in JSON vs {expected_n} in num_chunks_retrieved"
        )

        reranked_str = row.get("reranked_chunks", "")
        reranked_chunks = (
            json.loads(str(reranked_str))
            if pd.notna(reranked_str) and str(reranked_str).strip() not in ("", "nan", "[]")
            else []
        )

        # Use reranked if available, else raw; cap both at rerank_top_n for fair comparison
        rerank_top_n_val = int(row.get("rerank_top_n", 8))
        effective = (reranked_chunks if reranked_chunks else raw_chunks)[:rerank_top_n_val]

        citation_segments = citation_lookup[(str(row["config"]), str(row["question"]))]
        target_text = " ".join(text for _, text in citation_segments)

        if idx in needs_full:
            metrics = compute_retrieval_metrics(target_text, effective)
            print(
                f"  [{i}/{len(needs_metrics)}] {str(row['config'])[:50]} | "
                f"tok_f1={metrics['token_f1']:.2f} "
                f"mrr={metrics['mrr']:.2f} "
                f"rwc={metrics['rank_weighted_coverage']:.2f} "
                f"4g_iou={metrics['4gram_iou']:.2f}"
            )
            for col, val in metrics.items():
                detail_df.at[idx, col] = val

        if idx in needs_top1:
            top1_metrics = compute_retrieval_metrics(target_text, effective[:1])
            for col in _TOP1_RETRIEVAL_COLS:
                detail_df.at[idx, col] = top1_metrics[col[len("top1_") :]]

        save_detail(detail_df)  # throttled

    save_detail(detail_df, force=True)
    print(f"[Phase 3b] Done.")

    print(f"\nResults saved:")
    print(f"  Detail:  {DETAIL_CSV}")
    print(f"  Summary: {os.path.join(OUTPUT_DIR, 'results_summary.csv')}")


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    run_benchmark()
