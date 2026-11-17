"""Where a credential may be sent: https, and a host the deployment knows.

Every client that sends an API key, token or password with a request checks its
address here when it is built. The address must use ``https://``, except where
plain http is named below, and its host must be one of:

- the provider's own hosts (for example ``api.openai.com`` or
  ``*.openai.azure.com``);
- the host of an address set in the deployment's own environment for that
  provider (for example ``AZURE_ENDPOINT``, ``OPENAI_BASE_URL`` or
  ``DOCLING_API_BASE``), over ``http://`` too when the address is set that way.
  An http address there on a private network (a private or link-local IP address,
  or a single-label name such as ``docling`` or ``host.docker.internal``) is used
  quietly; any other http host is used with a warning, once per host, that the
  key goes to it without encryption;
- a host listed in ``GAIK_ALLOWED_ENDPOINT_HOSTS`` (comma-separated), or in the
  ``allowed_endpoint_hosts`` setting the application passes in code;
- the local machine (``localhost``, ``127.0.0.1``, ``::1``), over ``http://`` too,
  for services that commonly run there: OpenAI-compatible model servers, LiteLLM,
  Docling and local Whisper. For a cloud provider the local machine must be listed
  like any other host.

An entry is a host name (``llm.example.org``, a port is ignored), a suffix pattern
(``*.example.org``) or, to accept plain ``http://`` on a private network, the host
or pattern with its scheme (``http://docling.internal``). Anything else raises
:class:`EndpointNotAllowedError` before a request is made.

An application that forwards user settings to gaik should not forward
``allowed_endpoint_hosts``: the list is the deployment's decision. Hosts such as
Azure in a sovereign cloud, Azure API Management (``*.azure-api.net``) or a local
server reached by a service name (``host.docker.internal``) are not known to gaik
and must be listed. The Azure patterns accept every Azure resource, not only the
deployment's own.
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
    "vertex": (
        "aiplatform.googleapis.com",
        "*-aiplatform.googleapis.com",
        "aiplatform.eu.rep.googleapis.com",
        "aiplatform.us.rep.googleapis.com",
    ),
    "litellm": (),
    "jev": ("api.typesafe.ai", "gaik-decide.2.rahtiapp.fi"),
    "docling": (),
    "whisper_local": (),
}

# Environment variables through which a deployment sets a provider's address.
# The host of an address set there is trusted for that provider. DOCLING_API_BASE and
# LOCAL_TRANSCRIBER_API_BASE are the names the demo app and generated PoCs read;
# API_BASE is the older Docling name some examples still read.
PROVIDER_ENDPOINT_ENVS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_BASE_URL",),
    "openai_compatible": ("OPENAI_BASE_URL",),
    "azure": ("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE", "TTS_ENDPOINT"),
    "aitta": ("AITTA_BASE_URL",),
    "vertex": ("GOOGLE_GENERATE_CONTENT_URL",),
    "litellm": ("LITELLM_BASE_URL",),
    "jev": ("GAIK_DECIDE_URL", "TYPESAFE_BASE_URL"),
    "docling": ("DOCLING_API_BASE", "API_BASE"),
    "whisper_local": ("LOCAL_TRANSCRIBER_API_BASE",),
}

# Services that commonly run on the same machine as the application. For the others
# (OpenAI, Azure, Aitta, Jev, ...) a loopback address must be allowed like any host.
LOCAL_SERVICE_PROVIDERS = frozenset({"openai_compatible", "litellm", "docling", "whisper_local"})

OPENAI_BASE_URL = "https://api.openai.com/v1"
AITTA_BASE_URL = "https://aitta-api.csc.fi/openai/v1"
ANTHROPIC_URL = "https://api.anthropic.com"

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


_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
)
_PRIVATE_NAMES = {"host.docker.internal"}

_warned_http: set[str] = set()


def _is_private_network(host: str) -> bool:
    """This machine, a private or link-local IP address, or a single-label host name."""
    if _is_loopback(host) or host in _PRIVATE_NAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return any(address in net for net in _PRIVATE_NETWORKS if net.version == address.version)


def _warn_plain_http_once(provider: str, host: str) -> None:
    with _logged_lock:
        if host in _warned_http:
            return
        _warned_http.add(host)
    logger.warning(
        "gaik client: provider=%s sends its key to %s over http://, without encryption. "
        "Use https:// for a host outside a private network.",
        provider,
        host,
    )


def _split_entries(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    return [item.strip().lower() for item in items if item and item.strip()]


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*"):
        suffix = pattern[1:]
        return len(host) > len(suffix) and host.endswith(suffix)
    return host == pattern


_UNSAFE_URL_CHARS = re.compile(r"[\\\s\x00-\x1f\x7f]|[^\x00-\x7f]")


def _parse(url: str, what: str) -> tuple[str, str]:
    if not isinstance(url, str) or not url.strip():
        raise EndpointNotAllowedError(f"{what} is empty")
    url = url.strip()
    # HTTP libraries do not all split a URL the same way: a backslash, a space or a
    # user-info part can make them connect to a host other than the one read here.
    if _UNSAFE_URL_CHARS.search(url):
        raise EndpointNotAllowedError(
            f"{what} contains a backslash, whitespace, a control or a non-ASCII character"
        )
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError as exc:
        raise EndpointNotAllowedError(f"{what} is not a valid URL") from exc
    if "@" in parts.netloc:
        raise EndpointNotAllowedError(f"{what} must not carry a user name or password")
    scheme = parts.scheme.lower()
    if scheme not in {"https", "http"} or not host:
        raise EndpointNotAllowedError(f"{what} must be an https:// URL with a host name")
    return scheme, host


def _allowed_entries(allowed_hosts: str | Iterable[str] | None) -> tuple[list[str], list[str]]:
    """Host patterns from the env var and the application, and those allowed over http.

    An entry may carry a port (``llm.example.org:8443``); only its host is compared.
    """
    names: list[str] = []
    http_names: list[str] = []
    for entry in _split_entries(os.getenv(ALLOWED_HOSTS_ENV)) + _split_entries(allowed_hosts):
        try:
            parts = urlsplit(entry if "://" in entry else f"//{entry}")
            host = (parts.hostname or "").rstrip(".")
        except ValueError:
            host = ""
        if not host:
            logger.warning("Ignoring an entry in %s that names no host", ALLOWED_HOSTS_ENV)
            continue
        names.append(host)
        if parts.scheme == "http":
            http_names.append(host)
    return names, http_names


def _env_hosts(provider: str) -> tuple[list[str], list[str]]:
    """Hosts of the provider's addresses set in the environment, and those set with http://."""
    hosts, http_hosts = [], []
    for name in PROVIDER_ENDPOINT_ENVS.get(provider, ()):
        value = os.getenv(name, "").strip()
        if not value:
            continue
        try:
            scheme, host = _parse(value, name)
        except EndpointNotAllowedError:
            continue
        hosts.append(host)
        if scheme == "http":
            http_hosts.append(host)
    return hosts, http_hosts


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
        EndpointNotAllowedError: The address's host, or plain http to it, is not one
            this deployment allows (see the module docstring).
    """
    scheme, host = _parse(url, what)
    names, http_names = _allowed_entries(allowed_hosts)
    env_names, env_http_names = _env_hosts(provider)
    deployment = [*env_names, *names]
    if _is_loopback(host):
        if provider in LOCAL_SERVICE_PROVIDERS or any(
            _host_matches(host, pattern) for pattern in deployment
        ):
            return host
        raise EndpointNotAllowedError(
            f"{what} points at this machine, which is not a {provider} host. List "
            f"{host!r} in {ALLOWED_HOSTS_ENV} if a local server stands in for it."
        )
    if scheme == "http":
        if any(_host_matches(host, pattern) for pattern in http_names):
            return host
        # An address the deployment set with http:// in its environment is used as set.
        if host in env_http_names:
            if not _is_private_network(host):
                _warn_plain_http_once(provider, host)
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
    if any(_host_matches(host, pattern) for pattern in [*known, *deployment]):
        return host
    raise EndpointNotAllowedError(
        f"{what} host {host!r} is not a known {provider} host. Add it to "
        f"{ALLOWED_HOSTS_ENV} (or allowed_endpoint_hosts) if this deployment uses it."
    )


def check_openai_endpoint(config: dict, provider: str) -> str:
    """Check the address an OpenAI-SDK client for ``config`` will use; log its host once.

    Returns the host, or ``""`` for Azure without an endpoint (the SDK then reports
    the missing endpoint itself, or reads ``AZURE_OPENAI_ENDPOINT``).
    """
    if provider == "azure":
        url = config.get("base_url") or config.get("azure_endpoint")
        what = "base_url" if config.get("base_url") else "azure_endpoint"
        if not url:
            return ""
    else:
        # Without a base_url the OpenAI SDK itself reads OPENAI_BASE_URL.
        default = (
            AITTA_BASE_URL
            if provider == "aitta"
            else os.getenv("OPENAI_BASE_URL") or OPENAI_BASE_URL
        )
        url = config.get("base_url") or default
        what = "base_url"
    host = check_endpoint(
        url, provider=provider, allowed_hosts=config.get("allowed_endpoint_hosts"), what=what
    )
    log_endpoint(provider, host)
    return host


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


_VERTEX_LOCATION = re.compile(r"global|[a-z]+(?:-[a-z0-9]+)*")


_VERTEX_MULTI_REGIONS = frozenset({"eu", "us"})


def vertex_host(location: str) -> str:
    """Return the Vertex AI host for ``location``: ``global``, a multi-region (``eu``, ``us``)
    or a region (``europe-north1``).

    google-genai puts a region into ``https://{location}-aiplatform.googleapis.com`` and a
    multi-region into ``https://aiplatform.{location}.rep.googleapis.com``; a value with URL
    characters would name another host.
    """
    name = location.strip().lower() if isinstance(location, str) else ""
    if not _VERTEX_LOCATION.fullmatch(name):
        raise EndpointNotAllowedError("location must be 'global' or a Google Cloud region name")
    if name == "global":
        return "aiplatform.googleapis.com"
    if name in _VERTEX_MULTI_REGIONS:
        return f"aiplatform.{name}.rep.googleapis.com"
    return f"{name}-aiplatform.googleapis.com"


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
