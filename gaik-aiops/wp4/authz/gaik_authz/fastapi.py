"""FastAPI integration: per-route permission declarations, deny by default.

    authz = Authz(policy, verifier, audit)
    @app.get("/solutions", dependencies=[authz.require("solution.read")])
    authz.enforce(app, public={"/healthz"})   # fails at startup if a route declares nothing
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRoute

from .audit import AuditEmitter
from .policy import Policy
from .tokens import Principal, TokenError, TokenVerifier

_MARK = "_gaik_permission"


class UndeclaredRouteError(RuntimeError):
    pass


class Authz:
    def __init__(self, policy: Policy, verifier: TokenVerifier, audit: AuditEmitter | None = None) -> None:
        self.policy = policy
        self.verifier = verifier
        self.audit = audit or AuditEmitter(None, "unknown")

    def _principal(self, request: Request) -> Principal:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "bearer token required", headers={"WWW-Authenticate": "Bearer"})
        try:
            return self.verifier.verify(token)
        except TokenError:
            self.audit.emit("auth.token_rejected", "denied", client_address=_client(request),
                            resource_type="route", resource_id=request.url.path)
            raise HTTPException(401, "invalid token",
                                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}) from None

    def require(self, permission: str):
        def check(request: Request) -> Principal:
            principal = self._principal(request)
            if not self.policy.allows(principal.roles, permission):
                self.audit.emit("authz.denied", "denied", actor=principal.subject,
                                client_address=_client(request), resource_type="permission",
                                resource_id=permission)
                raise HTTPException(403, "forbidden")
            request.state.principal = principal
            return principal

        setattr(check, _MARK, permission)
        return Depends(check)

    def enforce(self, app: FastAPI, public: Iterable[str] = ()) -> None:
        """Refuse to start if any route other than the listed public paths lacks a permission."""
        public = set(public)
        missing = [r.path for r in app.routes
                   if isinstance(r, APIRoute) and r.path not in public and not _declares(r)]
        if missing:
            raise UndeclaredRouteError(f"routes without a permission: {', '.join(sorted(missing))}")


def _declares(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if hasattr(dep.call, _MARK):
            return True
        stack.extend(dep.dependencies)
    return False


def _client(request: Request) -> str | None:
    return request.client.host if request.client else None
