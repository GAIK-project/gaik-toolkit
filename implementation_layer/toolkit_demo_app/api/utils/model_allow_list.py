"""Which model names a route runs on the server's own credentials.

A request that names a model gets it only when the route offers that model, and a
model the server catalogue marks team-only (``server_models``) only for the GAIK
team. The team tier comes from the signed-in user's session: the Next proxy reads
it there and sends ``x-gaik-model-tier`` on the requests it forwards; it never
forwards a browser's own copy of that header. A request on the user's own key
runs on their credential and is not limited here.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from fastapi import HTTPException

from .model_settings import (
    _DEFAULT_MODELS,
    request_is_staff,
    request_model_settings,
    server_models,
)

# Speech-to-text models the report demos may name: the Report Writer offers the
# first two, and "whisper" is the toolkit's own default.
_TRANSCRIPTION_DEFAULT = "gpt-4o-transcribe,gpt-4o-mini-transcribe,whisper-1,whisper"
# Further chat deployments the report demos may name beside the server catalogue:
# the Report Writer page's writer and review defaults.
_EXTRA_CHAT_DEFAULT = "gpt-6-luna,gpt-5.5-deployment"


def _env_list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


def _server_config() -> dict:
    from .config import server_api_config

    try:
        return server_api_config()
    except Exception:
        return {}


def team_only_models() -> set[str]:
    """Model names kept for the GAIK team, whatever credentials the server has.

    A ``DEMO_SERVER_MODELS`` entry decides for the model it names (``:staff`` or
    not); any other model keeps the flag of the built-in list. The server's own
    model is open to everyone: it already runs for anyone who picks nothing.
    """
    flags = {model: staff for _family, model, staff in _DEFAULT_MODELS}
    for item in os.getenv("DEMO_SERVER_MODELS", "").split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            flags[parts[1]] = parts[2:3] == ["staff"]
    flags.pop(str(_server_config().get("model") or ""), None)
    return {model for model, staff in flags.items() if staff}


def chat_models() -> list[str]:
    """Chat models the report demos may name: the server's own model, the server
    catalogue's models on the same provider (these routes run every step on it)
    and ``DEMO_EXTRA_CHAT_MODELS`` (comma-separated)."""
    config = _server_config()
    provider, default = config.get("provider"), config.get("model")
    models = [str(default)] if default else []
    models += [m.model for m in server_models() if m.provider == provider]
    models += _env_list("DEMO_EXTRA_CHAT_MODELS", _EXTRA_CHAT_DEFAULT)
    return list(dict.fromkeys(models))


def transcription_models() -> list[str]:
    """Speech-to-text models the report demos may name (``DEMO_TRANSCRIPTION_MODELS``)."""
    models = _env_list("DEMO_TRANSCRIPTION_MODELS", _TRANSCRIPTION_DEFAULT)
    configured = _server_config().get("transcription_model")
    if configured:
        models.append(str(configured))
    return list(dict.fromkeys(models))


def offered_to(models: Iterable[str]) -> list[str]:
    """``models`` without the team-only ones, unless the request is from the team."""
    if request_is_staff():
        return list(models)
    team_only = team_only_models()
    return [m for m in models if m not in team_only]


def check_team_tier(model: str | None) -> None:
    """Refuse a team-only model outside the team (not for a user's own key)."""
    if not model or request_model_settings() is not None:
        return
    if not request_is_staff() and model in team_only_models():
        raise HTTPException(
            403, f"{model} is for the GAIK project team. Pick another model in the model menu."
        )


def check_model(model: str | None, offered: Iterable[str], field: str = "model") -> None:
    """Refuse a model the route does not offer, or a team-only one outside the team.

    No model named means the route's own default, which is always allowed. A request
    on the user's own key is not checked: it does not use the server's credentials.
    """
    if not model or request_model_settings() is not None:
        return
    offered = list(offered)
    if model not in offered:
        choices = ", ".join(offered_to(offered)[:12])
        raise HTTPException(
            422,
            f"The {field} '{model}' is not available on this demo. Leave the field empty "
            f"for the server's model, or use one of: {choices}.",
        )
    check_team_tier(model)
