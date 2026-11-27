"""Translate common chat options for OpenAI's reasoning model families."""

from __future__ import annotations

import re
from typing import Any

# OpenAI reasoning families that accept only max_completion_tokens.
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")
# Models known to accept reasoning_effort="none", with an optional snapshot date. Other
# GPT-6 models, such as Astra, gpt-6-rosalind and the gpt-6.x generation, reject it.
_EFFORT_NONE_MODELS = re.compile(
    r"(gpt-6-(sol|luna)|gpt-5\.6-(sol|luna|terra))(-\d{4}-\d{2}-\d{2})?"
)


def _family(model: str, config: dict) -> str:
    return str(config.get("model_family") or model).rsplit("/", 1)[-1].lower()


def _accepts_effort_none(model: str, config: dict | None = None) -> bool:
    """True for a model known to accept ``reasoning_effort="none"``.

    GPT-6 Sol/Luna and GPT-5.6 Sol/Luna/Terra, by name or ``model_family``, with or
    without a snapshot date. For an effort gaik picks itself, so it is an allowlist:
    an unknown name, a deployment alias without ``model_family`` and every other
    model give False.
    """
    return _EFFORT_NONE_MODELS.fullmatch(_family(model, config or {})) is not None


# OpenAI families without reasoning: the Responses API answers a ``reasoning`` parameter
# with 400 "Unsupported parameter: 'reasoning.effort' is not supported with this model."
# "gpt-35" is Azure's model name for GPT-3.5 Turbo.
_NO_REASONING_PREFIXES = ("gpt-4", "gpt-3.5", "gpt-35", "chatgpt-4")


def accepts_reasoning(model: str, config: dict | None = None) -> bool:
    """False for an OpenAI family known to reject the ``reasoning`` parameter.

    GPT-4o, GPT-4.1, GPT-4 Turbo, ChatGPT-4o and GPT-3.5, also fine-tuned (``ft:...``),
    by name, or by ``model_family`` when the config's ``model`` is the one called or
    unset (a family hint describes that model, not a per-call override). It is a denylist: every
    other name keeps the parameter, as before, so a deployment alias for a reasoning
    model still gets the effort it was configured with. A config whose ``provider`` is
    not OpenAI or Azure (a compatible server, LiteLLM) keeps it too: such names are free.
    """
    config = config or {}
    if config.get("provider") is not None and not _is_openai_api(config):
        return True
    hint = config.get("model_family") if config.get("model") in (None, model) else None
    family = str(hint or model).rsplit("/", 1)[-1].lower().removeprefix("ft:")
    return not family.startswith(_NO_REASONING_PREFIXES)


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
    ``max_tokens`` as before, so older Azure API versions keep working. GPT-4.x and
    GPT-3.5 get no ``reasoning_effort``, which they reject (``accepts_reasoning``).
    """
    result = dict(kwargs)
    config = config or {}
    if "reasoning_effort" not in result and config.get("reasoning_effort") is not None:
        result["reasoning_effort"] = config["reasoning_effort"]
    if not accepts_reasoning(model, config):
        result.pop("reasoning_effort", None)
    family = _family(model, config)
    is_gpt6 = family.startswith(("gpt-6-", "gpt-6."))
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
    # Astra and the gpt-6.x generation always reason: they reject "none".
    if not family.startswith(("gpt-6-astra", "gpt-6.")):
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
