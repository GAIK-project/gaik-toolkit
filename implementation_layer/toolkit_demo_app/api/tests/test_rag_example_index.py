"""The RAG example: its two documents, and the pinned embedding model for documents and queries."""

import asyncio
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from api.routers import rag
from langchain_core.documents import Document


def test_example_documents_are_shipped_and_named_for_their_citations():
    assert len(rag.EXAMPLE_DOCUMENTS) == 2
    for document in rag.EXAMPLE_DOCUMENTS:
        path = rag.EXAMPLE_DIR / document["filename"]
        assert path.read_bytes().startswith(b"%PDF"), path
        # Answers cite the document name; the page shows it as a readable title.
        assert document["document_name"] == path.stem
        assert not set(document["document_name"]) & set("[],")


def test_loading_the_example_indexes_both_documents_into_one_collection():
    rag.RAG_INSTANCES.clear()
    workflow = MagicMock()
    workflow.index_chunk_documents.side_effect = lambda chunks: len(chunks)

    def parse(path, *, document_name, parser_choice, config):
        return [Document(page_content=f"{document_name} text", metadata={})] * 3, parser_choice

    with (
        patch.object(rag, "get_api_config", return_value={}),
        patch.object(rag, "_build_demo_workflow", return_value=workflow),
        patch.object(rag, "_parse_document_to_chunks", side_effect=parse),
    ):
        response = asyncio.run(rag.load_example_document(parser_choice="pymupdf"))
    rag.RAG_INSTANCES.clear()

    assert response.collection_id == "example-demo-pymupdf"
    assert response.document_count == 2
    assert response.chunk_count == 6
    assert [d.filename for d in response.documents] == [
        d["filename"] for d in rag.EXAMPLE_DOCUMENTS
    ]


@pytest.mark.parametrize(
    "provider,model",
    [
        ("azure", rag.EXAMPLE_EMBEDDING_MODEL),
        ("openai", rag.EXAMPLE_EMBEDDING_MODEL),
        ("aitta", None),
    ],
)
def test_demo_workflow_embeds_with_the_pinned_model(provider, model):
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
