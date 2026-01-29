"""Minimal example for running the RAGWorkflow on a sample PDF."""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_modules.RAG_workflow import RAGWorkflow


def main() -> None:
    sample_pdf = (
        Path(__file__).parent.parent.parent
        / "software_components"
        / "parsers"
        / "sample_report.pdf"
    )

    if not sample_pdf.exists():
        print("No sample PDF found.")
        print(f"Expected: {sample_pdf}")
        return

    workflow = RAGWorkflow(
        persist=True,
        persist_path=str(Path(__file__).parent / "chroma_store"),
        citations=True,
        stream=True,
        conversation_history=False,
        last_n=3,
    )

    print("Indexing document...")
    workflow.index_documents([sample_pdf])
    print("Ready. Type 'exit' to quit.")

    while True:
        query = input("\nQuestion: ").strip()
        if query.lower() == "exit":
            break
        result = workflow.ask(query, stream=False)
        print("\nAnswer:")
        print(result.answer)


if __name__ == "__main__":
    main()
