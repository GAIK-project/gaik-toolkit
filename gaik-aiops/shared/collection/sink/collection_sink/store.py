"""Write parsed rows to Postgres."""

from __future__ import annotations

from dataclasses import asdict

import psycopg
from psycopg.types.json import Jsonb

from .otlp import Batch

_AUDIT_SQL = """
INSERT INTO collection.audit_events
    (event_time, trace_id, span_id, service_name, event_name, outcome, actor_pseudo_id,
     client_address, resource_type, resource_id, attributes, retention_until)
VALUES
    (%(event_time)s, %(trace_id)s, %(span_id)s, %(service_name)s, %(event_name)s, %(outcome)s,
     %(actor_pseudo_id)s, %(client_address)s, %(resource_type)s, %(resource_id)s,
     %(attributes)s, %(retention_until)s)
"""

_LOG_SQL = """
INSERT INTO collection.log_events
    (event_time, trace_id, span_id, service_name, event_class, event_name, severity, body,
     attributes, resource, retention_until)
VALUES
    (%(event_time)s, %(trace_id)s, %(span_id)s, %(service_name)s, %(event_class)s,
     %(event_name)s, %(severity)s, %(body)s, %(attributes)s, %(resource)s, %(retention_until)s)
"""


class Store:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def write(self, batch: Batch) -> None:
        """Insert a whole batch in one transaction, so a retry never half-applies."""
        audit = [_jsonb(asdict(r), "attributes") for r in batch.audit]
        logs = [_jsonb(asdict(r), "attributes", "resource", "body") for r in batch.logs]
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            if audit:
                cur.executemany(_AUDIT_SQL, audit)
            if logs:
                cur.executemany(_LOG_SQL, logs)

    def ping(self) -> None:
        with psycopg.connect(self._dsn, connect_timeout=2) as conn:
            conn.execute("SELECT 1")


def _jsonb(row: dict, *keys: str) -> dict:
    for key in keys:
        row[key] = None if row[key] is None else Jsonb(row[key])
    return row
