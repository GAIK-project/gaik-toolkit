"""Proof of Concept: Manufacturing Knowledge Base RAG Assistant

Role-aware, citation-grounded question answering over internal PDF documents.

Pipeline (custom / _generic):
  1. load_input        — parse poc_input_bundle.json, resolve sibling files
  2. ingest_and_index  — parse PDFs page-by-page, structure-aware chunk, embed,
                         build local in-memory numpy vector index with full metadata
  3. apply_rbac_and_retrieve — pre-retrieval RBAC: check top-1 match across ALL
                         chunks; if restricted → denied; else filter to permitted
                         and retrieve top-4 by cosine similarity
  4. generate_answers  — gpt-5.4 (Azure OpenAI, temp=0, reasoning_effort=medium),
                         grounded strictly in retrieved context, with validated
                         [file_name, page_number] citations

Output: output/results.json — list of RAGAnswerRecord objects.

Usage:
    python run_poc.py --input <path-to-poc_input_bundle.json>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()


# ---------------------------------------------------------------------------
# Console compatibility
# ---------------------------------------------------------------------------

def configure_console_output() -> None:
    """Prevent Windows legacy console encodings from terminating the PoC.

    PowerShell may expose stdout/stderr as cp1252. Model-generated answers or
    diagnostic text can contain characters outside that encoding. Preserve a
    readable ASCII escape instead of raising UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Azure OpenAI helpers
# ---------------------------------------------------------------------------

def get_azure_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.environ["AZURE_API_KEY"],
        azure_endpoint=os.environ["AZURE_ENDPOINT"],
        api_version=os.environ.get("AZURE_API_VERSION", "2025-01-01-preview"),
    )


def embed_texts(client: AzureOpenAI, texts: list[str], deployment: str) -> np.ndarray:
    """Embed a list of texts; returns (N, D) float32 array."""
    response = client.embeddings.create(input=texts, model=deployment)
    return np.array([item.embedding for item in response.data], dtype=np.float32)


