"""OpenAI / Azure OpenAI adapter for the multi-provider interface."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from gaik.software_components.config import create_openai_client
from gaik.software_components.llm.base import ChatMessage, ChatResponse
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.llm.providers import Provider, resolve_provider


class OpenAIProvider:
    def __init__(self, config: dict):
        self.provider = resolve_provider(config=config)
        self.model = config["model"]
        self.transcription_model = config.get("transcription_model")
        default_embedding = (
            "text-embedding-3-small"
            if self.provider in {Provider.OPENAI.value, Provider.AZURE.value}
            else ""
        )
        self.embedding_model = config.get("embedding_model", default_embedding)
        self._config = {**config, "provider": self.provider}
        self.raw = self._build_client(self._config)

    @staticmethod
    def _build_client(config: dict):
        return create_openai_client(config)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        model = kwargs.pop("model", self.model)
        kwargs = normalize_chat_kwargs(model, kwargs, config=self._config)
        completion = self.raw.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        choice = completion.choices[0].message
        usage = completion.usage.model_dump() if completion.usage else {}
        return ChatResponse(
            text=choice.content or "",
            model=completion.model,
            provider=self.provider,
            raw=completion,
            usage=usage,
        )

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        model = kwargs.pop("model", self.model)
        kwargs = normalize_chat_kwargs(model, kwargs, config=self._config)
        completion = self.raw.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_format,
            **kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI parse() returned None — check the model/schema.")
        return parsed

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]:
        model = kwargs.pop("model", self.model)
        kwargs = normalize_chat_kwargs(model, kwargs, config=self._config)
        stream = self.raw.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.pop("model", self.embedding_model)
        if not model:
            raise ValueError(
                f"Provider {self.provider!r} requires an explicit embedding_model "
                "supported by the endpoint, or embed(..., model=...)."
            )
        response = self.raw.embeddings.create(model=model, input=texts, **kwargs)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
