"""Translate common chat options for OpenAI's reasoning model families."""

from __future__ import annotations

from typing import Any


def normalize_chat_kwargs(
    model: str, kwargs: dict[str, Any], *, config: dict | None = None
) -> dict[str, Any]:
    """Return compatible options without mutating caller-owned dictionaries.

    GPT-6 sampling controls are supported only with reasoning disabled. Components
    historically request temperature=0; omit that sampling request when reasoning
    is enabled (including the model's default). Explicit reasoning levels are
    preserved and invalid levels fail before a network request. Custom Azure
    deployment names can identify their underlying family with ``model_family``.
    """
    result = dict(kwargs)
    config = config or {}
    if "reasoning_effort" not in result and config.get("reasoning_effort") is not None:
        result["reasoning_effort"] = config["reasoning_effort"]
    family = str(config.get("model_family") or model).rsplit("/", 1)[-1].lower()
    is_gpt6 = family.startswith("gpt-6-")
    if not is_gpt6 and not family.startswith("gpt-5.6-"):
        return result
    effort = result.get("reasoning_effort")
    allowed = {"low", "medium", "high", "xhigh", "max"}
    if not family.startswith("gpt-6-astra"):
        allowed.add("none")
    if is_gpt6 and effort is not None and effort not in allowed:
        raise ValueError(f"{family} reasoning_effort must be one of {sorted(allowed)}")
    if effort != "none":
        for key in ("temperature", "top_p", "top_logprobs", "logprobs"):
            result.pop(key, None)
    if "max_tokens" in result:
        if "max_completion_tokens" in result:
            raise ValueError("Use only one token limit: max_tokens or max_completion_tokens")
        result["max_completion_tokens"] = result.pop("max_tokens")
    if is_gpt6 and result.get("tools") and (family.startswith("gpt-6-astra") or effort != "none"):
        raise ValueError(
            "GPT-6 tool calling with reasoning requires the Responses API. "
            "Use a Responses client, or GPT-6 Sol/Luna with reasoning_effort='none'."
        )
    return result
