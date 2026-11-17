"""An HTTP transport that connects only to the addresses the URL policy checked.

``UrlPolicy`` resolves a host and checks that every address it resolves to is
public. If the HTTP client then looked the name up again to connect, a DNS answer
that changed between the two lookups could send the request somewhere the check
never saw. This transport closes that gap: its network backend asks the policy for
the addresses it already checked and opens the TCP connection to one of them.

Only the TCP connection changes. The request keeps its URL, so the ``Host`` header
and, for https, the TLS server name (SNI) and certificate check use the host name.
Every checked address is tried in the resolver's order, as a direct connection
would.

``environment_proxy_mounts`` keeps the proxies set in ``HTTP_PROXY``,
``HTTPS_PROXY``, ``ALL_PROXY`` and ``NO_PROXY`` working: httpx reads them only when
no transport is given, and the scraper always gives this one. A proxy connects to
the site itself, so for proxied requests only the address check before the request
applies.
"""

from __future__ import annotations

import os

import httpcore
import httpx

from .policy import UrlPolicy


class _VettedAddressBackend(httpcore.SyncBackend):
    """Opens TCP connections to the addresses ``UrlPolicy`` checked for the host."""

    def __init__(self, policy: UrlPolicy):
        self._policy = policy

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        if self._policy.allow_private_networks:
            return super().connect_tcp(host, port, timeout, local_address, socket_options)
        addresses = self._policy.public_addresses(host)
        if not addresses:
            raise httpcore.ConnectError(
                f"{host} resolves to a private or local address, or does not resolve"
            )
        *others, last = addresses
        for address in others:
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout):
                continue  # try the host's next checked address
        return super().connect_tcp(last, port, timeout, local_address, socket_options)


def environment_proxy_mounts() -> dict[str, httpx.BaseTransport | None]:
    """httpx ``mounts`` for the proxies the environment sets, as httpx would use them.

    A ``NO_PROXY`` host maps to ``None``: the client's own transport, the vetted
    one, handles it.
    """
    try:
        from httpx._utils import get_environment_proxies
    except ImportError as exc:  # an httpx that moved the helper
        names = ("http_proxy", "https_proxy", "all_proxy")
        if any(os.environ.get(n) or os.environ.get(n.upper()) for n in names):
            raise RuntimeError(
                "a proxy is set in the environment, but this httpx version does not "
                "expose the helper WebScraper reads it with; pass transport= with the "
                "proxy, or install an httpx the gaik web-scraper extra supports"
            ) from exc
        return {}
    return {
        pattern: None if proxy is None else httpx.HTTPTransport(proxy=proxy)
        for pattern, proxy in get_environment_proxies().items()
    }


class VettedAddressTransport(httpx.HTTPTransport):
    """``httpx.HTTPTransport`` whose connections go to the policy's checked addresses.

    With ``allow_private_networks=True`` on the policy, names are resolved as usual:
    there is no address to hold the connection to.
    """

    def __init__(self, policy: UrlPolicy):
        super().__init__()
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=_VettedAddressBackend(policy),
        )
