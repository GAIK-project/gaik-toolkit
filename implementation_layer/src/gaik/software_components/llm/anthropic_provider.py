"""Anthropic Claude adapter (direct API and Foundry).

Pydantic structured output is implemented with Anthropic's tool-use mechanism:
the schema is offered as a single forced, strict tool, and the tool input is
validated back through Pydantic.
"""

from __future__ import annotations

import base64
import copy
import logging
import math
import os
import types
import typing
from collections.abc import Iterator
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from gaik.software_components.endpoints import (
    ANTHROPIC_URL,
    check_endpoint,
    foundry_host,
    log_endpoint,
)
from gaik.software_components.env_file import load_env_file
from gaik.software_components.llm.base import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ChatMessage,
    ChatResponse,
    FitToBounds,
    UsageCounter,
)
from gaik.software_components.llm.content import image_data

logger = logging.getLogger(__name__)

# The `output_config.effort` levels each model accepts (Foundry deployments use
# the same ids). A model or level not listed here is not sent the option.
_ALL_EFFORTS = ("low", "medium", "high", "xhigh", "max")
_EFFORT_BY_MODEL: dict[str, tuple[str, ...]] = {
    "claude-opus-4-5": ("low", "medium", "high"),
    "claude-opus-4-6": ("low", "medium", "high", "max"),
    "claude-sonnet-4-6": ("low", "medium", "high", "max"),
    "claude-opus-4-7": _ALL_EFFORTS,
    "claude-opus-4-8": _ALL_EFFORTS,
    "claude-opus-5": _ALL_EFFORTS,
    "claude-sonnet-5": _ALL_EFFORTS,
    "claude-fable": _ALL_EFFORTS,
    "claude-mythos": _ALL_EFFORTS,
}


def _is_family(model: str, prefixes: tuple[str, ...]) -> bool:
    """Match a model id to a family with a version boundary.

    ``claude-opus-5`` covers ``claude-opus-5`` and ``claude-opus-5-5`` but not
    ``claude-opus-50``.
    """
    return any(model == p or model.startswith(p + "-") for p in prefixes)


def _accepts_effort(model: str, effort: object) -> bool:
    levels = next((v for k, v in _EFFORT_BY_MODEL.items() if _is_family(model, (k,))), ())
    return effort in levels


# Models that answer 400 to `temperature`, `top_p` or `top_k` ("deprecated for
# this model"). Components such as DataExtractor send temperature=0 for
# determinism; on these models the only choice is not to send it.
_NO_SAMPLING_MODELS = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-5",
    "claude-fable",
    "claude-mythos",
)
_SAMPLING_KEYS = ("temperature", "top_p", "top_k")

# Models that answer 400 to a forced tool_choice (`tool` or `any`).
_NO_FORCED_TOOL_MODELS = (
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-fable-5-1",
    "claude-mythos-5-1",
)

# Models that take `strict: true` on a tool. Others get the plain forced tool.
_STRICT_TOOL_MODELS = (
    "claude-fable",
    "claude-mythos",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-sonnet-5",
    "claude-haiku-5",
    "claude-haiku-4-5",
)

# Large structured outputs (a report section's facts and quotes) do not fit in
# 4096 tokens; 16000 stays under the SDK's limit for non-streaming requests.
DEFAULT_MAX_TOKENS = 16000


# Strict tool use rejects these with a 400 (Claude Sonnet 5.5: "For 'number'
# type, properties maximum, minimum are not supported").
_STRICT_UNSUPPORTED_KEYWORDS = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
    | {"minLength", "maxLength"}
)

# How a dropped bound is stated in the field's description instead.
_BOUND_NOTES = {
    "minLength": "At least {} characters.",
    "maxLength": "At most {} characters.",
    "minimum": "At least {}.",
    "exclusiveMinimum": "Greater than {}.",
    "maximum": "At most {}.",
    "exclusiveMaximum": "Less than {}.",
    "multipleOf": "A multiple of {}.",
}


