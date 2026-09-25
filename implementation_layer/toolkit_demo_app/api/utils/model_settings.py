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
        return None
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


def provider_error_detail(exc: Exception) -> str:
    """Do not expose remote error bodies from requests using a user's credential."""
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
            return await self.app(scope, receive, send)
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
