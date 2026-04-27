"""OpenAI / Azure OpenAI adapter for the multi-provider interface."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse


class OpenAIProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "azure" if config.get("use_azure") else "openai")
        self.model = config["model"]
        self.transcription_model = config.get("transcription_model")
        self.embedding_model = config.get("embedding_model", "text-embedding-3-small")
        self._config = config
        self.raw = self._build_client(config)

    @staticmethod
    def _build_client(config: dict):
        if config.get("use_azure") or config.get("provider") == "azure":
            return AzureOpenAI(
                api_key=config["api_key"],
                api_version=config["api_version"],
                azure_endpoint=config["azure_endpoint"],
            )
        return OpenAI(api_key=config["api_key"])

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        completion = self.raw.chat.completions.create(
            model=kwargs.pop("model", self.model),
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
        completion = self.raw.beta.chat.completions.parse(
            model=kwargs.pop("model", self.model),
            messages=messages,
            response_format=response_format,
            **kwargs,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI parse() returned None — check the model/schema.")
        return parsed

    def chat_stream(
        self, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[str]:
        stream = self.raw.chat.completions.create(
            model=kwargs.pop("model", self.model),
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
        response = self.raw.embeddings.create(model=model, input=texts, **kwargs)
        return [item.embedding for item in response.data]
