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


def test_a_number_outside_the_retrieved_chunks_is_left_as_written_and_not_cited(monkeypatch):
    generator = _generator(monkeypatch, "It runs for 36 hours [1]. Fuel is diesel [7].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "It runs for 36 hours [depot_manual.pdf, page 7]. Fuel is diesel [7]."
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7)]
    assert result.dropped_citations == []


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


def test_a_list_of_references_becomes_the_labels_of_its_chunks(monkeypatch):
    generator = _generator(monkeypatch, "Both apply [2, 1].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == ("Both apply [visitor_rules.pdf, page 2] [depot_manual.pdf, page 7].")
    assert [c.reference for c in result.citations] == [2, 1]
    assert result.dropped_citations == []


def test_a_list_with_a_number_outside_the_chunks_is_left_as_written(monkeypatch):
    generator = _generator(monkeypatch, "Both apply [2, 1, 5].")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "Both apply [2, 1, 5]."
    assert result.citations == []
    assert result.dropped_citations == []


def test_other_bracketed_text_is_left_as_written(monkeypatch):
    reply = "See [the manual](https://example.org) and the [optional] step."
    generator = _generator(monkeypatch, reply)

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == reply
    assert result.citations == []
    assert result.dropped_citations == []


def test_a_streamed_answer_resolves_references_split_across_deltas(monkeypatch):
    deltas = ["It runs for 36 hours ", "[", "1", "] and uses diesel ", "[", "2]", "."]
    generator = _generator(monkeypatch, deltas)

    result = generator.generate_with_citations(QUESTION, CHUNKS, stream=True)
    shown = list(result.answer)

    assert "".join(shown) == (
        "It runs for 36 hours [depot_manual.pdf, page 7]"
        " and uses diesel [visitor_rules.pdf, page 2]."
    )
    assert all("[1" not in delta and "[2" not in delta for delta in shown)
    assert _cited(result.citations) == [(1, "depot_manual.pdf", 7), (2, "visitor_rules.pdf", 2)]


def test_generate_returns_the_answer_with_the_built_citations(monkeypatch):
    generator = _generator(monkeypatch, ["Sign in [2", "][fake.pdf, page 9]."])

    assert generator.generate(QUESTION, CHUNKS) == "Sign in [visitor_rules.pdf, page 2]."
    assert "".join(generator.generate(QUESTION, CHUNKS, stream=True)) == (
        "Sign in [visitor_rules.pdf, page 2]."
    )


# The case of examples/software_components/RAG/answer_generator_example.py.
STRING_CONTEXT = "Invoice total amount is $1,500."
STRING_CONTEXT_REPLY = "The total amount is $1,500 [invoice.pdf, page 1]."
# The system prompt gaik 0.11.0 sends with citations=True, before the source-material
# sentence: a string context is still asked for [document_name, page X] citations.
STRING_CONTEXT_PROMPT = (
    "You are a helpful assistant that answers questions using only the provided context.\n"
    "If the context does not contain the answer, say you do not have enough information.\n"
    "Be concise and factual. Include citations in the form [document_name, page X]. "
    "When a context block starts with [Document: name, Page: X], take the document "
    "name and the page from that line."
)


@pytest.mark.parametrize("stream", [False, True], ids=["whole", "streamed"])
def test_a_string_context_keeps_the_citations_the_model_writes(monkeypatch, stream):
    generator = _generator(monkeypatch, STRING_CONTEXT_REPLY, stream=stream)
    sent = []
    create = generator.client.chat.completions.create

    def record(**kwargs):
        sent.append(kwargs["messages"])
        return create(**kwargs)

    generator.client.chat.completions.create = record

    result = generator.generate_with_citations("What is the total amount?", STRING_CONTEXT)
    answer = result.answer if isinstance(result.answer, str) else "".join(result.answer)

    assert answer == STRING_CONTEXT_REPLY
    assert result.citations == []
    assert result.dropped_citations == []
    system = sent[0][0]["content"]
    assert system.startswith(STRING_CONTEXT_PROMPT)
    assert "[1]" not in system
    assert generator.generate("What is the total amount?", STRING_CONTEXT, stream=False) == (
        STRING_CONTEXT_REPLY
    )


def test_a_string_context_leaves_a_bracketed_number_as_written(monkeypatch):
    generator = _generator(monkeypatch, "The total amount is $1,500 [1].")

    result = generator.generate_with_citations("What is the total amount?", STRING_CONTEXT)

    assert result.answer == "The total amount is $1,500 [1]."
    assert result.citations == []


def test_without_citations_the_answer_is_returned_as_written(monkeypatch):
    reply = "It runs for 36 hours [7] [depot_manual.pdf, page 99]."
    generator = _generator(monkeypatch, reply, citations=False)

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == reply
    assert result.citations == []


def test_the_history_keeps_the_answer_with_the_built_citations(monkeypatch):
    generator = _generator(
        monkeypatch, "It runs for 36 hours [1][fake.pdf, page 3].", conversation_history=True
    )

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


# Brackets that are code, data or an index stay as written. Each case is checked
# whole and streamed in every two-delta split, which must show the same text.
LEFT_AS_WRITTEN = [
    "Read `arr[0]` first.",
    "Then arr[0] holds it.",
    "Use x[2] here.",
    "The cell matrix[1][2] is set.",
    "Set nums = [1, 2] there.",
    "```python\nnums = [1, 2]\nprint(x [1])\n```\n",
    "~~~\n[2] stays\n~~~\n",
    "Call `` f([1]) `` once.",
    "It started in [2019] and has [12] sites.",
    "No reference [0] here.",
    "Sources [fake.pdf] and (depot_manual.pdf, page 9) stay.",
]


def _splits(text: str):
    for cut in range(1, len(text)):
        yield [text[:cut], text[cut:]]


@pytest.mark.parametrize("reply", LEFT_AS_WRITTEN)
def test_code_data_and_indexes_are_left_as_written(monkeypatch, reply):
    generator = _generator(monkeypatch, reply)

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == reply
    assert result.citations == []
    assert result.dropped_citations == []


MIXED = (
    "Intro [1].\n"
    "```\n"
    "rows = data[2]\n"
    "print([1, 2])\n"
    "```\n"
    "Then `x[1]` and y[2], but the visitors sign in [2]."
)
MIXED_RESOLVED = (
    "Intro [depot_manual.pdf, page 7].\n"
    "```\n"
    "rows = data[2]\n"
    "print([1, 2])\n"
    "```\n"
    "Then `x[1]` and y[2], but the visitors sign in [visitor_rules.pdf, page 2]."
)


@pytest.mark.parametrize("reply", [*LEFT_AS_WRITTEN, MIXED])
def test_a_streamed_answer_shows_what_the_whole_answer_shows(monkeypatch, reply):
    whole = _generator(monkeypatch, reply).generate_with_citations(QUESTION, CHUNKS)

    for deltas in [*_splits(reply), list(reply)]:
        streamed = _generator(monkeypatch, deltas).generate_with_citations(
            QUESTION, CHUNKS, stream=True
        )
        assert "".join(streamed.answer) == whole.answer, deltas
        assert _cited(streamed.citations) == _cited(whole.citations)


def test_references_outside_code_resolve_and_code_stays(monkeypatch):
    result = _generator(monkeypatch, MIXED).generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == MIXED_RESOLVED
    assert [c.reference for c in result.citations] == [1, 2]


def test_references_next_to_each_other_on_one_page_show_the_page_once(monkeypatch):
    chunks = [
        Document(
            page_content="a", metadata={"document_name": "depot_manual.pdf", "page_number": 7}
        ),
        Document(
            page_content="b", metadata={"document_name": "depot_manual.pdf", "page_number": 7}
        ),
    ]
    generator = _generator(monkeypatch, "It runs for 36 hours [1][2]. And [1] [2].")

    result = generator.generate_with_citations(QUESTION, chunks)

    assert result.answer == (
        "It runs for 36 hours [depot_manual.pdf, page 7]. And [depot_manual.pdf, page 7]."
    )
    assert [c.reference for c in result.citations] == [1, 2]


def test_a_citation_removed_at_a_line_start_leaves_no_space(monkeypatch):
    generator = _generator(monkeypatch, "Intro.\n[fake.pdf, page 9] Refill weekly.")

    result = generator.generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == "Intro.\nRefill weekly."
    assert result.dropped_citations == ["[fake.pdf, page 9]"]


AFTER_A_DROPPED_CITATION = [
    (
        "See the report [fake.pdf, page 9][1].",
        "See the report [depot_manual.pdf, page 7].",
        [1],
        ["[fake.pdf, page 9]"],
    ),
    (
        "See [fake.pdf, page 9][other.pdf, page 1][2] first.",
        "See [visitor_rules.pdf, page 2] first.",
        [2],
        ["[fake.pdf, page 9]", "[other.pdf, page 1]"],
    ),
    (
        "It runs [1][fake.pdf, page 9][1] long.",
        "It runs [depot_manual.pdf, page 7] long.",
        [1],
        ["[fake.pdf, page 9]"],
    ),
    # Not a citation: the bracket stays, with the space the removed one had.
    ("See [fake.pdf, page 9][x] now.", "See [x] now.", [], ["[fake.pdf, page 9]"]),
    ("See the report [fake.pdf, page 9].", "See the report.", [], ["[fake.pdf, page 9]"]),
]


@pytest.mark.parametrize(("reply", "answer", "cited", "dropped"), AFTER_A_DROPPED_CITATION)
def test_a_reference_right_after_a_removed_citation_still_resolves(
    monkeypatch, reply, answer, cited, dropped
):
    result = _generator(monkeypatch, reply).generate_with_citations(QUESTION, CHUNKS)

    assert result.answer == answer
    assert [c.reference for c in result.citations] == cited
    assert result.dropped_citations == dropped
    for deltas in [*_splits(reply), list(reply)]:
        streamed = _generator(monkeypatch, deltas).generate_with_citations(
            QUESTION, CHUNKS, stream=True
        )
        assert "".join(streamed.answer) == answer, deltas


PAGELESS_CHUNKS = [
    Document(page_content="Refill weekly.", metadata={"document_name": "notes.md"}),
    # TextRagParser writes "Unknown" for a Word or text file, which has no pages.
    Document(
        page_content="Sign in first.",
        metadata={"document_name": "guide.docx", "page_number": "Unknown"},
    ),
    *CHUNKS,
]


@pytest.mark.parametrize(
    "written",
    ["[notes.md, page unknown]", "[Document: notes.md, Page: unknown]", "[notes, page Unknown]"],
)
def test_a_chunk_without_a_page_is_cited_as_its_context_header_names_it(monkeypatch, written):
    generator = _generator(monkeypatch, f"Refill weekly {written}. Sign in [guide, page unknown].")

    result = generator.generate_with_citations(QUESTION, PAGELESS_CHUNKS)

    assert result.answer == "Refill weekly [notes.md]. Sign in [guide.docx, page Unknown]."
    assert [c.reference for c in result.citations] == [1, 2]
    assert result.dropped_citations == []


def test_a_chunk_with_an_empty_page_is_cited_without_one(monkeypatch):
    chunks = [
        Document(
            page_content="Refill weekly.", metadata={"document_name": "notes.md", "page_number": ""}
        )
    ]
    generator = _generator(monkeypatch, "Refill weekly [notes.md, page unknown].")

    result = generator.generate_with_citations(QUESTION, chunks)

    assert result.answer == "Refill weekly [notes.md]."
    assert result.dropped_citations == []


def test_page_unknown_does_not_match_a_chunk_that_has_a_page(monkeypatch):
    generator = _generator(monkeypatch, "It runs for 36 hours [depot_manual.pdf, page unknown].")

    result = generator.generate_with_citations(QUESTION, PAGELESS_CHUNKS)

    assert result.answer == "It runs for 36 hours."
    assert result.dropped_citations == ["[depot_manual.pdf, page unknown]"]


def test_the_context_header_of_a_pageless_chunk_says_page_unknown():
    material = answer_generator_module.SourceMaterial()
    context = AnswerGenerator._format_context(PAGELESS_CHUNKS[:1], material, references=True)

    assert "[1] [Document: notes.md, Page: unknown]" in context
