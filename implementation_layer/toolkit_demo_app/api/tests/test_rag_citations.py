"""The streamed RAG answer lists as sources only the retrieved chunks it cites."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from api.routers import rag
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document

CHUNKS = [
    Document(
        page_content="New staff get a laptop on the first day.",
        metadata={"document_name": "halden_onboarding", "page_number": 3},
    ),
    Document(
        page_content="Holidays are agreed with the team lead.",
        metadata={"document_name": "halden_handbook", "page_number": 5},
    ),
]


@pytest.fixture(autouse=True)
def empty_store(monkeypatch) -> None:
    monkeypatch.setattr(rag, "RAG_INSTANCES", {})
    monkeypatch.setattr(rag, "_USAGE", {})
    monkeypatch.setattr(rag, "_collection_locks", {})


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(rag.router, prefix="/rag")
    return TestClient(app)


def _workflow(answer_generator) -> SimpleNamespace:
    return SimpleNamespace(
        embedder=SimpleNamespace(embed_query=lambda question: [0.0]),
        vector_store=SimpleNamespace(
            search=lambda embedding, **kwargs: [(chunk, 0.9) for chunk in CHUNKS]
        ),
        answer_generator=answer_generator,
    )


def _result(response) -> dict:
    events = response.text.strip().split("\n\n")
    [result] = [e for e in events if e.startswith("event: result\n")]
    return json.loads(result.split("data: ", 1)[1])


def _stream(reply: str) -> object:
    """A gaik AnswerGenerator whose model replies ``reply`` in two deltas."""
    generator_module = pytest.importorskip(
        "gaik.software_components.RAG.answer_generator.generator"
    )
    middle = len(reply) // 2

    class _Completions:
        def create(self, *, model, messages, stream=False, **kwargs):
            return iter(
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
                for part in (reply[:middle], reply[middle:])
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    original = generator_module.build_compat_client
    generator_module.build_compat_client = lambda config: client
    try:
        return generator_module.AnswerGenerator(
            config={"model": "test-model"},
            citations=True,
            stream=True,
            prompt=rag.CUSTOM_RAG_PROMPT,
        )
    finally:
        generator_module.build_compat_client = original


def test_sources_are_the_cited_chunks_and_never_an_invented_page() -> None:
    generator = _stream("A laptop on day one [1]. Ask HR [halden_handbook, page 9].")
    rag.RAG_INSTANCES["c1"] = _workflow(generator)

    response = _client().post(
        "/rag/query/stream", data={"question": "Laptop?", "collection_id": "c1"}
    )

    result = _result(response)
    assert result["answer"] == "A laptop on day one [halden_onboarding, page 3]. Ask HR."
    assert result["sources"] == [
        {"document_name": "halden_onboarding", "relevance_score": None, "page_number": 3}
    ]


def test_a_generator_without_a_citation_list_still_answers() -> None:
    def generate(question, documents, *, stream):
        return iter(["Holidays go via the lead ", "[halden_handbook, page 5]."])

    rag.RAG_INSTANCES["c2"] = _workflow(SimpleNamespace(generate=generate))

    response = _client().post(
        "/rag/query/stream", data={"question": "Holidays?", "collection_id": "c2"}
    )

    result = _result(response)
    assert result["answer"] == "Holidays go via the lead [halden_handbook, page 5]."
    assert [s["page_number"] for s in result["sources"]] == [5]


def test_the_prompt_asks_for_numbered_references_only_when_gaik_resolves_them() -> None:
    class _Resolves:
        def generate_with_citations(self): ...

    class _Older:
        def generate(self): ...

    numbered = rag.rag_prompt(_Resolves)
    named = rag.rag_prompt(_Older)

    assert "such as [1]" in numbered
    assert "such as [1]" not in named
    assert "- Include citations [document_name, page X] when answering questions" in named
    for prompt in (numbered, named):
        assert "{citation_guideline}" not in prompt
        assert prompt.endswith("Context:\n{context}\n\nQuestion: {query}")


def test_a_page_cited_twice_is_one_source() -> None:
    page = Document(
        page_content="New staff get a laptop on the first day.",
        metadata={"document_name": "halden_onboarding", "page_number": 3},
    )
    citations = [SimpleNamespace(document=page), SimpleNamespace(document=page)]

    sources = rag._cited_sources(citations, [])

    assert sources == [
        {"document_name": "halden_onboarding", "relevance_score": None, "page_number": 3}
    ]
