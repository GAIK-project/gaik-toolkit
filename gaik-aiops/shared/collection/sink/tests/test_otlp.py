from datetime import datetime, timedelta, timezone

from collection_sink.otlp import Retention, any_value, parse_logs

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
RETENTION = Retention(audit_days=365, log_days=30)


def s(key, value):
    return {"key": key, "value": {"stringValue": value}}


def payload(*records, service="demo-app"):
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [s("service.name", service)]},
                "scopeLogs": [{"logRecords": list(records)}],
            }
        ]
    }


def test_audit_event_goes_to_audit_columns():
    batch = parse_logs(
        payload(
            {
                "timeUnixNano": "1760000000000000000",
                "traceId": "0AF7651916CD43DD8448EB211C80319C",
                "spanId": "b7ad6b7169203331",
                "attributes": [
                    s("gaik.event.class", "audit"),
                    s("event.name", "auth.login"),
                    s("gaik.audit.outcome", "denied"),
                    s("gaik.audit.resource.type", "session"),
                    s("gaik.audit.resource.id", "42"),
                    s("enduser.pseudo.id", "abc"),
                    s("client.address", "203.0.113.0"),
                    s("http.route", "/login"),
                ],
            }
        ),
        RETENTION,
        NOW,
    )
    assert batch.logs == [] and batch.rejected == 0
    row = batch.audit[0]
    assert row.event_name == "auth.login"
    assert row.outcome == "denied"
    assert (row.resource_type, row.resource_id) == ("session", "42")
    assert row.actor_pseudo_id == "abc"
    assert row.client_address == "203.0.113.0"
    assert row.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert row.service_name == "demo-app"
    assert row.attributes == {"http.route": "/login"}
    assert row.retention_until == NOW + timedelta(days=365)
    assert row.event_time == datetime.fromtimestamp(1760000000, tz=timezone.utc)


def test_audit_event_without_name_is_rejected():
    batch = parse_logs(payload({"attributes": [s("gaik.event.class", "audit")]}), RETENTION, NOW)
    assert batch.audit == [] and batch.logs == []
    assert batch.rejected == 1


def test_other_classes_go_to_logs_with_log_retention():
    batch = parse_logs(
        payload(
            {"severityText": "WARN", "body": {"stringValue": "slow"}, "attributes": [s("x", "1")]},
            {"attributes": [s("gaik.event.class", "llm_call")]},
        ),
        RETENTION,
        NOW,
    )
    assert [r.event_class for r in batch.logs] == ["log", "llm_call"]
    first = batch.logs[0]
    assert first.severity == "WARN" and first.body == "slow"
    assert first.attributes == {"x": "1"}
    assert first.resource == {"service.name": "demo-app"}
    assert first.retention_until == NOW + timedelta(days=30)
    # No timestamp on the record: fall back to receive time.
    assert first.event_time == NOW


def test_unset_ids_and_missing_service():
    batch = parse_logs(
        {
            "resourceLogs": [
                {"scopeLogs": [{"logRecords": [{"traceId": "0" * 32, "spanId": ""}]}]}
            ]
        },
        RETENTION,
        NOW,
    )
    row = batch.logs[0]
    assert row.trace_id is None and row.span_id is None
    assert row.service_name == "unknown"


def test_any_value_types():
    assert any_value({"intValue": "7"}) == 7
    assert any_value({"doubleValue": 1.5}) == 1.5
    assert any_value({"boolValue": False}) is False
    assert any_value({"arrayValue": {"values": [{"stringValue": "a"}]}}) == ["a"]
    assert any_value({"kvlistValue": {"values": [s("k", "v")]}}) == {"k": "v"}
    assert any_value(None) is None
