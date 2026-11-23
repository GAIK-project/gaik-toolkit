"""Service-to-service auth between wizard_v2_web and wizard_api (#132).

The web app's server-side proxy is the only legitimate caller of this API, so
a single shared secret is the right shape here. This is NOT user auth: a
caller holding the token can still act as any `user_id`. Real per-user
authentication is #134.

Implemented as middleware rather than a router dependency on purpose — a
dependency has to be remembered on every new router, and the one that gets
forgotten is the one that leaks. Middleware fails closed for anything mounted
on the app.
"""

from __future__ import annotations

import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from wizard_api import config

logger = logging.getLogger(__name__)

SERVICE_TOKEN_HEADER = "x-wizard-service-token"

# Probes must stay reachable without the secret: OpenShift liveness/readiness
# checks hit /health directly on the pod and have no way to hold a token.
EXEMPT_PATHS = frozenset({"/health"})


class ServiceTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        expected = config.get_service_token()

        # Not configured -> auth off. Startup already warned about this.
        if expected is None:
            return await call_next(request)

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # CORS preflight never carries custom headers.
        if request.method == "OPTIONS":
            return await call_next(request)

        presented = request.headers.get(SERVICE_TOKEN_HEADER, "")

        # compare_digest to keep the check constant-time.
        if not presented or not hmac.compare_digest(presented, expected):
            logger.warning(
                "rejected unauthenticated request path=%s method=%s reason=%s",
                request.url.path,
                request.method,
                "missing_token" if not presented else "bad_token",
            )
            return JSONResponse({"detail": "Missing or invalid service token."}, status_code=401)

        return await call_next(request)
