"""Token validation and route enforcement with locally signed tokens (no IdP needed)."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from example_api import create_app
from gaik_authz.fastapi import Authz, UndeclaredRouteError
from gaik_authz.policy import Policy
from gaik_authz.tokens import TokenVerifier

ISS = "https://idp.example.test/realms/gaik"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class RecordingAudit:
    def __init__(self):
        self.events = []

    def emit(self, event_name, outcome, **kw):
        self.events.append((event_name, outcome, kw))


def token(roles=(), *, key=KEY, iss=ISS, aud="gaik-api", exp_in=300, sub="user-1", **extra):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_in, "roles": list(roles), **extra}
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def audit():
    return RecordingAudit()


@pytest.fixture
def client(audit):
    verifier = TokenVerifier(ISS, "gaik-api", key=KEY.public_key())
    return TestClient(create_app(verifier=verifier, audit=audit))


def call(client, method, path, tok=None):
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return client.request(method, path, headers=headers).status_code


MATRIX = [
    # role,      GET /solutions, POST /solutions, approve, GET /audit
    ("viewer",   200, 403, 403, 403),
    ("expert",   200, 200, 403, 403),
    ("approver", 200, 403, 200, 403),
    ("admin",    200, 403, 403, 200),
    (None,       403, 403, 403, 403),
]


@pytest.mark.parametrize("role,get_s,post_s,approve,audit_read", MATRIX)
def test_access_matrix(client, role, get_s, post_s, approve, audit_read):
    tok = token([role] if role else [])
    assert call(client, "GET", "/solutions", tok) == get_s
    assert call(client, "POST", "/solutions", tok) == post_s
    assert call(client, "POST", "/results/r1/approve", tok) == approve
    assert call(client, "GET", "/audit", tok) == audit_read


def test_health_is_public(client):
    assert call(client, "GET", "/healthz") == 200


@pytest.mark.parametrize("tok", [
    None,
    "not-a-jwt",
    token(["admin"], key=OTHER_KEY),                       # wrong signer
    token(["admin"], iss="https://evil.example.test/"),    # wrong issuer
    token(["admin"], aud="some-other-api"),               # wrong audience
    token(["admin"], exp_in=-120),                        # expired beyond leeway
])
def test_bad_tokens_are_401(client, tok):
    assert call(client, "GET", "/solutions", tok) == 401


def test_unsigned_token_rejected(client):
    now = int(time.time())
    tok = jwt.encode({"iss": ISS, "aud": "gaik-api", "sub": "x", "iat": now, "exp": now + 60, "roles": ["admin"]},
                     key=None, algorithm="none")
    assert call(client, "GET", "/audit", tok) == 401


def test_roles_from_nested_claim():
    verifier = TokenVerifier(ISS, "gaik-api", key=KEY.public_key(), role_claim="realm_access.roles")
    principal = verifier.verify(token([], realm_access={"roles": ["expert"]}))
    assert principal.roles == {"expert"}


def test_denial_is_audited(client, audit):
    call(client, "POST", "/results/r1/approve", token(["expert"], sub="user-42"))
    name, outcome, kw = audit.events[-1]
    assert (name, outcome) == ("authz.denied", "denied")
    assert kw["actor"] == "user-42" and kw["resource_id"] == "result.approve"


def test_undeclared_route_fails_at_startup():
    app = FastAPI()
    authz = Authz(Policy({"viewer": {"permissions": ["a"]}}), TokenVerifier(ISS, "gaik-api", key=KEY.public_key()))

    @app.get("/ok", dependencies=[authz.require("a")])
    def ok():
        return {}

    @app.get("/forgotten")
    def forgotten():
        return {}

    with pytest.raises(UndeclaredRouteError, match="/forgotten"):
        authz.enforce(app)
