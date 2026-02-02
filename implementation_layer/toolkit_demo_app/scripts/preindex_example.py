#!/usr/bin/env python3
"""
Pre-index the example PDF for fast demo loading.

This script parses the example PDF with docling, generates embeddings,
and saves everything to a JSON file that can be loaded instantly.

Usage:
    cd implementation_layer/toolkit_demo_app
    uv run python scripts/preindex_example.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env.local
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from gaik.software_components.config import get_openai_config
from gaik.software_modules.RAG_workflow import RAGWorkflow

# Paths
EXAMPLE_PDF = Path(__file__).parent.parent / "public" / "GAIK_Test_Document_Demo.pdf"
OUTPUT_JSON = Path(__file__).parent.parent / "public" / "example-index.json"


def main():
    """Pre-index the example PDF and save to JSON."""
    print(f"Pre-indexing: {EXAMPLE_PDF}")

    if not EXAMPLE_PDF.exists():
        print(f"ERROR: Example PDF not found at {EXAMPLE_PDF}")
        sys.exit(1)

    # Get API config
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set AZURE_API_KEY or OPENAI_API_KEY environment variable")
        sys.exit(1)

    config = get_openai_config(use_azure=use_azure)
    print(f"Using {'Azure' if use_azure else 'OpenAI'} API")

    # Create workflow and index the document
    print("Parsing PDF with docling (this may take a moment)...")
    workflow = RAGWorkflow(
        api_config=config,
        persist=False,  # In-memory, we'll export manually
        collection_name="gaik_rag_example",
        retriever_top_k=5,
        citations=True,
        stream=True,
    )

    result = workflow.index_documents(
        [str(EXAMPLE_PDF)],
        filenames=["GAIK_Test_Document_Demo"],
    )

    print(f"Indexed {result.num_chunks} chunks from {result.num_documents} document(s)")

    # Export to JSON
    chunks_data = []
    for doc, embedding in zip(
        workflow.vector_store._documents,
        workflow.vector_store._embeddings,
    ):
        chunks_data.append({
            "page_content": doc.page_content,
            "metadata": doc.metadata,
            "embedding": embedding,
        })

    export_data = {
        "metadata": {
            "collection_id": "example-demo",
            "source_file": "GAIK_Test_Document_Demo.pdf",
            "created_at": datetime.now().isoformat(),
            "num_chunks": len(chunks_data),
            "embedding_model": config.get("embedding_model", "text-embedding-3-large"),
        },
        "chunks": chunks_data,
    }

    # Write JSON
    print(f"Writing to {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False)

    # Print file size
    file_size = OUTPUT_JSON.stat().st_size
    if file_size > 1024 * 1024:
        size_str = f"{file_size / (1024 * 1024):.1f} MB"
    else:
        size_str = f"{file_size / 1024:.1f} KB"

    print(f"Done! Created {OUTPUT_JSON.name} ({size_str})")
    print(f"  - Chunks: {len(chunks_data)}")
    print(f"  - Embedding dimensions: {len(chunks_data[0]['embedding']) if chunks_data else 0}")


if __name__ == "__main__":
    main()
