"""Example resource server showing the policy layer. Not part of any GAIK component.

    OIDC_ISSUER=http://localhost:8180/realms/gaik OIDC_AUDIENCE=gaik-api \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uvicorn example_api:app
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request

from gaik_authz.audit import AuditEmitter
from gaik_authz.fastapi import Authz
from gaik_authz.policy import Policy
from gaik_authz.tokens import TokenVerifier


def create_app(verifier: TokenVerifier | None = None, audit: AuditEmitter | None = None) -> FastAPI:
    policy = Policy.load(os.environ.get("AUTHZ_POLICY", Path(__file__).with_name("policy.yaml")))
    verifier = verifier or TokenVerifier(
        issuer=os.environ["OIDC_ISSUER"], audience=os.environ.get("OIDC_AUDIENCE", "gaik-api"),
        role_claim=os.environ.get("OIDC_ROLE_CLAIM", "roles"))
    audit = audit or AuditEmitter(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"), "example-api")
    authz = Authz(policy, verifier, audit)
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/solutions", dependencies=[authz.require("solution.read")])
    def list_solutions():
        return []

    @app.post("/solutions", dependencies=[authz.require("solution.write")])
    def create_solution(request: Request):
        return {"owner": request.state.principal.subject}

    @app.post("/results/{result_id}/approve", dependencies=[authz.require("result.approve")])
    def approve(result_id: str, request: Request):
        audit.emit("result.approved", "success", actor=request.state.principal.subject,
                   resource_type="result", resource_id=result_id)
        return {"approved": result_id}

    @app.get("/audit", dependencies=[authz.require("audit.read")])
    def read_audit():
        return []

    authz.enforce(app, public={"/healthz"})
    return app


app = create_app() if "OIDC_ISSUER" in os.environ else None
