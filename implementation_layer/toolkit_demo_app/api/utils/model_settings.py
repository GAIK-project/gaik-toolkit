"""Transient per-request model credentials for the browser demo.

No process environment mutation or session storage. The ASGI wrapper keeps the
context alive through a streaming response and releases its HTTP client afterwards.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from starlette.responses import JSONResponse

from .errors import public_error

HEADER = b"x-gaik-model-settings"
_AZURE_HOST = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:openai\.azure\.com|services\.ai\.azure\.com)"
)
_PATHS = (
    "/extract",
    "/extract-vision",
    "/llm-judge/text-pair",
    "/llm-judge/hallucinations",
    "/llm-judge/validate",
    "/schema-generator",
    "/classify",
    "/parse",
    "/postgres-agent/ask",
    # Incident reporting: the schema, then text, scanned-form and audio extraction.
    "/pipeline/schema",
    "/pipeline/text/stream",
    "/pipeline/document/stream",
    "/pipeline/audio/stream",
    "/model-settings/test",
    # Web scraper: the extraction step after the crawl.
    "/web-scraper/run",
)


@dataclass(frozen=True)
class RequestModelSettings:
    provider: str
    model: str
    api_key: str = field(repr=False)
    azure_endpoint: str | None = None
    api_version: str = "2025-03-01-preview"


_settings: ContextVar[RequestModelSettings | None] = ContextVar("demo_model_settings", default=None)
_http_client: ContextVar[httpx.Client | None] = ContextVar("demo_model_http_client", default=None)

# --- Server models a signed-in user can switch between without a key -------
SERVER_HEADER = b"x-gaik-server-model"
# Set by the Next proxy, the only way to this API, from the signed-in user: "staff"
# for the admin, the demo account and haaga-helia.fi addresses. Never from a browser.
TIER_HEADER = b"x-gaik-model-tier"


@dataclass(frozen=True)
class ServerModel:
    provider: str
    model: str
    label: str
    # Costlier models: only the GAIK team (admin, demo account, haaga-helia.fi).
    staff: bool = False
    # False when the provider has no speech-to-text: the audio demos then
    # transcribe with the server's own transcriber and extract with this model.
    audio: bool = True
    # False for a text-only model: demos that send page images refuse it.
    vision: bool = True

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"


_server_model: ContextVar[ServerModel | None] = ContextVar("demo_server_model", default=None)
# Whether the request carries the team tier, set by ModelSettingsMiddleware for the
# routes that check a named model (utils/model_allow_list.py).
_staff: ContextVar[bool] = ContextVar("demo_model_staff", default=False)

# The reasoning effort picked in the model menu. Absent means Auto: each model
# keeps the effort get_model_options chooses for it (utils/config.py).
EFFORT_HEADER = b"x-gaik-reasoning-effort"
_EFFORTS = (b"low", b"medium", b"high")
_reasoning_effort: ContextVar[str | None] = ContextVar("demo_reasoning_effort", default=None)

_LABELS = {
    "gpt-6-luna": "GPT-6 Luna",
    "gpt-6-sol": "GPT-6 Sol",
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6.2-sol": "GPT-6.2 Sol",
    "gpt-6-astra": "GPT-6 Astra",
    "google/gemma-4-31b-it": "Gemma 4 31B",
    "Qwen/Qwen3.8-27B": "Qwen 3.8 27B",
    "Qwen/Qwen3.6-35B-A3B": "Qwen 3.6 35B",
    "openai/gpt-oss-120b": "gpt-oss 120B",
}

# (family, model, staff only). Families map to the provider that has credentials.
_DEFAULT_MODELS = (
    ("gpt", "gpt-6-luna", False),
    ("gpt", "gpt-6-sol", False),
    ("gpt", "gpt-6.1-sol", True),
    ("gpt", "gpt-6.2-sol", True),
    ("gpt", "gpt-6-astra", True),
    ("claude", "claude-haiku-5-5", False),
    ("claude", "claude-sonnet-5-5", False),
    ("claude", "claude-opus-5-5", True),
    ("gemini", "gemini-3.8-flash", False),
    ("gemini", "gemini-4-argon", True),
    # Read every test receipt right on 2026-11-19, but takes 25 s to 3 min a page.
    # Gemini 4 Neon and Hydrogen answer too, but left line prices empty
    # (docs/MODEL_REQUIREMENTS.md); DEMO_SERVER_MODELS can list them.
    ("gemini", "gemini-4-carbon", True),
    # CSC Aitta: open models hosted in Finland. Of the models tested through
    # gaik on 2026-11-16 these two are worth offering: Gemma reads images, and
    # gpt-oss answers three times faster (docs/MODEL_REQUIREMENTS.md). Others
    # can be listed with DEMO_SERVER_MODELS.
    ("aitta", "google/gemma-4-31b-it", False),
    ("aitta", "openai/gpt-oss-120b", False),
)
_FAMILIES = {
    "gpt": ("azure", "openai"),
    "claude": ("anthropic_foundry", "anthropic"),
    "gemini": ("vertex", "google"),
    "aitta": ("aitta",),
}

AITTA_BASE_URL = "https://aitta-api.csc.fi/openai/v1"
# Aitta chat models that answered an image request with an error or without
# reading the image (2026-11-16). A model not listed here is taken to read images.
_AITTA_TEXT_ONLY = (
    "openai/gpt-oss-",
    "qwen/qwen3-coder",
    "qwen/qwen-agentworld",
    "swiss-ai/apertus",
    "allenai/olmo",
    "lumiopen/",
    "meta-llama/llama-3.3",
    "tinyllama/",
)


def reads_images(provider: str | None, model: str | None) -> bool:
    """False for a model known to be text-only. Only Aitta models are listed."""
    if provider != "aitta" or not model:
        return True
    return not model.lower().startswith(_AITTA_TEXT_ONLY)


def _aitta_token() -> str | None:
    import os

    return os.getenv("AITTA_API_KEY") or os.getenv("AITTA_API_TOKEN") or os.getenv("AITTA_TOKEN")


def model_name(model: str | None) -> str:
    """The name a model goes by in the menu, or its ID when it has none."""
    return _LABELS.get(model or "", model or "The model")


def _label(model: str) -> str:
    """gemini-3.8-flash -> Gemini 3.8 Flash, claude-haiku-5-5 -> Claude Haiku 5.5."""
    if model in _LABELS:
        return _LABELS[model]
    words: list[str] = []
    for part in model.split("-"):
        if part.isdigit() and words and words[-1].replace(".", "").isdigit():
            words[-1] += "." + part
        elif any(c.isdigit() for c in part):
            words.append(part)
        else:
            words.append(part.capitalize())
    return " ".join(words)


def _has_credentials(provider: str) -> bool:
    import os

    env = os.getenv
    return {
        "azure": bool(env("AZURE_API_KEY") and env("AZURE_ENDPOINT")),
        "openai": bool(env("OPENAI_API_KEY")),
        "anthropic_foundry": bool(
            env("ANTHROPIC_FOUNDRY_API_KEY") and env("ANTHROPIC_FOUNDRY_RESOURCE")
        ),
        "anthropic": bool(env("ANTHROPIC_API_KEY")),
        "vertex": bool(
            env("GOOGLE_SERVICE_ACCOUNT_JSON")
            and (env("GOOGLE_PROJECT_ID") or env("GOOGLE_CLOUD_PROJECT"))
        ),
        "google": bool(env("GOOGLE_API_KEY") or env("GEMINI_API_KEY")),
        "aitta": bool(_aitta_token()),
    }.get(provider, False)


def _server_default() -> tuple[str, str] | None:
    """Provider and model of the deployment's own config, or None if it has none."""
    from .config import server_api_config

    try:
        config = server_api_config()
    except Exception:
        return None
    provider, model = config.get("provider"), config.get("model")
    return (str(provider), str(model)) if provider and model else None


