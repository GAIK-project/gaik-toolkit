"""Tests for AnswerGenerator prompt construction."""

import pytest
from gaik.software_components.RAG.answer_generator import AnswerGenerator
from gaik.software_components.RAG.answer_generator import generator as answer_generator_module
from gaik.software_components.RAG.answer_generator.generator import (
    DEFAULT_PROMPT,
    DEFAULT_PROMPT_WITH_CITATIONS,
)


def _generator(*, prompt: str | None = None, citations: bool = False) -> AnswerGenerator:
    generator = AnswerGenerator.__new__(AnswerGenerator)
    generator.prompt = prompt
    generator.citations = citations
    return generator


@pytest.mark.parametrize(
    ("prompt", "missing"),
    [
        ("Question: {query}", ["{context}"]),
        ("Context: {context}", ["{query}"]),
        ('JSON: {"ok": true}', ["{context}", "{query}"]),
    ],
)
def test_custom_prompt_requires_query_and_context(prompt: str, missing: list[str]) -> None:
    generator = _generator(prompt=prompt)

    with pytest.raises(ValueError) as exc_info:
        generator._build_prompt("What is the answer?", "The answer is 42.")

    for placeholder in missing:
        assert placeholder in str(exc_info.value)


def test_constructor_rejects_custom_prompt_without_grounding_placeholders(monkeypatch) -> None:
    monkeypatch.setattr(
        answer_generator_module,
        "build_compat_client",
        lambda config: pytest.fail("client should not be created for an invalid prompt"),
    )

    with pytest.raises(ValueError, match=r"\{context\}, \{query\}"):
        AnswerGenerator(config={"model": "test"}, prompt="Answer briefly.")


def test_custom_prompt_substitutes_placeholders_and_preserves_json_braces() -> None:
    generator = _generator(prompt='{"question": "{query}", "evidence": "{context}"}')

    prompt = generator._build_prompt("What is the date?", "Due date: July 1")

    assert prompt == '{"question": "What is the date?", "evidence": "Due date: July 1"}'


def test_custom_prompt_unescapes_legacy_doubled_braces() -> None:
    generator = _generator(prompt='{{"question": "{query}", "evidence": "{context}"}}')

    prompt = generator._build_prompt("What is the date?", "Due date: July 1")

    assert prompt == '{"question": "What is the date?", "evidence": "Due date: July 1"}'


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        # A nested JSON example ends in "}}"; it is text, not an escaped brace.
        (
            'Reply as JSON like {"answer": {"text": "..."}} using {context} for {query}',
            'Reply as JSON like {"answer": {"text": "..."}} using Evidence for Question',
        ),
        (
            '{"question": "{query}", "meta": {"evidence": "{context}"}}',
            '{"question": "Question", "meta": {"evidence": "Evidence"}}',
        ),
        # Every other brace doubled: a str.format template, nested or not.
        (
            '{{"question": "{query}", "meta": {{"evidence": "{context}"}}}}',
            '{"question": "Question", "meta": {"evidence": "Evidence"}}',
        ),
        ("{{{query}}} and {{{context}}}", "{Question} and {Evidence}"),
    ],
)
def test_custom_prompt_keeps_nested_json_and_reads_format_templates(
    template: str, expected: str
) -> None:
    assert _generator(prompt=template)._build_prompt("Question", "Evidence") == expected


def test_escaped_placeholders_do_not_count_as_placeholders() -> None:
    generator = _generator(prompt="Write {{query}} and {{context}} literally.")

    with pytest.raises(ValueError, match=r"\{context\}, \{query\}"):
        generator._build_prompt("Question", "Evidence")


def test_custom_prompt_does_not_reformat_braces_in_query_or_context() -> None:
    generator = _generator(prompt="Question: {query}\nContext: {context}")

    prompt = generator._build_prompt("What does {context} mean?", '{"query": "literal {query}"}')

    assert prompt == ('Question: What does {context} mean?\nContext: {"query": "literal {query}"}')


def test_custom_prompt_replaces_repeated_placeholders() -> None:
    generator = _generator(prompt="{query} / {query}\n{context} / {context}")

    prompt = generator._build_prompt("Question", "Evidence")

    assert prompt == "Question / Question\nEvidence / Evidence"


@pytest.mark.parametrize(
    ("citations", "template"),
    [(False, DEFAULT_PROMPT), (True, DEFAULT_PROMPT_WITH_CITATIONS)],
)
def test_default_prompts_are_unchanged(citations: bool, template: str) -> None:
    generator = _generator(citations=citations)

    prompt = generator._build_prompt("Question", "Evidence")

    assert prompt == template.format(query="Question", context="Evidence")
