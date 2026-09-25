"""Provider identifiers and resolution from arguments / env / legacy configs."""

from __future__ import annotations

import os
from enum import Enum


class Provider(str, Enum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    AITTA = "aitta"
    AZURE = "azure"
    ANTHROPIC = "anthropic"
    ANTHROPIC_FOUNDRY = "anthropic_foundry"
    GOOGLE = "google"
    VERTEX = "vertex"
    LITELLM = "litellm"


_VALID = {p.value for p in Provider}


def resolve_provider(
    provider: str | None = None,
    config: dict | None = None,
) -> str:
    """Pick a provider name following the documented priority order.

    Priority: explicit argument > config["provider"] > legacy config["use_azure"] >
    LLM_PROVIDER env > default ``azure``. An explicit legacy config keeps its
    selected backend even when a different default is set in the environment.
    """
    if provider:
        return _validate(provider)
    if config and "provider" in config:
        return _validate(config["provider"])
    if config and "use_azure" in config:
        return Provider.AZURE.value if config["use_azure"] else Provider.OPENAI.value
    env = os.getenv("LLM_PROVIDER")
    if env:
        return _validate(env)
    return Provider.AZURE.value


def _validate(name: str) -> str:
    if isinstance(name, Provider):
        return name.value
    if not isinstance(name, str):
        raise ValueError(f"Unknown LLM provider {name!r}. Expected one of: {sorted(_VALID)}")
    name = name.strip().lower()
    if name not in _VALID:
        raise ValueError(f"Unknown LLM provider '{name}'. Expected one of: {sorted(_VALID)}")
    return name