_LITERAL_KEYWORDS = frozenset({"default", "const", "enum", "examples"})


def _bound_note(keyword: str, value: int | float) -> str:
    note = _BOUND_NOTES[keyword].format(value)
    return note.replace(" 1 characters.", " 1 character.")


def _strict_schema(node: Any) -> Any:
    """Copy a JSON schema into the shape strict tool use accepts.

    Strict mode needs every object closed (`additionalProperties: false`) with
    all its properties required. Optional fields stay nullable through their
    `anyOf` with null, so Pydantic still validates the answer. Numeric and
    string bounds are dropped and stated in the field's description instead;
    :func:`_within_dropped_bounds` fits an answer that still breaks one on a
    field marked :data:`FIT_TO_BOUNDS`, and any other field raises as before.
    """
    if isinstance(node, list):
        return [_strict_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    copied = {}
    for key, value in node.items():
        if key in ("properties", "$defs") and isinstance(value, dict):
            # Field and model names, not keywords: keep a field called "maximum".
            copied[key] = {name: _strict_schema(sub) for name, sub in value.items()}
        elif key in _LITERAL_KEYWORDS:
            # Values, not schemas: a default such as {"maximum": 5} stays as it is.
            copied[key] = value
        elif key not in _STRICT_UNSUPPORTED_KEYWORDS:
            copied[key] = _strict_schema(value)
    notes = [
        _bound_note(key, node[key])
        for key in _BOUND_NOTES
        if isinstance(node.get(key), int | float) and not isinstance(node.get(key), bool)
    ]
    node = copied
    if notes:
        description = node.get("description")
        node["description"] = " ".join(
            [description, *notes] if isinstance(description, str) and description else notes
        )
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"])
    return node


def _fit(value: Any, kind: str, bound: Any) -> tuple[bool, Any]:
    """``value`` brought within a bound the strict schema could not carry.

    A string is cut to its maximum length and a number is moved to the nearest
    allowed value: the next integer for an integer bound (an ``int`` field), the
    next float otherwise. A minimum length or a multiple cannot be met without
    inventing data, so those are left to fail.
    """
    if kind == "string_too_long" and isinstance(value, str) and isinstance(bound, int):
        return True, value[:bound]
    if not isinstance(value, int | float) or isinstance(value, bool) or isinstance(bound, bool):
        return False, value
    if kind in ("greater_than_equal", "less_than_equal"):
        return True, bound
    if kind in ("greater_than", "less_than"):
        # Pydantic reports a float field's bound as a float, so an int bound
        # belongs to an int field, also when the answer was 0.0.
        if isinstance(bound, int):
            return True, bound + (1 if kind == "greater_than" else -1)
        toward = math.inf if kind == "greater_than" else -math.inf
        return True, math.nextafter(float(bound), toward)
    return False, value


_BOUND_ERRORS = {
    "string_too_long": "max_length",
    "greater_than_equal": "ge",
    "less_than_equal": "le",
    "greater_than": "gt",
    "less_than": "lt",
}


def _without_none(annotation: Any) -> Any:
    """``X`` for ``X | None`` (or ``Optional[X]``); anything else as it is."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        members = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        if len(members) == 1:
            return members[0]
    return annotation


def _fits_to_bounds(model: type[BaseModel], loc: tuple) -> bool:
    """Whether ``loc`` names a field marked :data:`FIT_TO_BOUNDS`.

    The field is one of the model's own or of a model held directly (or as
    ``Model | None``) in one of its fields; a place in a list, a dict or another
    union is never fitted.
    """
    current: Any = model
    field = None
    for part in loc:
        current = _without_none(current)
        if not (
            isinstance(part, str) and isinstance(current, type) and issubclass(current, BaseModel)
        ):
            return False
        field = next(
            (info for name, info in current.model_fields.items() if part in (name, info.alias)),
            None,
        )
        if field is None:
            return False
        current = field.annotation
    return field is not None and any(isinstance(item, FitToBounds) for item in field.metadata)


def _within_dropped_bounds(
    response_format: type[BaseModel], error: ValidationError, data: Any
) -> tuple[Any, list[str]] | None:
    """``data`` with the values that break a dropped bound fitted to it, or None.

    The strict tool schema could not hold these bounds. Only a field marked
    :data:`FIT_TO_BOUNDS` (gaik's own explanation fields) is fitted: a caller's
    field, such as an invoice number or an amount, is never changed. Returns the
    fitted copy and the paths changed, or None when any error is another kind
    or on a field that is not marked.
    """
    errors = error.errors()
    if not isinstance(data, dict) or not all(
        e["type"] in _BOUND_ERRORS and _fits_to_bounds(response_format, e["loc"]) for e in errors
    ):
        return None
    fitted = copy.deepcopy(data)
    changed = []
    for e in errors:
        parent, node = None, fitted
        for part in e["loc"]:
            if not isinstance(node, dict) or part not in node:
                return None
            parent, node = node, node[part]
        bound = (e.get("ctx") or {}).get(_BOUND_ERRORS[e["type"]])
        ok, value = _fit(node, e["type"], bound)
        if parent is None or not ok:
            return None
        parent[e["loc"][-1]] = value
        changed.append(".".join(str(part) for part in e["loc"]))
    return fitted, changed


def _is_schema_rejection(error: anthropic.BadRequestError) -> bool:
    message = str(getattr(error, "message", error)).lower()
    return "strict" in message or "schema" in message


def _usage(response) -> dict[str, int]:
    if not getattr(response, "usage", None):
        return {}
    return {
        "prompt_tokens": getattr(response.usage, "input_tokens", 0),
        "completion_tokens": getattr(response.usage, "output_tokens", 0),
    }


class AnthropicProvider:
    def __init__(self, config: dict):
        self.provider = config.get("provider", "anthropic")
        self.model = config["model"]
        self.max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
        self._config = config
        self.raw = self._build_client(config)
        self.usage = UsageCounter()

    @staticmethod
    def _build_client(config: dict):
        load_env_file()
        options = {
            key: config[key]
            for key in ("timeout", "max_retries", "http_client")
            if config.get(key) is not None
        }
        options.setdefault("timeout", DEFAULT_TIMEOUT_SECONDS)
        options.setdefault("max_retries", DEFAULT_MAX_RETRIES)
        if config.get("provider") == "anthropic_foundry":
            log_endpoint("anthropic_foundry", foundry_host(config["resource"]))
            return anthropic.AnthropicFoundry(
                resource=config["resource"],
                api_key=config["api_key"],
                **options,
            )
        base_url = config.get("base_url")
        # Without a base_url the SDK itself reads ANTHROPIC_BASE_URL. Either address
        # receives the key, so both are checked: the variable's host is trusted, but
        # plain http to a public host is logged and a user name or password refused.
        url = base_url or os.getenv("ANTHROPIC_BASE_URL", "").strip() or ANTHROPIC_URL
        host = check_endpoint(
            url,
            provider="anthropic",
            allowed_hosts=config.get("allowed_endpoint_hosts"),
            what="base_url" if base_url else "ANTHROPIC_BASE_URL",
        )
        if base_url:
            options["base_url"] = base_url
        log_endpoint("anthropic", host)
        return anthropic.Anthropic(api_key=config["api_key"], **options)

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
        system_parts = []
        for message in messages:
            if message.get("role") != "system":
                continue
            content = message["content"]
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list) and all(
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
                for part in content
            ):
                system_parts.extend(part["text"] for part in content)
            else:
                raise ValueError("AnthropicProvider system messages require text content")
        rest = []
        for message in messages:
            if message.get("role") == "system":
                continue
            if message.get("role") not in {"user", "assistant"} or message.get("tool_calls"):
                raise ValueError("AnthropicProvider supports user, assistant and system messages")
            content = message["content"]
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        mime_type, data = image_data(part)
                        parts.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64.b64encode(data).decode("ascii"),
                                },
                            }
                        )
                    elif isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part)
                    else:
                        raise ValueError("AnthropicProvider supports text and inline image parts")
                content = parts
            rest.append({"role": message["role"], "content": content})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, rest

    def _options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        options = dict(kwargs)
        # The Messages API rejects `reasoning_effort`; its equivalent is
        # `output_config.effort`. Map it for models that take effort and drop it
        # for the rest (Haiku 4.5, Sonnet 4.5 and older error on it, a level a
        # model lacks errors too, and "none" is OpenAI's). Dropping it everywhere
        # made a component's thinking setting silently do nothing on Claude.
        effort = options.pop("reasoning_effort", None)
        model = str(options.get("model", self.model))
        if _accepts_effort(model, effort):
            options["output_config"] = {**options.get("output_config", {}), "effort": effort}
        if _is_family(model, _NO_SAMPLING_MODELS):
            for key in _SAMPLING_KEYS:
                options.pop(key, None)
        token_keys = [
            key
            for key in ("max_tokens", "max_completion_tokens", "max_output_tokens")
            if key in options
        ]
        if len(token_keys) > 1:
            raise ValueError("Use only one token limit: " + ", ".join(token_keys))
        if token_keys:
            options["max_tokens"] = options.pop(token_keys[0])
        return options

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        kwargs = self._options(kwargs)
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
        usage = _usage(response)
        self.usage.add(usage)
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
        kwargs = self._options(kwargs)
        schema = response_format.model_json_schema()
        tool_name = response_format.__name__
        tool = {
            "name": tool_name,
            "description": (
                response_format.__doc__ or f"Return data matching {tool_name}."
            ).strip(),
            "input_schema": schema,
        }
        system, rest = self._split_system(messages)
        model = kwargs.pop("model", self.model)
        if _is_family(str(model), _STRICT_TOOL_MODELS):
            # Without strict, Claude Sonnet 5 sometimes wraps the arguments in an
            # extra key, and Pydantic rejects the whole response.
            tool["input_schema"] = _strict_schema(schema)
            tool["strict"] = True
        tool_choice: dict[str, Any] = {"type": "tool", "name": tool_name}
        if _is_family(str(model), _NO_FORCED_TOOL_MODELS):
            # These models reject a forced tool, so offer it and ask for it; a
            # reply without the call still raises below.
            tool_choice = {"type": "auto"}
            ask = f"Answer only by calling the {tool_name} tool."
            system = f"{system}\n\n{ask}" if system else ask
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "messages": rest,
            "tools": [tool],
            "tool_choice": tool_choice,
        }
        if system is not None:
            params["system"] = system
        params.update(kwargs)
        try:
            response = self.raw.messages.create(**params)
        except anthropic.BadRequestError as error:
            # A schema strict mode cannot express (an open dict field, say) is
            # still worth sending as a plain forced tool.
            if "strict" not in tool or not _is_schema_rejection(error):
                raise
            tool.pop("strict")
            tool["input_schema"] = schema
            response = self.raw.messages.create(**params)
        self.usage.add(_usage(response))
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ValueError(
                f"Anthropic response for '{tool_name}' was cut off at "
                f"max_tokens={params['max_tokens']}; raise max_tokens or ANTHROPIC_MAX_TOKENS."
            )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                try:
                    return response_format.model_validate(block.input)
                except ValidationError as error:
                    # The model saw the dropped bounds only as words in the
                    # descriptions, so an answer that breaks only those is fitted.
                    fitted = (
                        _within_dropped_bounds(response_format, error, block.input)
                        if "strict" in tool
                        else None
                    )
                    if fitted is None:
                        raise
                    data, changed = fitted
                    result = response_format.model_validate(data)
                    logger.warning(
                        "Claude's answer for '%s' broke bounds its strict tool schema could "
                        "not hold; fitted to them: %s",
                        tool_name,
                        ", ".join(changed),
                    )
                    return result
        raise ValueError(f"Anthropic response did not return tool_use for '{tool_name}'.")

    def chat_stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[str]:
        kwargs = self._options(kwargs)
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
