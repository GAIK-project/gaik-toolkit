"""Anthropic Claude adapter (direct API and Foundry).

Pydantic structured output is implemented with Anthropic's tool-use mechanism:
the schema is offered as a single forced tool, and the tool input is validated
back through Pydantic.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic
from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse


class AnthropicProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "anthropic")
        self.model = config["model"]
        self.max_tokens = config.get("max_tokens", 4096)
        self._config = config
        self.raw = self._build_client(config)

    @staticmethod
    def _build_client(config: dict):
        if config.get("provider") == "anthropic_foundry":
            return anthropic.AnthropicFoundry(
                resource=config["resource"],
                api_key=config["api_key"],
            )
        return anthropic.Anthropic(api_key=config["api_key"])

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        system = "\n\n".join(str(s) for s in system_parts) if system_parts else None
        return system, rest

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        system, rest = self._split_system(messages)
        params: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "messages": rest,
        }
        if system is not None:
            params["system"] = system
        params.update(kwargs)
        response = self.raw.messages.create(**params)
        text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        usage = {
            "prompt_tokens": getattr(response.usage, "input_tokens", 0),
            "completion_tokens": getattr(response.usage, "output_tokens", 0),
        } if getattr(response, "usage", None) else {}
        return ChatResponse(
            text="".join(text_blocks),
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
        schema = response_format.model_json_schema()
        tool_name = response_format.__name__
        tool = {
            "name": tool_name,
            "description": (response_format.__doc__ or f"Return data matching {tool_name}.").strip(),
            "input_schema": schema,
        }
        system, rest = self._split_system(messages)
        params: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "messages": rest,
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system is not None:
            params["system"] = system
        params.update(kwargs)
        response = self.raw.messages.create(**params)
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return response_format.model_validate(block.input)
        raise ValueError(
            f"Anthropic response did not return tool_use for '{tool_name}'."
        )

    def chat_stream(
        self, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[str]:
        system, rest = self._split_system(messages)
        params: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "messages": rest,
        }
        if system is not None:
            params["system"] = system
        params.update(kwargs)
        with self.raw.messages.stream(**params) as stream:
            for text in stream.text_stream:
                if text:
                    yield text

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic does not provide a native embeddings API. "
            "Anthropic recommends Voyage AI (https://docs.voyageai.com/) for embeddings."
        )
