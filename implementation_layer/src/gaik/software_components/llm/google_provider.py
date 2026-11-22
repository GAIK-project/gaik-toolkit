"""Google Gemini and Vertex AI adapters using the ``google-genai`` SDK."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from gaik.software_components.endpoints import log_endpoint, vertex_host
from gaik.software_components.llm.base import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ChatMessage,
    ChatResponse,
    UsageCounter,
)
from gaik.software_components.llm.content import image_data

logger = logging.getLogger(__name__)

# What a default Vertex location was found not to serve, shared by every
# provider in the process: components build a provider per request, and each
# would otherwise wait for the same answer again. Both are keyed on
# (project, location, model), so one model's answer does not move the others.
# -> monotonic time until which the fallback is used, after the location
# answered 404 for the model.
_NOT_SERVED: dict[tuple[str, str, str], float] = {}
# -> monotonic time until which the fallback is used, after the location failed
# with a server error, a timeout or a quota answer for the model.
_UNAVAILABLE_UNTIL: dict[tuple[str, str, str], float] = {}
# Guards both records; an entry is dropped once read after it expired.
_STATE_LOCK = threading.Lock()
# How long a failing location is left alone before it is tried again.
LOCATION_RETRY_SECONDS = 600.0
# How long a model the location does not serve goes to the fallback before the
# location is asked again, so a model added to the location later is used there.
NOT_SERVED_RETRY_SECONDS = 3600.0
# The request timeout when the config sets none and the location has a fallback.
PREFERRED_LOCATION_TIMEOUT_SECONDS = 120.0
# The variable a warning tells the reader to set to choose the location.
LOCATION_ENV = "GOOGLE_CLOUD_LOCATION"


def _fallback_location(config: dict) -> str | None:
    """The location that takes over from the config's own, or None.

    ``location_fallback`` in the config decides, also when it is None. A config
    with neither key gets the default pair: the EU, then the global endpoint.
    A location other than the EU is used as given when the fallback is still
    the one ``get_llm_config`` filled in by default: the location was then set
    on the returned dict. A fallback the caller named applies with any location.
    """
    if "location_fallback" in config:
        fallback = config["location_fallback"]
        if config.get("_default_location_fallback") and (config.get("location") or "eu") != "eu":
            return None
    else:
        fallback = None if config.get("location") else "global"
    return fallback if fallback and fallback != (config.get("location") or "eu") else None


def _on_fallback(key: tuple[str, str, str]) -> bool:
    """Whether the model's requests go to the fallback now; drops expired entries."""
    now = time.monotonic()
    on_fallback = False
    with _STATE_LOCK:
        for record in (_NOT_SERVED, _UNAVAILABLE_UNTIL):
            until = record.get(key)
            if until is None:
                continue
            if until > now:
                on_fallback = True
            else:
                del record[key]
    return on_fallback


def _is_timeout(exc: BaseException) -> bool:
    return "Timeout" in type(exc).__name__ or isinstance(exc, TimeoutError)


def _usage(response) -> dict[str, int]:
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return {}
    return {
        # The SDK declares every count Optional; a missing count is 0 tokens.
        "prompt_tokens": meta.prompt_token_count or 0,
        # Thinking tokens are billed as output but counted apart from the answer's
        # (candidates) tokens; like OpenAI's completion tokens, the count holds both.
        "completion_tokens": (meta.candidates_token_count or 0)
        + (getattr(meta, "thoughts_token_count", None) or 0),
    }


class GoogleProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "google")
        self.model = config["model"]
        self.embedding_model = config.get("embedding_model", "gemini-embedding-001")
        self._config = config
        self.usage = UsageCounter()
        # Threads that share the provider build each location's client once.
        self._clients_lock = threading.Lock()
        options = {}
        http_options = {}
        timeout = config.get("timeout")
        if timeout is None:
            timeout = DEFAULT_TIMEOUT_SECONDS
        http_options["timeout"] = int(timeout * 1000)
        retries = config.get("max_retries")
        if retries is None:
            retries = DEFAULT_MAX_RETRIES
        if not isinstance(retries, int) or retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        # Google counts the initial request in attempts; OpenAI-style
        # max_retries counts only the additional attempts.
        http_options["retry_options"] = genai_types.HttpRetryOptions(attempts=retries + 1)
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
            # No location in the config: the EU first, the global endpoint for a
            # model the EU does not serve or while the EU does not answer (see
            # llm/config.py).
            self.location = config.get("location") or "eu"
            self._fallback_location = _fallback_location(config)
            self._project = str(config["project_id"])
            self._preferred_location = self.location
            self._clients: dict[str, Any] = {}
            # A location with URL characters would name another host.
            for location in (self.location, self._fallback_location):
                if location:
                    vertex_host(location)

            def vertex_client(location: str):
                with self._clients_lock:
                    return build(location)

            def build(location: str):
                if location not in self._clients:
                    log_endpoint("vertex", vertex_host(location))
                    client_options = options
                    if self._fallback_location and location == self._preferred_location:
                        preferred = dict(http_options)
                        if config.get("timeout") is None:
                            # Shorter than the default, so a location that does
                            # not answer hands over to the fallback quickly. The
                            # fallback itself keeps the default.
                            preferred["timeout"] = int(PREFERRED_LOCATION_TIMEOUT_SECONDS * 1000)
                        if config.get("max_retries") is None:
                            # The fallback is the retry: the SDK's own retries would
                            # hold a request for minutes in a location that is down.
                            preferred["retry_options"] = genai_types.HttpRetryOptions(attempts=1)
                        client_options = {"http_options": genai_types.HttpOptions(**preferred)}
                    self._clients[location] = genai.Client(
                        vertexai=True,
                        project=config["project_id"],
                        location=location,
                        credentials=credentials,
                        **client_options,
                    )
                return self._clients[location]

            self._vertex_client = vertex_client
            self.raw = vertex_client(self.location)
        else:
            self.location = None
            self._fallback_location = None
            log_endpoint("google", "generativelanguage.googleapis.com")
            self.raw = genai.Client(api_key=config["api_key"], **options)
            self._clients = {"": self.raw}

    def close(self) -> None:
        """Close every SDK client this provider built: after a fallback that is two.

        Closing ``raw`` alone would leave the other location's connections open.
        """
        with self._clients_lock:
            clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def _use(self, location: str) -> Any:
        # Return the client itself: another thread may set ``raw`` in between.
        client = self._vertex_client(location)
        self.location, self.raw = location, client
        return client

    def _in_location(self, call: Callable[[Any], Any], model: str) -> Any:
        """Run ``call(client)`` in the preferred location, else in the fallback.

        Only a default location has a fallback; one set by the caller or the
        environment is used as given. The fallback takes the model's requests
        for ``NOT_SERVED_RETRY_SECONDS`` after the preferred location answered
        that it does not serve the model (404), and for ``LOCATION_RETRY_SECONDS``
        after it failed for the model with a server error, a timeout or a quota
        answer. After that the preferred location is tried again. Other models
        keep using the preferred location. Each switch is logged, because the
        global endpoint is not tied to a region.
        """
        fallback = self._fallback_location
        if fallback is None:
            return call(self.raw)
        preferred = self._preferred_location
        key = (self._project, preferred, model)
        if _on_fallback(key):
            return call(self._use(fallback))
        try:
            return call(self._use(preferred))
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(exc, genai_errors.ClientError) and code == 404:
                with _STATE_LOCK:
                    _NOT_SERVED[key] = time.monotonic() + NOT_SERVED_RETRY_SECONDS
                reason = (
                    f"does not serve {model}; it is asked again in "
                    f"{int(NOT_SERVED_RETRY_SECONDS / 60)} minutes"
                )
            elif (
                isinstance(exc, genai_errors.ServerError)
                or (isinstance(exc, genai_errors.ClientError) and code == 429)
                or _is_timeout(exc)
            ):
                with _STATE_LOCK:
                    _UNAVAILABLE_UNTIL[key] = time.monotonic() + LOCATION_RETRY_SECONDS
                reason = (
                    f"did not answer for {model} ({type(exc).__name__}"
                    f"{f' {code}' if code else ''}); it is tried again in "
                    f"{int(LOCATION_RETRY_SECONDS / 60)} minutes"
                )
            else:
                raise
            logger.warning(
                "Vertex AI location %r %s. Using %r, which is not tied to a region. "
                "Set %s to choose the location.",
                preferred,
                reason,
                fallback,
                self._config.get("_location_env") or LOCATION_ENV,
            )
            return call(self._use(fallback))

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
            # OpenAI's reasoning option; components document it as ignored elsewhere,
            # and GenerateContentConfig rejects unknown fields.
            normalized.pop("reasoning_effort", None)
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
        contents = self._to_contents(rest)
        request_config = self._config_for(system, kwargs or None)
        response = self._in_location(
            lambda client: client.models.generate_content(
                model=model, contents=contents, config=request_config
            ),
            model,
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
        contents = self._to_contents(rest)
        response = self._in_location(
            lambda client: client.models.generate_content(
                model=model, contents=contents, config=config
            ),
            model,
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
        contents = self._to_contents(rest)
        request_config = self._config_for(system, kwargs or None)

        def first_chunk(client):
            # The request is sent when the stream is first read, so a missing
            # model shows there.
            stream = iter(
                client.models.generate_content_stream(
                    model=model, contents=contents, config=request_config
                )
            )
            return next(stream, None), stream

        chunk, stream = self._in_location(first_chunk, model)
        while chunk is not None:
            if chunk.text:
                yield chunk.text
            chunk = next(stream, None)

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.pop("model", self.embedding_model)
        result = self._in_location(
            lambda client: client.models.embed_content(model=model, contents=texts, **kwargs),
            model,
        )
        return [e.values for e in result.embeddings]