def server_models() -> list[ServerModel]:
    """Models the deployment's own credentials can run, default first.

    ``DEMO_SERVER_MODELS`` overrides the list as comma-separated
    ``provider:model`` entries, with ``:staff`` for a team-only model and
    ``:text`` for one that cannot read images. A provider without credentials
    is left out.
    """
    import os

    configured = os.getenv("DEMO_SERVER_MODELS", "").strip()
    entries: list[tuple[str, str, bool]] = []
    text_only: set[tuple[str, str]] = set()
    if configured:
        for item in configured.split(","):
            parts = [p.strip() for p in item.split(":")]
            if len(parts) >= 2 and parts[0] and parts[1]:
                entries.append((parts[0], parts[1], "staff" in parts[2:]))
                if "text" in parts[2:]:
                    text_only.add((parts[0], parts[1]))
    else:
        for family, model, staff in _DEFAULT_MODELS:
            provider = next((p for p in _FAMILIES[family] if _has_credentials(p)), None)
            if provider:
                entries.append((provider, model, staff))
    # The model a request without a choice runs on leads the list and is open to
    # everyone: it already runs for anyone who picks nothing.
    default = _server_default()
    if default is not None:
        entries = [(default[0], default[1], False)] + [
            e for e in entries if (e[0], e[1]) != default
        ]
    models, seen = [], set()
    for provider, model, staff in entries:
        if not _has_credentials(provider) or (provider, model) in seen:
            continue
        seen.add((provider, model))
        models.append(
            ServerModel(
                provider,
                model,
                _label(model),
                staff=staff,
                # Aitta transcribes with its own Whisper (utils/config.py).
                audio=provider in {"azure", "openai", "aitta"},
                vision=(provider, model) not in text_only and reads_images(provider, model),
            )
        )
    return models


