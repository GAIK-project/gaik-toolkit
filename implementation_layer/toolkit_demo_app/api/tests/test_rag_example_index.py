"""The pre-indexed RAG example only answers well when queries use its embedding model."""

import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from api.routers import rag


def test_example_index_matches_the_pinned_model_and_names_only_its_file():
    index = json.loads(rag.EXAMPLE_INDEX_PATH.read_text(encoding="utf-8"))
    assert index["metadata"]["embedding_model"] == rag.EXAMPLE_EMBEDDING_MODEL
    # The index is served publicly, so chunk metadata must not carry a local path.
    assert {chunk["metadata"]["source"] for chunk in index["chunks"]} == {rag.EXAMPLE_FILENAME}


@pytest.mark.parametrize(
    "provider,model",
    [
        ("azure", rag.EXAMPLE_EMBEDDING_MODEL),
        ("openai", rag.EXAMPLE_EMBEDDING_MODEL),
        ("aitta", None),
    ],
)
def test_demo_workflow_embeds_with_the_example_index_model(provider, model):
    components = (
        "answer_generator.AnswerGenerator",
        "retriever.Retriever",
        "vector_store.VectorStore",
    )
    with ExitStack() as stack:
        for name in components:
            stack.enter_context(patch(f"gaik.software_components.RAG.{name}"))
        embedder = stack.enter_context(patch("gaik.software_components.RAG.embedder.Embedder"))
        # gaik 0.8 configs name text-embedding-3-small; the pin must win over it.
        config = {
            "provider": provider,
            "model": "chat",
            "embedding_model": "text-embedding-3-small",
        }
        rag.DemoRagWorkflow(config=config, collection_name="test")
    assert embedder.call_args.kwargs["model"] == model
