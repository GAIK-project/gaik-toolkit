"""Where a credential may be sent: https, and a host the deployment knows.

Every client that sends an API key, token or password with a request checks its
address here when it is built. The address must use ``https://`` and its host
must be one of:

- the provider's own hosts (for example ``api.openai.com`` or
  ``*.openai.azure.com``);
- the host of an address set in the deployment's own environment for that
  provider (for example ``AZURE_ENDPOINT`` or ``OPENAI_BASE_URL``);
- a host listed in ``GAIK_ALLOWED_ENDPOINT_HOSTS`` (comma-separated), or in the
  ``allowed_endpoint_hosts`` setting the application passes in code;
- the local machine (``localhost``, ``127.0.0.1``, ``::1``), for local models,
  where plain ``http://`` is accepted too.

An entry is a host name (``llm.example.org``), a suffix pattern
(``*.example.org``) or, to accept plain ``http://`` for one host on a private
network, that host with its scheme (``http://docling.internal``). Anything else
raises :class:`EndpointNotAllowedError` before a request is made.

An application that forwards user settings to gaik should not forward
``allowed_endpoint_hosts``: the list is the deployment's decision.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import threading
from collections.abc import Iterable
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

ALLOWED_HOSTS_ENV = "GAIK_ALLOWED_ENDPOINT_HOSTS"

# Hosts each provider serves its API from. A pattern starting with ``*`` matches
# any host that ends with the rest of the pattern.
PROVIDER_HOSTS: dict[str, tuple[str, ...]] = {
    "openai": ("api.openai.com",),
    "azure": (
        "*.openai.azure.com",
        "*.cognitiveservices.azure.com",
        "*.services.ai.azure.com",
    ),
    "aitta": ("aitta-api.csc.fi",),
    "openai_compatible": (),
    "anthropic": ("api.anthropic.com",),
    "anthropic_foundry": ("*.services.ai.azure.com",),
    "google": ("generativelanguage.googleapis.com",),
    "vertex": ("aiplatform.googleapis.com", "*-aiplatform.googleapis.com"),
    "litellm": (),
    "jev": ("api.typesafe.ai", "gaik-decide.2.rahtiapp.fi"),
    "docling": (),
    "whisper_local": (),
}

# Environment variables through which a deployment sets a provider's address.
# The host of an address set there is trusted for that provider.
PROVIDER_ENDPOINT_ENVS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_BASE_URL",),
    "openai_compatible": ("OPENAI_BASE_URL",),
    "azure": ("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE", "TTS_ENDPOINT"),
    "aitta": ("AITTA_BASE_URL",),
    "vertex": ("GOOGLE_GENERATE_CONTENT_URL",),
    "litellm": ("LITELLM_BASE_URL",),
    "jev": ("GAIK_DECIDE_URL",),
}

_LOOPBACK_NAMES = {"localhost"}

_logged: set[tuple[str, str]] = set()
_logged_lock = threading.Lock()


class EndpointNotAllowedError(ValueError):
    """An address that would receive a credential is not https or not an allowed host."""


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _split_entries(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    return [item.strip().lower().rstrip(".") for item in items if item and item.strip()]


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*"):
        suffix = pattern[1:]
        return len(host) > len(suffix) and host.endswith(suffix)
    return host == pattern


def _parse(url: str, what: str) -> tuple[str, str]:
    if not isinstance(url, str) or not url.strip():
        raise EndpointNotAllowedError(f"{what} is empty")
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower().rstrip(".")
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError as exc:
        raise EndpointNotAllowedError(f"{what} is not a valid URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"https", "http"} or not host:
        raise EndpointNotAllowedError(f"{what} must be an https:// URL with a host name")
    return scheme, host


def _allowed_entries(allowed_hosts: str | Iterable[str] | None) -> tuple[list[str], set[str]]:
    """Host patterns from the env var and the application, and the hosts allowed over http."""
    names: list[str] = []
    http_hosts: set[str] = set()
    for entry in _split_entries(os.getenv(ALLOWED_HOSTS_ENV)) + _split_entries(allowed_hosts):
        if "://" not in entry:
            names.append(entry)
            continue
        try:
            scheme, host = _parse(entry, ALLOWED_HOSTS_ENV)
        except EndpointNotAllowedError:
            continue
        names.append(host)
        if scheme == "http":
            http_hosts.add(host)
    return names, http_hosts


def _env_hosts(provider: str) -> list[str]:
    hosts = []
    for name in PROVIDER_ENDPOINT_ENVS.get(provider, ()):
        value = os.getenv(name, "").strip()
        if not value:
            continue
        try:
            hosts.append(_parse(value, name)[1])
        except EndpointNotAllowedError:
            continue
    return hosts


def check_endpoint(
    url: str,
    *,
    provider: str,
    allowed_hosts: str | Iterable[str] | None = None,
    what: str = "endpoint",
) -> str:
    """Return the host of ``url`` when a credential may be sent there.

    Args:
        url: The address that will receive the request and its credential.
        provider: Key into :data:`PROVIDER_HOSTS`, e.g. ``"azure"`` or ``"docling"``.
        allowed_hosts: Extra hosts the application allows, on top of
            ``GAIK_ALLOWED_ENDPOINT_HOSTS``.
        what: Name of the setting, used in the error message.

    Raises:
        EndpointNotAllowedError: The address is not https (other than to the local
            machine) or its host is not one this deployment allows.
    """
    scheme, host = _parse(url, what)
    if _is_loopback(host):
        return host
    names, http_hosts = _allowed_entries(allowed_hosts)
    if scheme == "http":
        if host in http_hosts:
            return host
        raise EndpointNotAllowedError(
            f"{what} must use https:// (got http:// for host {host!r}). For a server on a "
            f"private network, list 'http://{host}' in {ALLOWED_HOSTS_ENV}."
        )
    # LiteLLM routes to the provider its model ID names, so any known provider host fits.
    known = (
        [pattern for hosts in PROVIDER_HOSTS.values() for pattern in hosts]
        if provider == "litellm"
        else PROVIDER_HOSTS.get(provider, ())
    )
    patterns = [
        *known,
        *_env_hosts(provider),
        *names,
    ]
    if any(_host_matches(host, pattern) for pattern in patterns):
        return host
    raise EndpointNotAllowedError(
        f"{what} host {host!r} is not a known {provider} host. Add it to "
        f"{ALLOWED_HOSTS_ENV} (or allowed_endpoint_hosts) if this deployment uses it."
    )


def host_of(url: str) -> str:
    """The host of ``url`` for logging, or ``"?"`` when it has none."""
    try:
        return (urlsplit(url).hostname or "?").lower()
    except ValueError:
        return "?"


def log_endpoint(provider: str, host: str) -> None:
    """Log the provider and endpoint host once per process, without the key."""
    key = (provider, host)
    with _logged_lock:
        if key in _logged:
            return
        _logged.add(key)
    logger.info("gaik client: provider=%s endpoint host=%s", provider, host)


_RESOURCE_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def foundry_host(resource: str) -> str:
    """Return the Azure AI Foundry host for ``resource``, a single DNS label.

    The Anthropic SDK puts the resource name into ``https://{resource}.services.ai.azure.com``;
    a value with dots, slashes or other URL characters would name another host.
    """
    name = resource.strip().lower() if isinstance(resource, str) else ""
    if not _RESOURCE_LABEL.fullmatch(name):
        raise EndpointNotAllowedError(
            "resource must be an Azure AI Foundry resource name (letters, digits and "
            "hyphens), not a URL or host name"
        )
    return f"{name}.services.ai.azure.com"