def is_staff(scope_or_headers) -> bool:
    headers = scope_or_headers.get("headers", []) if isinstance(scope_or_headers, dict) else []
    return any(k.lower() == TIER_HEADER and v == b"staff" for k, v in headers)


def request_is_staff() -> bool:
    """Whether the current request may run the team-only models."""
    return _staff.get()


def request_server_model() -> ServerModel | None:
    return _server_model.get()


def parse_reasoning_effort(values: list[bytes]) -> str | None:
    """The effort one header names: low, medium or high. Anything else is Auto.

    "none" is not offered: only some models accept it, and Auto already sends it
    to those. A wrong or repeated header falls back to Auto and refuses nothing.
    """
    if len(values) != 1 or values[0] not in _EFFORTS:
        return None
    return values[0].decode("ascii")


def request_reasoning_effort() -> str | None:
    """The effort the user picked for this request, or None for Auto."""
    return _reasoning_effort.get()


def request_model_settings() -> RequestModelSettings | None:
    return _settings.get()


def supports_model_settings(path: str, method: str) -> bool:
    return method == "POST" and any(
        path == prefix or path.startswith(prefix + "/") for prefix in _PATHS
    )


# A picked server model also runs these; an own key does not. The RAG index
# stays on the server between requests, where a browser key must not, and the
# transcriber takes a speech model, not the chat model of the key dialog.
_SERVER_MODEL_PATHS = ("/rag/index", "/rag/load-example", "/transcribe")


def supports_server_model(path: str, method: str) -> bool:
    return supports_model_settings(path, method) or (
        method == "POST"
        and any(path == prefix or path.startswith(prefix + "/") for prefix in _SERVER_MODEL_PATHS)
    )


def aitta_speech_model() -> str:
    import os

    return os.getenv("AITTA_TRANSCRIPTION_MODEL", "openai/whisper-large-v3")


def aitta_embedding_model() -> str:
    import os

    return os.getenv("AITTA_EMBEDDING_MODEL", "intfloat/multilingual-e5-large")


_aitta_warmed = 0.0


def warm_aitta_models() -> list[str]:
    """Ask Aitta to start its idle speech and embedding models; returns those asked.

    Aitta stops a model that has been idle, and the next request then waits
    minutes for it. Called when a user picks an Aitta model, so that the models
    are up by the time a recording or a document arrives. At most once in five
    minutes, whoever asks.
    """
    import time

    global _aitta_warmed, _aitta_status
    token = _aitta_token()
    if not token or (_aitta_warmed and time.monotonic() - _aitta_warmed < 300):
        return []
    _aitta_warmed = time.monotonic()
    statuses = aitta_model_status()
    asked = []
    for model in (aitta_speech_model(), aitta_embedding_model()):
        if statuses.get(model) in {None, "running", "starting", "requested"}:
            continue
        try:
            httpx.post(
                f"https://aitta-api.csc.fi/model/{model.replace('/', '~')}/preload",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            ).raise_for_status()
            asked.append(model)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Aitta preload failed for %s (%s)", model, type(exc).__name__
            )
    if asked:
        _aitta_status = (0.0, {})  # The next list shows them starting.
    return asked


_aitta_status: tuple[float, dict[str, str]] = (0.0, {})


def aitta_model_status() -> dict[str, str]:
    """Aitta's own status per model id ("running", "offline", ...), cached a minute.

    An offline model starts on its first request, which can take minutes. Empty
    when the deployment has no Aitta key or the catalog does not answer.
    """
    import time

    global _aitta_status
    checked, statuses = _aitta_status
    if checked and time.monotonic() - checked < 60:
        return statuses
    statuses = {}
    token = _aitta_token()
    if token:
        try:
            response = httpx.get(
                "https://aitta-api.csc.fi/model",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            )
            response.raise_for_status()
            statuses = {
                str(m["id"]): str(m.get("status") or "")
                for m in response.json().get("_embedded", {}).get("models", [])
                if isinstance(m, dict) and m.get("id")
            }
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Aitta catalog check failed (%s)", type(exc).__name__
            )
    _aitta_status = (time.monotonic(), statuses)
    return statuses


