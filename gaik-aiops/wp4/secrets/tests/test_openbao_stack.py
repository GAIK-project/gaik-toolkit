"""Checks of the OpenBao overlay against the running local stack.

Start first:
  docker compose -f deploy/compose/docker-compose.yml -f deploy/compose/openbao.yml up -d --build --wait
Skipped when OpenBao is not reachable.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import psycopg
import pytest

BAO = os.environ.get("OPENBAO_ADDR", "http://127.0.0.1:8200")
ROOT = os.environ.get("OPENBAO_ROOT_TOKEN", "root-local-only")
OTLP = "http://127.0.0.1:4318"
READER = "host=127.0.0.1 port=55432 dbname=observability user=collection_reader password=reader-local-only"


def bao(method, path, token=ROOT, body=None):
    req = urllib.request.Request(f"{BAO}/v1/{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Vault-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}


def _up():
    try:
        return bao("GET", "sys/health")[0] == 200
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="OpenBao overlay not running")


def login(role):
    role_id = bao("GET", f"auth/approle/role/{role}/role-id")[1]["data"]["role_id"]
    secret_id = bao("POST", f"auth/approle/role/{role}/secret-id")[1]["data"]["secret_id"]
    status, out = bao("POST", "auth/approle/login", token="", body={"role_id": role_id, "secret_id": secret_id})
    assert status == 200
    return out["auth"]["client_token"]


KEY_PATH = "gaik/data/collection/pseudonym"


def pseudonym_key():
    return bao("GET", KEY_PATH)[1]["data"]["data"]["key"]


@pytest.mark.parametrize("role,allowed,denied", [
    ("api", ["gaik/data/deployments/local/api"],
     ["gaik/data/deployments/local/sandbox", "gaik/data/collection/sink", KEY_PATH]),
    ("sandbox", ["gaik/data/deployments/local/sandbox"],
     ["gaik/data/deployments/local/api", "gaik/data/collection/sink", KEY_PATH]),
    ("sink", ["gaik/data/collection/sink"],
     ["gaik/data/deployments/local/api", "gaik/data/deployments/local/sandbox", KEY_PATH]),
    ("collector", [KEY_PATH],
     ["gaik/data/collection/sink", "gaik/data/deployments/local/api", "gaik/data/deployments/local/sandbox"]),
])
def test_least_privilege_reads(role, allowed, denied):
    token = login(role)
    for path in allowed:
        assert bao("GET", path, token)[0] == 200, path
    for path in denied:
        assert bao("GET", path, token)[0] == 403, path


def test_the_pseudonymisation_key_is_random_and_written_once():
    # A new key would give every user a new pseudonym; init must never overwrite it.
    assert re.fullmatch(r"[0-9a-f]{64}", pseudonym_key())
    status, meta = bao("GET", "gaik/metadata/collection/pseudonym")
    assert status == 200 and meta["data"]["current_version"] == 1


def test_consumers_cannot_change_the_key_or_policies():
    for role in ("collector", "sink"):
        token = login(role)
        assert bao("POST", KEY_PATH, token, {"data": {"key": "0" * 64}})[0] == 403
        assert bao("PUT", f"sys/policies/acl/{role}", token, {"policy": 'path "*" {capabilities=["sudo"]}'})[0] == 403


def test_stored_actor_is_the_keyed_hash_of_the_raw_id():
    service = f"openbao-test-{secrets.token_hex(4)}"
    user = f"person-{secrets.token_hex(4)}@example.com"
    body = {"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
                              "scopeLogs": [{"logRecords": [{"attributes": [
                                  {"key": "gaik.event.class", "value": {"stringValue": "audit"}},
                                  {"key": "event.name", "value": {"stringValue": "auth.login"}},
                                  {"key": "enduser.id", "value": {"stringValue": user}}]}]}]}]}
    req = urllib.request.Request(f"{OTLP}/v1/logs", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).close()
    row = None
    deadline = time.time() + 20
    while row is None and time.time() < deadline:
        with psycopg.connect(READER) as conn:
            row = conn.execute("SELECT actor_pseudo_id, attributes::text FROM collection.audit_events"
                               " WHERE service_name = %s", (service,)).fetchone()
        if row is None:
            time.sleep(1)
    assert row is not None, "event not stored"
    actor, attrs = row
    assert actor == hashlib.sha256((pseudonym_key() + user).encode()).hexdigest()
    assert user not in attrs and "enduser.id" not in attrs


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")
def test_audit_device_records_access_without_clear_values():
    marker = f"marker-{secrets.token_hex(6)}@example.com"
    path = f"gaik/data/audit-test-{secrets.token_hex(4)}"
    assert bao("POST", path, body={"data": {"value": marker}})[0] == 200
    time.sleep(1)
    logs = subprocess.run(["docker", "logs", "--since", "60s", "wp45-openbao-1"],
                          capture_output=True, text=True, timeout=30).stdout
    entries = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
    assert [e for e in entries if e.get("request", {}).get("path") == path], "write not in the audit device"
    assert marker not in logs
    bao("DELETE", path.replace("/data/", "/metadata/"))


# --- OpenBao audit device -> collection layer -------------------------------------------------------

def vault_events(where: str, params: tuple, expect: int = 1, timeout: float = 25):
    """Rows from OpenBao in the audit store matching a condition, waiting for the collector to ship them."""
    deadline = time.time() + timeout
    rows = []
    while time.time() < deadline:
        with psycopg.connect(READER) as conn:
            rows = conn.execute(
                "SELECT event_name, outcome, resource_id, actor_pseudo_id, client_address, attributes"
                "  FROM collection.audit_events WHERE service_name = 'openbao' AND " + where, params).fetchall()
        if len(rows) >= expect:
            return rows
        time.sleep(1)
    return rows


def test_secret_read_and_denial_reach_the_audit_store():
    token = login("sandbox")
    since = time.time() - 1
    assert bao("GET", "gaik/data/deployments/local/sandbox", token)[0] == 200
    assert bao("GET", "gaik/data/deployments/local/api", token)[0] == 403
    rows = vault_events("event_time >= to_timestamp(%s) AND attributes->>'vault.auth.role' = 'sandbox'"
                        " AND event_name = 'secret.accessed'", (since,), expect=2)
    got = {(r[2], r[1]) for r in rows}
    assert ("gaik/data/deployments/local/sandbox", "success") in got
    assert ("gaik/data/deployments/local/api", "denied") in got
    for _, _, _, actor, address, attrs in rows:
        assert actor and re.fullmatch(r"[0-9a-f]{64}", actor)  # pseudonymised entity id
        assert address.endswith(".0")                           # masked
        assert "enduser.id" not in attrs
        assert not any("local-fake-" in str(v) for v in attrs.values())   # no secret values


def test_rotation_login_and_policy_change_are_named():
    key = f"audit-name-test-{secrets.token_hex(4)}"  # transit stays enabled for application keys
    since = time.time() - 1
    bao("POST", f"transit/keys/{key}")
    bao("POST", f"transit/keys/{key}/rotate")
    bao("PUT", "sys/policies/acl/audit-name-test", body={"policy": 'path "nothing/*" { capabilities = ["read"] }'})
    login("api")
    expected = {("secret.rotated", f"transit/keys/{key}/rotate"), ("config.changed", f"transit/keys/{key}"),
                ("config.changed", "sys/policies/acl/audit-name-test"),
                ("credential.issued", "auth/approle/role/api/secret-id"), ("auth.login", "auth/approle/login")}
    names = set()
    deadline = time.time() + 25
    while not expected <= names and time.time() < deadline:
        names = {(r[0], r[2]) for r in vault_events("event_time >= to_timestamp(%s)", (since,), expect=0)}
        time.sleep(1)
    assert expected <= names, expected - names
    bao("DELETE", "sys/policies/acl/audit-name-test")
    bao("POST", f"transit/keys/{key}/config", body={"deletion_allowed": True})
    bao("DELETE", f"transit/keys/{key}")


def test_vault_events_do_not_grow_while_idle():
    # The agents read their secrets on a timer; nothing may feed back into more events.
    time.sleep(12)
    with psycopg.connect(READER) as conn:
        before = conn.execute("SELECT count(*) FROM collection.audit_events WHERE service_name = 'openbao'"
                              " AND received_at > now() - interval '1 hour'").fetchone()[0]
    time.sleep(15)
    with psycopg.connect(READER) as conn:
        after = conn.execute("SELECT count(*) FROM collection.audit_events WHERE service_name = 'openbao'"
                             " AND received_at > now() - interval '1 hour'").fetchone()[0]
    assert after - before <= 2, "OpenBao events keep growing while idle"
