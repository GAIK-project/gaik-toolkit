"""Optional LiteLLM backend behind the same GAIK component interface."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import litellm
from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse, UsageCounter
from gaik.software_components.llm.parameters import normalize_chat_kwargs


class LiteLLMProvider:
    """Use explicit LiteLLM model IDs such as ``azure/gpt-6-luna``.

    Credentials and options are scoped to each request. This adapter does not
    modify LiteLLM globals, environment variables, callbacks, or logging.
    """

    provider = "litellm"

    def __init__(self, config: dict):
        self.model = config.get("model", "")
        if not self.model or "/" not in self.model:
            raise ValueError("LiteLLM requires a provider-prefixed model, e.g. azure/gpt-6-luna")
        self.embedding_model = config.get("embedding_model", "")
        self._config = dict(config)
        self.raw = litellm
        self.usage = UsageCounter()

    def _options(self, kwargs: dict[str, Any], *, chat: bool = True) -> dict[str, Any]:
        options = {}
        for source, target in (
            ("api_key", "api_key"),
            ("base_url", "api_base"),
            ("api_version", "api_version"),
            ("timeout", "timeout"),
            ("max_retries", "num_retries"),
            ("vertex_project", "vertex_project"),
            ("vertex_location", "vertex_location"),
            ("vertex_credentials", "vertex_credentials"),
        ):
            if self._config.get(source) is not None:
                options[target] = self._config[source]
        options.update(kwargs)
        if chat:
            model = options.get("model", self.model)
            options = normalize_chat_kwargs(model, options, config=self._config)
        return options

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        options = self._options(kwargs)
        response = litellm.completion(
            model=options.pop("model", self.model), messages=messages, **options
        )
        usage = (
            {k: v for k, v in response.usage.model_dump().items() if isinstance(v, int)}
            if response.usage
            else {}
        )
        self.usage.add(usage)
        return ChatResponse(
            text=response.choices[0].message.content or "",
            model=response.model,
            provider=self.provider,
            raw=response,
            usage=usage,
        )

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        response = self.chat(messages, response_format=response_format, **kwargs)
        return response_format.model_validate_json(response.text)

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]:
        options = self._options(kwargs)
        stream = litellm.completion(
            model=options.pop("model", self.model), messages=messages, stream=True, **options
        )
        try:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.pop("model", self.embedding_model)
        if not model:
            raise ValueError("LiteLLM embeddings require an explicit embedding_model")
        response = litellm.embedding(model=model, input=texts, **self._options(kwargs, chat=False))
        return [item["embedding"] for item in sorted(response.data, key=lambda item: item["index"])]
