"""OIDC access token validation for a resource server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import jwt

ALGORITHMS = ["RS256", "PS256", "ES256"]


class TokenError(Exception):
    """The token is missing, malformed, expired or not meant for this API."""


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    claims: dict[str, Any] = field(repr=False)


def _claim(claims: dict[str, Any], path: str) -> Any:
    value: Any = claims
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class TokenVerifier:
    """Checks signature (from the issuer's JWKS), issuer, audience and expiry, then reads roles.

    role_claim is a dotted path, e.g. "roles" or "realm_access.roles", so that any OIDC provider
    can be used by configuration only.
    """

    def __init__(self, issuer: str, audience: str, jwks_url: str | None = None,
                 role_claim: str = "roles", leeway: int = 30, key: Any = None) -> None:
        self.issuer = issuer
        self.audience = audience
        self.role_claim = role_claim
        self.leeway = leeway
        self._key = key
        self._jwks = None if key is not None else jwt.PyJWKClient(
            jwks_url or f"{issuer.rstrip('/')}/protocol/openid-connect/certs", cache_keys=True)

    def verify(self, token: str) -> Principal:
        try:
            key = self._key if self._key is not None else self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=ALGORITHMS, audience=self.audience,
                                issuer=self.issuer, leeway=self.leeway,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            raise TokenError(str(exc)) from exc
        roles = _claim(claims, self.role_claim)
        if not isinstance(roles, list):
            roles = []
        return Principal(subject=claims["sub"], roles=frozenset(r for r in roles if isinstance(r, str)),
                         claims=claims)