def cosine_similarities(query_vec: np.ndarray, chunk_matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a single query vector and all chunk vectors."""
    q = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(chunk_matrix, axis=1, keepdims=True) + 1e-10
    return (chunk_matrix / norms) @ q


# ---------------------------------------------------------------------------
# PDF parsing + chunking (LocalVectorIndexer — Step: ingest_and_index)
# ---------------------------------------------------------------------------

def parse_pdf_by_page(pdf_path: Path) -> list[dict]:
    """Extract text per page. Returns [{text, page_number (1-based)}]."""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text").strip()
        if text:
            pages.append({"text": text, "page_number": i + 1})
    doc.close()
    return pages


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """Structure-aware chunking: split on paragraph boundaries then merge to chunk_size.

    chunk_size / overlap are in approximate tokens (chars / 4).
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if (len(current) + len(para)) // 4 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            # Begin new chunk with overlap from previous
            if chunks and overlap > 0:
                tail_chars = overlap * 4
                tail = chunks[-1][-tail_chars:].strip()
                current = (tail + "\n\n" + para).strip()
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks or [text]


def build_index(
    pdf_paths: list[Path],
    access_manifest: dict,
    client: AzureOpenAI,
    embedding_deployment: str,
    chunk_size: int = 400,
    overlap: int = 80,
    batch_size: int = 16,
) -> list[dict]:
    """Parse all PDFs, chunk with access metadata, embed, return chunk list.

    Each chunk dict:
        text, file_name, page_number, classification, allowed_roles, embedding
    """
    raw_chunks: list[dict] = []

    for pdf_path in pdf_paths:
        fname = pdf_path.name
        meta = access_manifest.get(fname, {})
        classification = meta.get("classification", "unclassified")
        allowed_roles = meta.get("allowed_roles", [])

        print(f"  Parsing {fname}  (class={classification}, roles={allowed_roles})")
        pages = parse_pdf_by_page(pdf_path)

        for page in pages:
            for chunk_text_val in chunk_text(page["text"], chunk_size, overlap):
                if chunk_text_val.strip():
                    raw_chunks.append({
                        "text": chunk_text_val,
                        "file_name": fname,
                        "page_number": page["page_number"],
                        "classification": classification,
                        "allowed_roles": allowed_roles,
                        "embedding": None,
                    })

    print(f"  Embedding {len(raw_chunks)} chunks in batches of {batch_size}...")
    texts = [c["text"] for c in raw_chunks]
    all_embs: list[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        all_embs.append(embed_texts(client, texts[i:i + batch_size], embedding_deployment))
    emb_matrix = np.vstack(all_embs)

    for i, chunk in enumerate(raw_chunks):
        chunk["embedding"] = emb_matrix[i]

    print(f"  Index ready: {len(raw_chunks)} chunks from {len(pdf_paths)} document(s).\n")
    return raw_chunks


# ---------------------------------------------------------------------------
# RBAC + retrieval (RBACPreFilter — Step: apply_rbac_and_retrieve)
# ---------------------------------------------------------------------------

def rbac_check_and_retrieve(
    question: str,
    role: str,
    all_chunks: list[dict],
    client: AzureOpenAI,
    embedding_deployment: str,
    top_k: int = 4,
) -> tuple[str, list[dict], str | None]:
    """Pre-retrieval RBAC gate, then semantic retrieval.

    Returns (access_decision, retrieved_chunks, refusal_reason).

    Algorithm:
      1. Embed the question.
      2. Compute cosine similarity against ALL chunks (restricted + permitted).
      3. Find the top-1 overall match.
         - If that chunk's document is NOT accessible to the role → "denied".
           (The query's answer lives in a restricted document.)
         - Otherwise → proceed.
      4. Filter the chunk pool to role-permitted chunks only.
      5. Retrieve top-k by cosine similarity from the permitted pool.

    Critical guarantee: restricted chunk TEXT never enters the model context.
    The access check uses only vector similarity (no text forwarded to LLM).
    """
    emb_matrix = np.stack([c["embedding"] for c in all_chunks])
    query_emb = embed_texts(client, [question], embedding_deployment)[0]
    sims = cosine_similarities(query_emb, emb_matrix)

    # --- Access gate: inspect top-1 result globally ---
    top1_idx = int(np.argmax(sims))
    top1 = all_chunks[top1_idx]
    if role not in top1["allowed_roles"]:
        return (
            "denied",
            [],
            (
                "Access denied: the information you requested is contained in a document "
                "classified as restricted for your role. Contact your manager if you "
                "require access."
            ),
        )

    # --- Permitted retrieval: filter BEFORE similarity ranking ---
    permitted_indices = [i for i, c in enumerate(all_chunks) if role in c["allowed_roles"]]
    if not permitted_indices:
        return "denied", [], "No documents are accessible for your role."

    permitted_sims = sims[permitted_indices]
    top_k_pos = np.argsort(permitted_sims)[-top_k:][::-1]
    retrieved = [all_chunks[permitted_indices[i]] for i in top_k_pos]

    return "allowed", retrieved, None


# ---------------------------------------------------------------------------
# Answer generation (CitedRAGPipeline — Step: generate_answers)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a manufacturing company knowledge assistant. Answer the user's question
using ONLY the document passages provided. Follow these rules exactly:

CITATION FORMAT
  Every factual claim must be cited as [filename, page_number], where filename is
  the exact file name string and page_number is a 1-based integer.
  Example: According to the travel policy, the hotel limit is EUR 180 per night
           [employee_travel_policy.pdf, 3].

VALUE PRESERVATION
  Reproduce numeric values and units exactly as they appear in the source:
  EUR 180, 250 operating hours, 1,000 operating hours, 1.8 bar, 12 percent,
  22 percent. Do not round, paraphrase, or drop units.

NO FABRICATION
  If the passages do not contain enough information, respond:
  "The information was not found in the available documents."
  Do not speculate or draw on knowledge outside the provided passages.

CONFLICT HANDLING
  If passages contradict each other, state the conflict clearly and cite both.

NO EXTRA CITATIONS
  Only cite sources that appear in the passages below. Do not invent citations."""


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[Passage {i} | {c['file_name']}, page {c['page_number']}]\n{c['text']}"
        )
    return "\n\n---\n\n".join(parts)


def _extract_validated_citations(
    answer_text: str, retrieved_chunks: list[dict]
) -> list[list]:
    """Extract [file_name, page_number] citations from the answer.

    Only returns citations that map to an actually retrieved chunk,
    preventing fabricated or hallucinated citations.
    """
    valid_pairs = {(c["file_name"], c["page_number"]) for c in retrieved_chunks}
    seen: set[tuple] = set()
    citations: list[list] = []

    # Match patterns like [employee_travel_policy.pdf, 3]
    pattern = re.compile(
        r'\[([A-Za-z0-9_\-\s]+\.(?:pdf|docx|txt|md)),\s*(\d+)\]',
        re.IGNORECASE,
    )
    for m in pattern.finditer(answer_text):
        fname = m.group(1).strip()
        pnum = int(m.group(2))
        key = (fname, pnum)
        if key in valid_pairs and key not in seen:
            seen.add(key)
            citations.append([fname, pnum])

    return citations


def generate_cited_answer(
    question: str,
    retrieved_chunks: list[dict],
    client: AzureOpenAI,
    chat_deployment: str,
    temperature: float,
    reasoning_effort: str,
) -> tuple[str, list[list]]:
    """Call gpt-5.4 and return (answer_text, validated_citations)."""
    context = _build_context(retrieved_chunks)
    user_msg = f"Document passages:\n\n{context}\n\nQuestion: {question}"

    call_kwargs: dict[str, Any] = {
        "model": chat_deployment,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
    }

    # reasoning_effort is valid for o-series and gpt-5.x models on Azure OpenAI.
    # Pass it directly; if the deployment does not support it the API will return
    # an error that surfaces clearly to the operator.
    if reasoning_effort:
        call_kwargs["reasoning_effort"] = reasoning_effort

    response = client.chat.completions.create(**call_kwargs)
    answer_text = response.choices[0].message.content.strip()
    citations = _extract_validated_citations(answer_text, retrieved_chunks)
    return answer_text, citations


# ---------------------------------------------------------------------------
# RAGAnswerRecord helpers
# ---------------------------------------------------------------------------

def denied_record(
    query_id: str, role: str, question: str, refusal_reason: str
) -> dict:
    return {
        "query_id": query_id,
        "role": role,
        "question": question,
        "access_decision": "denied",
        "answer": "Access denied. You are not authorised to access this information.",
        "citations": [],
        "refusal_reason": refusal_reason,
    }


def allowed_record(
    query_id: str, role: str, question: str, answer: str, citations: list[list]
) -> dict:
    return {
        "query_id": query_id,
        "role": role,
        "question": question,
        "access_decision": "allowed",
        "answer": answer,
        "citations": citations,
        "refusal_reason": None,
    }


# ---------------------------------------------------------------------------
# Input bundle loading (Step: load_input)
# ---------------------------------------------------------------------------

def _normalise_manifest(raw: Any, manifest_dir: Path | None = None) -> dict:
    """Convert any supported access_manifest format to {basename: {classification, allowed_roles, rel_path}}.

    Supports:
      - list of entries with 'file', 'filename', 'file_name', or 'name'
      - dict with a 'documents' list
      - dict already keyed by filename
    'file' values may be relative paths (e.g. 'documents/foo.pdf'); the basename
    is used as the manifest key and rel_path is stored for PDF resolution.
    """
    manifest: dict = {}

    def _add(entry: dict) -> None:
        raw_path = (
            entry.get("file")          # e.g. "documents/foo.pdf"
            or entry.get("filename")
            or entry.get("file_name")
            or entry.get("name", "")
        )
        if not raw_path:
            return
        # Use basename as key; store the original relative path for resolution
        basename = Path(raw_path).name
        manifest[basename] = {
            "classification": entry.get("classification", "unclassified"),
            "allowed_roles": entry.get("allowed_roles", []),
            "_rel_path": raw_path,           # relative to manifest dir
            "_manifest_dir": manifest_dir,   # needed to resolve full path
        }

    if isinstance(raw, list):
        for item in raw:
            _add(item)
    elif isinstance(raw, dict):
        if "documents" in raw:
            for item in raw["documents"]:
                _add(item)
        else:
            # Already keyed by filename
            for fname, meta in raw.items():
                if isinstance(meta, dict):
                    manifest[fname] = {
                        "classification": meta.get("classification", "unclassified"),
                        "allowed_roles": meta.get("allowed_roles", []),
                    }
    return manifest


def _normalise_queries(raw: Any) -> list[dict]:
    """Return a flat list of query dicts."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("queries", [])
    return []


def load_bundle(
    bundle_path: Path,
) -> tuple[dict, list[Path], dict, list[dict]]:
    """Load poc_input_bundle.json and resolve all referenced files.

    Returns (bundle, pdf_paths, access_manifest, queries).

    Supported bundle formats:
      A) {"documents_directory": "...", "access_manifest": "...", "query_set": "..."}
         (paths are relative to the bundle file)
      B) {"documents": [...], "access_manifest_path": "...", "query_set_path": "..."}
      C) Embedded data: {"documents": [...], "queries": [...], "access_manifest": {...}}
    """
    base = bundle_path.parent
    bundle: dict = json.loads(bundle_path.read_text(encoding="utf-8"))

    # --- access manifest ---
    # Support both "access_manifest" as a file path string and as embedded data,
    # and the legacy "access_manifest_path" key.
    manifest_dir = base  # default: resolve PDF rel-paths from bundle dir
    raw_manifest: Any = {}

    for key in ("access_manifest", "access_manifest_path"):
        if key in bundle:
            val = bundle[key]
            if isinstance(val, str):
                manifest_path = (base / val).resolve()
                raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_dir = manifest_path.parent
            else:
                raw_manifest = val   # already embedded
            break
    else:
        candidate = base / "access_manifest.json"
        if candidate.exists():
            raw_manifest = json.loads(candidate.read_text(encoding="utf-8"))
            manifest_dir = candidate.parent

    access_manifest = _normalise_manifest(raw_manifest, manifest_dir)

    # --- queries ---
    raw_qs: Any = []
    _qs_found = False
    for key in ("query_set", "query_set_path"):
        if key in bundle:
            val = bundle[key]
            if isinstance(val, str):
                raw_qs = json.loads((base / val).resolve().read_text(encoding="utf-8"))
            else:
                raw_qs = val
            _qs_found = True
            break
    if not _qs_found:
        if "queries" in bundle:
            raw_qs = bundle["queries"]
        else:
            candidate = base / "query_set.json"
            if candidate.exists():
                raw_qs = json.loads(candidate.read_text(encoding="utf-8"))
    queries = _normalise_queries(raw_qs)

    # --- PDF paths ---
    pdf_paths: list[Path] = []

    # Priority 1: resolve paths recorded in the access manifest
    for bname, meta in access_manifest.items():
        rel = meta.get("_rel_path", "")
        mdir = meta.get("_manifest_dir") or manifest_dir
        if rel:
            full = (mdir / rel).resolve()
            if full.exists() and full.suffix.lower() == ".pdf":
                pdf_paths.append(full)

    # Priority 2: bundle has an explicit "documents" list
    if not pdf_paths and "documents" in bundle:
        for doc in bundle["documents"]:
            rel = (
                doc.get("file")
                or doc.get("path")
                or doc.get("filename")
                or doc.get("file_name")
                or doc.get("name", "")
            )
            if rel:
                full = (base / rel).resolve()
                if full.exists() and full.suffix.lower() == ".pdf":
                    pdf_paths.append(full)
                    bname = full.name
                    if bname not in access_manifest:
                        access_manifest[bname] = {
                            "classification": doc.get("classification", "unclassified"),
                            "allowed_roles": doc.get("allowed_roles", []),
                        }

    # Priority 3: bundle names a documents_directory
    if not pdf_paths and "documents_directory" in bundle:
        docs_dir = (base / bundle["documents_directory"]).resolve()
        pdf_paths = sorted(docs_dir.glob("*.pdf"))

    # Priority 4: scan sibling directory
    if not pdf_paths:
        pdf_paths = sorted(base.glob("*.pdf"))

    # Remove private resolution keys from the manifest before returning
    for meta in access_manifest.values():
        meta.pop("_rel_path", None)
        meta.pop("_manifest_dir", None)

    return bundle, pdf_paths, access_manifest, queries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    configure_console_output()

    parser = argparse.ArgumentParser(
        description="Manufacturing Knowledge Base RAG Assistant PoC"
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="poc_input_bundle.json",
        help="Path to poc_input_bundle.json; all other files are resolved relative to it.",
    )
    args = parser.parse_args()

    bundle_path = Path(args.input).resolve()
    if not bundle_path.exists():
        print(f"ERROR: Input bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    config = load_config()
    rag_cfg = config.get("rag", {})
    top_k = int(rag_cfg.get("top_k", 4))
    chunk_size = int(rag_cfg.get("chunk_size_tokens", 400))
    overlap = int(rag_cfg.get("chunk_overlap_tokens", 80))

    chat_deployment = os.environ.get(
        "AZURE_CHAT_DEPLOYMENT",
        config.get("models", {}).get("extraction", "gpt-5.4"),
    )
    embedding_deployment = os.environ.get(
        "AZURE_EMBEDDING_DEPLOYMENT",
        config.get("models", {}).get("embedding", "text-embedding-3-large"),
    )
    temperature = 1 
    reasoning_effort = config.get("models", {}).get("reasoning_effort", "medium")

    print("=== Manufacturing Knowledge Base RAG Assistant - PoC ===\n")
    print(f"Input bundle : {bundle_path}")
    print(f"Chat model   : {chat_deployment}  (temp={temperature}, reasoning={reasoning_effort})")
    print(f"Embedding    : {embedding_deployment}")
    print(f"Top-k        : {top_k}\n")

    # ── Step 1: load_input ──────────────────────────────────────────────────
    bundle, pdf_paths, access_manifest, queries = load_bundle(bundle_path)
    print(f"Documents found : {[p.name for p in pdf_paths]}")
    print(f"Access manifest : {list(access_manifest.keys())}")
    print(f"Queries loaded  : {len(queries)}\n")

    if not pdf_paths:
        print("ERROR: No PDF files resolved from bundle.", file=sys.stderr)
        sys.exit(1)
    if not queries:
        print("ERROR: No queries found in bundle.", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: ingest_and_index ────────────────────────────────────────────
    print("Building local vector index...")
    client = get_azure_client()
    all_chunks = build_index(
        pdf_paths, access_manifest, client, embedding_deployment, chunk_size, overlap
    )

    # ── Steps 3+4: per-query RBAC + retrieval + generation ─────────────────
    results: list[dict] = []

    for q in queries:
        query_id = q.get("query_id") or q.get("id", "unknown")
        role = q.get("role", "employee")
        question = q.get("question") or q.get("text", "")

        print("-" * 60)
        print(f"Query : {query_id}  role={role}")
        print(f"Q     : {question[:100]}")

        access_decision, retrieved_chunks, refusal_reason = rbac_check_and_retrieve(
            question=question,
            role=role,
            all_chunks=all_chunks,
            client=client,
            embedding_deployment=embedding_deployment,
            top_k=top_k,
        )

        if access_decision == "denied":
            record = denied_record(query_id, role, question, refusal_reason)
            print(f"DENIED  |  {refusal_reason}")
        else:
            print(
                f"ALLOWED | retrieved {len(retrieved_chunks)} chunk(s): "
                + str([(c["file_name"], c["page_number"]) for c in retrieved_chunks])
            )
            answer, citations = generate_cited_answer(
                question=question,
                retrieved_chunks=retrieved_chunks,
                client=client,
                chat_deployment=chat_deployment,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )
            record = allowed_record(query_id, role, question, answer, citations)
            print(f"  Citations: {citations}")

        results.append(record)

    # ── Save output ─────────────────────────────────────────────────────────
    out_path = output_dir / "results.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"Results saved to: {out_path}")
    print("=" * 60 + "\n")
    # The file above retains Unicode. Keep only the diagnostic console copy
    # ASCII-safe so Windows cp1252 logging cannot terminate execution.
    print(json.dumps(results, indent=2, ensure_ascii=True))

    # Contract variables (for validation harness)
    extracted_fields = results
    source_text = ""


if __name__ == "__main__":
    main()