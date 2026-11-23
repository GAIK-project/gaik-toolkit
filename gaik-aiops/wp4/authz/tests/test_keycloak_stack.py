"""End-to-end: tokens from the local Keycloak, denials stored in the audit log.

Start first:  docker compose -f deploy/compose/docker-compose.yml --profile identity up -d --build --wait
Skipped when Keycloak or the collection stack is not reachable.
"""

import json
import time
import urllib.parse
import urllib.request
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from example_api import create_app
from gaik_authz.audit import AuditEmitter
from gaik_authz.tokens import TokenVerifier

ISSUER = "http://localhost:8180/realms/gaik"
OTLP = "http://127.0.0.1:4318"
READER = "host=127.0.0.1 port=55432 dbname=observability user=collection_reader password=reader-local-only"


def _up() -> bool:
    try:
        urllib.request.urlopen(f"{ISSUER}/.well-known/openid-configuration", timeout=2).close()
        with psycopg.connect(READER, connect_timeout=2):
            pass
    except Exception:  # noqa: BLE001
        return False
    return True


pytestmark = pytest.mark.skipif(not _up(), reason="Keycloak or collection stack not running")


def login(user: str) -> str:
    data = urllib.parse.urlencode({"grant_type": "password", "client_id": "gaik-local-test",
                                   "username": user, "password": f"{user}-local-only"}).encode()
    with urllib.request.urlopen(f"{ISSUER}/protocol/openid-connect/token", data=data, timeout=5) as r:
        return json.load(r)["access_token"]


@pytest.fixture(scope="module")
def service():
    return f"authz-stack-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client(service):
    app = create_app(verifier=TokenVerifier(ISSUER, "gaik-api"), audit=AuditEmitter(OTLP, service))
    return TestClient(app)


@pytest.mark.parametrize("user,expected", [
    ("viewer", {"GET /solutions": 200, "POST /solutions": 403, "POST /results/r1/approve": 403, "GET /audit": 403}),
    ("expert", {"GET /solutions": 200, "POST /solutions": 200, "POST /results/r1/approve": 403, "GET /audit": 403}),
    ("approver", {"GET /solutions": 200, "POST /solutions": 403, "POST /results/r1/approve": 200, "GET /audit": 403}),
    ("security-admin", {"GET /solutions": 200, "POST /solutions": 403, "POST /results/r1/approve": 403, "GET /audit": 200}),
    ("norole", {"GET /solutions": 403, "POST /solutions": 403, "POST /results/r1/approve": 403, "GET /audit": 403}),
])
def test_keycloak_roles(client, user, expected):
    headers = {"Authorization": f"Bearer {login(user)}"}
    got = {}
    for call in expected:
        method, path = call.split(" ")
        got[call] = client.request(method, path, headers=headers).status_code
    assert got == expected


def test_tampered_keycloak_token_rejected(client):
    head, body, sig = login("viewer").split(".")
    forged = f"{head}.{body}.{sig[:-4]}AAAA"
    assert client.get("/audit", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_denial_reaches_audit_log_pseudonymised():
    service = f"authz-audit-test-{uuid.uuid4().hex[:8]}"
    client = TestClient(create_app(verifier=TokenVerifier(ISSUER, "gaik-api"), audit=AuditEmitter(OTLP, service)))
    tok = login("expert")
    assert client.get("/audit", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    deadline = time.time() + 20
    row = None
    while time.time() < deadline and row is None:
        with psycopg.connect(READER) as conn:
            row = conn.execute(
                "SELECT event_name, outcome, actor_pseudo_id, resource_id, attributes::text"
                "  FROM collection.audit_events WHERE service_name = %s AND event_name = 'authz.denied'",
                (service,)).fetchone()
        if row is None:
            time.sleep(1)
    assert row is not None, "authz.denied event not stored"
    event_name, outcome, actor, resource_id, attrs = row
    assert (event_name, outcome, resource_id) == ("authz.denied", "denied", "audit.read")
    assert actor and len(actor) == 64          # pseudonym, not the raw subject
    assert "expert@example.test" not in attrs and "enduser.id" not in attrs
