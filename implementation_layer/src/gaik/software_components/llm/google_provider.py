"""Google Gemini and Vertex AI adapters using the ``google-genai`` SDK."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from gaik.software_components.llm.base import ChatMessage, ChatResponse, UsageCounter
from gaik.software_components.llm.content import image_data


def _usage(response) -> dict[str, int]:
    if not getattr(response, "usage_metadata", None):
        return {}
    return {
        "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
        "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
    }


class GoogleProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "google")
        self.model = config["model"]
        self.embedding_model = config.get("embedding_model", "gemini-embedding-001")
        self._config = config
        self.usage = UsageCounter()
        options = {}
        http_options = {}
        if config.get("timeout") is not None:
            http_options["timeout"] = int(config["timeout"] * 1000)
        if config.get("max_retries") is not None:
            retries = config["max_retries"]
            if not isinstance(retries, int) or retries < 0:
                raise ValueError("max_retries must be a non-negative integer")
            # Google counts the initial request in attempts; OpenAI-style
            # max_retries counts only the additional attempts.
            http_options["retry_options"] = genai_types.HttpRetryOptions(attempts=retries + 1)
        if http_options:
            options["http_options"] = genai_types.HttpOptions(**http_options)
        if self.provider == "vertex":
            credentials = config.get("credentials")
            source = config.get("service_account_json")
            if credentials is None and source:
                from google.oauth2 import service_account

                scopes = config.get("scopes") or ["https://www.googleapis.com/auth/cloud-platform"]
                if isinstance(source, dict):
                    info = source
                elif str(source).lstrip().startswith("{"):
                    info = json.loads(source)
                else:
                    info = json.loads(Path(source).read_text(encoding="utf-8"))
                credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=scopes
                )
            self.raw = genai.Client(
                vertexai=True,
                project=config["project_id"],
                location=config.get("location", "global"),
                credentials=credentials,
                **options,
            )
        else:
            self.raw = genai.Client(api_key=config["api_key"], **options)

    @staticmethod
    def _text_parts(content: Any) -> list[str]:
        """Normalize text messages without silently discarding media or tools."""
        if isinstance(content, str):
            return [content]
        if isinstance(content, list):
            parts = []
            for part in content:
                if (
                    not isinstance(part, dict)
                    or part.get("type") != "text"
                    or not isinstance(part.get("text"), str)
                ):
                    raise ValueError(
                        "GoogleProvider supports text content only; image, audio, and tool "
                        "content require a provider-specific multimodal component."
                    )
                parts.append(part["text"])
            return parts
        raise ValueError("GoogleProvider message content must be a string or text parts.")

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
        system_parts = [
            text
            for message in messages
            if message.get("role") == "system"
            for text in GoogleProvider._text_parts(message["content"])
        ]
        rest = [m for m in messages if m.get("role") != "system"]
        system = "\n\n".join(system_parts) if system_parts else None
        return system, rest

    @staticmethod
    def _to_contents(messages: list[ChatMessage]) -> list[genai_types.Content]:
        contents: list[genai_types.Content] = []
        for msg in messages:
            if msg.get("role") not in {"user", "assistant"} or msg.get("tool_calls"):
                raise ValueError(
                    "GoogleProvider supports user, assistant, and system text messages; "
                    "tool calls and other message roles are not supported."
                )
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if not isinstance(content, list):
                raise ValueError("GoogleProvider supports text and inline image parts")
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    try:
                        mime_type, data = image_data(part)
                    except ValueError as exc:
                        raise ValueError(f"GoogleProvider supports inline images: {exc}") from exc
                    parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime_type))
                else:
                    for text in GoogleProvider._text_parts([part]):
                        parts.append(genai_types.Part.from_text(text=text))
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
            normalized = dict(extra)
            token_keys = [
                key
                for key in ("max_tokens", "max_completion_tokens", "max_output_tokens")
                if key in normalized
            ]
            if len(token_keys) > 1:
                raise ValueError("Use only one token limit: " + ", ".join(token_keys))
            if token_keys:
                normalized["max_output_tokens"] = normalized.pop(token_keys[0])
            kwargs.update(normalized)
        return genai_types.GenerateContentConfig(**kwargs)

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        response = self.raw.models.generate_content(
            model=model,
            contents=self._to_contents(rest),
            config=self._config_for(system, kwargs or None),
        )
        usage = _usage(response)
        self.usage.add(usage)
        return ChatResponse(
            text=response.text or "",
            model=model,
            provider=self.provider,
            raw=response,
            usage=usage,
        )

    @staticmethod
    def _gemini_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
        """Convert a Pydantic model to a Gemini-compatible JSON schema.

        Strips fields that Gemini's ``response_schema`` rejects
        (``additionalProperties``, ``title``, ``$defs``/``$ref``) and inlines
        any references the Pydantic generator emits for nested models.
        """

        raw = model_cls.model_json_schema()
        defs = raw.get("$defs") or raw.get("definitions") or {}

        def clean(node: Any, resolving: frozenset[str] = frozenset()) -> Any:
            if isinstance(node, dict):
                if "$ref" in node:
                    ref = node["$ref"].split("/")[-1]
                    if ref in resolving:
                        raise ValueError(
                            "Recursive schemas are not supported by GoogleProvider: " + ref
                        )
                    if ref not in defs:
                        raise ValueError("Unresolved GoogleProvider schema reference: " + ref)
                    return clean(defs[ref], resolving | {ref})
                result: dict[str, Any] = {}
                for key, value in node.items():
                    if key in {"additionalProperties", "$defs", "definitions"}:
                        continue
                    # Pydantic emits a metadata "title" string in every schema node.
                    # A user field literally named ``title`` is a dict subschema,
                    # not a string — keep those untouched.
                    if key == "title" and isinstance(value, str):
                        continue
                    result[key] = clean(value, resolving)
                return result
            if isinstance(node, list):
                return [clean(item, resolving) for item in node]
            return node

        return clean(raw)

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        # Use response_json_schema rather than response_schema. The latter routes
        # through types.Schema, which auto-adds an unsupported additional_properties
        # field; the json-schema path takes our cleaned dict verbatim.
        config = self._config_for(
            system,
            {
                "response_mime_type": "application/json",
                "response_json_schema": self._gemini_schema(response_format),
                **kwargs,
            },
        )
        response = self.raw.models.generate_content(
            model=model,
            contents=self._to_contents(rest),
            config=config,
        )
        self.usage.add(_usage(response))
        if response.parsed is not None:
            if isinstance(response.parsed, response_format):
                return response.parsed
            return response_format.model_validate(response.parsed)
        return response_format.model_validate_json(response.text or "")

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]:
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
