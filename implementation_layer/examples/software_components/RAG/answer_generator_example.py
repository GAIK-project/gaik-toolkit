"""Minimal example for AnswerGenerator."""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.RAG.answer_generator import AnswerGenerator


def main() -> None:
    generator = AnswerGenerator(
        citations=True,
        stream=False,
        conversation_history=True,
        last_n=5,
    )

    answer = generator.generate(
        query="What is the total amount?",
        context="Invoice total amount is $1,500.",
    )

    print(answer)


if __name__ == "__main__":
    main()
