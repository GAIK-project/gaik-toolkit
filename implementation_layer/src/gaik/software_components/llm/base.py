"""Provider-agnostic LLM client interface."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

ChatMessage = dict[str, Any]


@dataclass
class ChatResponse:
    text: str
    model: str
    provider: str
    raw: Any = None
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class ProviderClient(Protocol):
    provider: str
    model: str
    raw: Any

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse: ...

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel: ...

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]: ...

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]: ...
