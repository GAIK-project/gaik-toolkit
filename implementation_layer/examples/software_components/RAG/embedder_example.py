"""Minimal example for running the Embedder on text inputs."""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.embedder import Embedder, get_openai_config


def main() -> None:
    texts = [
        "Invoice #12345 total amount $1,500",
        "Project Alpha budget 2.5M EUR",
    ]

    config = get_openai_config(use_azure=True)
    embedder = Embedder(config=config)

    embeddings, documents = embedder.embed(texts)

    print(f"Embeddings: {len(embeddings)}")
    if embeddings:
        print(f"Embedding dimension: {len(embeddings[0])}")
    print(f"Documents: {len(documents)}")
    print(f"First metadata: {documents[0].metadata}")


if __name__ == "__main__":
    main()