def parse_model_settings(raw: str) -> RequestModelSettings:
    """Validate without ever including submitted secrets in error messages."""
    try:
        if len(raw) > 8192:
            raise ValueError
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) - {
            "provider",
            "model",
            "apiKey",
            "azureEndpoint",
            "apiVersion",
        }:
            raise ValueError
        provider, model, key = data.get("provider"), data.get("model"), data.get("apiKey")
        if provider not in {"azure", "openai", "aitta"}:
            raise ValueError
        if (
            not isinstance(model, str)
            or not model.strip()
            or len(model) > 200
            or any(ord(c) < 32 or ord(c) == 127 for c in model)
        ):
            raise ValueError
        if (
            not isinstance(key, str)
            or not key.strip()
            or len(key) > 6000
            or not re.fullmatch(r"[\x21-\x7e]+", key.strip())
        ):
            raise ValueError
        endpoint = None
        version = data.get("apiVersion") or "2025-03-01-preview"
        if not isinstance(version, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(?:-preview)?", version
        ):
            raise ValueError
        if provider == "azure":
            url = urlsplit(data.get("azureEndpoint", ""))
            host = (url.hostname or "").lower()
            if (
                url.scheme != "https"
                or not _AZURE_HOST.fullmatch(host)
                or url.port is not None
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in ("", "/", "/openai/v1", "/openai/v1/")
            ):
                raise ValueError
            endpoint = f"https://{host}"
        elif data.get("azureEndpoint") or data.get("apiVersion"):
            raise ValueError
        return RequestModelSettings(provider, model.strip(), key.strip(), endpoint, version)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            400, "Invalid model settings. Check the provider, model, key, and Azure endpoint."
        ) from None


def _validate_public_endpoint(endpoint: str) -> None:
    """Reject Azure private endpoints as well as DNS resolving to local networks."""
    host = urlsplit(endpoint).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise HTTPException(400, "The Azure resource hostname could not be resolved.") from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise HTTPException(
            400, "Use a public Azure endpoint. Private network endpoints are not supported."
        )


def get_request_api_config() -> dict | None:
    settings = _settings.get()
    if settings is None:
        chosen = _server_model.get()
        if chosen is None:
            return None
        from gaik.software_components.llm import get_llm_config

        return get_llm_config(chosen.provider, model=chosen.model)
    from gaik.software_components.llm import get_llm_config

    overrides = {
        "api_key": settings.api_key,
        "model": settings.model,
        "timeout": 600.0 if settings.provider == "aitta" else 120.0,
        "max_retries": 0,
        "embedding_model": "",  # Never inherit the deployment's embedding identity.
    }
    if settings.provider == "azure":
        overrides.update(
            azure_endpoint=settings.azure_endpoint, base_url=None, api_version=settings.api_version
        )
    else:
        overrides["base_url"] = (
            AITTA_BASE_URL if settings.provider == "aitta" else "https://api.openai.com/v1"
        )
    if _http_client.get() is not None:
        overrides["http_client"] = _http_client.get()
    return get_llm_config(settings.provider, **overrides)


def unsupported_option_detail(exc: BaseException) -> str | None:
    """Explain a provider 400 that rejects one request option, such as ``temperature``.

    Only the option name is read from the error body, so this is safe to show for
    requests that use a user's credential.
    """
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or error.get("code") not in {
        "unsupported_value",
        "unsupported_parameter",
    }:
        return None
    param = str(error.get("param") or "an option")
    return (
        f"The selected model does not accept the '{param}' option as sent. "
        f"Clear '{param}' (use \"model default\") in the settings of the step that "
        "failed, or choose another model."
    )


def provider_error_detail(exc: Exception, what: str = "The request") -> str:
    """A message for a failed request that never carries the exception's own text.

    A request on the user's credential gets a hint about their settings; one on the
    server's credentials gets an error id, with the exception logged under it
    (utils/errors.py). An HTTPException raised on purpose keeps its detail.
    """
    if (detail := unsupported_option_detail(exc)) is not None:
        return detail
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if getattr(exc, "status_code", None) == 413:
        # CSC Aitta answers a large scanned page this way.
        return (
            "The model's service refused the request as too large. "
            "Try a smaller file or fewer pages, or pick another model."
        )
    if _settings.get() is not None:
        return (
            "Model request failed. Check your credentials, model or deployment, "
            "and the operation supported by that model."
        )
    return public_error(exc, what)


