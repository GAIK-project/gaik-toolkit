"""Live test of the RAG AnswerGenerator over two fixed context chunks.

The chunks are given as retrieved Documents, so no embedding call is needed: one chat
call, streamed (the generator's default, and how the demo app's RAG page calls it), with
citations on, as RAGWorkflow sets them by default.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

from __future__ import annotations

import os

import pytest
from gaik.software_components.llm import get_llm_config
from gaik.software_components.RAG.answer_generator import AnswerGenerator
from langchain_core.documents import Document

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

CHUNKS = [
    Document(
        page_content=(
            "The backup generator at the Lakeside depot runs for 36 hours on a full tank of diesel."
        ),
        metadata={"document_name": "depot_manual.pdf", "page_number": 7},
    ),
    Document(
        page_content="Visitors sign in at the reception desk before entering the warehouse.",
        metadata={"document_name": "visitor_rules.pdf", "page_number": 2},
    ),
]


def test_answer_generator_answers_from_the_given_chunks():
    generator = AnswerGenerator(config=get_llm_config("azure"), citations=True)

    answer = "".join(
        generator.generate("How long does the backup generator run on a full tank?", CHUNKS)
    )
    print(answer)

    assert answer.strip()
    assert "36" in answer, answer
    assert "depot_manual" in answer, answer
