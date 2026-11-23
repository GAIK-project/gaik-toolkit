"""Map OTLP/HTTP JSON log payloads to storage rows.

Only the transport, storage and retention side is interpreted here. Payload
content beyond the common envelope attributes is stored as-is in
``attributes`` / ``body``; its meaning belongs to the producer's schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Envelope attribute names (see ../schema/envelope.schema.json).
EVENT_CLASS = "gaik.event.class"
EVENT_NAME = "event.name"
AUDIT_OUTCOME = "gaik.audit.outcome"
AUDIT_RESOURCE_TYPE = "gaik.audit.resource.type"
AUDIT_RESOURCE_ID = "gaik.audit.resource.id"
ACTOR_PSEUDO_ID = "enduser.pseudo.id"
CLIENT_ADDRESS = "client.address"
SERVICE_NAME = "service.name"

AUDIT = "audit"
DEFAULT_CLASS = "log"

# Lifted into dedicated audit columns, so not repeated in ``attributes``.
_AUDIT_COLUMNS = {
    EVENT_CLASS,
    EVENT_NAME,
    AUDIT_OUTCOME,
    AUDIT_RESOURCE_TYPE,
    AUDIT_RESOURCE_ID,
    ACTOR_PSEUDO_ID,
    CLIENT_ADDRESS,
}


@dataclass(frozen=True)
class Retention:
    audit_days: int
    log_days: int

    def until(self, event_class: str, now: datetime) -> datetime:
        days = self.audit_days if event_class == AUDIT else self.log_days
        return now + timedelta(days=days)


@dataclass
class AuditRow:
    event_time: datetime
    trace_id: str | None
    span_id: str | None
    service_name: str
    event_name: str
    outcome: str | None
    actor_pseudo_id: str | None
    client_address: str | None
    resource_type: str | None
    resource_id: str | None
    attributes: dict[str, Any]
    retention_until: datetime


@dataclass
class LogRow:
    event_time: datetime
    trace_id: str | None
    span_id: str | None
    service_name: str
    event_class: str
    event_name: str | None
    severity: str | None
    body: Any
    attributes: dict[str, Any]
    resource: dict[str, Any]
    retention_until: datetime


@dataclass
class Batch:
    audit: list[AuditRow] = field(default_factory=list)
    logs: list[LogRow] = field(default_factory=list)
    rejected: int = 0


def any_value(value: dict[str, Any] | None) -> Any:
    """Decode an OTLP ``AnyValue`` into a plain Python value."""
    if not value:
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "bytesValue" in value:
        return value["bytesValue"]
    if "arrayValue" in value:
        return [any_value(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return attributes_to_dict(value["kvlistValue"].get("values", []))
    return None


def attributes_to_dict(attrs: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {a["key"]: any_value(a.get("value")) for a in attrs or [] if "key" in a}


def _time(record: dict[str, Any], received: datetime) -> datetime:
    nanos = record.get("timeUnixNano") or record.get("observedTimeUnixNano")
    if nanos in (None, "", "0", 0):
        return received
    return datetime.fromtimestamp(int(nanos) / 1e9, tz=timezone.utc)


def _id(value: str | None) -> str | None:
    # OTLP/JSON encodes trace and span ids as hex; all-zero means "not set".
    if not value or set(value) == {"0"}:
        return None
    return value.lower()


def parse_logs(payload: dict[str, Any], retention: Retention, now: datetime | None = None) -> Batch:
    """Split an ``ExportLogsServiceRequest`` into audit and log rows."""
    now = now or datetime.now(timezone.utc)
    batch = Batch()
    for resource_logs in payload.get("resourceLogs", []):
        resource = attributes_to_dict(resource_logs.get("resource", {}).get("attributes"))
        service = str(resource.get(SERVICE_NAME) or "unknown")
        for scope_logs in resource_logs.get("scopeLogs", []):
            for record in scope_logs.get("logRecords", []):
                attrs = attributes_to_dict(record.get("attributes"))
                event_class = str(attrs.get(EVENT_CLASS) or DEFAULT_CLASS)
                event_name = attrs.get(EVENT_NAME) or record.get("eventName") or None
                common = dict(
                    event_time=_time(record, now),
                    trace_id=_id(record.get("traceId")),
                    span_id=_id(record.get("spanId")),
                    service_name=service,
                    retention_until=retention.until(event_class, now),
                )
                if event_class == AUDIT:
                    if not event_name:
                        # An audit event without a name cannot be interpreted later.
                        batch.rejected += 1
                        continue
                    batch.audit.append(
                        AuditRow(
                            **common,
                            event_name=str(event_name),
                            outcome=attrs.get(AUDIT_OUTCOME),
                            actor_pseudo_id=attrs.get(ACTOR_PSEUDO_ID),
                            client_address=attrs.get(CLIENT_ADDRESS),
                            resource_type=attrs.get(AUDIT_RESOURCE_TYPE),
                            resource_id=attrs.get(AUDIT_RESOURCE_ID),
                            attributes={k: v for k, v in attrs.items() if k not in _AUDIT_COLUMNS},
                        )
                    )
                else:
                    batch.logs.append(
                        LogRow(
                            **common,
                            event_class=event_class,
                            event_name=str(event_name) if event_name else None,
                            severity=record.get("severityText") or None,
                            body=any_value(record.get("body")),
                            attributes={k: v for k, v in attrs.items() if k != EVENT_CLASS},
                            resource=resource,
                        )
                    )
    return batch
