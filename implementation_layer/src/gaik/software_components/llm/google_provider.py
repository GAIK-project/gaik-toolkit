"""Google Gemini adapter using the ``google-genai`` SDK.

Supports the direct Gemini API (provider=``google``). Vertex AI (provider=
``vertex``) raises ``NotImplementedError`` for now — the
``multimodal_parser/config.py`` HTTP-based flow remains the reference for
Vertex callers until a future iteration ports it here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse


class GoogleProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "google")
        if self.provider == "vertex":
            raise NotImplementedError(
                "Vertex AI is not yet wired into GoogleProvider. "
                "Use provider='google' with GOOGLE_API_KEY for now, or call the "
                "Vertex helpers in software_components.parsers.multimodal_parser."
            )
        self.model = config["model"]
        self.embedding_model = config.get("embedding_model", "text-embedding-004")
        self._config = config
        self.raw = genai.Client(api_key=config["api_key"])

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        system = "\n\n".join(str(s) for s in system_parts) if system_parts else None
        return system, rest

    @staticmethod
    def _to_contents(messages: list[ChatMessage]) -> list[genai_types.Content]:
        contents: list[genai_types.Content] = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]
            if isinstance(content, str):
                parts = [genai_types.Part.from_text(text=content)]
            else:
                parts = [genai_types.Part.from_text(text=str(content))]
            contents.append(genai_types.Content(role=role, parts=parts))
        return contents

    def _config_for(
        self,
        system: str | None,
        extra: dict[str, Any] | None = None,
    ) -> genai_types.GenerateContentConfig:
        kwargs: dict[str, Any] = {}
        if system is not None:
            kwargs["system_instruction"] = system
        if extra:
            kwargs.update(extra)
        return genai_types.GenerateContentConfig(**kwargs)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        response = self.raw.models.generate_content(
            model=model,
            contents=self._to_contents(rest),
            config=self._config_for(system, kwargs or None),
        )
        usage = {
            "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
            "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
        } if getattr(response, "usage_metadata", None) else {}
        return ChatResponse(
            text=response.text or "",
            model=model,
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
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        config = self._config_for(
            system,
            {
                "response_mime_type": "application/json",
                "response_schema": response_format,
                **kwargs,
            },
        )
        response = self.raw.models.generate_content(
            model=model,
            contents=self._to_contents(rest),
            config=config,
        )
        if response.parsed is not None:
            if isinstance(response.parsed, response_format):
                return response.parsed
            return response_format.model_validate(response.parsed)
        return response_format.model_validate_json(response.text or "")

    def chat_stream(
        self, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[str]:
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        stream = self.raw.models.generate_content_stream(
            model=model,
            contents=self._to_contents(rest),
            config=self._config_for(system, kwargs or None),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.pop("model", self.embedding_model)
        result = self.raw.models.embed_content(model=model, contents=texts, **kwargs)
        return [e.values for e in result.embeddings]