class _CredentialRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        settings = _settings.get()
        if settings is not None:
            # httpx logs every request URL at INFO, which names the user's own
            # Azure resource and deployment.
            if record.name.split(".")[0] in {"httpx", "httpcore"}:
                return False
            if record.exc_info:
                # Provider exceptions can include remote response bodies. Keep only
                # their type in BYOK logs rather than serializing an exception body.
                record.msg = f"Model request error ({record.exc_info[0].__name__})"
                record.exc_info = None
                record.exc_text = None
            else:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        type(arg).__name__ if isinstance(arg, BaseException) else arg
                        for arg in record.args
                    )
                record.msg = record.getMessage().replace(settings.api_key, "[redacted]")
            record.args = ()
        return True


class ModelSettingsMiddleware:
    def __init__(self, app):
        self.app = app
        for handler in logging.getLogger().handlers:
            if not any(isinstance(f, _CredentialRedactionFilter) for f in handler.filters):
                handler.addFilter(_CredentialRedactionFilter())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        staff_token = _staff.set(is_staff(scope))
        # Read on the routes that take a picked model, with an own key as well as
        # with a server model.
        effort = None
        if supports_server_model(scope["path"], scope["method"]):
            effort = parse_reasoning_effort(
                [v for k, v in scope.get("headers", []) if k.lower() == EFFORT_HEADER]
            )
        effort_token = _reasoning_effort.set(effort)
        try:
            return await self._call(scope, receive, send)
        finally:
            _reasoning_effort.reset(effort_token)
            _staff.reset(staff_token)

    async def _call(self, scope, receive, send):
        raw_headers = [v for k, v in scope.get("headers", []) if k.lower() == HEADER]
        if not raw_headers:
            return await self._server_model_call(scope, receive, send)
        try:
            if len(raw_headers) != 1 or not supports_model_settings(scope["path"], scope["method"]):
                raise HTTPException(400, "This demo uses server model settings.")
            settings = parse_model_settings(raw_headers[0].decode("ascii"))
            if settings.azure_endpoint:
                await asyncio.to_thread(_validate_public_endpoint, settings.azure_endpoint)
        except (HTTPException, UnicodeDecodeError) as exc:
            status = exc.status_code if isinstance(exc, HTTPException) else 400
            detail = exc.detail if isinstance(exc, HTTPException) else "Invalid model settings."
            return await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        # Own this transport for exactly one response, including SSE. Disallow
        # redirects and ambient proxy settings for browser-supplied credentials.
        client = httpx.Client(follow_redirects=False, trust_env=False)
        settings_token = _settings.set(settings)
        client_token = _http_client.set(client)
        response_started = False

        async def private_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store")]}
            await send(message)

        try:
            await self.app(scope, receive, private_send)
        except Exception as exc:
            # Unexpected failures must not carry a provider response body out of
            # the credential context into the application's global error handler.
            logging.getLogger(__name__).warning("Model request failed (%s)", type(exc).__name__)
            if response_started:
                raise RuntimeError("Model request failed while streaming.") from None
            await JSONResponse({"detail": provider_error_detail(exc)}, status_code=502)(
                scope, receive, private_send
            )
        finally:
            _http_client.reset(client_token)
            _settings.reset(settings_token)
            await asyncio.to_thread(client.close)

    async def _server_model_call(self, scope, receive, send):
        """Run one request on a server model the user picked (no key involved).

        Only routes that honour model settings switch; elsewhere the header is
        ignored and the page shows that it runs on the server default. A model
        without speech-to-text still runs the audio demos: they transcribe with
        the server's transcriber (``get_transcription_api_config``).
        """
        raw = [v for k, v in scope.get("headers", []) if k.lower() == SERVER_HEADER]
        if not raw or not supports_server_model(scope["path"], scope["method"]):
            return await self.app(scope, receive, send)
        wanted = raw[0].decode("ascii", "replace").strip()
        chosen = next((m for m in server_models() if m.id == wanted), None)
        if len(raw) != 1 or chosen is None:
            return await JSONResponse(
                {"detail": "That server model is not available. Pick another in the model menu."},
                status_code=400,
            )(scope, receive, send)
        if chosen.staff and not is_staff(scope):
            return await JSONResponse(
                {
                    "detail": f"{chosen.label} is for the GAIK project team. "
                    "Pick another model in the model menu."
                },
                status_code=403,
            )(scope, receive, send)
        token = _server_model.set(chosen)
        try:
            await self.app(scope, receive, send)
        finally:
            _server_model.reset(token)
