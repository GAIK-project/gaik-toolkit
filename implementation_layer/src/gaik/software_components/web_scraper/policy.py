"""Which URLs the scraper may fetch, and how URLs are compared.

A URL passes when it is http(s), carries no credentials, lies inside the allowed
domains (when a list is given) and resolves to public addresses only. The address
check stops a page, a redirect or a typed URL from reaching a cloud metadata
endpoint or a service inside the cluster the scraper runs in.

The address check resolves the host once per scraper and caches the answer. The
HTTP client resolves the host again when it connects, so a domain whose DNS answer
changes between the two lookups (DNS rebinding) is not covered: list the domains
you trust in ``allowed_domains`` when the URLs come from users.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


class ScrapeError(Exception):
    """A URL that could not be scraped, with the reason in plain words."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


def normalize_url(url: str, base: str | None = None) -> str:
    """The URL resolved against ``base``, without its fragment, in one canonical form.

    The scheme and host are lowercased, a default port is dropped and an empty path
    becomes ``/``, so the same page reached by two spellings is fetched once.
    """
    if base is not None:
        url = urljoin(base, url)
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, ""))
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"
    if parts.username or parts.password:
        userinfo = parts.username or ""
        if parts.password:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def host_of(url: str) -> str:
    """The URL's host, lowercased; empty when it has none."""
    return (urlsplit(url).hostname or "").lower()


def _clean_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if "://" in domain:
        domain = host_of(domain)
    return domain.strip(".")


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class UrlPolicy:
    """Decides whether a URL may be fetched.

    Args:
        allowed_domains: Domains the scraper may fetch from. A domain also allows its
            subdomains: ``haaga-helia.fi`` allows ``www.haaga-helia.fi``. ``None``
            allows every public host.
        allow_private_networks: Allow hosts that resolve to private, loopback or
            link-local addresses. Off by default; turn it on only for an intranet
            you mean to scrape.
    """

    def __init__(
        self,
        allowed_domains: Iterable[str] | None = None,
        *,
        allow_private_networks: bool = False,
    ):
        if isinstance(allowed_domains, str):
            allowed_domains = [allowed_domains]
        self.allowed_domains: tuple[str, ...] | None = (
            None
            if allowed_domains is None
            else tuple(d for d in (_clean_domain(d) for d in allowed_domains) if d)
        )
        if self.allowed_domains == ():
            raise ValueError("allowed_domains is empty: pass None to allow every public host")
        self.allow_private_networks = allow_private_networks
        self._public: dict[str, bool] = {}

    def in_allowed_domains(self, url: str) -> bool:
        """Whether the URL's host is inside the allowed domains (no DNS lookup)."""
        host = host_of(url)
        if not host:
            return False
        if self.allowed_domains is None:
            return True
        return any(host == d or host.endswith(f".{d}") for d in self.allowed_domains)

    def refusal(self, url: str, *, check_domains: bool = True) -> str | None:
        """Why the URL may not be fetched, or ``None`` when it may.

        ``check_domains=False`` checks only the scheme and the address: a browser
        loading a page's scripts and images from a CDN goes outside the allowed
        domains, but must still never reach a private address.
        """
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return f"only http and https URLs are fetched, not {parts.scheme or 'this'}"
        host = (parts.hostname or "").lower()
        if not host:
            return "the URL has no host"
        if parts.username or parts.password:
            return "URLs with a user name or password are not fetched"
        if check_domains and not self.in_allowed_domains(url):
            allowed = ", ".join(self.allowed_domains or ())
            return f"{host} is outside the allowed domains ({allowed})"
        if not self.allow_private_networks and not self._resolves_public(host):
            return f"{host} resolves to a private or local address, or does not resolve"
        return None

    def _resolves_public(self, host: str) -> bool:
        if host not in self._public:
            try:
                infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
                addresses = {info[4][0] for info in infos}
                self._public[host] = bool(addresses) and all(map(_is_public, addresses))
            except (OSError, ValueError, UnicodeError):
                self._public[host] = False
        return self._public[host]
