"""AnswerGenerator builds the citations from the retrieved chunks, not from the model.

Offline: a fake chat client returns a set reply, whole or in deltas.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from gaik.software_components.RAG.answer_generator import AnswerGenerator, Citation
from gaik.software_components.RAG.answer_generator import generator as answer_generator_module

langchain_documents = pytest.importorskip("langchain_core.documents")
Document = langchain_documents.Document

QUESTION = "How long does the backup generator run?"
CHUNKS = [
    Document(
        page_content="The backup generator runs for 36 hours on a full tank.",
        metadata={"document_name": "depot_manual.pdf", "page_number": 7, "chunk_id": 3},
    ),
    Document(
        page_content="Visitors sign in at reception.",
        metadata={"document_name": "visitor_rules.pdf", "page_number": 2, "chunk_id": 0},
    ),
]


class _FakeCompletions:
    """Returns ``reply``; when streaming, in the deltas it is given as a list."""

    def __init__(self, reply: str | list[str]) -> None:
        self.reply = reply

    def create(self, *, model, messages, stream=False, **kwargs):
        if stream:
            deltas = self.reply if isinstance(self.reply, list) else [self.reply]
            return iter(
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=delta))])
                for delta in deltas
            )
        text = self.reply if isinstance(self.reply, str) else "".join(self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _generator(monkeypatch, reply: str | list[str], **kwargs) -> AnswerGenerator:
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(reply)))
    monkeypatch.setattr(answer_generator_module, "build_compat_client", lambda config: client)
    kwargs.setdefault("stream", False)
    kwargs.setdefault("citations", True)
    return AnswerGenerator(config={"model": "test-model"}, **kwargs)


def _cited(citations: list[Citation]) -> list[tuple[int, str | None, object]]:
    return [(c.reference, c.document_name, c.page_number) for c in citations]


def test_a_reference_becomes_the_document_and_page_of_its_chunk(monkeypatch):
    generator = _generator(monkeypatch, "It runs for 36 hours [1].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "It runs for 36 hours [depot_manual.pdf, page 7]."
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7)]
    assert result.citations[0].document is CHUNKS[0]
    assert result.dropped_citations == []


def test_a_reference_outside_the_retrieved_chunks_never_reaches_the_citations(monkeypatch):
    generator = _generator(monkeypatch, "It runs for 36 hours [1]. Fuel is diesel [7].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "It runs for 36 hours [depot_manual.pdf, page 7]. Fuel is diesel."
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7)]
    assert result.dropped_citations == ["[7]"]


def test_a_page_the_retrieval_did_not_return_never_reaches_the_citations(monkeypatch):
    generator = _generator(
        monkeypatch,
        "It runs for 36 hours [depot_manual.pdf, page 99]."
        " Refill weekly [service_plan.pdf, page 2].",
    )

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "It runs for 36 hours. Refill weekly."
    assert result.citations == []
    assert result.dropped_citations == [
        "[depot_manual.pdf, page 99]",
        "[service_plan.pdf, page 2]",
    ]
    assert "99" not in result.answer
    assert "service_plan" not in result.answer


def test_a_document_and_page_written_by_the_model_is_kept_when_a_chunk_has_them(monkeypatch):
    generator = _generator(monkeypatch, "Sign in first [Document: visitor_rules, Page: 2].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "Sign in first [visitor_rules.pdf, page 2]."
    assert _cited(result.citations) == [(2, "visitor_rules.pdf", 2)]


def test_a_list_of_references_keeps_the_retrieved_ones_and_drops_the_rest(monkeypatch):
    generator = _generator(monkeypatch, "Both apply [2, 1, 5].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == ("Both apply [visitor_rules.pdf, page 2] [depot_manual.pdf, page 7].")
    assert [c.reference for c in result.citations] == [2, 1]
    assert result.dropped_citations == ["[5]"]


def test_other_bracketed_text_is_left_as_written(monkeypatch):
    reply = "See [the manual](https://example.org) and the [optional] step."
    generator = _generator(monkeypatch, reply)

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == reply
    assert result.citations == []
    assert result.dropped_citations == []


def test_a_streamed_answer_resolves_references_split_across_deltas(monkeypatch):
    deltas = ["It runs for 36 hours ", "[", "1", "] and uses diesel ", "[", "4]", "."]
    generator = _generator(monkeypatch, deltas)

    result = generator.generate_with_citations(QUESTION, CHUNKS, stream=True)
    shown = list(result.answer)

    assert "".join(shown) == ("It runs for 36 hours [depot_manual.pdf, page 7] and uses diesel.")
    assert all("[4" not in delta for delta in shown)
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7)]
    assert result.dropped_citations == ["[4]"]


def test_generate_returns_the_answer_with_the_built_citations(monkeypatch):
    generator = _generator(monkeypatch, ["Sign in [2", "][9]."])

    assert generator.generate(QUESTION, CHUNKS) == "Sign in [visitor_rules.pdf, page 2]."
    assert "".join(generator.generate(QUESTION, CHUNKS, stream=True)) == (
        "Sign in [visitor_rules.pdf, page 2]."
    )


def test_a_string_context_has_no_chunks_to_cite(monkeypatch):
    generator = _generator(monkeypatch, "Total is 1 500 EUR [1] [invoice.pdf, page 1].")

    result = generator.generate_with_citations(QUESTION, "Invoice total is 1 500 EUR.")

    assert result.answer == "Total is 1 500 EUR."
    assert result.citations == []
    assert result.dropped_citations == ["[1]", "[invoice.pdf, page 1]"]


def test_without_citations_the_answer_is_returned_as_written(monkeypatch):
    reply = "It runs for 36 hours [7] [depot_manual.pdf, page 99]."
    generator = _generator(monkeypatch, reply, citations=False)

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == reply
    assert result.citations == []


def test_the_history_keeps_the_answer_with_the_built_citations(monkeypatch):
    generator = _generator(monkeypatch, "It runs for 36 hours [1][3].", conversation_history=True)

    generator.generate(QUESTION, CHUNKS)

    assert generator._history == [(QUESTION, "It runs for 36 hours [depot_manual.pdf, page 7].")]


def test_rag_workflow_returns_the_citations_of_the_retrieved_chunks(monkeypatch):
    pipeline = pytest.importorskip("gaik.software_modules.RAG_workflow.pipeline")
    generator = _generator(monkeypatch, "It runs for 36 hours [1] [depot_manual.pdf, page 8].")
    workflow = object.__new__(pipeline.RAGWorkflow)
    workflow.retriever = SimpleNamespace(search=lambda query, **kwargs: CHUNKS)
    workflow.answer_generator = generator

    result = workflow.ask(QUESTION, stream=False)

    assert result.answer == "It runs for 36 hours [depot_manual.pdf, page 7]."
    assert result.documents is CHUNKS
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7)]
    assert result.dropped_citations == ["[depot_manual.pdf, page 8]"]
