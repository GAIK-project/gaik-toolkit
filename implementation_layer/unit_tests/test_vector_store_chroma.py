"""The Chroma-backed VectorStore stores and filters like the in-memory one."""

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("langchain_core")

from gaik.software_components.RAG.vector_store.vector_store import VectorStore  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


@pytest.fixture(params=[False, True], ids=["memory", "chroma"])
def store(request, tmp_path):
    return VectorStore(persist=request.param, persist_path=str(tmp_path / "chroma"))


def test_a_second_add_keeps_the_first_documents_and_adds_the_new_ones(store):
    store.add([Document(page_content="first", metadata={"n": 1})], [[1.0, 0.0]])
    store.add([Document(page_content="second", metadata={"n": 2})], [[0.0, 1.0]])

    assert store.count() == 2
    found = [doc.page_content for doc, _ in store.search([0.0, 1.0], top_k=2)]
    assert found == ["second", "first"]


def test_a_document_without_metadata_is_stored(store):
    store.add([Document(page_content="bare")], [[1.0, 0.0]])

    [(doc, _)] = store.search([1.0, 0.0], top_k=1)
    assert doc.page_content == "bare"
    assert doc.metadata == {}


def test_a_metadata_value_of_none_does_not_stop_the_add(store):
    store.add([Document(page_content="chunk", metadata={"heading": None, "page": 3})], [[1.0, 0.0]])

    [(doc, _)] = store.search([1.0, 0.0], top_k=1)
    assert doc.metadata.get("heading") is None
    assert doc.metadata["page"] == 3


def test_filters_on_several_keys_must_all_match(store):
    store.add(
        [
            Document(page_content="a", metadata={"doc": "x", "page": 1}),
            Document(page_content="b", metadata={"doc": "x", "page": 2}),
            Document(page_content="c", metadata={"doc": "y", "page": 1}),
        ],
        [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
    )

    found = store.search([1.0, 0.0], top_k=5, filters={"doc": "x", "page": 1})

    assert [doc.page_content for doc, _ in found] == ["a"]


def test_adding_nothing_is_a_no_op(store):
    store.add([], [])

    assert store.count() == 0
