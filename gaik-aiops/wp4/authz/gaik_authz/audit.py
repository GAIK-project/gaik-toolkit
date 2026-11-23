"""Minimal audit event emitter: OTLP/HTTP JSON to the collection layer.

Best effort: a failed send is reported to the caller's logger and never blocks the request path.
The raw user id is sent as enduser.id; the collector pseudonymises it before storage.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request

log = logging.getLogger(__name__)


def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


class AuditEmitter:
    def __init__(self, endpoint: str | None, service_name: str, timeout: float = 2.0) -> None:
        self.url = f"{endpoint.rstrip('/')}/v1/logs" if endpoint else None
        self.service_name = service_name
        self.timeout = timeout

    def emit(self, event_name: str, outcome: str, *, actor: str | None = None,
             client_address: str | None = None, resource_type: str | None = None,
             resource_id: str | None = None, trace_id: str | None = None) -> None:
        if not self.url:
            return
        attrs = [_attr("gaik.event.class", "audit"), _attr("event.name", event_name),
                 _attr("gaik.audit.outcome", outcome)]
        for key, value in (("enduser.id", actor), ("client.address", client_address),
                           ("gaik.audit.resource.type", resource_type), ("gaik.audit.resource.id", resource_id)):
            if value:
                attrs.append(_attr(key, value))
        record = {"timeUnixNano": str(time.time_ns()), "attributes": attrs}
        if trace_id:
            record["traceId"] = trace_id
        body = {"resourceLogs": [{"resource": {"attributes": [_attr("service.name", self.service_name)]},
                                  "scopeLogs": [{"logRecords": [record]}]}]}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=self.timeout).close()
        except Exception as exc:  # noqa: BLE001
            log.warning("audit event %s not sent: %s", event_name, exc)
