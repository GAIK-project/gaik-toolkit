"""Translate common chat options for OpenAI's reasoning model families."""

from __future__ import annotations

from typing import Any

# OpenAI reasoning families that accept only max_completion_tokens.
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def normalize_chat_kwargs(
    model: str, kwargs: dict[str, Any], *, config: dict | None = None
) -> dict[str, Any]:
    """Return compatible options without mutating caller-owned dictionaries.

    GPT-6 sampling controls are supported only with reasoning disabled. Components
    historically request temperature=0; omit that sampling request when reasoning
    is enabled (including the model's default). Explicit reasoning levels are
    preserved and invalid levels fail before a network request. Custom Azure
    deployment names can identify their underlying family with ``model_family``.
    OpenAI and Azure OpenAI reasoning models (o-series, gpt-5.x) reject
    ``max_tokens`` and get ``max_completion_tokens``. Other models, custom
    deployment names without ``model_family``, compatible servers and LiteLLM keep
    ``max_tokens`` as before, so older Azure API versions keep working.
    """
    result = dict(kwargs)
    config = config or {}
    if "reasoning_effort" not in result and config.get("reasoning_effort") is not None:
        result["reasoning_effort"] = config["reasoning_effort"]
    family = str(config.get("model_family") or model).rsplit("/", 1)[-1].lower()
    is_gpt6 = family.startswith("gpt-6-")
    is_reasoning_family = is_gpt6 or family.startswith("gpt-5.6-")
    is_openai_reasoning = _is_openai_api(config) and family.startswith(_REASONING_PREFIXES)
    if "max_tokens" in result and (is_reasoning_family or is_openai_reasoning):
        if "max_completion_tokens" in result:
            raise ValueError("Use only one token limit: max_tokens or max_completion_tokens")
        result["max_completion_tokens"] = result.pop("max_tokens")
    if not is_reasoning_family:
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
    if is_gpt6 and result.get("tools") and (family.startswith("gpt-6-astra") or effort != "none"):
        raise ValueError(
            "GPT-6 tool calling with reasoning requires the Responses API. "
            "Use a Responses client, or GPT-6 Sol/Luna with reasoning_effort='none'."
        )
    return result


def _is_openai_api(config: dict) -> bool:
    """True for configs that select OpenAI or Azure OpenAI, including legacy ``use_azure``."""
    provider = config.get("provider")
    if provider is None:
        return "use_azure" in config
    return str(getattr(provider, "value", provider)).strip().lower() in {"openai", "azure"}
