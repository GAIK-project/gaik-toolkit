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


@dataclass(frozen=True)
class ServerModel:
    provider: str
    model: str
    label: str
    # False when the model cannot run the audio demos (no transcription).
    audio: bool = True

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"


_AUDIO_PATHS = ("/pipeline/audio/stream",)
_server_model: ContextVar[ServerModel | None] = ContextVar("demo_server_model", default=None)

_GPT_LABELS = {
    "gpt-6-luna": "GPT-6 Luna",
    "gpt-6-sol": "GPT-6 Sol",
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6-astra": "GPT-6 Astra",
}


def _label(model: str) -> str:
    if model in _GPT_LABELS:
        return _GPT_LABELS[model]
    if model.startswith("claude-"):
        # claude-sonnet-5-5 -> Claude Sonnet 5.5
        parts = model.split("-")[1:]
        words = [p.capitalize() for p in parts if not p.isdigit()]
        version = ".".join(p for p in parts if p.isdigit())
        return " ".join(["Claude", *words, version]).strip()
    return model


def server_models() -> list[ServerModel]:
    """Models the deployment's own credentials can run, default first.

    ``DEMO_SERVER_MODELS`` overrides the list as comma-separated
    ``provider:model`` entries. A provider without credentials is left out.
    """
    import os

    azure = bool(os.getenv("AZURE_API_KEY") and os.getenv("AZURE_ENDPOINT"))
    openai = bool(os.getenv("OPENAI_API_KEY"))
    has_creds = {
        "azure": azure,
        "openai": openai,
        "anthropic_foundry": bool(
            os.getenv("ANTHROPIC_FOUNDRY_API_KEY") and os.getenv("ANTHROPIC_FOUNDRY_RESOURCE")
        ),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "vertex": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
    }
    configured = os.getenv("DEMO_SERVER_MODELS", "").strip()
    if configured:
        entries = [e.strip().split(":", 1) for e in configured.split(",") if ":" in e]
    else:
        gpt = "azure" if azure else "openai" if openai else None
        default = os.getenv("DEMO_LLM_MODEL") or os.getenv("AZURE_DEPLOYMENT") or "gpt-6-luna"
        entries = []
        if gpt:
            entries.append([gpt, default])
            entries += [[gpt, m] for m in _GPT_LABELS if m != default]
        entries.append(
            [
                "anthropic_foundry",
                os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL") or "claude-sonnet-5-5",
            ]
        )
        entries.append(["anthropic", os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5-5"])
        entries.append(["google", os.getenv("GOOGLE_MODEL") or "gemini-2.5-flash"])
        entries.append(["vertex", os.getenv("VERTEX_MODEL") or "gemini-2.5-flash"])
    models, seen = [], set()
    for provider, model in entries:
        provider, model = provider.strip(), model.strip()
        if not model or not has_creds.get(provider) or (provider, model) in seen:
            continue
        if provider == "anthropic" and has_creds["anthropic_foundry"]:
            continue  # One Claude entry is enough; Foundry is the Haaga-Helia route.
        seen.add((provider, model))
        models.append(
            ServerModel(provider, model, _label(model), audio=provider in {"azure", "openai"})
        )
    return models


def request_server_model() -> ServerModel | None:
    return _server_model.get()


def request_model_settings() -> RequestModelSettings | None:
    return _settings.get()


def supports_model_settings(path: str, method: str) -> bool:
    return method == "POST" and (
        any(path == prefix or path.startswith(prefix + "/") for prefix in _PATHS)
        or path.startswith("/wizard/message/")
    )


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
            "https://aitta-api.csc.fi/openai/v1"
            if settings.provider == "aitta"
            else "https://api.openai.com/v1"
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


def provider_error_detail(exc: Exception) -> str:
    """Do not expose remote error bodies from requests using a user's credential."""
    if (detail := unsupported_option_detail(exc)) is not None:
        return detail
    if _settings.get() is not None:
        if isinstance(exc, HTTPException):
            return str(exc.detail)
        return (
            "Model request failed. Check your credentials, model or deployment, "
            "and the operation supported by that model."
        )
    return str(exc)


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
        ignored and the page shows that it runs on the server default.
        """
        raw = [v for k, v in scope.get("headers", []) if k.lower() == SERVER_HEADER]
        if not raw or not supports_model_settings(scope["path"], scope["method"]):
            return await self.app(scope, receive, send)
        wanted = raw[0].decode("ascii", "replace").strip()
        chosen = next((m for m in server_models() if m.id == wanted), None)
        if len(raw) != 1 or chosen is None:
            return await JSONResponse(
                {"detail": "That server model is not available. Pick another in the model menu."},
                status_code=400,
            )(scope, receive, send)
        if not chosen.audio and any(scope["path"].startswith(p) for p in _AUDIO_PATHS):
            return await JSONResponse(
                {
                    "detail": f"{chosen.label} cannot transcribe audio. "
                    "Pick a GPT model in the model menu for this demo."
                },
                status_code=400,
            )(scope, receive, send)
        token = _server_model.set(chosen)
        try:
            await self.app(scope, receive, send)
        finally:
            _server_model.reset(token)
