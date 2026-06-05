"""Shared test helper: an explicit ``ProviderClient`` stub.

Lives next to the postgres_agent test files. The underscore prefix keeps
pytest from collecting it as a test module.

A plain ``MagicMock`` no longer satisfies ``isinstance(_, ProviderClient)``
on Python 3.12+ — ``runtime_checkable`` Protocols now inspect class-level
attribute annotations, not just method names, so the agent's
``isinstance(client, ProviderClient)`` branch in ``generate_sql`` /
``_synthesize_answer`` silently routed every mocked call to the
``client.beta.chat.completions.parse`` fallback path. Tests using only a
``MagicMock`` then either hung or raised ``RuntimeError("LLM did not
return a SQL query.")``.

``FakeProviderClient`` is a concrete class that implements the protocol
explicitly. Tests pass closures (``chat_parsed_impl`` / ``chat_impl``)
that record the prompts they receive and return the canned response shape
the agent expects.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse
from gaik.software_components.postgres_agent.models import GeneratedSQL


class FakeProviderClient:
    provider: str = "stub"
    model: str = "stub-model"
    raw: Any = None

    def __init__(
        self,
        chat_parsed_impl: Callable[..., BaseModel] | None = None,
        chat_impl: Callable[..., ChatResponse] | None = None,
    ) -> None:
        self._chat_parsed = chat_parsed_impl or (
            lambda **_: GeneratedSQL(sql="SELECT 1", reasoning="stub")
        )
        self._chat = chat_impl or (
            lambda **_: ChatResponse(text="stub answer", model=self.model, provider=self.provider)
        )

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self._chat(messages=messages, **kwargs)

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        return self._chat_parsed(messages=messages, response_format=response_format, **kwargs)

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]:
        yield "stub"

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[0.0] for _ in texts]
