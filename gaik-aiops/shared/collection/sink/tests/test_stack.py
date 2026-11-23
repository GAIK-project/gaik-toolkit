"""End-to-end checks against the local compose stack.

Start it first:  docker compose -f deploy/compose/docker-compose.yml up -d --build --wait
Skipped when the stack is not reachable.
"""

import json
import os
import secrets
import time
import urllib.request

import psycopg
import pytest

OTLP = os.environ.get("OTLP_HTTP", "http://127.0.0.1:4318")
PG = "host=127.0.0.1 port=55432 dbname=observability"
OWNER = f"{PG} user=wp45 password=wp45-local-only"
WRITER = f"{PG} user=collection_writer password=writer-local-only"
READER = f"{PG} user=collection_reader password=reader-local-only"


def _stack_up() -> bool:
    try:
        with psycopg.connect(READER, connect_timeout=2):
            pass
        urllib.request.urlopen(OTLP, timeout=2)
    except urllib.error.HTTPError:
        return True  # collector answers; 404 on "/" is fine
    except Exception:  # noqa: BLE001
        return False
    return True


pytestmark = pytest.mark.skipif(not _stack_up(), reason="compose stack not running")


def s(key, value):
    return {"key": key, "value": {"stringValue": value}}


def send(trace_id: str) -> None:
    body = {
        "resourceLogs": [
            {
                "resource": {"attributes": [s("service.name", "stack-test")]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "traceId": trace_id,
                                "attributes": [
                                    s("gaik.event.class", "audit"),
                                    s("event.name", "auth.login"),
                                    s("gaik.audit.outcome", "success"),
                                    s("enduser.id", "someone@example.com"),
                                    s("client.address", "198.51.100.23"),
                                ],
                            },
                            {
                                "traceId": trace_id,
                                "severityText": "INFO",
                                "body": {"stringValue": "request handled"},
                                "attributes": [s("client.address", "2001:db8:abcd:12::1")],
                            },
                        ]
                    }
                ],
            }
        ]
    }
    req = urllib.request.Request(
        f"{OTLP}/v1/logs",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=5)


def wait_rows(trace_id: str, expected: int, timeout: float = 15) -> list[tuple]:
    deadline = time.time() + timeout
    with psycopg.connect(READER) as conn:
        while True:
            rows = conn.execute(
                "SELECT event_class, attributes FROM collection.correlated_events "
                "WHERE trace_id = %s ORDER BY event_class",
                (trace_id,),
            ).fetchall()
            if len(rows) >= expected or time.time() > deadline:
                return rows
            time.sleep(0.5)


@pytest.fixture(scope="module")
def trace_id() -> str:
    tid = secrets.token_hex(16)
    send(tid)
    rows = wait_rows(tid, 2)
    assert [r[0] for r in rows] == ["audit", "log"]
    return tid


def test_identity_is_pseudonymised_and_address_masked(trace_id):
    with psycopg.connect(READER) as conn:
        actor, address, attrs = conn.execute(
            "SELECT actor_pseudo_id, client_address, attributes "
            "FROM collection.audit_events WHERE trace_id = %s",
            (trace_id,),
        ).fetchone()
        log_attrs = conn.execute(
            "SELECT attributes FROM collection.log_events WHERE trace_id = %s", (trace_id,)
        ).fetchone()[0]
    assert actor and "someone" not in actor and "example.com" not in actor
    assert "enduser.id" not in attrs
    assert address == "198.51.100.0"
    assert log_attrs["client.address"] == "2001:db8:abcd::"


def test_audit_rows_cannot_be_changed_or_deleted_early(trace_id):
    with psycopg.connect(OWNER) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
            conn.execute(
                "UPDATE collection.audit_events SET outcome = 'denied' WHERE trace_id = %s",
                (trace_id,),
            )
        conn.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="retention"):
            conn.execute("DELETE FROM collection.audit_events WHERE trace_id = %s", (trace_id,))
        conn.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="truncated"):
            conn.execute("TRUNCATE collection.audit_events")


def test_writer_can_only_insert(trace_id):
    with psycopg.connect(WRITER) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM collection.audit_events")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM collection.log_events")


def test_reader_cannot_write(trace_id):
    with psycopg.connect(READER) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM collection.log_events WHERE trace_id = %s", (trace_id,))


def test_purge_removes_only_expired_rows():
    tid = secrets.token_hex(16)
    with psycopg.connect(OWNER) as conn:
        conn.execute(
            "INSERT INTO collection.audit_events "
            "(event_time, trace_id, service_name, event_name, retention_until) "
            "VALUES (now() - interval '2 years', %s, 'stack-test', 'auth.login', now() - interval '1 day')",
            (tid,),
        )
        conn.commit()
        audit_deleted, _ = conn.execute("SELECT * FROM collection.purge_expired()").fetchone()
        conn.commit()
        left = conn.execute(
            "SELECT count(*) FROM collection.audit_events WHERE trace_id = %s", (tid,)
        ).fetchone()[0]
        unexpired = conn.execute(
            "SELECT count(*) FROM collection.audit_events WHERE retention_until > now()"
        ).fetchone()[0]
    assert audit_deleted >= 1 and left == 0
    assert unexpired >= 1
