"""Provider-agnostic LLM client interface."""

from __future__ import annotations

import threading
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


class UsageCounter:
    """Running token totals of a client's calls; safe to add to from worker threads.

    Every provider keeps one as ``usage`` and adds each ``chat`` and ``chat_parsed``
    call to it, since ``chat_parsed`` returns only the parsed model.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals: dict[str, int] = {}

    def add(self, usage: dict[str, int]) -> None:
        with self._lock:
            self._totals = add_usage(self._totals, usage)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._totals)


def usage_since(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """The counts added between two ``UsageCounter.snapshot()`` calls."""
    return {k: v - before.get(k, 0) for k, v in after.items() if v != before.get(k, 0)}


def add_usage(*usages: dict[str, int]) -> dict[str, int]:
    """Sum token-count dicts key by key."""
    total: dict[str, int] = {}
    for usage in usages:
        for key, value in usage.items():
            total[key] = total.get(key, 0) + value
    return total


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
