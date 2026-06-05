"""Provider identifiers and resolution from arguments / env / legacy configs."""

from __future__ import annotations

import os
from enum import Enum


class Provider(str, Enum):
    OPENAI = "openai"
    AZURE = "azure"
    ANTHROPIC = "anthropic"
    ANTHROPIC_FOUNDRY = "anthropic_foundry"
    GOOGLE = "google"
    VERTEX = "vertex"


_VALID = {p.value for p in Provider}


def resolve_provider(
    provider: str | None = None,
    config: dict | None = None,
) -> str:
    """Pick a provider name following the documented priority order.

    Priority: explicit argument > config["provider"] > LLM_PROVIDER env >
    legacy config["use_azure"] > default ``azure``.
    """
    if provider:
        return _validate(provider)
    if config and "provider" in config:
        return _validate(str(config["provider"]))
    env = os.getenv("LLM_PROVIDER")
    if env:
        return _validate(env)
    if config and "use_azure" in config:
        return Provider.AZURE.value if config["use_azure"] else Provider.OPENAI.value
    return Provider.AZURE.value


def _validate(name: str) -> str:
    name = name.strip().lower()
    if name not in _VALID:
        raise ValueError(f"Unknown LLM provider '{name}'. Expected one of: {sorted(_VALID)}")
    return name
