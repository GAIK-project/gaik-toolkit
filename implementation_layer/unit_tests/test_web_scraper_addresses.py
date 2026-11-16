"""Offline regression tests for WebScraper proxies and checked addresses (issue #197).

The proxy tests hide httpx's helper; the address tests patch ``getaddrinfo``, the
clock and the TCP connect, so no test reaches the network.
"""

from __future__ import annotations

import builtins
import socket

import httpcore
import pytest

pytest.importorskip("trafilatura")
pytest.importorskip("protego")

from gaik.software_components.web_scraper import (
    UrlPolicy,  # noqa: E402
    connect,  # noqa: E402
)
from gaik.software_components.web_scraper import policy as policy_module  # noqa: E402

PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


# ------------------------------------------- #197 item 1: a required proxy


def _hide_proxy_helper(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "httpx._utils" and fromlist and "get_environment_proxies" in fromlist:
            raise ImportError("moved")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_a_set_proxy_is_not_skipped_when_the_helper_is_missing(monkeypatch):
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test:3128")
    _hide_proxy_helper(monkeypatch)
    with pytest.raises(RuntimeError, match="proxy"):
        connect.environment_proxy_mounts()


def test_no_proxy_and_no_helper_gives_no_mounts(monkeypatch):
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    _hide_proxy_helper(monkeypatch)
    assert connect.environment_proxy_mounts() == {}


# ------------------------------------- #197 item 2: checked addresses expire


def _fake_dns(monkeypatch, answers: dict[str, list[str]], calls: list[str]):
    def fake_getaddrinfo(host, *args, **kwargs):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in answers[host]]

    clock = [1000.0]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(policy_module.time, "monotonic", lambda: clock[0])
    return clock


def test_checked_addresses_expire_and_the_new_answer_is_checked(monkeypatch):
    answers = {"site.test": ["8.8.8.8"]}
    calls: list[str] = []
    clock = _fake_dns(monkeypatch, answers, calls)
    policy = UrlPolicy(["site.test"])

    assert policy.public_addresses("site.test") == ("8.8.8.8",)
    answers["site.test"] = ["10.0.0.5"]
    clock[0] += policy_module.ADDRESS_TTL_SECONDS - 1
    assert policy.public_addresses("site.test") == ("8.8.8.8",)  # kept, no new lookup
    assert calls == ["site.test"]

    clock[0] += 2
    assert policy.public_addresses("site.test") == ()  # looked up again and refused
    assert policy.refusal("https://site.test/") is not None
    assert calls == ["site.test", "site.test"]


def test_after_expiry_the_connection_goes_only_to_a_newly_checked_address(monkeypatch):
    answers = {"site.test": ["8.8.8.8"]}
    clock = _fake_dns(monkeypatch, answers, [])
    connected: list[str] = []
    monkeypatch.setattr(
        httpcore.SyncBackend,
        "connect_tcp",
        lambda self, host, port, *a, **k: connected.append(host) or "stream",
    )
    policy = UrlPolicy(["site.test"])
    backend = connect._VettedAddressBackend(policy)
    assert policy.refusal("https://site.test/") is None

    answers["site.test"] = ["10.0.0.5"]
    clock[0] += policy_module.ADDRESS_TTL_SECONDS + 1
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("site.test", 443)
    assert connected == []

    answers["site.test"] = ["8.8.4.4"]
    clock[0] += policy_module.ADDRESS_TTL_SECONDS + 1
    assert backend.connect_tcp("site.test", 443) == "stream"
    assert connected == ["8.8.4.4"]
