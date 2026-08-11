"""Manufacturing Internal Knowledge Assistant -- Proof of Concept

Role-aware RAG pipeline with RBAC access control and [file_name, page_number] citations.
Reads queries from a supplied input bundle, filters document access by role, and writes
RAGAnswerRecord results to output/results.json.

Usage:
    python run_poc.py --input <path-to-poc_input_bundle.json>

RBAC logic (applied per query):
    1. Identify documents restricted for the query role (from access_manifest).
    2. Query the FULL index (no filter) to detect whether the answer lives in a
       restricted document.  If any top-k result is from a restricted doc → deny.
    3. Otherwise query with a Chroma ``document_name`` filter that limits retrieval
       to the role's allowed documents, then generate a cited answer.

Role is always taken from the query record; it is never inferred from question text.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# Resolve the GAIK src directory relative to this file.
# Depth: poc/ → a34c17e7bc10/ → .wizard_workspaces/ → api/ → toolkit_demo_app/ → implementation_layer/
_gaik_src = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "src"
if _gaik_src.exists():
    sys.path.insert(0, str(_gaik_src))

from gaik.software_modules.RAG_workflow import RAGWorkflow  # noqa: E402


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Input-bundle helpers
# ---------------------------------------------------------------------------

def load_input_bundle(bundle_path: Path) -> dict:
    with open(bundle_path, encoding="utf-8") as f:
        return json.load(f)


def load_access_manifest(manifest_path: Path) -> list[dict]:
    """Return the ``documents`` list from access_manifest.json."""
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["documents"]


def load_query_set(query_set_path: Path) -> list[dict]:
    """Return the ``queries`` list from query_set.json."""
    with open(query_set_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


def _basename(file_field: str) -> str:
    """Extract just the filename from a relative path like 'documents/foo.pdf'."""
    return Path(file_field).name


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

def allowed_basenames(manifest_docs: list[dict], role: str) -> list[str]:
    return [_basename(d["file"]) for d in manifest_docs if role in d.get("allowed_roles", [])]


def restricted_basenames(manifest_docs: list[dict], role: str) -> list[str]:
    return [_basename(d["file"]) for d in manifest_docs if role not in d.get("allowed_roles", [])]


# ---------------------------------------------------------------------------
# Citation builder
# ---------------------------------------------------------------------------

def build_citations(documents: list[Any]) -> list[list]:
    """
    Build deduplicated [[file_name, page_number], ...] pairs from retrieved
    documents.  ``file_name`` is the bare filename string; ``page_number`` is
    a 1-based integer.
    """
    seen: set[tuple] = set()
    citations: list[list] = []
    for doc in documents:
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        raw_name = meta.get("document_name") or meta.get("source", "")
        file_name = Path(raw_name).name if raw_name else ""
        page_raw = meta.get("page_number", 1)
        try:
            page_number = int(page_raw)
        except (TypeError, ValueError):
            page_number = 1
        key = (file_name, page_number)
        if file_name and key not in seen:
            seen.add(key)
            citations.append([file_name, page_number])
    return citations


# ---------------------------------------------------------------------------
# Query processor
# ---------------------------------------------------------------------------

def process_query(
    workflow: RAGWorkflow,
    manifest_docs: list[dict],
    query_id: str,
    role: str,
    question: str,
    top_k: int = 4,
) -> dict:
    """
    Process one query with RBAC and return a RAGAnswerRecord dict.

    access_decision is 'denied' when:
      - The full-collection retrieval surfaces a restricted document in its
        top-k results, meaning the answer exists but is out of scope for
        this role.

    access_decision is 'allowed' when:
      - All top-k results are from documents the role may access, or
      - The restricted-document list is empty for this role (manager).
    """
    allowed = allowed_basenames(manifest_docs, role)
    restricted = restricted_basenames(manifest_docs, role)

    # --- Step 1: detect restricted-document hits ---------------------------
    if restricted:
        full_result = workflow.ask(question, top_k=top_k, stream=False)
        full_names = {
            Path(
                doc.metadata.get("document_name", doc.metadata.get("source", ""))
            ).name
            for doc in full_result.documents
        }
        if full_names & set(restricted):
            return {
                "query_id": query_id,
                "role": role,
                "question": question,
                "access_decision": "denied",
                "answer": (
                    "Access denied. The information you requested is contained in a "
                    "document that your role is not authorised to access."
                ),
                "citations": [],
                "refusal_reason": (
                    "The requested information exists in a management-confidential "
                    "document. Access is restricted to authorised roles only."
                ),
            }

    # --- Step 2: role-filtered retrieval and answer generation -------------
    if not allowed:
        return {
            "query_id": query_id,
            "role": role,
            "question": question,
            "access_decision": "denied",
            "answer": "Access denied. No documents are accessible to your role.",
            "citations": [],
            "refusal_reason": "No documents are authorised for your role.",
        }

    # Apply document-name filter only when some docs are excluded
    total_docs = len(manifest_docs)
    filters: dict | None = (
        {"document_name": {"$in": allowed}} if len(allowed) < total_docs else None
    )

    role_result = workflow.ask(question, top_k=top_k, filters=filters, stream=False)
    answer = getattr(role_result, "answer", str(role_result))
    citations = build_citations(role_result.documents)

    if not role_result.documents:
        return {
            "query_id": query_id,
            "role": role,
            "question": question,
            "access_decision": "allowed",
            "answer": (
                "The information was not found in the documents authorised for your role."
            ),
            "citations": [],
            "refusal_reason": None,
        }

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
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manufacturing Internal Knowledge Assistant PoC"
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="BUNDLE",
        help="Path to poc_input_bundle.json",
    )
    cli_args = parser.parse_args()

    bundle_path = Path(cli_args.input).resolve()
    if not bundle_path.exists():
        print(f"ERROR: Bundle file not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    bundle_dir = bundle_path.parent

    # -- Load bundle and resolve all paths relative to bundle file ----------
    bundle = load_input_bundle(bundle_path)
    manifest_path = (bundle_dir / bundle["access_manifest"]).resolve()
    query_set_path = (bundle_dir / bundle["query_set"]).resolve()
    docs_dir = (bundle_dir / bundle["documents_directory"]).resolve()

    # -- Load manifest and queries ------------------------------------------
    manifest_docs = load_access_manifest(manifest_path)
    queries = load_query_set(query_set_path)

    # -- Resolve document paths --------------------------------------------
    doc_filenames = [_basename(d["file"]) for d in manifest_docs]
    doc_paths = [docs_dir / fn for fn in doc_filenames]
    missing = [p for p in doc_paths if not p.exists()]
    if missing:
        print(
            f"ERROR: Missing document(s): {[str(p) for p in missing]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # -- Prepare output directory and Chroma store --------------------------
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir = output_dir / "chroma_store"

    # Always start with a fresh index so re-runs don't accumulate duplicates
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)

    # -- Build RAGWorkflow --------------------------------------------------
    config = load_config()
    workflow = RAGWorkflow(
        use_azure=config.get("use_azure", True),
        persist=True,
        persist_path=str(chroma_dir),
        collection_name="manufacturing_knowledge",
        citations=True,
        conversation_history=False,
        stream=False,
        retriever_top_k=4,
    )

    # -- Index all documents with explicit filenames -----------------------
    print(f"Indexing {len(doc_paths)} document(s):")
    for fn in doc_filenames:
        print(f"  - {fn}")
    workflow.index_documents(doc_paths, filenames=doc_filenames)
    print("Index ready.\n")

    # -- Process all queries -----------------------------------------------
    results: list[dict] = []
    for q in queries:
        query_id = q["query_id"]
        role = q["role"]
        question = q["question"]
        print(f"[{query_id}] role={role}  {question[:70]}...")
        record = process_query(
            workflow=workflow,
            manifest_docs=manifest_docs,
            query_id=query_id,
            role=role,
            question=question,
            top_k=4,
        )
        results.append(record)
        n_cites = len(record["citations"])
        print(f"        -> access_decision={record['access_decision']}, citations={n_cites}")

    # -- Save results -------------------------------------------------------
    output_path = output_dir / "results.json"
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResults saved to: {output_path}")
    print(f"Processed {len(results)} quer{'y' if len(results) == 1 else 'ies'}.")


if __name__ == "__main__":
    main()
