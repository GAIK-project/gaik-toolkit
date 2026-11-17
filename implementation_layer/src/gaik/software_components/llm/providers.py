"""Provider identifiers and resolution from arguments / env / legacy configs."""

from __future__ import annotations

import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


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
        name = _validate(env)
        _log_once(f"gaik provider {name!r} chosen by LLM_PROVIDER")
        return name
    _log_once("gaik provider 'azure' chosen by default: no provider given and LLM_PROVIDER unset")
    return Provider.AZURE.value


_logged: set[str] = set()


def _log_once(message: str) -> None:
    """Log how the provider was chosen once per process, so a changed environment shows."""
    if message not in _logged:
        _logged.add(message)
        logger.info(message)


def _validate(name: str) -> str:
    if isinstance(name, Provider):
        return name.value
    if not isinstance(name, str):
        raise ValueError(f"Unknown LLM provider {name!r}. Expected one of: {sorted(_VALID)}")
    name = name.strip().lower()
    if name not in _VALID:
        raise ValueError(f"Unknown LLM provider '{name}'. Expected one of: {sorted(_VALID)}")
    return name
